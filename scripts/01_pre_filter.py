# -*- coding: utf-8 -*-
"""KR8 step 1: stream the Discogs releases dump into a small SQLite DB (~45 min).

Changes vs. the old version
  * vinyl/CD only, CD-R / acetate / lathe cut excluded (config.OBSCURE_FORMATS)
  * output stats count ALL release-level artists and labels (not only the first),
    Jungle/DnB numerator counts every format and year, Breakbeat Hardcore has its
    own column and never triggers the "core" caps
  * placeholder artists (Various, Unknown Artist, No Artist) and pseudo-labels
    (Not On Label, White Label, ...) are never counted, so they can't become "core"
  * remix credits (track-level AND release-level) are stored with the real track index
  * only records tagged Jungle / Drum n Bass / clean Breakbeat Hardcore are stored: a jungle remix
    on an otherwise non-jungle record makes Discogs list the Jungle style, so untagged records
    with remix credits are not jungle remixes
  * versions per master are counted over the WHOLE dump (all formats, all genres)
  * genre tags, formats and descriptions are stored, so year / genre / provenance
    decisions no longer need a re-run
  * tally memory: master-less releases are plain counters instead of giant sets
"""
import gzip
import re
import sqlite3
from array import array

from lxml import etree

import config
from common import (REMIX_RE, is_pseudo_label, is_placeholder_artist, pause, resolve_dump, setup_console,
                    to_int)

setup_console()

MAX_ENTITY_ID = 100000000
YEAR_RE = re.compile(r"\s*(\d{4})")
DECADE_RE = re.compile(r"\s*(\d{3})[^0-9]")          # "199?" / "199-"
OBSCURE = frozenset(config.OBSCURE_FORMATS)
BH_NOISE = frozenset(config.BH_NOISE_STYLES)
DB_YEARS = config.DB_YEARS


def parse_year(text):
    """-> (year, approx). '199?' becomes 1995 with approx=1 instead of being dropped."""
    if not text:
        return 0, 0
    m = YEAR_RE.match(text)
    if m:
        return int(m.group(1)), 0
    m = DECADE_RE.match(text)
    if m:
        return int(m.group(1)) * 10 + 5, 1
    return 0, 0


class Tally(object):
    """Distinct masters per entity id.

    Real masters are de-duplicated through a set of packed (entity, master) ints.
    Master-less releases are each their own unique 'master', so a plain counter is exact
    and needs no set at all.
    """

    def __init__(self):
        self.arr = array("I")
        self.pairs = set()

    def _grow(self, idx):
        need = idx + 1 - len(self.arr) + 500000
        self.arr.frombytes(bytes(self.arr.itemsize * need))

    def add(self, ent, master):
        if master > 0:
            self.pairs.add((ent << 32) | master)
        else:
            if ent >= len(self.arr):
                self._grow(ent)
            self.arr[ent] += 1

    def finish(self):
        arr = self.arr
        for p in self.pairs:
            ent = p >> 32
            if ent >= len(arr):
                self._grow(ent)
            arr[ent] += 1
        self.pairs = set()
        return arr


def collect_credits(elem):
    """Remix credits only. -> [(track_idx, tracks_text, artist_id, name)].
    track_idx = -1 for release-level credits (tracks_text says which tracks, if given)."""
    out = []
    for a in elem.findall("extraartists/artist"):
        if REMIX_RE.search(a.findtext("role") or ""):
            out.append((-1, (a.findtext("tracks") or "").strip(),
                        to_int(a.findtext("id")), (a.findtext("name") or "").strip()))
    for idx, tr in enumerate(elem.findall("tracklist/track")):
        for a in tr.findall("extraartists/artist"):
            if REMIX_RE.search(a.findtext("role") or ""):
                out.append((idx, "", to_int(a.findtext("id")), (a.findtext("name") or "").strip()))
    return out


