# -*- coding: utf-8 -*-
"""Shared helpers for the KR8 scripts (Python 3.8 compatible)."""
import os
import re
import sys
from collections import defaultdict
from datetime import date, timedelta

import config
ZERO = (0, 0, 0)
REMIX_RE = re.compile(r"remix|rmx|re-mix", re.I)
NAME_SUFFIX_RE = re.compile(r"\s*\(\d+\)$")          # Discogs "Name (2)" disambiguation
TRACK_SPLIT_RE = re.compile(r"[,;/&]+|\band\b", re.I)
NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
REISSUE_MARKS = ("|reissue|", "|repress|", "|remastered|")
GTAG_RANK = {"J": 0, "D": 1, "B": 2}

_NON_ARTIST_IDS = frozenset(config.NON_ARTIST_IDS)
_NON_ARTIST_NAMES = frozenset(config.NON_ARTIST_NAMES)
_PSEUDO_PREFIXES = tuple(config.PSEUDO_LABEL_PREFIXES)


# ------------------------------------------------------------------ small utils
def setup_console():
    """Windows consoles default to cp1252 and crash on kana/emoji."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def pause(msg="\nPress Enter to exit..."):
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            input(msg)
    except (EOFError, OSError):
        pass


def to_int(text, default=0):
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def is_placeholder_artist(aid, name):
    return aid in _NON_ARTIST_IDS or (name or "").strip().lower() in _NON_ARTIST_NAMES


def is_pseudo_label(name):
    return (name or "").strip().lower().startswith(_PSEUDO_PREFIXES)


def clean_name(name):
    return NAME_SUFFIX_RE.sub("", name or "").strip()


def pct(t, j):
    return (j * 100.0 / t) if t else 0.0


NON_F = "SELECT release_id FROM releases WHERE gtag <> 'F'"   # ignore rows of older DBs' untagged candidates


def check_schema(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(releases)")]
    if "gtag" not in cols:
        print("This database was built by an older 01_pre_filter.py.")
        print("Run the new 01_pre_filter.py first (~45 min).")
        pause()
        sys.exit(1)


# ------------------------------------------------------------------ finding the Discogs dumps
# Dumps are discogs_YYYYMMDD_<kind>.xml.gz, dated the 1st of the month, one folder per year at
# https://data.discogs.com/?prefix=data%2F<year>%2F . Going by the 2026 dumps: every month's dump
# is posted the same day (August slipped by one), except January's, which lags about two weeks
# (posted 2026-01-15). find_dump() picks whatever is newest already on disk; resolve_dump() also
# checks the real listing (best-effort: silently skipped without internet or if it's blocked) so it
# can say when a newer dump exists, or help fetch one if none is present at all.
_DUMP_PAT = r"discogs_(\d{8})_%s\.xml\.gz"


def find_dump(kind, folder="."):
    """The newest discogs_YYYYMMDD_<kind>.xml.gz already in `folder`, or None."""
    rx = re.compile("^" + (_DUMP_PAT % kind) + "$")
    best = None
    for name in os.listdir(folder):
        m = rx.match(name)
        if m and (best is None or m.group(1) > best[0]):
            best = (m.group(1), os.path.join(folder, name))
    return best[1] if best else None


def _dump_date(path):
    m = re.search(r"discogs_(\d{8})_", os.path.basename(path))
    return m.group(1) if m else None


def _expected_dump_date():
    """Calendar fallback for when the real listing can't be reached."""
    today = date.today()
    d = date(today.year, today.month, 1)
    if d.month == 1 and today < d + timedelta(days=14):
        d = date(d.year - 1, 12, 1)
    return "%04d%02d01" % (d.year, d.month)


def _fetch_year_listing(year):
    import urllib.request
    url = "https://data.discogs.com/?prefix=data%%2F%d%%2F" % year
    try:
        with urllib.request.urlopen(url, timeout=6) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception:
        return None


