# -*- coding: utf-8 -*-
"""Builds tiny fake Discogs dumps (releases, artists, labels) that exercise every KR8 rule:
core artists/labels, aliases, sublabels, remixes, comps, BH, formats, versions, white labels...

Smoke test after changing any script (30 seconds instead of a 45 minute run):
    make a scratch folder, copy all KR8 scripts + this file into it, then
    python make_test_dumps.py && python 01_pre_filter.py && python 02_build_groups.py && python 04_build_dashboard.py
Expected: 65 records in the dashboard (60 visible on first load)."""
import gzip
from xml.sax.saxutils import escape as x

out = []


def artist_xml(aid, name, role="", tracks=""):
    return ("<artist><id>%d</id><name>%s</name><anv></anv><join></join><role>%s</role><tracks>%s</tracks></artist>"
            % (aid, x(name), x(role), x(tracks)))


def release(rid, title, artists, labels, styles, formats, released, master=None, tracks=None,
            rel_credits=None, videos=None, genres=("Electronic",)):
    """artists: [(id,name)]; labels: [(id,name,catno)]; formats: [(name,[descs])];
    tracks: [(pos,title,[(aid,name,role)])]; rel_credits: [(aid,name,role,tracks)]"""
    s = ['<release id="%d" status="Accepted">' % rid]
    s.append("<artists>%s</artists>" % "".join(artist_xml(a, n) for a, n in artists))
    s.append("<title>%s</title>" % x(title))
    s.append("<labels>%s</labels>" % "".join('<label name="%s" catno="%s" id="%d"/>' % (x(n), x(c), i) for i, n, c in labels))
    if rel_credits:
        s.append("<extraartists>%s</extraartists>" % "".join(artist_xml(a, n, r, t) for a, n, r, t in rel_credits))
    s.append("<formats>%s</formats>" % "".join(
        '<format name="%s" qty="1" text=""><descriptions>%s</descriptions></format>' % (
            x(n), "".join("<description>%s</description>" % x(d) for d in ds)) for n, ds in formats))
    s.append("<genres>%s</genres>" % "".join("<genre>%s</genre>" % g for g in genres))
    s.append("<styles>%s</styles>" % "".join("<style>%s</style>" % x(st) for st in styles))
    s.append("<country>UK</country>")
    if released is not None:
        s.append("<released>%s</released>" % released)
    if master:
        s.append('<master_id is_main_release="true">%d</master_id>' % master)
    tl = tracks or [("A1", "Track One", []), ("B1", "Track Two", [])]
    s.append("<tracklist>%s</tracklist>" % "".join(
        "<track><position>%s</position><title>%s</title><duration></duration>%s</track>" % (
            p, x(t), ("<extraartists>%s</extraartists>" % "".join(artist_xml(a, n, r) for a, n, r in ex)) if ex else "")
        for p, t, ex in tl))
    if videos:
        s.append("<videos>%s</videos>" % "".join(
            '<video src="%s" duration="300" embed="%s"><title>%s</title><description></description></video>' % (
                x(u), e, x(t)) for u, t, e in videos))
    s.append("</release>")
    out.append("".join(s))


V12 = ("Vinyl", ['12"', "33 \u2153 RPM"])
JUNGLE = ["Jungle"]
rid = [100000]


def nid():
    rid[0] += 1
    return rid[0]


# --- CoreGuy: 9 jungle masters on CoreLabel (hard cap 8 -> core artist; label core by share)
core = (1001, "CoreGuy")
corelab = (2001, "CoreLabel", "CL")
for i in range(9):
    release(nid(), "Core Tune %d" % i, [core], [(2001, "CoreLabel", "CL%03d" % i)], JUNGLE, [V12],
            "199%d-05-00" % (4 + i % 3), master=(10001 + i) if i < 5 else None,
            videos=[("https://www.youtube.com/watch?v=core%d" % i, "CoreGuy - Core Tune %d" % i, "true")])

