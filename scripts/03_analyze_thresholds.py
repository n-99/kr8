# -*- coding: utf-8 -*-
"""KR8 step 3: who sits on the edge of the thresholds, what does each rule
remove, and what does each setting do to the result count?

Same thresholds and same selection code as 04_build_dashboard.py (config.py),
including alias / sublabel groups when 02_build_groups.py has been run.
Read, edit config.py, run again. Nothing here changes any file.
"""
import sqlite3
import textwrap

import config
from common import (NON_F, Params, Stats, check_schema, clean_name, default_view_reason, in_default_view,
                    load_data, pause, pct, select_rows, setup_console)

setup_console()

W = 78
BUCKETS = (("remix", "remixes"), ("nj_artist", "non-jungle artist"), ("nj_label", "non-jungle label"),
           ("small", "small acts"))


def head(title):
    print("\n" + "=" * W)
    print(title)
    print("=" * W)


def entity_rows(stats, kind, names):
    """Only entities that have records in the DB (alias-group members without any are noise here)."""
    own = stats.a_own if kind == "a" else stats.l_own
    gids = stats.a_gid if kind == "a" else stats.l_gid
    for eid, (t, j, b) in own.items():
        if j == 0 or eid not in names:
            continue
        gt, gj, gb = stats.a_group_stats(eid) if kind == "a" else stats.l_group_stats(eid)
        yield eid, t, j, gt, gj, eid in gids


def show(title, picked, names, kind, stats, P, by_share=False, limit=15):
    head(title)
    fmt = "%-26s %9s %10s %6s  %s"
    print(fmt % ("Name", "own j/t", "group j/t", "share", "status"))
    print("-" * W)
    if by_share:
        picked = sorted(picked, key=lambda r: (-pct(r[3], r[4]), r[0]))     # most jungle-like first
    else:
        picked = sorted(picked, key=lambda r: (-r[1], r[0]))                # biggest output first
    if not picked:
        print("(none)")
    for eid, t, j, gt, gj, in_group in picked[:limit]:
        why = stats.artist_core(eid, P) if kind == "a" else stats.label_core(eid, P)
        listed = eid in (stats.keep_ids("a", P.KEEP_ARTISTS) if kind == "a" else stats.keep_ids("l", P.KEEP_LABELS))
        # "share" reflects whichever numbers actually decided the verdict: for a plain "hard"/"pct"/"mid"
        # verdict that's the entity's own share, even when it also belongs to a group (a group's diluted
        # share is irrelevant if the entity was already core on its own); only a "group-" verdict, or no
        # verdict at all, falls back to the group's share (or own, when it isn't grouped).
        shown_pct = pct(t, j) if (why and not why.startswith("group-")) or listed else pct(gt, gj)
        status = "kept (KEEP list)" if listed else ("EXCLUDED " + why) if why else "kept"
        print(fmt % (clean_name(names[eid])[:26], "%d/%d" % (j, t),
                     ("%d/%d" % (gj, gt)) if in_group else "-", "%5.1f%%" % shown_pct, status))


def database_checks(conn):
    """What used to be hand-typed SQL: sanity checks on what 01_pre_filter.py stored."""
    head("DATABASE CHECKS")
    by_tag = dict(conn.execute("SELECT gtag, COUNT(*) FROM releases WHERE gtag <> 'F' GROUP BY gtag"))
    print("Stored records: Jungle %s, DnB %s, Breakbeat hardcore %s" % tuple(
        format(by_tag.get(k, 0), ",") for k in ("J", "D", "B")))
    n_track = conn.execute("SELECT COUNT(*) FROM credits WHERE track_idx >= 0 AND release_id IN (%s)" % NON_F
                           ).fetchone()[0]
    n_rel = conn.execute("SELECT COUNT(*) FROM credits WHERE track_idx = -1 AND release_id IN (%s)" % NON_F
                         ).fetchone()[0]
    print("Remix credits: %s on tracks, %s release-level" % (format(n_track, ","), format(n_rel, ",")))
    if not n_rel:
        print("  (0 release-level: remixers are only credited on tracks in this dump)")
    seen = conn.execute("""SELECT artist_name, artist_id, COUNT(*) FROM release_artists
                           WHERE release_id IN (%s) AND lower(trim(artist_name)) IN (%s)
                           GROUP BY artist_name, artist_id ORDER BY 3 DESC""" % (
        NON_F, ",".join("?" * len(config.NON_ARTIST_NAMES))), config.NON_ARTIST_NAMES).fetchall()
    print(textwrap.fill("Placeholder artists (never counted as core): " + (
        ", ".join("%s = id %d" % (n, i) for n, i, _ in seen[:6]) or "none in the stored records"),
        W, subsequent_indent="  "))
    odd = [(n, i) for n, i, _ in seen if i not in config.NON_ARTIST_IDS]
    if odd:
        print(textwrap.fill("  Not in NON_ARTIST_IDS (still ignored, they match by name): " + ", ".join(
            "%s = %d" % x for x in odd[:6]), W))