def latest_remote_dump(kind, year=None):
    """Best-effort: the newest discogs_YYYYMMDD_<kind>.xml.gz actually listed on
    data.discogs.com right now, or None if that page can't be reached (no internet, a
    firewall, ...). Callers need a calendar-based fallback for when this is None."""
    year = year or date.today().year
    rx = re.compile(_DUMP_PAT % kind)
    dates = rx.findall(_fetch_year_listing(year) or "")
    if date.today().month == 1:      # this January's dump may not be listed yet; check last December too
        dates += rx.findall(_fetch_year_listing(year - 1) or "")
    return max(dates) if dates else None


def resolve_dump(kind, configured, required=True):
    """Find, or help fetch, a discogs_YYYYMMDD_<kind>.xml.gz file. `configured` is the matching
    config.py setting: a literal filename pins that exact dump; None auto-detects the newest one
    already in this folder. Returns a path, or None if not required and nothing was found."""
    path = configured if configured and os.path.exists(configured) else find_dump(kind)
    local_date = _dump_date(path) if path else None
    this_month = "%04d%02d" % (date.today().year, date.today().month)
    if local_date and local_date[:6] == this_month:
        return path                              # this month's dump, if any, can't beat it

    expected = latest_remote_dump(kind) or _expected_dump_date()
    fname = "discogs_%s_%s.xml.gz" % (expected, kind)
    url = "https://data.discogs.com/?prefix=data%%2F%s%%2F" % expected[:4]

    if path:
        if local_date and local_date < expected:
            print("Note: using %s, but a newer %s dump looks available: %s" % (path, kind, fname))
            print("      %s" % url)
        return path

    print("No discogs_*_%s.xml.gz found in this folder." % kind)
    print("Looking for: %s" % fname)
    print("Download page: %s" % url)
    try:
        ans = input("Open that page in your browser now? [y/N] ").strip().lower()
    except (EOFError, OSError):
        ans = ""
    if ans == "y":
        try:
            import webbrowser
            if not webbrowser.open(url):
                raise RuntimeError("no browser controller registered")
        except Exception:
            print("Couldn't open a browser here \u2014 use the link above instead.")
    if required:
        pause()
        sys.exit(1)
    return None


class Params(object):
    """Every UPPERCASE name in config.py, overridable: Params(ARTIST_HARD_CAP=6)."""

    def __init__(self, **over):
        for name in dir(config):
            if name.isupper():
                setattr(self, name, over.pop(name, getattr(config, name)))
        if over:
            raise TypeError("unknown parameter(s): " + ", ".join(sorted(over)))


# ------------------------------------------------------------------ core tests
def core_artist(t, j, P):
    if j >= P.ARTIST_HARD_CAP and pct(t, j) >= P.ARTIST_HARD_MIN_PCT:
        return "hard"
    if t and j >= P.ABS_MIN and j * 100.0 / t >= P.ARTIST_PCT:
        return "pct"
    return ""


def core_label(t, j, P):
    if j >= P.LABEL_HARD_CAP and pct(t, j) >= P.LABEL_HARD_MIN_PCT:
        return "hard"
    if t:
        share = j * 100.0 / t
        if j >= P.LABEL_MID_ABS and share >= P.LABEL_MID_PCT:
            return "mid"
        if j >= P.ABS_MIN and share >= P.LABEL_PCT:
            return "pct"
    return ""


