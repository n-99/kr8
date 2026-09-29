KR8 v3
======

[kɹeɪt] | [kʁaxt]. Made by Nine99 (IG: jets.am).
Vibecoded with Qwen3.7-Plus and Sonnet 5, 2026-09-29.


The Licence (RTV 002):
----------------------
You're given the Source, Direct - all rights are reversed, do what thou wilt.

All that is free, it seems,
Like a dream within your dreams.


Description
-----------
Finds overlooked jungle / early drum & bass / breakbeat hardcore records (vinyl and CD) in a
Discogs data dump: small artists and labels, non-jungle artists and labels, and remixes by
jungle producers on non-jungle records ("remixes"). Output: a CSV and one offline HTML dashboard.
A design blueprint is given as Markdown file.


System Requirements
-------------------
- Python 3.8+ (compatible with Windows 7)
- lxml - run `pip install lxml` to install.

Running any of these scripts creates a `__pycache__` folder next to them, holding compiled copies of
`config.py` and `common.py` (`.pyc` files). That's normal CPython behavior for anything that gets
`import`-ed rather than run directly, not specific to this project, and safe to delete any time; Python
just rebuilds it next run. It doesn't get cleaned up automatically because Python has no way to know
you're done with a folder of scripts.


Getting the Discogs dumps
-------------------------
Download `discogs_YYYYMMDD_releases.xml.gz` (about 10 GB) into the scripts' folder, plus `..._artists.xml.gz`
and `..._labels.xml.gz` if you want alias / sublabel merging. Dumps are dated the 1st of each month and live
in one folder per year: https://data.discogs.com/?prefix=data%2F2026%2F (swap in the year). In 2026 every
month's dump was posted the same day (August one day late), except January's, which came two weeks late.

Nothing to configure: the scripts pick the newest matching file already in the folder (`config.py`
RELEASES_XML / ARTISTS_XML / LABELS_XML = None; put a literal filename there to pin one dump). If a
file is missing, `01_pre_filter.py` and `02_build_groups.py` check the real listing on data.discogs.com (skipped
silently without internet), say which file to get, and ask `[y/N]` whether to open the download page in your
browser. `01_pre_filter.py` does this before touching the database, so a missing file can't wipe a good one.
If a newer dump than the one you have looks available, they print a note and carry on with what you have.


Run order
---------
- `01_pre_filter.py`        ~50-55 min, once per dump. Streams the releases dump into `jungle_gems_prefilter.db`.
- `02_build_groups.py`      optional, once per dump (10-30 min). Needs the artists and labels dumps (ideally
                          the same date as the releases dump). Merges aliases and sublabels so producers
                          can't hide behind them.
- `03_analyze_thresholds.py` ~1 min. Who sits on the edge of each threshold, which records come back if the
                          artist hard cap / label hard cap / alias merging is switched off (sampled), the top
                          remixers, why default-hidden remixes are hidden, records per year, and result
                          counts for grids of settings. Edit `config.py`, run again.
- `04_build_dashboard.py`    seconds. Writes `jungle_hidden_gems.csv` and `jungle_hidden_gems_dashboard.html`.

`config.py` holds every setting. Section A needs the re-run of step 1, section B is instant.
Obsolete (delete): `extract_gems_python.py`, `extract_dashboard_data.py`, `generate_html.py`.
`make_test_dumps.py` builds tiny fake dumps for a 30 s smoke test after code changes.


Rules
-----
* Stored: physical (vinyl / CD) only; CD-R, acetate and lathe cut are excluded.
  Jungle 1992-2006, DnB-only 1993-1995, clean Breakbeat Hardcore 1993-1995 (config.DB_YEARS).
  Records without one of these styles are never stored: when a jungle producer remixes a track on an otherwise
  non-jungle record, Discogs lists the Jungle style, so an untagged record with a remix credit is not a jungle
  remix. (A DB built by an earlier version may still hold such rows, marked gtag F; everything ignores them.)
* Counts are per distinct master (master-less releases count once each). Every release-level artist and label
  is counted, not just the first. Jungle/DnB numerator: all years, all formats, no compilations.
  Breakbeat Hardcore has its own column and never makes anyone "core".