# --- Alias of CoreGuy: 1 jungle master on TinyLabel (only core once aliases are merged)
release(nid(), "Alias Only Track", [(1002, "CoreGuy Alias")], [(2002, "TinyLabel", "TL001")], JUNGLE, [V12],
        "1995-01-00", master=20001)
# --- Obscure: kept ("small"), white label, with video whose title contains extra hyphens
release(nid(), "Hidden Gem", [(1003, "Obscure")], [(2002, "TinyLabel", "TL002")], JUNGLE,
        [("Vinyl", ['12"', "White Label"])], "1995-03-00",
        videos=[("https://www.youtube.com/watch?v=gem1", "Obscure - Hidden Gem - Dub Mix", "false")])

# --- TechnoGuy + HouseLabel: non-jungle artist and non-jungle label
for i in range(20):
    release(nid(), "House Thing %d" % i, [(1004, "TechnoGuy")], [(2003, "HouseLabel", "HL%03d" % i)], ["House"], [V12],
            "199%d-01-00" % (3 + i % 6), master=30000 + i)
for i in range(10):
    release(nid(), "Other House %d" % i, [(3000 + i, "House Act %d" % i)], [(2003, "HouseLabel", "HX%03d" % i)], ["House"],
            [V12], "1996-01-00", master=31000 + i)
release(nid(), "Techno Guy Goes Jungle", [(1004, "TechnoGuy")], [(2003, "HouseLabel", "HL999")], JUNGLE, [V12],
        "1995-06-00", master=32000)

# --- Sub Artist on a sublabel of CoreLabel (only excluded once labels are merged)
release(nid(), "Sub Label Jungle", [(1005, "Sub Artist")], [(2006, "CoreLabelSub", "CS001")], JUNGLE, [V12],
        "1996-02-00", master=40001)

# --- Jungle remixes on otherwise non-jungle records: Discogs lists the Jungle style for them
release(nid(), "House Anthem", [(1006, "HouseGuy")], [(2004, "HouseLabel2", "H2001")], ["House", "Jungle"], [V12],
        "1996-07-00", master=50001,
        tracks=[("A1", "House Anthem (Original)", []),
                ("B1", "House Anthem (CoreGuy Remix)", [(1001, "CoreGuy", "Remix")]),
                ("B2", "House Anthem (Mixed)", [(1006, "HouseGuy", "Mixed By")])],
        videos=[("https://www.youtube.com/watch?v=flip1", "HouseGuy - House Anthem", "true")])
release(nid(), "Release Level Remix", [(1007, "HouseGuy2")], [(2004, "HouseLabel2", "H2002")], ["Trance", "Jungle"], [V12],
        "1997-02-00", master=50002, rel_credits=[(1001, "CoreGuy", "Remix", "A2")],
        tracks=[("A1", "First", []), ("A2", "Second Track", []), ("B1", "Third", [])])
release(nid(), "Remix By Nobody Known", [(1008, "HouseGuy3")], [(2004, "HouseLabel2", "H2003")], ["House", "Jungle"], [V12],
        "1997-03-00", master=50003, tracks=[("A1", "X (Obscure Remix)", [(1003, "Obscure", "Remix")])])
release(nid(), "Unrelated Remix", [(1009, "PopAct")], [(2009, "PopLabel", "PL1")], ["Pop Rock"], [V12],
        "1999-03-00", master=50004, tracks=[("A1", "Y (Some Remix)", [(9000, "Random Remixer", "Remix")])])
# A remix well outside the default 1992-1998 year window: must still be visible on first load.
release(nid(), "Millennium Flip", [(1006, "HouseGuy")], [(2004, "HouseLabel2", "H2010")], ["House", "Jungle"], [V12],
        "2001-01-00", master=50010, tracks=[("A1", "Millennium Flip (CoreGuy Remix)", [(1001, "CoreGuy", "Remix")])])

# realistic filler so HouseLabel2 / HouseGuy are clearly non-jungle (jungle share well under 10%)
for i in range(30):
    release(nid(), "HouseGuy Filler %d" % i, [(1006, "HouseGuy")], [(2004, "HouseLabel2", "HF%03d" % i)], ["House"], [V12],
            "199%d-04-00" % (3 + i % 6), master=52000 + i)