class Stats(object):
    """Per-artist / per-label master counts, optionally merged over alias groups.

    Rule: an entity is core if ITS OWN numbers or its GROUP's numbers are core.
    Merging can only add exclusions, never rescue anyone.
    """

    def __init__(self, conn, use_groups=True):
        cur = conn.cursor()
        self.a_own, self.l_own = {}, {}
        self.a_gid, self.l_gid = {}, {}
        self.a_grp, self.l_grp = {}, {}
        if use_groups:
            self.a_gid = dict(cur.execute("SELECT artist_id, group_id FROM artist_groups").fetchall())
            self.l_gid = dict(cur.execute("SELECT label_id, group_id FROM label_groups").fetchall())
        for aid, t, j, b in cur.execute(
                """SELECT artist_id, total_masters, jungle_masters, bh_masters FROM artist_stats
                   WHERE artist_id IN (SELECT artist_id FROM release_artists
                                       UNION SELECT artist_id FROM credits
                                       UNION SELECT artist_id FROM artist_groups)"""):
            self.a_own[aid] = (t, j, b)
        for lid, t, j, b in cur.execute(
                """SELECT label_id, total_masters, jungle_masters, bh_masters FROM label_stats
                   WHERE label_id IN (SELECT label_id FROM release_labels
                                      UNION SELECT label_id FROM label_groups)"""):
            self.l_own[lid] = (t, j, b)
        self._sum(self.a_gid, self.a_own, self.a_grp)
        self._sum(self.l_gid, self.l_own, self.l_grp)
        # id -> lowercase name, for the KEEP_ARTISTS / KEEP_LABELS lists (name entries)
        self._names = {
            "a": dict((i, clean_name(n).lower()) for i, n in cur.execute(
                "SELECT artist_id, MIN(artist_name) FROM release_artists GROUP BY artist_id")),
            "l": dict((i, clean_name(n).lower()) for i, n in cur.execute(
                "SELECT label_id, MIN(label_name) FROM release_labels GROUP BY label_id")),
        }
        self._keep_cache = {}

    def _match(self, kind, entries):
        """Ids named by a list of names and / or ids. kind is "a" (artists) or "l" (labels)."""
        want_ids = set(e for e in entries if isinstance(e, int))
        want_names = set(e.strip().lower() for e in entries if isinstance(e, str))
        return frozenset(want_ids | set(i for i, n in self._names[kind].items() if n in want_names))

    def keep_ids(self, kind, entries):
        """Ids on a KEEP list."""
        entries = tuple(entries)
        if not entries:
            return frozenset()
        key = ("keep", kind, entries)
        if key not in self._keep_cache:
            self._keep_cache[key] = self._match(kind, entries)
        return self._keep_cache[key]

    def core_ids(self, kind, entries):
        """Ids on a CORE list plus the rest of their alias / sublabel group (merging only adds exclusions)."""
        entries = tuple(entries)
        if not entries:
            return frozenset()
        key = ("core", kind, entries)
        if key not in self._keep_cache:
            base = self._match(kind, entries)
            gid_of = self.a_gid if kind == "a" else self.l_gid
            groups = set(gid_of[i] for i in base if i in gid_of)
            self._keep_cache[key] = base | frozenset(i for i, g in gid_of.items() if g in groups)
        return self._keep_cache[key]

    @staticmethod
    def _sum(gid_of, own, out):
        for ent, gid in gid_of.items():
            t, j, b = own.get(ent, ZERO)
            g = out.setdefault(gid, [0, 0, 0])
            g[0] += t
            g[1] += j
            g[2] += b

    @property
    def has_groups(self):
        return bool(self.a_gid or self.l_gid)

    # own numbers
    def a_stats(self, aid):
        return self.a_own.get(aid, ZERO)

    def l_stats(self, lid):
        return self.l_own.get(lid, ZERO)

    # group numbers (fall back to own when not in a group)
    def a_group_stats(self, aid):
        gid = self.a_gid.get(aid)
        return tuple(self.a_grp[gid]) if gid is not None else self.a_stats(aid)

    def l_group_stats(self, lid):
        gid = self.l_gid.get(lid)
        return tuple(self.l_grp[gid]) if gid is not None else self.l_stats(lid)

    def a_group_id(self, aid):
        return self.a_gid.get(aid, aid)

    # verdicts: "" = kept, otherwise the rule that fired
    def artist_core(self, aid, P):
        if aid in self.keep_ids("a", P.KEEP_ARTISTS):
            return ""
        if aid in self.core_ids("a", P.CORE_ARTISTS):
            return "list"
        t, j, _ = self.a_stats(aid)
        why = core_artist(t, j, P)
        if why:
            return why
        if aid in self.a_gid:
            t, j, _ = self.a_group_stats(aid)
            why = core_artist(t, j, P)
            if why:
                return "group-" + why
        return ""

    def label_core(self, lid, P):
        if lid in self.keep_ids("l", P.KEEP_LABELS):
            return ""
        if lid in self.core_ids("l", P.CORE_LABELS):
            return "list"
        t, j, _ = self.l_stats(lid)
        why = core_label(t, j, P)
        if why:
            return why
        if lid in self.l_gid:
            t, j, _ = self.l_group_stats(lid)
            why = core_label(t, j, P)
            if why:
                return "group-" + why
        return ""

    def remixer_core(self, aid, P):
        """Jungle-identified remixer: enough jungle masters AND enough share."""
        for t, j, _ in (self.a_stats(aid), self.a_group_stats(aid)):
            if j >= P.REMIXER_MIN_JUNGLE and pct(t, j) >= P.REMIXER_MIN_PCT:
                return True
        return False


