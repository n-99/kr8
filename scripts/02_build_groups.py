# -*- coding: utf-8 -*-
"""KR8 step 2 (optional, ~10-15 min, run once per dump): alias + sublabel merging.

Jungle producers scatter their output over many aliases, and each alias has its own
Discogs id, so every alias stays under the "core" thresholds. This script reads the
Discogs ARTISTS and LABELS dumps (same date as the releases dump) and writes

    artist_groups(artist_id, group_id)   people and their aliases
    label_groups(label_id, group_id)     labels with their parent / sublabels

into the database. The build then sums the counts over each group. Merging only ever
adds exclusions (see common.Stats). Groups bigger than config.MAX_*_GROUP are treated
as Discogs noise (e.g. a major label with hundreds of sublabels) and dissolved.

Download from https://data.discogs.com/?prefix=data%2F2026%2F :
    discogs_20260901_artists.xml.gz   discogs_20260901_labels.xml.gz
"""
import gzip
import sqlite3
from collections import defaultdict

from lxml import etree

import config
from common import clean_name, is_pseudo_label, is_placeholder_artist, pause, resolve_dump, setup_console, to_int

setup_console()


class DSU(object):
    """Union-find over ids."""

    def __init__(self):
        self.p = {}

    def find(self, x):
        p = self.p
        p.setdefault(x, x)
        root = x
        while p[root] != root:
            root = p[root]
        while p[x] != root:
            p[x], x = root, p[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def stream(path, tag):
    return etree.iterparse(gzip.open(path, "rb"), events=("end",), tag=tag, huge_tree=True)


def cleanup(elem):
    elem.clear()
    while elem.getprevious() is not None:
        del elem.getparent()[0]


def merge_artists(interesting, path):
    dsu, names = DSU(), {}
    scanned = links = 0
    for _, elem in stream(path, "artist"):
        scanned += 1
        if scanned % 1000000 == 0:
            print("  artists scanned: %s" % format(scanned, ","))
        aid = to_int(elem.findtext("id"))
        aliases = [(to_int(n.get("id")), (n.text or "").strip()) for n in elem.findall("aliases/name")]
        aliases = [(i, n) for i, n in aliases if i > 0]
        if aliases and (aid in interesting or any(i in interesting for i, _ in aliases)):
            ids = [(aid, (elem.findtext("name") or "").strip())] + aliases
            ids = [(i, n) for i, n in ids if i > 0 and not is_placeholder_artist(i, n)]
            for i, n in ids:
                names[i] = n
            for i, _ in ids[1:]:
                dsu.union(ids[0][0], i)
                links += 1
        cleanup(elem)
    return dsu, names, scanned, links


def merge_labels(interesting, path):
    dsu, names = DSU(), {}
    scanned = links = 0
    for _, elem in stream(path, "label"):
        parent = elem.getparent()
        if parent is None or parent.tag != "labels":
            continue        # nested <label> inside <sublabels>: leave it to its parent
        scanned += 1
        if scanned % 200000 == 0:
            print("  labels scanned: %s" % format(scanned, ","))
        lid = to_int(elem.findtext("id"))
        name = (elem.findtext("name") or "").strip()
        rel = [(to_int(x.get("id")), (x.text or "").strip()) for x in elem.findall("sublabels/label")]
        p = elem.find("parentLabel")
        if p is not None:
            rel.append((to_int(p.get("id")), (p.text or "").strip()))
        rel = [(i, n) for i, n in rel if i > 0]
        if rel and (lid in interesting or any(i in interesting for i, _ in rel)):
            ids = [(lid, name)] + rel
            ids = [(i, n) for i, n in ids if i > 0 and not is_pseudo_label(n)]
            for i, n in ids:
                names[i] = n
            for i, _ in ids[1:]:
                dsu.union(ids[0][0], i)
                links += 1
        cleanup(elem)
    return dsu, names, scanned, links


def components(dsu, max_size):
    comp = defaultdict(list)
    for x in list(dsu.p):
        comp[dsu.find(x)].append(x)
    kept = dict((r, m) for r, m in comp.items() if 2 <= len(m) <= max_size)
    dissolved = [m for m in comp.values() if len(m) > max_size]
    return kept, dissolved


def report(kind, kept, dissolved, names, scanned, links):
    print("  %s scanned: %s, links: %s" % (kind, format(scanned, ","), format(links, ",")))
    print("  groups kept: %s (%s members)" % (
        format(len(kept), ","), format(sum(len(m) for m in kept.values()), ",")))
    print("  dissolved as too big: %d (largest: %s)" % (
        len(dissolved), ", ".join(format(len(m), ",") for m in sorted(dissolved, key=len, reverse=True)[:5]) or "-"))
    if scanned and not links:
        print("  WARNING: no links found. Check the tag names in your dump:")
        print("    artists: <aliases><name id=..>")
        print("    labels:  <sublabels><label id=..> / <parentLabel id=..>")
    for m in sorted(kept.values(), key=len, reverse=True)[:8]:
        line = "    %2d: %s" % (len(m), ", ".join(clean_name(names.get(x, "#%d" % x)) for x in m[:6]))
        print(line if len(line) <= 76 else line[:73] + "...")


def main():
    conn = sqlite3.connect(config.DB_FILE)
    cur = conn.cursor()
    art, lab = set(), set()
    for q in ("SELECT artist_id FROM artist_stats WHERE jungle_masters > 0 OR bh_masters > 0",
              "SELECT DISTINCT artist_id FROM release_artists",
              "SELECT DISTINCT artist_id FROM credits"):
        art.update(r[0] for r in cur.execute(q))
    for q in ("SELECT label_id FROM label_stats WHERE jungle_masters > 0 OR bh_masters > 0",
              "SELECT DISTINCT label_id FROM release_labels"):
        lab.update(r[0] for r in cur.execute(q))
    print("Entities of interest: %s artists, %s labels" % (format(len(art), ","), format(len(lab), ",")))

    artists_file = resolve_dump("artists", config.ARTISTS_XML, required=False)
    if artists_file:
        print("Reading %s ..." % artists_file)
        dsu, names, scanned, links = merge_artists(art, artists_file)
        kept, dissolved = components(dsu, config.MAX_ARTIST_GROUP)
        cur.execute("DELETE FROM artist_groups")
        cur.executemany("INSERT INTO artist_groups VALUES (?,?)",
                        [(m, root) for root, members in kept.items() for m in members])
        conn.commit()
        report("artists", kept, dissolved, names, scanned, links)
    else:
        print("Skipping artists: no dump found or fetched.")

    labels_file = resolve_dump("labels", config.LABELS_XML, required=False)
    if labels_file:
        print("Reading %s ..." % labels_file)
        dsu, names, scanned, links = merge_labels(lab, labels_file)
        kept, dissolved = components(dsu, config.MAX_LABEL_GROUP)
        cur.execute("DELETE FROM label_groups")
        cur.executemany("INSERT INTO label_groups VALUES (?,?)",
                        [(m, root) for root, members in kept.items() for m in members])
        conn.commit()
        report("labels", kept, dissolved, names, scanned, links)
    else:
        print("Skipping labels: no dump found or fetched.")

    conn.close()
    print("\nDone. Re-run 03_analyze_thresholds.py / 04_build_dashboard.py to use the groups.")
    pause()


if __name__ == "__main__":
    main()