for i in range(20):
    release(nid(), "HouseLabel2 Filler %d" % i, [(4000 + i, "Filler Act %d" % i)], [(2004, "HouseLabel2", "HG%03d" % i)], ["House"], [V12],
            "199%d-05-00" % (3 + i % 6), master=53000 + i)
# NOT tagged jungle, but remixed by a core jungle producer: must NOT be stored (no Jungle style = no jungle remix)
release(nid(), "Untagged Core Remix", [(1006, "HouseGuy")], [(2004, "HouseLabel2", "H2006")], ["House"], [V12],
        "1996-08-00", master=50006, tracks=[("A1", "Untagged (CoreGuy Remix)", [(1001, "CoreGuy", "Remix")])])
release(nid(), "Cassette Flip", [(1006, "HouseGuy")], [(2004, "HouseLabel2", "H2004")], ["House"],
        [("Cassette", [])], "1996-07-00", tracks=[("A1", "Z", [(1001, "CoreGuy", "Remix")])])
# release-level credit with a broken/odd tracks text (unresolvable)
release(nid(), "Odd Tracks Text", [(1006, "HouseGuy")], [(2004, "HouseLabel2", "H2005")], ["House", "Jungle"], [V12],
        "1998-01-00", master=50005, rel_credits=[(1001, "CoreGuy", "Remix [Extra]", "A1 to B2")])

# --- Compilations
release(nid(), "Jungle Sampler", [(194, "Various")], [(2005, "CompLabel", "CP1")], JUNGLE,
        [("Vinyl", ['12"', "Compilation"])], "2003-01-00", master=60001)
release(nid(), "Core Label Comp", [(194, "Various")], [(2001, "CoreLabel", "CLC1")], JUNGLE,
        [("Vinyl", ['12"', "Compilation"])], "1996-01-00", master=60002)

# --- Breakbeat hardcore
release(nid(), "Rave Tune", [(1010, "RaveGuy")], [(2010, "RaveLabel", "RV1")], ["Breakbeat", "Hardcore"], [V12], "1994-01-00", master=70001)
release(nid(), "Crossover Rave", [(1011, "CrossGuy")], [(2010, "RaveLabel", "RV2")], ["Breakbeat", "Hardcore"], [V12], "1994-05-00", master=70002)
release(nid(), "Crossguy Jungle", [(1011, "CrossGuy")], [(2011, "CrossLabel", "CR1")], JUNGLE, [V12], "1995-05-00", master=70003)
release(nid(), "Gabber Noise", [(1010, "RaveGuy")], [(2010, "RaveLabel", "RV3")], ["Breakbeat", "Hardcore", "Gabber"], [V12], "1994-01-00", master=70004)

# --- DnB
release(nid(), "Early DnB", [(1012, "DnB Guy")], [(2012, "DnBLabel", "DB1")], ["Drum n Bass"], [V12], "1994-01-00", master=80001)
release(nid(), "Late DnB", [(1012, "DnB Guy")], [(2012, "DnBLabel", "DB2")], ["Drum n Bass"], [V12], "1997-01-00", master=80002)

# --- formats that must not be stored
release(nid(), "Digital Only Jungle", [(1015, "Digi Guy")], [(2013, "DigiLabel", "DG1")], JUNGLE, [("File", ["MP3"])], "1995-01-00", master=90001)
release(nid(), "CDr Jungle", [(1016, "CDr Guy")], [(2013, "DigiLabel", "DG2")], JUNGLE, [("CDr", [])], "1995-01-00", master=90002)
release(nid(), "Acetate Jungle", [(1017, "Ace Guy")], [(2013, "DigiLabel", "DG3")], JUNGLE, [("Vinyl", ['12"', "Acetate"])], "1995-01-00")
release(nid(), "Cassette Jungle", [(1018, "Tape Guy")], [(2013, "DigiLabel", "DG4")], JUNGLE, [("Cassette", [])], "1995-01-00", master=90003)
release(nid(), "Real CD Jungle", [(1019, "CD Guy")], [(2013, "DigiLabel", "DG5")], JUNGLE, [("CD", ["Album"])], "1996-01-00", master=90004)