def removed_by(title, base_rows, alt_rows, P, n=12):
    """Records that come back when a rule is switched off, evenly sampled."""
    base = set(r["key"] for r in base_rows)
    extra = [r for r in alt_rows if r["key"] not in base]
    view = [r for r in extra if in_default_view(r, P)]
    print("\n%s" % title)
    print("  %d more records (%d in the default view)" % (len(extra), len(view)))
    pool = view or extra
    for r in pool[::max(1, len(pool) // n)][:n]:
        line = "  %s  %s - %s [%s]" % (r["year_text"], r["artist"], r["title"], r["label"])
        print(line if len(line) <= W else line[:W - 3] + "...")


def main():
    conn = sqlite3.connect(config.DB_FILE)
    check_schema(conn)
    P = Params()
    stats = Stats(conn, P.USE_GROUPS)
    stats_nog = Stats(conn, False)
    an, ln = {}, {}
    for q in ("SELECT artist_id, MIN(artist_name) FROM release_artists WHERE release_id IN (%s) "
              "GROUP BY artist_id" % NON_F,
              "SELECT artist_id, MIN(artist_name) FROM credits WHERE release_id IN (%s) "
              "GROUP BY artist_id" % NON_F):
        for i, n in conn.execute(q):
            an.setdefault(i, n)
    for i, n in conn.execute("SELECT label_id, MIN(label_name) FROM release_labels WHERE release_id IN (%s) "
                             "GROUP BY label_id" % NON_F):
        ln[i] = n

    print("Artists: hard cap %d (share floor %.0f%%), %d+ masters and %.0f%%" % (
        P.ARTIST_HARD_CAP, P.ARTIST_HARD_MIN_PCT, P.ABS_MIN, P.ARTIST_PCT))
    print("Labels:  hard cap %d (share floor %.0f%%), mid %d+ and %.0f%%, %d+ and %.0f%%" % (
        P.LABEL_HARD_CAP, P.LABEL_HARD_MIN_PCT, P.LABEL_MID_ABS, P.LABEL_MID_PCT, P.ABS_MIN, P.LABEL_PCT))
    print("Groups:  %s" % ("merged (%s artist, %s label members)" % (
        format(len(stats.a_gid), ","), format(len(stats.l_gid), ",")) if stats.has_groups
        else "not loaded (run 02_build_groups.py)"))
    print("share = jungle/DnB masters / all masters (of the group, when grouped)")
    for name, ents in (("CORE", (P.CORE_ARTISTS, P.CORE_LABELS)), ("KEEP", (P.KEEP_ARTISTS, P.KEEP_LABELS))):
        if ents[0] or ents[1]:
            print(textwrap.fill("%s lists: artists %s, labels %s" % (
                name, ", ".join(map(str, ents[0])) or "-", ", ".join(map(str, ents[1])) or "-"), W))

    database_checks(conn)

    A = list(entity_rows(stats, "a", an))
    L = list(entity_rows(stats, "l", ln))
    ha, hl, low = P.ARTIST_HARD_CAP, P.LABEL_HARD_CAP, P.NONJUNGLE_PCT
    near_a = [r for r in A if ha - 2 <= max(r[2], r[4]) <= ha + 2]
    near_l = [r for r in L if hl - 3 <= max(r[2], r[4]) <= hl + 3]
    show("ARTISTS at the hard cap (%d-%d masters), jungle share %.0f%%+" % (ha - 2, ha + 2, low),
         [r for r in near_a if pct(r[3], r[4]) >= low], an, "a", stats, P, by_share=True)
    show("ARTISTS at the hard cap (%d-%d masters), share under %.0f%%" % (ha - 2, ha + 2, low),
         [r for r in near_a if pct(r[3], r[4]) < low], an, "a", stats, P)
    show("ARTISTS near the share threshold (%.0f%% +/- 8, below the hard cap)" % P.ARTIST_PCT,
         [r for r in A if P.ABS_MIN <= r[2] < ha and abs(pct(r[1], r[2]) - P.ARTIST_PCT) <= 8],
         an, "a", stats, P)
    show("LABELS at the hard cap (%d-%d masters), jungle share %.0f%%+" % (hl - 3, hl + 3, low),
         [r for r in near_l if pct(r[3], r[4]) >= low], ln, "l", stats, P, by_share=True)
    show("LABELS at the hard cap (%d-%d masters), share under %.0f%%" % (hl - 3, hl + 3, low),
         [r for r in near_l if pct(r[3], r[4]) < low], ln, "l", stats, P)
    show("LABELS near the share thresholds (mid %.0f%% / top %.0f%%, +/- 8)" % (P.LABEL_MID_PCT, P.LABEL_PCT),
         [r for r in L if r[2] < hl and (
             (r[2] >= P.ABS_MIN and abs(pct(r[1], r[2]) - P.LABEL_PCT) <= 8)
             or (r[2] >= P.LABEL_MID_ABS - 2 and abs(pct(r[1], r[2]) - P.LABEL_MID_PCT) <= 8))],
         ln, "l", stats, P)

    print("\nLoading records for the counts below ...")
    data = load_data(conn)
    conn.close()
    rows = select_rows(data, stats, P)

    head("WHAT EACH RULE REMOVES (records that come back if it is switched off)")
    removed_by("Artist hard cap:", rows, select_rows(data, stats, Params(ARTIST_HARD_CAP=10 ** 9)), P)
    removed_by("Label hard cap:", rows, select_rows(data, stats, Params(LABEL_HARD_CAP=10 ** 9)), P)
    if stats.has_groups:
        removed_by("Alias / sublabel merging:", rows, select_rows(data, stats_nog, P), P)

    head("TOP REMIXERS (who the remix records come from)")
    tally = {}
    for r in rows:
        for rid, who in r["remixers"]:
            tally.setdefault(rid, [who, 0])[1] += 1
    ranked = sorted(tally.items(), key=lambda kv: (-kv[1][1], kv[1][0]))
    n_remix = sum(1 for r in rows if r["remixers"])
    print("%d remix records from %d remixers; the top 25 account for %d of them." % (
        n_remix, len(ranked), sum(v[1] for _, v in ranked[:25])))
    print("(jungle-identified = %d+ masters and %.0f%%+; own and group numbers below)" % (
        P.REMIXER_MIN_JUNGLE, P.REMIXER_MIN_PCT))
    fmt = "%-26s %7s %9s %10s %6s"
    print(fmt % ("Remixer", "records", "own j/t", "group j/t", "share"))
    print("-" * 62)
    for rid, (who, n) in ranked[:25]:
        t, j, _ = stats.a_stats(rid)
        gt, gj, _ = stats.a_group_stats(rid)
        print(fmt % (who[:26], n, "%d/%d" % (j, t), ("%d/%d" % (gj, gt)) if rid in stats.a_gid else "-",
                     "%5.1f%%" % pct(gt, gj)))

    head("RECORDS BY YEAR (no comps / BH / reissues, versions <= %d)" % P.UI_MAX_VERSIONS)
    by_year = {}
    for r in rows:
        if not (r["comp"] or r["reiss"] or r["gtag"] == "B" or r["versions"] > P.UI_MAX_VERSIONS):
            by_year[r["year"]] = by_year.get(r["year"], 0) + 1
    run = 0
    print("%-6s %8s %12s" % ("Year", "records", "cumulative"))
    for y in sorted(by_year):
        run += by_year[y]
        print("%-6d %8d %12d" % (y, by_year[y], run))

    by_t = {}
    for r in rows:
        for t in r["tags"]:
            by_t[t] = by_t.get(t, 0) + 1
    print("\n" + textwrap.fill("Buckets (a record can be in several): " + ", ".join(
        "%s %d" % (label, by_t.get(t, 0)) for t, label in BUCKETS), W))

    head("WHY REMIXES ARE HIDDEN ON FIRST LOAD (remixes already skip the year range)")
    remixes_all = [r for r in rows if "remix" in r["tags"]]
    reasons = {}
    for r in remixes_all:
        why = default_view_reason(r, P)
        if why:
            reasons[why] = reasons.get(why, 0) + 1
    shown = len(remixes_all) - sum(reasons.values())
    print("%d of %d remix records are visible by default." % (shown, len(remixes_all)))
    for k in sorted(reasons, key=lambda k: -reasons[k]):
        print("  hidden, %s: %d" % (k, reasons[k]))

    comp_remixes = [r for r in remixes_all if r["comp"]]
    if comp_remixes:
        head("SAMPLE OF COMPILATION REMIXES (see if these still feel like hidden finds)")
        print("%d of the %d remix records are compilations (Various Artists samplers)." % (
            len(comp_remixes), len(remixes_all)))
        print("A comp collects many tracks by design, so it's far more likely than a single")
        print("to happen to include one track remixed by a name producer. Judge from these:")
        for r in comp_remixes[::max(1, len(comp_remixes) // 12)][:12]:
            line = "  %s  %s [%s]  %s" % (r["year_text"], r["title"], r["label"], "; ".join(r["remixes"])[:40])
            print(line if len(line) <= W else line[:W - 3] + "...")

    head("RESULT COUNTS: exported / visible on first load (years %d-%d)" % (P.UI_YEAR_MIN, P.UI_YEAR_MAX))

    def count(**over):
        Q = Params(**over)
        res = select_rows(data, stats, Q)
        return "%d / %d" % (len(res), sum(1 for r in res if in_default_view(r, Q)))

    def table(title, corner, cols, rows_, cell):
        print("\n" + title)
        print("%-12s" % corner + "".join("%-16s" % c[0] for c in cols))
        for rl, rv in rows_:
            print("%-12s" % rl + "".join("%-16s" % cell(rv, cv) for _, cv in cols))

    pcts = [("%.0f%%" % p, p) for p in (20.0, 30.0, 40.0)]
    table("Artist hard cap (rows) x artist share (columns)", "", pcts,
          [("cap %d" % h, h) for h in (6, 8, 10, 12)],
          lambda h, p: count(ARTIST_HARD_CAP=h, ARTIST_PCT=p))
    lp = [("%.0f%%" % p, p) for p in (50.0, 60.0, 70.0)]
    table("Label hard cap (rows) x label share (columns)", "", lp,
          [("cap %d" % h, h) for h in (10, 15, 25)],
          lambda h, p: count(LABEL_HARD_CAP=h, LABEL_PCT=p))
    table("Hard-cap share floor: the cap only bites at this jungle share or more", "floor",
          [("artists", "a"), ("labels", "l")], [("%.0f%%" % f, f) for f in (0.0, 2.0, 5.0, 10.0)],
          lambda f, k: count(ARTIST_HARD_MIN_PCT=f) if k == "a" else count(LABEL_HARD_MIN_PCT=f))

    def remix_count(**over):
        return "%d" % sum(1 for r in select_rows(data, stats, Params(**over)) if "remix" in r["tags"])

    table("Remix records: remixer needs N jungle masters (rows) and share (columns)", "",
          [("%.0f%%" % p, p) for p in (10.0, 20.0, 40.0)], [("%d+" % n, n) for n in (3, 5, 8)],
          lambda n, p: remix_count(REMIXER_MIN_JUNGLE=n, REMIXER_MIN_PCT=p))
    print("\nCurrent settings: %s" % count())
    pause()


if __name__ == "__main__":
    main()