* Various / Unknown Artist / No Artist and pseudo-labels (Not On Label, White Label, ...) are never counted,
  so they can't become core and hide every white label.
* Core artist: 8+ jungle masters, or 4+ and 30% of their output. Core label: 15+, or 8+ and 40%, or 4+ and 60%.
  The hard caps only bite above a jungle share: artists 10% (ARTIST_HARD_MIN_PCT, the same line the tool uses for
  "non-jungle artist"), labels 5% (LABEL_HARD_MIN_PCT). So Snoop Dogg or Ariola, with a handful of jungle-tagged
  records among hundreds, stay in: those records are remixes / bootlegs, which is what you're digging for. A real
  jungle artist or label (100% share) is still core at the cap. Set a floor to 0 to make a cap share-blind.
  Jungle-adjacent (breakcore, IDM, happy hardcore, ...) counts as jungle. The numbers already drop labels like
  Shockout or Blue Planet; where a floor would let a hardcore artist like Slipmatt through, list him in
  CORE_ARTISTS (or CORE_LABELS) in `config.py`: dropped as core, together with his aliases / sublabels.
  KEEP_ARTISTS / KEEP_LABELS do the opposite for an entity the numbers wrongly drop. Entries are names (only
  entities with stored records match by name) or Discogs ids.
  A record is dropped if ANY of its artists or labels is core (compilations: label only).
  With groups loaded, an entity is core if it OR its group is core (merging never rescues anyone).
* Remix (tag) = a stored (so Jungle-tagged) record, not itself a compilation, with a Remix credit by a
  jungle-identified remixer (5+ jungle masters and 20%+ of output) who is not the record's own artist
  or an alias of them. A compilation's remix credit is still shown in the "Jungle Remix Highlight"
  column (it's real), it just doesn't grant the remix tag or bucket: a Various Artists sampler collects
  many tracks by design, so it's far likelier than a single to happen to include one by a name producer,
  which isn't the same kind of find as a jungle remix hiding on an otherwise ordinary release. Remixers come only from Discogs credits, never from track titles.
  Both track-level and release-level credits are read; release-level ones name tracks in a free-text field,
  which is only used to look up the track title for display.
* Reissue / Repress / Remastered on any release of the master marks it reissued (hidden by default).
  Versions = releases of the master in the whole dump, all formats.
* Tags: `remix`, `non-jungle artist` / `non-jungle label` (group jungle share under 10%), otherwise `small act`.

`03_analyze_thresholds.py`'s borderline tables show whichever share actually decided the verdict: an entity's
own share if that alone was enough, otherwise (for a `group-...` verdict) the merged group's share. Don't
read the printed "share" as always being the group's; it's whichever number the status next to it used.


Dashboard
---------
Year range, max versions, the four tag buckets, compilations (ignore the year range), breakbeat hardcore,
reissued, white label only, YouTube only, and star marks (wanted / seen, kept in the browser). Start state:
1992-1998, versions <= 4, no comps / BH / reissues (config.UI_*). Remixes ignore the year range too, same as
compilations: the remix is the point, not the year of the record it's hiding on. Search also matches other
pressings' cat#s.
YouTube stays plain links (file:// has no Referer, embeds give error 153).


Things worth checking on the first real run
-------------------------------------------
* `03_analyze_thresholds.py` opens with DATABASE CHECKS (no SQL needed): records stored per genre, how many remix
  credits are track-level vs release-level, and which ids the placeholder artists (Various, ...) have.
* build_groups prints "WARNING: no links found" if the alias / sublabel tag names in your dump differ from
  `<aliases><name id>`, `<sublabels><label id>`, `<parentLabel id>`.


Quirks that still matter
------------------------
* `<released>` can be "199?" or "0000-00-00": "199?" is stored as 1995 with a `?` shown, unknown years are dropped.
* Console is cp1252 on Windows: every script forces UTF-8 output.
* Discogs names carry "(2)" suffixes; they are stripped for display only.
* Case-differing names for one id: everything groups by id.