# A compilation containing a jungle remix: must be tagged remix AND stay hidden by default until
# "Include > Compilations" is checked (remixes only bypass the YEAR filter, not this one).
release(nid(), "Comp Flip Sampler", [(194, "Various")], [(2090, "SamplerLabel", "SM1")], JUNGLE,
        [("Vinyl", ['12"', "Compilation"])], "1995-06-00", master=200001,
        tracks=[("A1", "Comp Flip Sampler (CoreGuy Remix)", [(1001, "CoreGuy", "Remix")]),
                ("A2", "Other Track", [])])
# A remix pressed more than EXPORT_MAX_VERSIONS/UI_MAX_VERSIONS times: must be tagged remix AND stay
# hidden by default until "Max versions" is raised (remixes don't bypass the versions filter either).
for i in range(5):
    release(nid(), "Overpressed Flip", [(1006, "HouseGuy")], [(2091, "PressLabel", "PR%d" % i)], ["House", "Jungle"],
            [V12], "1995-07-00", master=200002,
            tracks=[("A1", "Overpressed Flip (CoreGuy Remix)", [(1001, "CoreGuy", "Remix")])])

# --- many versions of one master (8 > EXPORT_MAX_VERSIONS 6) and 3 versions (expandable group)
for i in range(8):
    release(nid(), "Popular One", [(1013, "Popular Guy")], [(2007, "PopLabel2", "PP%d" % i)], JUNGLE, [V12], "1995-01-00", master=91001)
for i in range(3):
    release(nid(), "Three Pressings", [(1020, "Triple Guy")], [(2014, "TripLabel", "TP%d" % i)], JUNGLE, [V12], "1995-0%d-00" % (i + 1), master=91002)

# --- master-less duplicates (collapse) and Unknown Artist white labels (must NOT collapse)
for i in range(2):
    release(nid(), "Same Record", [(1014, "Dup Guy")], [(2008, "DupLabel", "DP%d" % i)], JUNGLE, [V12], "1995-04-00")
for i in range(2):
    release(nid(), "Untitled", [(355, "Unknown Artist")], [(26, "White Label", "")], JUNGLE,
            [("Vinyl", ['12"', "White Label"])], "1995-08-00")

# --- pseudo-label "Not On Label" with 20 jungle releases by 20 different artists: must NOT become core
for i in range(20):
    release(nid(), "Selfrelease %d" % i, [(2000 + i, "Loner %d" % i)], [(27, "Not On Label (Loner %d Self-released)" % i, "")],
            JUNGLE, [V12], "1995-09-00", master=95000 + i)
release(nid(), "Selfrelease NOL", [(2050, "Loner X")], [(27, "Not On Label", "")], JUNGLE, [V12], "1995-09-00", master=95100)

# --- odd dates
release(nid(), "Approx Year", [(2060, "Guess Guy")], [(2061, "GuessLabel", "GG1")], JUNGLE, [V12], "199?", master=96001)
release(nid(), "Junk Year", [(2062, "Junk Guy")], [(2063, "JunkLabel", "JG1")], JUNGLE, [V12], "0000-00-00", master=96002)
release(nid(), "No Year", [(2064, "None Guy")], [(2065, "NoneLabel", "NG1")], JUNGLE, [V12], None, master=96003)

# --- reissue, mastermix, collab with a core artist
release(nid(), "Reissued Gem", [(2070, "Reissue Guy")], [(2071, "ReLabel", "RE1")], JUNGLE, [V12], "1995-01-00", master=97001)
release(nid(), "Reissued Gem", [(2070, "Reissue Guy")], [(2071, "ReLabel", "RE2")], JUNGLE, [("Vinyl", ['12"', "Reissue"])], "1995-01-00", master=97001)
release(nid(), "Jungle Mastermix Vol 1", [(2072, "Mix Guy")], [(2073, "MixLabel", "MM1")], JUNGLE, [V12], "1995-01-00", master=97002)
release(nid(), "Collab With Core", [(1003, "Obscure"), (1001, "CoreGuy")], [(2002, "TinyLabel", "TL003")], JUNGLE, [V12], "1995-11-00", master=97003)