# ------------------------------------------------------------------ data loading
class Rel(object):
    __slots__ = ("id", "master", "title", "year", "approx", "label_id", "label_name", "catno",
                 "artist_id", "artist_name", "comp", "gtag", "fmt", "versions")

    def __init__(self, r):
        (self.id, m, title, year, self.approx, self.label_id, self.label_name, self.catno,
         self.artist_id, self.artist_name, comp, self.gtag, fmt, v) = r
        self.master = m or 0
        self.title = title or ""
        self.year = year or 0
        self.comp = bool(comp)
        self.fmt = fmt or ""
        self.versions = v or 1


class Data(object):
    pass


def load_data(conn):
    cur = conn.cursor()
    d = Data()
    d.releases = {}
    d.reissued = set()
    for r in cur.execute(
            """SELECT release_id, master_id, title, year, year_approx, label_id, label_name, catno,
                      main_artist_id, main_artist_name, is_compilation, gtag, fmt, versions
               FROM releases WHERE gtag IN ('J', 'D', 'B')"""):    # older DBs also hold untagged "F" rows
        rel = Rel(r)
        d.releases[rel.id] = rel
        if rel.master and any(k in rel.fmt for k in REISSUE_MARKS):
            d.reissued.add(rel.master)
    d.artists = defaultdict(list)
    for rid, aid, name in cur.execute(
            "SELECT release_id, artist_id, artist_name FROM release_artists ORDER BY release_id, pos"):
        if rid in d.releases:
            d.artists[rid].append((aid, name))
    d.labels = defaultdict(list)
    for rid, lid, name, catno in cur.execute(
            "SELECT release_id, label_id, label_name, catno FROM release_labels ORDER BY release_id, pos"):
        if rid in d.releases:
            d.labels[rid].append((lid, name, catno))
    d.credits = defaultdict(list)
    for rid, tidx, ttext, aid, name in cur.execute(
            "SELECT release_id, track_idx, tracks_text, artist_id, artist_name FROM credits"):
        if rid in d.releases:
            d.credits[rid].append((tidx, ttext, aid, name))
    d.tracks = defaultdict(list)
    for rid, idx, pos, title in cur.execute(
            """SELECT release_id, idx, position, title FROM tracks
               WHERE release_id IN (SELECT DISTINCT c.release_id FROM credits c
                                    JOIN releases r ON r.release_id = c.release_id
                                    WHERE r.gtag <> 'F')
               ORDER BY release_id, idx"""):
        if rid in d.releases:
            d.tracks[rid].append((idx, pos, title))
    d.videos = defaultdict(list)
    for rid, url, title in cur.execute("SELECT release_id, url, title FROM videos"):
        if rid in d.releases:
            d.videos[rid].append((url, title))
    return d


