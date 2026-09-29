# -*- coding: utf-8 -*-
"""KR8 settings. Every script imports this file.

Section A only matters for 01_pre_filter.py (changing it means the ~45 min re-run).
Section B is applied instantly by 03_analyze_thresholds.py / 04_build_dashboard.py.
"""

# ------------------------------------------------------------------ files
# None auto-detects the newest matching discogs_YYYYMMDD_<kind>.xml.gz already in this folder
# (01_pre_filter.py / 02_build_groups.py will also check data.discogs.com and offer to open it in a
# browser if nothing is found). Set a literal filename instead to pin one specific dump.
RELEASES_XML = None
ARTISTS_XML = None    # 02_build_groups.py only
LABELS_XML = None     # 02_build_groups.py only
DB_FILE = "jungle_gems_prefilter.db"
CSV_FILE = "jungle_hidden_gems.csv"
HTML_FILE = "jungle_hidden_gems_dashboard.html"


# ============================================================================
# A. 01_pre_filter.py: what goes into the DB
# ============================================================================

# Year window stored per genre tag.
#   J = tagged Jungle          D = tagged Drum n Bass (not Jungle)
#   B = clean Breakbeat Hardcore
# Records without one of these styles are never stored: a jungle remix on an otherwise
# non-jungle record makes Discogs list the Jungle style.
DB_YEARS = {"J": (1992, 2006), "D": (1993, 1995), "B": (1993, 1995)}

# Breakbeat Hardcore only counts if none of these styles is present.
BH_NOISE_STYLES = ("house", "happy hardcore", "euro house", "gabber", "bleep")

# Placeholders that must never count as "core" (ids AND lowercase names are checked,
# so a wrong id here is caught by the name). They are never tallied at all.
# 03_analyze_thresholds.py prints which ids carry these names in your data (DATABASE CHECKS).
NON_ARTIST_IDS = (194, 355, 118760)   # Various, Unknown Artist, No Artist
NON_ARTIST_NAMES = ("various", "unknown artist", "no artist")

# Pseudo-labels (lowercase prefixes). Without this, "White Label" and
# "Not On Label (...)" would hit the label hard cap and silently delete
# every white label and self-release.
PSEUDO_LABEL_PREFIXES = ("not on label", "white label", "no label", "unknown",
                         "private release", "self-released", "self released",
                         "test pressing")

# Formats that already signal obscurity by themselves: excluded.
OBSCURE_FORMATS = ("acetate", "lathe cut", "cdr", "cd-r")


# ============================================================================
# B. Applied instantly (03_analyze_thresholds.py / 04_build_dashboard.py)
# ============================================================================

# A record is dropped if ANY of its artists / labels is "core".
ABS_MIN = 4               # minimum jungle masters for the percentage rules
ARTIST_HARD_CAP = 8       # this many jungle/DnB masters: core, whatever the share
ARTIST_HARD_MIN_PCT = 10.0  # ...but only at this jungle share or more. 10 = NONJUNGLE_PCT: an artist the
                            # tool calls "non-jungle" is never dropped by volume alone; their jungle-tagged
                            # records are remixes / bootlegs, i.e. what you're digging for (0 = share-blind)
ARTIST_PCT = 30.0         # ABS_MIN+ masters and this share of total output: core
LABEL_HARD_CAP = 15
LABEL_HARD_MIN_PCT = 5.0  # keeps generalist majors (Ariola 0.1%, PolyGram 0.2%, ...) in play;
                          # 0.0 goes back to share-blind (also excludes majors' rare crossover jungle tracks)

LABEL_MID_ABS = 8         # middle tier: 8+ masters and 40%+
LABEL_MID_PCT = 40.0
LABEL_PCT = 60.0

# Per-name exceptions for calls the numbers can't make. Entries are names (case-insensitive, Discogs
# "(2)" suffixes ignored; only artists / labels with stored records can be matched by name) or Discogs ids. Jungle-adjacent (breakcore, IDM, happy hardcore, ...) counts as
# jungle here, so the numbers already drop labels like Shockout or Blue Planet; the lists fix the rest.
#   CORE_*: always dropped as core, together with the rest of their alias / sublabel group.
#           Slipmatt is a hardcore artist (3% jungle share): the artist share floor above would let him in.
#   KEEP_*: never dropped as core on their own numbers (their group members are still judged as before).
CORE_ARTISTS = ("Slipmatt",)
CORE_LABELS = ()
KEEP_ARTISTS = ()
KEEP_LABELS = ()

# Merge aliases / sublabels (needs 02_build_groups.py). Merging only ever adds
# exclusions: an entity is core if it OR its group is core.
USE_GROUPS = True
MAX_ARTIST_GROUP = 40     # bigger alias groups are treated as Discogs noise
MAX_LABEL_GROUP = 40

# A "jungle remixer" (remix source): this many jungle masters AND this share.
REMIXER_MIN_JUNGLE = 5
REMIXER_MIN_PCT = 20.0

# "non-jungle artist / label" tag: jungle share below this.
NONJUNGLE_PCT = 10.0

# What ends up in the dashboard (the dashboard filters further, live).
# These windows can only narrow what is in the DB (DB_YEARS above); widening them
# needs a 01_pre_filter.py re-run.
EXPORT_YEARS = {"J": (1992, 2006), "D": (1993, 1995), "B": (1993, 1995)}
EXPORT_MAX_VERSIONS = 6   # Discogs versions of the master (all formats)
BH_REQUIRE_JUNGLE_LINK = True   # BH-only rows need a jungle/DnB master by the same artist, or a remix
EXCLUDE_TITLE_WORDS = ("mastermix",)

# Dashboard start state.
UI_YEAR_MIN = 1992
UI_YEAR_MAX = 1998
UI_MAX_VERSIONS = 4