# --- alias-as-remix-source pair: neither alias core alone, but the pair is (tested via group merge)
# main artist with alias remixing own track: "SelfRemix" (id 2080) remixed by alias 2081
for i in range(3):
    release(nid(), "Alias A Jungle %d" % i, [(2080, "Split Persona")], [(2082, "SPLabel", "SP%d" % i)], JUNGLE, [V12], "1995-01-00", master=98000 + i)
for i in range(3):
    release(nid(), "Alias B Jungle %d" % i, [(2081, "Persona Two")], [(2083, "SP2Label", "SQ%d" % i)], JUNGLE, [V12], "1995-01-00", master=98010 + i)
release(nid(), "Self Remix Case", [(2080, "Split Persona")], [(2084, "OtherLabel", "OL1")], ["Techno", "Jungle"], [V12], "1996-01-00", master=98100,
        tracks=[("A1", "Self Remix Case (Persona Two Remix)", [(2081, "Persona Two", "Remix")])])

# --- a generalist major label with 16 jungle-tagged masters among 400 others (3.8%) (label hard cap 15 hits it
#     unless config.LABEL_HARD_MIN_PCT > 3.8), and a mainstream artist with 9 jungle bootlegs among 300
for i in range(16):
    release(nid(), "Major Jungle %d" % i, [(3500 + i, "Minor Act %d" % i)], [(2500, "MegaMajor", "MM%03d" % i)], JUNGLE, [V12],
            "1995-02-00", master=99000 + i)
for i in range(400):
    release(nid(), "Major Pop %d" % i, [(3600 + i % 40, "Pop Act %d" % (i % 40))], [(2500, "MegaMajor", "MP%03d" % i)], ["Pop Rock"], [V12],
            "199%d-02-00" % (i % 9), master=99500 + i)
for i in range(9):
    release(nid(), "Star Bootleg %d" % i, [(2600, "MegaStar")], [(2601 + i, "Bootleg Label %d" % i, "BL1")], JUNGLE, [V12],
            "1996-03-00", master=99900 + i)
for i in range(300):
    release(nid(), "Star Hit %d" % i, [(2600, "MegaStar")], [(2620, "StarLabel", "SL%03d" % i)], ["Pop Rock"], [V12],
            "199%d-03-00" % (i % 9), master=98500 + i)

# A real Discogs master_id is one canonical release: it never covers two different titles.
# Reusing a master id across an intentional multi-pressing group is fine as long as the title
# matches; catching a *different* title on a reused id is what actually catches ID collisions.
import re as _re
from collections import defaultdict as _dd
_by_master = _dd(set)
for _r in out:
    _m = _re.search(r'<master_id[^>]*>(\d+)</master_id>', _r)
    if _m:
        _t = _re.search(r'<title>(.*?)</title>', _r)
        _by_master[int(_m.group(1))].add(_t.group(1) if _t else "?")
_bad = dict((k, v) for k, v in _by_master.items() if len(v) > 1)
if _bad:
    raise SystemExit("Fixture bug: master id(s) shared by releases with different titles: %s" % _bad)

# A label whose OWN share alone should trigger the "mid" tier (9/20 = 45% >= LABEL_MID_PCT 40%),
# merged with a large non-jungle sublabel that dilutes the GROUP share well under 40% (9/50 = 18%).
# Regression check for 03_analyze_thresholds.py's "show()": the printed share must reflect whichever
# numbers actually decided the verdict (here, its own 45%), not just always the group's.
for i in range(9):
    release(nid(), "Solo High Share Jungle %d" % i, [(2710 + i, "Solo Act %d" % i)], [(2700, "SoloHighShare", "SH%02d" % i)],
            JUNGLE, [V12], "1995-01-00", master=200100 + i)