# ------------------------------------------------------------------ selection
def _year_text(rel):
    if rel.approx:
        return "%d?" % (rel.year // 10)
    return str(rel.year) if rel.year else ""


def _remix_text(title, who):
    if title:
        return '"%s" (remixed by %s)' % (title, who)
    return "(remixed by %s)" % who


def _resolve_tracks(ttext, tracks):
    toks = set(t.strip().lower() for t in TRACK_SPLIT_RE.split(ttext) if t.strip())
    return [title for (idx, pos, title) in tracks if title and pos.strip().lower() in toks]


def _remixes(rel, real_arts, data, stats, P):
    """-> (remix highlight texts, [(remixer_id, name)])"""
    creds = data.credits.get(rel.id)
    if not creds:
        return [], []
    own_groups = set(stats.a_group_id(a) for a in real_arts)
    tracks = data.tracks.get(rel.id, [])
    by_idx = dict((idx, title) for idx, pos, title in tracks)
    out, who_list = [], []
    for tidx, ttext, raid, rname in creds:
        if raid <= 0 or is_placeholder_artist(raid, rname):
            continue
        if stats.a_group_id(raid) in own_groups:      # self-remix, also under an alias
            continue
        if not stats.remixer_core(raid, P):
            continue
        who = clean_name(rname)
        if all(x[0] != raid for x in who_list):
            who_list.append((raid, who))
        if tidx >= 0:
            texts = [_remix_text(by_idx.get(tidx, ""), who)]
        elif ttext:
            hits = _resolve_tracks(ttext, tracks)
            texts = [_remix_text(h, who) for h in hits] if hits else ["[%s] (remixed by %s)" % (ttext, who)]
        else:
            texts = [_remix_text("", who)]
        for t in texts:
            if t not in out:
                out.append(t)
    return out, who_list


def _group_key(rel):
    if rel.master:
        return ("m", rel.master)
    if rel.artist_id > 0 and not is_placeholder_artist(rel.artist_id, rel.artist_name):
        nt = NON_ALNUM_RE.sub("", rel.title.lower())
        if len(nt) >= 2:                              # same record entered twice without a master
            return ("n", rel.artist_id, nt, rel.label_id)
    return ("r", rel.id)


def select_rows(data, stats, P):
    """Apply all filters, group by master, return dashboard rows (list of dicts)."""
    groups = {}
    order = sorted(data.releases.values(), key=lambda r: (r.year or 9999, r.id))
    for rel in order:
        low = rel.title.lower()
        if any(w in low for w in P.EXCLUDE_TITLE_WORDS):
            continue
        window = P.EXPORT_YEARS.get(rel.gtag)
        if not window or not (window[0] <= rel.year <= window[1]):
            continue
        arts = data.artists.get(rel.id) or [(rel.artist_id, rel.artist_name)]
        labs = data.labels.get(rel.id) or [(rel.label_id, rel.label_name, rel.catno)]
        real_arts = [a for a, n in arts if a > 0 and not is_placeholder_artist(a, n)]
        real_labs = [l for l, n, c in labs if l > 0 and not is_pseudo_label(n)]

        # ANY core artist / label drops the record. Compilations (artist = Various)
        # are only judged by their label.
        if not rel.comp and any(stats.artist_core(a, P) for a in real_arts):
            continue
        if any(stats.label_core(l, P) for l in real_labs):
            continue

        remixes, rmx = _remixes(rel, real_arts, data, stats, P)
        if rel.gtag == "B" and P.BH_REQUIRE_JUNGLE_LINK and not remixes:
            if not any(stats.a_group_stats(a)[1] > 0 for a in real_arts):
                continue

        tags = []
        if remixes and not rel.comp:    # a comp's remix credit is real but unsurprising: it's just
            tags.append("remix")        # one more track on a sampler that collects many by design
        if (not rel.comp and real_arts
                and all(pct(*stats.a_group_stats(a)[:2]) < P.NONJUNGLE_PCT for a in real_arts)):
            tags.append("nj_artist")
        if real_labs and all(pct(*stats.l_group_stats(l)[:2]) < P.NONJUNGLE_PCT for l in real_labs):
            tags.append("nj_label")
        if not tags:
            tags.append("small")

        g = groups.setdefault(_group_key(rel), {"items": [], "tags": [], "remixes": [], "rmx": []})
        g["items"].append((rel, arts, labs))
        if not rel.comp:
            for x in rmx:
                if x not in g["rmx"]:
                    g["rmx"].append(x)
        for t in tags:
            if t not in g["tags"]:
                g["tags"].append(t)
        for f in remixes:
            if f not in g["remixes"]:
                g["remixes"].append(f)

    rows = []
    for g in groups.values():
        items = g["items"]
        first = items[0][0]
        versions = first.versions if first.master else len(items)
        if versions > P.EXPORT_MAX_VERSIONS:
            continue
        rel_rows, vids, seen = [], [], set()
        wl = comp = False
        gtag = first.gtag
        for rel, arts, labs in items:
            is_wl = "|white label|" in rel.fmt
            wl = wl or is_wl
            comp = comp or rel.comp
            if GTAG_RANK[rel.gtag] < GTAG_RANK[gtag]:
                gtag = rel.gtag
            lab = labs[0] if labs else (0, "", "")
            rel_rows.append({"id": rel.id, "url": "https://www.discogs.com/release/%d" % rel.id,
                             "catno": lab[2] or "", "label": clean_name(lab[1]),
                             "year": _year_text(rel), "wl": is_wl})
            for url, title in data.videos.get(rel.id, ()):
                if url not in seen:
                    seen.add(url)
                    vids.append({"url": url, "title": title})
        arts0, labs0 = items[0][1], items[0][2]
        artist = " / ".join(clean_name(n) for a, n in arts0[:3]) + (" / …" if len(arts0) > 3 else "")
        label = " / ".join(clean_name(n) for l, n, c in labs0[:2])
        catno = "; ".join(c for l, n, c in labs0[:2] if c)
        if first.master:
            key = "master_%d" % first.master
            url = ("https://www.discogs.com/master/%d" % first.master) if len(items) > 1 else rel_rows[0]["url"]
            reiss = first.master in data.reissued
        else:
            key = "release_%d" % first.id
            url = rel_rows[0]["url"]
            reiss = any(k in first.fmt for k in REISSUE_MARKS)
        rows.append({"key": key, "url": url, "title": first.title, "artist": artist, "label": label,
                     "catno": catno, "year": first.year, "year_text": _year_text(first), "gtag": gtag,
                     "comp": comp, "versions": versions, "n": len(items), "reiss": reiss, "wl": wl,
                     "yt": bool(vids), "tags": g["tags"], "remixes": g["remixes"], "remixers": g["rmx"],
                     "releases": rel_rows, "videos": vids})
    rows.sort(key=lambda r: (r["year"] or 9999, r["title"].lower()))
    return rows


def default_view_reason(row, P):
    """Why a record is hidden on first load, or None if it's visible. Remixes ignore the year
    range, same as comps: the remix is the point, not the year of the record it's hiding on."""
    if row["comp"]:
        return "compilation"
    if row["reiss"]:
        return "reissued"
    if row["gtag"] == "B":
        return "breakbeat hardcore"
    if "remix" not in row["tags"] and not (P.UI_YEAR_MIN <= row["year"] <= P.UI_YEAR_MAX):
        return "outside %d-%d" % (P.UI_YEAR_MIN, P.UI_YEAR_MAX)
    if row["versions"] > P.UI_MAX_VERSIONS:
        return "more than %d versions" % P.UI_MAX_VERSIONS
    return None


def in_default_view(row, P):
    """Mirrors what the dashboard shows on load."""
    return default_view_reason(row, P) is None