def save_release(cur, elem, rid, master_id, year, approx, artists, labels, comp, gtag,
                 styles_txt, fmt_txt, credits):
    first_a = artists[0] if artists else (0, "Unknown")
    first_l = labels[0] if labels else (0, "Unknown", "Unknown")
    cur.execute(
        """INSERT INTO releases (release_id, master_id, title, year, year_approx, label_id, label_name,
                                 catno, main_artist_id, main_artist_name, is_compilation, gtag,
                                 styles, fmt, versions)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
        (rid, master_id or None, elem.findtext("title") or "Unknown Title", year, approx,
         first_l[0], first_l[1], first_l[2], first_a[0], first_a[1], comp, gtag, styles_txt, fmt_txt))
    cur.executemany("INSERT INTO release_artists VALUES (?,?,?,?)",
                    [(rid, i, a, n) for i, (a, n) in enumerate(artists)])
    cur.executemany("INSERT INTO release_labels VALUES (?,?,?,?,?)",
                    [(rid, i, l, n, c) for i, (l, n, c) in enumerate(labels)])
    cur.executemany("INSERT INTO tracks VALUES (?,?,?,?)",
                    [(rid, i, (t.findtext("position") or "").strip(), (t.findtext("title") or "").strip())
                     for i, t in enumerate(elem.findall("tracklist/track"))])
    if credits:
        cur.executemany("INSERT INTO credits VALUES (?,?,?,?,?)",
                        [(rid, ti, tt, a, n) for (ti, tt, a, n) in credits])
    seen = set()
    vids = []
    for v in elem.findall("videos/video"):
        url = (v.get("src") or "").strip()
        if url and url not in seen:          # embed flag ignored: plain links work either way
            seen.add(url)
            vids.append((rid, url, (v.findtext("title") or "Video").strip()))
    if vids:
        cur.executemany("INSERT INTO videos VALUES (?,?,?)", vids)


def write_stats(cur, table, tot, jun, bh):
    def rows():
        for i in range(1, len(tot)):
            t = tot[i]
            if t:
                yield (i, t, jun[i] if i < len(jun) else 0, bh[i] if i < len(bh) else 0)
    cur.executemany("INSERT INTO %s VALUES (?,?,?,?)" % table, rows())


def main():
    releases_file = resolve_dump("releases", config.RELEASES_XML)   # checked before touching the DB

    conn = sqlite3.connect(config.DB_FILE)
    cur = conn.cursor()
    cur.executescript("""
        PRAGMA journal_mode = OFF;
        PRAGMA synchronous = OFF;
        DROP TABLE IF EXISTS releases;
        DROP TABLE IF EXISTS release_artists;
        DROP TABLE IF EXISTS release_labels;
        DROP TABLE IF EXISTS tracks;
        DROP TABLE IF EXISTS credits;
        DROP TABLE IF EXISTS videos;
        DROP TABLE IF EXISTS artist_stats;
        DROP TABLE IF EXISTS label_stats;
        DROP TABLE IF EXISTS artist_groups;
        DROP TABLE IF EXISTS label_groups;

        CREATE TABLE releases (
            release_id INTEGER PRIMARY KEY, master_id INTEGER, title TEXT,
            year INTEGER, year_approx INTEGER,
            label_id INTEGER, label_name TEXT, catno TEXT,
            main_artist_id INTEGER, main_artist_name TEXT,
            is_compilation INTEGER,
            gtag TEXT,            -- J / D / B (see config.DB_YEARS)
            styles TEXT,          -- |jungle|ragga|...
            fmt TEXT,             -- |vinyl|12"|white label|...
            versions INTEGER      -- releases of this master in the whole dump (capped at 255)
        );
        CREATE TABLE release_artists (release_id INTEGER, pos INTEGER, artist_id INTEGER, artist_name TEXT);
        CREATE TABLE release_labels (release_id INTEGER, pos INTEGER, label_id INTEGER, label_name TEXT, catno TEXT);
        CREATE TABLE tracks (release_id INTEGER, idx INTEGER, position TEXT, title TEXT);
        CREATE TABLE credits (release_id INTEGER, track_idx INTEGER, tracks_text TEXT,
                              artist_id INTEGER, artist_name TEXT);   -- remix credits of stored records
        CREATE TABLE videos (release_id INTEGER, url TEXT, title TEXT);
        CREATE TABLE artist_stats (artist_id INTEGER PRIMARY KEY, total_masters INTEGER,
                                   jungle_masters INTEGER, bh_masters INTEGER);
        CREATE TABLE label_stats (label_id INTEGER PRIMARY KEY, total_masters INTEGER,
                                  jungle_masters INTEGER, bh_masters INTEGER);
        CREATE TABLE artist_groups (artist_id INTEGER PRIMARY KEY, group_id INTEGER);   -- filled by 02_build_groups.py
        CREATE TABLE label_groups (label_id INTEGER PRIMARY KEY, group_id INTEGER);
    """)
    conn.commit()

    print("Streaming %s ..." % releases_file)
    context = etree.iterparse(gzip.open(releases_file, "rb"), events=("end",),
                              tag="release", huge_tree=True)

    at, aj, ab = Tally(), Tally(), Tally()      # artists: total / jungle+dnb / breakbeat hardcore
    lt, lj, lb = Tally(), Tally(), Tally()      # labels
    versions = bytearray(6000000)               # releases per master id, saturating at 255
    n_total = n_saved = 0

    for _, elem in context:
        n_total += 1
        if n_total % 500000 == 0:
            print("  %s releases scanned, %s saved" % (format(n_total, ","), format(n_saved, ",")))

        rid = to_int(elem.get("id"))
        mel = elem.find("master_id")
        master_id = to_int(mel.text) if mel is not None else 0

        artists = [(to_int(a.findtext("id")), (a.findtext("name") or "Unknown").strip())
                   for a in elem.findall("artists/artist")]
        labels = [(to_int(l.get("id")), (l.get("name") or "Unknown").strip(), (l.get("catno") or "").strip())
                  for l in elem.findall("labels/label")]

        styles = [s.text.strip().lower() for s in elem.findall("styles/style") if s.text]
        formats, descs = [], []
        for f in elem.findall("formats/format"):
            name = (f.get("name") or "").strip().lower()
            if name:
                formats.append(name)
            for d in f.findall("descriptions/description"):
                if d.text:
                    descs.append(d.text.strip().lower())
        fmt_all = formats + descs
        comp = 1 if any("compilation" in d or "mixed" in d for d in descs) else 0
        is_physical = (any(f in ("vinyl", "cd") for f in formats)
                       and not (OBSCURE & set(fmt_all)))
        year, approx = parse_year(elem.findtext("released"))

        is_jungle = "jungle" in styles
        is_dnb = "drum n bass" in styles
        is_bh = ("breakbeat" in styles and "hardcore" in styles and not (BH_NOISE & set(styles)))
        gtag = "J" if is_jungle else "D" if is_dnb else "B" if is_bh else None

        # ---- output tallies (placeholders never counted)
        art_ids, lab_ids = [], []
        for a, n in artists:
            if 0 < a <= MAX_ENTITY_ID and a not in art_ids and not is_placeholder_artist(a, n):
                art_ids.append(a)
        for l, n, c in labels:
            if 0 < l <= MAX_ENTITY_ID and l not in lab_ids and not is_pseudo_label(n):
                lab_ids.append(l)
        for a in art_ids:
            at.add(a, master_id)
        for l in lab_ids:
            lt.add(l, master_id)
        if 0 < master_id:
            if master_id >= len(versions):
                versions.extend(bytes(master_id + 1 - len(versions) + 500000))
            if versions[master_id] < 255:
                versions[master_id] += 1
        if not comp:
            if is_jungle or is_dnb:                 # all years, all formats
                for a in art_ids:
                    aj.add(a, master_id)
                for l in lab_ids:
                    lj.add(l, master_id)
            elif is_bh:
                for a in art_ids:
                    ab.add(a, master_id)
                for l in lab_ids:
                    lb.add(l, master_id)

        # ---- what to store
        if gtag:
            y0, y1 = DB_YEARS[gtag]
            if is_physical and y0 <= year <= y1:
                n_saved += 1
                save_release(cur, elem, rid, master_id, year, approx, artists, labels, comp, gtag,
                             "|" + "|".join(styles) + "|", "|" + "|".join(fmt_all) + "|",
                             collect_credits(elem))

        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]

    conn.commit()

    print("Writing master-based stats ...")
    a_tot, a_jun, a_bh = at.finish(), aj.finish(), ab.finish()
    l_tot, l_jun, l_bh = lt.finish(), lj.finish(), lb.finish()
    write_stats(cur, "artist_stats", a_tot, a_jun, a_bh)
    write_stats(cur, "label_stats", l_tot, l_jun, l_bh)
    conn.commit()
    del at, aj, ab, lt, lj, lb, a_tot, a_jun, a_bh, l_tot, l_jun, l_bh

    print("Writing version counts ...")
    upd = []
    for rid, m in cur.execute("SELECT release_id, master_id FROM releases").fetchall():
        upd.append((versions[m] if m and m < len(versions) else 1, rid))
    cur.executemany("UPDATE releases SET versions = ? WHERE release_id = ?", upd)

    cur.executescript("""
        CREATE INDEX idx_rel_year ON releases(year);
        CREATE INDEX idx_rel_master ON releases(master_id);
        CREATE INDEX idx_ra_artist ON release_artists(artist_id);
        CREATE INDEX idx_ra_rel ON release_artists(release_id);
        CREATE INDEX idx_rl_label ON release_labels(label_id);
        CREATE INDEX idx_cr_rel ON credits(release_id);
        CREATE INDEX idx_cr_artist ON credits(artist_id);
    """)
    conn.commit()

    counts = dict(cur.execute("SELECT gtag, COUNT(*) FROM releases GROUP BY gtag").fetchall())
    conn.close()

    print("\n" + "=" * 60)
    print("PRE-FILTER COMPLETE")
    print("=" * 60)
    print("Releases scanned:            %s" % format(n_total, ","))
    print("Saved  Jungle / DnB / BH:    %s / %s / %s" % (format(counts.get("J", 0), ","),
                                                        format(counts.get("D", 0), ","),
                                                        format(counts.get("B", 0), ",")))
    print("Database file:               %s" % config.DB_FILE)
    print("=" * 60)
    print("Next: 02_build_groups.py (optional, needs the artists + labels dumps),")
    print("      03_analyze_thresholds.py, then 04_build_dashboard.py")
    pause()


if __name__ == "__main__":
    main()