for i in range(11):
    release(nid(), "Solo High Share Filler %d" % i, [(2730 + i, "Solo Filler %d" % i)], [(2700, "SoloHighShare", "SF%02d" % i)],
            ["House"], [V12], "1996-01-00", master=200120 + i)
for i in range(30):
    release(nid(), "Solo High Share Sub Filler %d" % i, [(2760 + i, "Sub Filler %d" % i)], [(2701, "SoloHighShareSub", "SS%02d" % i)],
            ["House"], [V12], "1996-01-00", master=200150 + i)

with gzip.open("discogs_20260901_releases.xml.gz", "wb") as f:
    f.write(b'<?xml version="1.0" encoding="UTF-8"?>\n<releases>\n')
    f.write("\n".join(out).encode("utf-8"))
    f.write(b"\n</releases>\n")
print("releases written:", len(out))

# ------------------------------------------------------------------ artists dump
art = ["<artists>"]
art.append('<artist><id>1001</id><name>CoreGuy</name><realname>C. Guy</realname><aliases><name id="1002">CoreGuy Alias</name></aliases><groups><name id="5555">Some Group</name></groups></artist>')
art.append('<artist><id>1002</id><name>CoreGuy Alias</name><aliases><name id="1001">CoreGuy</name></aliases></artist>')
art.append('<artist><id>2080</id><name>Split Persona</name><aliases><name id="2081">Persona Two</name></aliases></artist>')
art.append('<artist><id>2081</id><name>Persona Two</name><aliases><name id="2080">Split Persona</name></aliases></artist>')
art.append('<artist><id>1003</id><name>Obscure</name><profile>no aliases</profile></artist>')
art.append('<artist><id>355</id><name>Unknown Artist</name><aliases><name id="1003">Obscure</name></aliases></artist>')  # placeholder must not link
# oversize group: person with 50 aliases + one interesting artist (1013)
big = "".join('<name id="%d">Alias %d</name>' % (7000 + i, i) for i in range(50)) + '<name id="1013">Popular Guy</name>'
art.append('<artist><id>6999</id><name>Big Aliaser</name><aliases>%s</aliases></artist>' % big)
for i in range(200):
    art.append('<artist><id>%d</id><name>Filler %d</name></artist>' % (8000 + i, i))
art.append("</artists>")
with gzip.open("discogs_20260901_artists.xml.gz", "wb") as f:
    f.write(("\n".join(art)).encode("utf-8"))

# ------------------------------------------------------------------ labels dump
lab = ["<labels>"]
lab.append('<label><id>2001</id><name>CoreLabel</name><contactinfo>x</contactinfo>'
           '<sublabels><label id="2006">CoreLabelSub</label></sublabels></label>')
lab.append('<label><id>2006</id><name>CoreLabelSub</name><parentLabel id="2001">CoreLabel</parentLabel></label>')
# a mega parent with 60 sublabels, one of them interesting (2007) -> dissolved
subs = "".join('<label id="%d">Sub %d</label>' % (9000 + i, i) for i in range(60)) + '<label id="2007">PopLabel2</label>'
lab.append('<label><id>5000</id><name>Mega Corp</name><sublabels>%s</sublabels></label>' % subs)
lab.append('<label><id>26</id><name>White Label</name><sublabels><label id="2002">TinyLabel</label></sublabels></label>')  # pseudo: must not link
lab.append('<label><id>2700</id><name>SoloHighShare</name><sublabels><label id="2701">SoloHighShareSub</label></sublabels></label>')
lab.append('<label><id>2701</id><name>SoloHighShareSub</name><parentLabel id="2700">SoloHighShare</parentLabel></label>')
lab.append("</labels>")
with gzip.open("discogs_20260901_labels.xml.gz", "wb") as f:
    f.write(("\n".join(lab)).encode("utf-8"))
print("artists / labels dumps written")
