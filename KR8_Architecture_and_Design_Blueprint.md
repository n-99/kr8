# KR8 — Architecture and Design Blueprint

## About this document

This is a design blueprint, not a changelog and not a user manual. `ReadMe.md` covers how to
run the tool. The source files (`config.py`, `common.py`, `01_pre_filter.py`, `02_build_groups.py`,
`03_analyze_thresholds.py`, `04_build_dashboard.py`, `make_test_dumps.py`) are the implementation.
This document explains the *shape* of the system and the *reasoning* behind it, at a level that
should let a reader — human or LLM — do any of the following without needing to reverse-engineer
intent from code alone:

- Continue developing this exact tool (fix bugs, add features, recalibrate thresholds).
- Extract the underlying pattern and build a generic version of it for an unspecified domain.
- Build a new tool for a *specific* different domain (a different catalog, a different genre or
  category, a different notion of "obscure" or "overlooked") using this one as a template.

It is split into two parts on purpose:

- **Part 1 — Generic Architecture** describes the pattern in the abstract: the problem being
  solved, the pipeline shape, the statistical model, and the engineering pitfalls that were
  designed around. Nothing in Part 1 assumes the reader knows or cares what jungle music is.
- **Part 2 — Domain Instantiation: Jungle / Discogs** describes how that generic pattern was
  filled in for this specific case: which catalog, which category, which exact numbers, and why
  each number is what it is. Nothing in Part 2 is needed to understand Part 1.

A reader who only wants to keep working on KR8 as-is needs both parts. A reader who wants to
build something unrelated only needs Part 1 (plus the worked example at the end of it). A reader
who wants to build a close cousin (a different music genre, a different discography site) needs
Part 1 for the pattern and Part 2 as a fully worked example of applying it.

This document does not describe visual/cosmetic choices (colors, fonts, layout) in the generated
HTML page — those are ordinary front-end code, adequately self-explanatory by reading
`04_build_dashboard.py`'s `PAGE` template directly, and not part of the architecture.

---

# Part 1 — Generic Architecture

## 1.1 The problem this pattern solves

Given a very large, publicly maintained catalog of creative works (far too large to hold in
memory or re-scan casually — think tens of millions of entries, tens of gigabytes), where each
work is tagged with one or more categories and attributed to one or more creators and
publishers, find the subset of works that:

1. Belong to a target category (or small set of related categories), and
2. Were **not** produced by a creator or publisher who is already a well-established, prolific
   name within that category — because a well-established name's output is, by definition, not
   overlooked, however good it is.

Additionally, surface a secondary, related class of interesting works: items that do **not**
carry the target category tag themselves, but that carry a documented **contribution credit**
(a remix, a feature, an edit, a guest verse — any "additional-contributor" credit type the
catalog tracks explicitly) from someone who is independently established within the target
category. These are "crossovers" — an established name's fingerprint on something outside their
main scene, which is often exactly the kind of curiosity a collector or researcher wants
surfaced, precisely because it's unexpected.

The output is a browsable, personal reference artifact: something a human can open, filter,
sort, mark up with personal notes ("seen this", "want this"), and revisit — not just a one-shot
report.

## 1.2 Pipeline shape

The pattern is a four-stage pipeline. Each stage exists because the one before it makes the next
one tractable — the expensive stage happens once and produces something small and fast; every
later stage operates on that small, fast artifact instead of the original huge source.

| Stage | Cost | Frequency | Purpose |
|---|---|---|---|
| 1. Ingest | Very high (a full streaming pass over the entire source, order of an hour) | Once per source refresh | Filter the source down to a small local database of candidate works, while *also* computing aggregate per-creator and per-publisher statistics across the **entire** source (not just the filtered subset) |
| 2. Resolve identities (optional) | High, but less than stage 1 | Once per source refresh | Merge creator aliases and publisher sub-imprints into groups, using a *separate* identity-relationship source, so statistics aren't diluted across fragmented identities |
| 3. Calibrate | Instant (well under a second per query against the small database) | As often as needed | Let a human inspect borderline classification calls by name, sample what each rule removes, and sweep grids of threshold combinations, so classification boundaries can be tuned by informed inspection rather than guesswork |
| 4. Select & present | Instant | As often as needed | Run the final classification once, and generate both a structured export (for spreadsheets, further processing) and an interactive local browsing artifact from the exact same result set |

The key efficiency insight is in stage 1: because the source is too large to scan more than
once practically, everything that *might* later be useful for calibration (broader category and
date windows than the "default" view, raw provenance strings, computed duplicate/edition counts)
should be captured during that one pass, even if it isn't used immediately. Re-scanning the
source to add one more captured field is exactly the kind of expensive operation this
architecture exists to avoid. Anything that can instead be decided at stage 3 or 4 — because it
only needs to slice data already captured in stage 1 — should be deferred there, where it's free
to change your mind.

## 1.3 Data model

Four core entity types recur in this kind of catalog, regardless of domain:

- **Works** — the individual catalog entries being filtered. A work may have a **canonical work
  identifier** shared by several catalog entries that represent the same underlying creative
  output through different editions, pressings, or reissues (see §1.5).
- **Creators** — individual attributed authors/performers/artists of a work. A work can have
  more than one.
- **Publishers** — the entity that issued or distributed the work (a label, imprint, studio,
  publisher). A work can have more than one (co-releases).
- **Contribution credits** — a documented, typed credit distinct from primary authorship: a
  specific person did a specific *kind* of thing (remixed, edited, mastered, featured on) a
  specific work or a specific part of it. These are the raw material for the "crossover" signal
  in §1.7.

Two further catalog conventions matter a great deal and need explicit handling (§1.8):
**placeholder identifiers** (a real, exact catalog value that stands in for "not applicable" or
"not known," e.g. "Various", "Unknown") and **pseudo-publisher strings** (label-name text that
means "there is no real publisher," e.g. "self-released", "no label").

## 1.4 The core/non-core classification model

This is the central statistical judgment call the whole system makes, repeated once per creator
and once per publisher: *is this entity already an established name within the target
category?*

Two raw numbers are available for any entity: how many of their works are tagged in the target
category (call it **count**), and what fraction of their **total** output (every category, not
just the target one) that represents (call it **share**). Neither number alone is safe to
threshold on:

- **Count alone** is unsafe because a prolific creator from a *different* field who happens to
  have a handful of works tagged in the target category — an official remix, a novelty
  crossover, a widely-circulated unofficial edit — can accumulate a nontrivial absolute count
  purely by being enormously prolific overall, while that handful represents a fraction of a
  percent of their real output. Excluding them on count alone throws away exactly the kind of
  interesting crossover material described in §1.1, on the mistaken assumption that volume
  implies belonging to the scene.
- **Share alone** is unsafe in the opposite direction: a genuinely tiny, dedicated participant
  whose entire output is three works, all tagged in the target category, is 100% "in-genre" by
  share, but is not an established, well-known name — excluding entities purely by share
  wrongly classifies exactly the obscure participants this tool exists to surface.

The resolved model combines both numbers, plus a **floor**: the count-based rule is only allowed
to fire once the share also clears a minimum threshold. In pseudocode:

```
is_core(count, share):
    if count >= HARD_CAP and share >= HARD_CAP_MIN_SHARE:
        return "hard"                      # prolific AND meaningfully specialized: established
    if count >= MIN_ABSOLUTE and share >= MID_SHARE:
        return "mid_tier_rule"             # optional graduated tier(s); see below
    if count >= MIN_ABSOLUTE and share >= HIGH_SHARE:
        return "share_rule"                # majority of output is in-genre: established
    return None                            # not established: eligible to be surfaced
```

`HARD_CAP_MIN_SHARE` is the piece most easily left out by mistake, and its absence is a common
source of exactly the failure mode described above (prolific outsiders wrongly excluded). Setting
it to 0 makes the hard-cap rule share-blind, which is sometimes the desired behavior for a
publisher-type entity if a domain's data shows that even a very small share of a huge publisher's
catalog still represents meaningful, worth-surfacing overlap — the floor's value is itself a
per-domain judgment call, calibrated with the tool in §1.9, not a universal constant.

One or more middle tiers (lower absolute count, but a very high share) can be added for entities
whose output is small in absolute terms but overwhelmingly specialized — a small operation that
puts out almost nothing else. Whether that's "obscure and dedicated" (keep) or "small but
established within its niche" (exclude) is a domain-specific judgment call; the model supports
either by tuning where the tiers sit.

**Group-aware verdicts.** Once creator/publisher identities are merged into groups (§1.6), the
classification above runs twice: once on the entity's own numbers, once on its merged group's
numbers. The entity is core if *either* verdict fires. This direction only — merging can only add
exclusions, never remove one an entity already earned on its own numbers, and never rescue an
entity whose own numbers alone say it's established just because its alias group's numbers look
smaller (which would be backwards: an established name doesn't become obscure because it also
has minor aliases).

**Manual overrides.** No purely numeric model resolves every real-world case correctly — genre
and scene boundaries are matters of human judgment, not just statistics, and some entities will
sit exactly on a line the numbers can't see (see §2.6 for two concrete examples). The
architecture should include two named override lists per entity type: one that always treats a
listed entity as established (core) regardless of its numbers, and one that always protects a
listed entity from being classified as established regardless of its numbers. A "force-core"
listing should extend to the rest of that entity's merged identity group (if it's core, its
aliases are too); a "force-keep" listing should apply only to the named entity's own verdict, not
rescue other members of its group that independently earn a core verdict.

## 1.5 Deduplication: canonical work identity

Large catalogs routinely contain many near-duplicate entries for the same underlying creative
work — different pressings, editions, territories, or remaster passes of one release. Counting
raw catalog entries (rather than distinct *works*) inflates every statistic derived from them:
a creator's true output looks larger than it is, and a single popular work can appear many times
in a result list.

The fix is to group by a canonical work identifier whenever the source provides one. When it
doesn't (common for the most obscure, least-curated entries — exactly the ones this tool cares
about most), fall back to a composite key built from creator + normalized title + publisher, so
that duplicate manual entries of an unlinked work still collapse into one group instead of
appearing as unrelated duplicates. A work with no identifier and no duplicate match falls back
to its own raw entry id as a last resort, so it's still represented as its own single-member
group.

The number of catalog entries collapsed into one canonical work group is itself a useful
signal, separate from category and creator/publisher classification: a work re-pressed or
re-issued many times has likely already had significant commercial circulation, which cuts
against "overlooked." This count is worth exposing as a further, independently adjustable
filter (see §1.7's presentation layer) rather than baking a fixed cutoff into the core
classification.

## 1.6 Identity resolution (alias / sub-imprint merging)

Creators in many creative fields — and especially in underground or DIY scenes — commonly
release work under numerous different names: stylistic conventions, contractual reasons, or
simply prolific experimentation all encourage it. Publishers similarly often operate a
constellation of sub-imprints under one parent organization. Without resolving these into
groups, a creator who has genuinely produced, say, forty target-category works split evenly
across ten aliases at four each will look like ten separate small, obscure entities to the
count/share model above — none crossing the hard-cap threshold individually. This is a real
false negative: the model should recognize this as one prolific, established participant, not
ten obscure ones.

The general technique is a **union-find** (disjoint-set) merge: read a *second*, independent
source that documents alias and parent/child relationships between identifiers (most catalog
sites publish creator and publisher identity records separately from the works themselves,
exactly for this purpose), and union every pair of related identifiers into one group. Sum each
group's underlying statistics, and re-run the count/share classification on the summed numbers
as well as on each member's own numbers (§1.4).

**A group-size ceiling matters.** In practice, some resulting groups will be enormous — hundreds
or thousands of members. These tend to be one of two things: (a) a genuinely huge publisher
conglomerate, where merging adds no new information because the parent organization is already
unambiguously established regardless, or (b) noise in the identity-relationship source itself —
an overly broad or spurious link that chains together many otherwise-unrelated identifiers under
one incorrect group. Dissolving (not merging) any group above a chosen size ceiling avoids
letting a single bad link contaminate the shared statistics of many unrelated small entities.
This ceiling is a heuristic, tuned by inspecting the actual dissolved and kept groups on the real
data (via the calibration tool, §1.9) — expect to look at the biggest few kept and dissolved
groups by name and sanity-check that the split looks right for the specific source being used.
It will occasionally, and acceptably, fail to merge a genuinely large legitimate alias network
that happens to exceed the ceiling; that is a preferable failure mode to admitting identity-graph
noise.

## 1.7 The crossover / contribution-credit signal

Beyond works natively tagged in the target category, works carrying a documented contribution
credit from an independently-established target-category participant are a distinct, valuable
class of find. Two design points here matter enough to spell out, because getting them wrong
produces a signal that looks plausible but is actually broken or useless:

**Avoid circular identification.** "Independently established" must be computed from the
credited contributor's *own*, separately-tagged body of work — their own primary-creator
catalog, run through exactly the same count/share model as §1.4 — never from the pool of
crossover candidate works being evaluated. If a contributor's established-in-category status
were instead inferred from the crossover credits themselves, every candidate would trivially
"prove" its own contributor is established, and the filter could never reject anything.

**Contribution credit is a distinct field, not inferred from titles.** The catalog's own
structured contributor-credit metadata (a named credit field on the work or on an individual
track/part within it) is the only reliable source for this signal. Free-text titles that
happen to mention a contribution (a title containing a parenthetical credit, say) are far too
inconsistently formatted across a large catalog to parse reliably, and should not be used as a
primary detection method — at best as a low-confidence fallback for display purposes once a
credit has already been found through the structured field by some other means (e.g., using a
free-text field to identify *which part* of a work a known, structured credit applies to, which
is a narrower and safer use of free text than detecting the credit's existence from it).

**Scope the search correctly, or drown in false positives.** Whether it's worth searching for
crossover credits on works that do *not* already carry the target category tag depends entirely
on how the source catalog's tagging convention behaves. If the convention is such that any
credited contribution from a target-category contributor already causes the *enclosing* work to
inherit the target category tag (common in track/album-style catalogs, where a single track's
metadata can promote the whole release's classification), then a genuinely untagged work with a
"hidden" target-category contribution essentially never occurs — every real case has already
been tagged by the source itself. Searching untagged works for this pattern anyway, in that
situation, produces overwhelming numbers of false candidates for negligible real signal, because
almost every credit that superficially matches turns out to belong to an untagged work for
unrelated reasons. Establishing which behavior a given source catalog exhibits, and restricting
the crossover search accordingly, is a necessary calibration step before trusting this signal at
all — it is not safe to assume either way without checking.

**Compilations dilute this signal.** A multi-contributor anthology (a various-artists
compilation) mechanically has a much higher chance of incidentally including a credit from an
established contributor simply because it aggregates many works' worth of tracks — a base-rate
effect, not a discovery. In practice, most "the compilation contains an established-name credit"
hits are ordinary genre samplers where that's the expected norm, not a surprise. The credit
information is still worth recording and displaying (it's real and can be interesting context),
but it should not by itself qualify a compilation for the "crossover discovery" classification
the way it would for a single-work release credited to one specific, otherwise-unestablished
creator.

**A credit from the work's own listed creator, under an alias, is not a crossover.** Resolve the
credited contributor's identity through the same alias-group mapping (§1.6) as the work's primary
creator before comparing them, so a self-remix under a different name isn't mistaken for an
external crossover.

## 1.8 Placeholder identifiers and pseudo-publishers

Large collaboratively-maintained catalogs use fixed sentinel values for "the creator is unknown,"
"this is a various-artists compilation with no single creator," or "not applicable." Because
these sentinels are reused across enormous numbers of unrelated works, they accumulate massive
raw counts — easily enough to cross any count-based threshold — despite representing no single
real entity at all. They must be explicitly identified (by their known fixed identifiers, and
defensively also by their known display names, in case an identifier is ever entered
incorrectly) and permanently excluded from ever being classified as "established," at every
stage: they should never be counted into any entity's statistics in the first place, ideally,
and must never be allowed to fail the core/non-core test even if some are.

The same problem shows up on the publisher side as free-text convention rather than a fixed
identifier: catalogs frequently let a publisher field be filled with a string that conventionally
means "not really published by anyone" ("self-released," "no label," "white label," "test
pressing," and similar). These need to be matched by normalized text (case-insensitive prefix or
full-string match against a known list of such conventions) and excluded the same way.

Skipping this step is a serious correctness bug, not a cosmetic one: in scenes where
self-released or unofficially-distributed work is common — which is often true precisely in the
"underground" or "overlooked" corners a tool like this is built to explore — failing to exclude
these placeholders means the placeholder itself gets classified as an enormous "established
publisher," and every genuinely self-released, anonymous, or unlabeled work in the dataset is
silently dropped as if it were the output of a prolific insider. That is close to the worst
possible failure for this kind of tool, since it disproportionately removes the most obscure,
valuable material.

## 1.9 The calibration tool

Because stages 1 and 2 (§1.2) are expensive and stages 3 and 4 are not, the interactive
calibration tool is where almost all of the *judgment* in this system should happen, and it
should be built to support real inspection, not just report a final number. At minimum it should
provide:

- **Borderline listings by name.** For any threshold (a hard cap, a share line), list the actual
  named entities sitting near that boundary, sorted so the most recognizable ones surface first,
  with enough of their own numbers shown to see *why* they landed where they did. A human
  calibrating a fuzzy real-world boundary needs to recognize specific names to judge whether a
  threshold is in the right place — an aggregate count carries none of that information.
- **"What does this rule remove" sampling.** For each major rule, show a representative sample of
  the specific works that would be included if that one rule were switched off, not just a count
  of how many. Seeing five or ten actual titles is far more informative than a number when
  deciding whether a rule is doing its job.
- **Threshold sweeps.** A grid of result counts across plausible combinations of a rule's
  parameters (e.g., cap value across rows, share value across columns), so the sensitivity of the
  final result to any one setting is visible before committing to a change.
- **Provenance / sanity checks on the ingested data itself**, run against the small database
  rather than by hand-writing throwaway queries each time: how many records were kept per
  category, whether a given metadata field is populated at all in this particular source (some
  sources simply don't use certain optional fields, and a rule built around one that turns out to
  be always-empty in practice is silently inert), and which identifiers matched which placeholder
  names, so a wrong hardcoded identifier is caught by a name mismatch rather than failing
  silently.
- **A note on what actually decided a displayed number.** If a diagnostic shows a derived
  percentage or share for an entity, it must show the number that *actually drove* whichever
  verdict is displayed next to it — not a different, more aggregated number that happens to also
  be available. An entity whose *own* numbers already crossed a threshold, but who also happens
  to belong to a merged group with very different (often much more diluted) numbers, is a
  realistic case; showing the group number next to an own-number-driven verdict silently tells
  the person calibrating the wrong story, and any conclusions drawn from it (e.g. "this threshold
  seems too aggressive because the shown share is tiny") will be wrong.

A single settings module, with every tunable value in one place, some marked as requiring the
expensive stage-1 re-run and others as applying instantly, makes it clear to whoever is
calibrating what a given change will cost before they make it. An internal indirection layer
that can snapshot all current settings but override any individual one per call (without
mutating the shared settings) is what makes the sweep grids and "what does this rule remove"
sampling practical to implement — each hypothetical combination runs the exact same selection
logic under a locally modified settings snapshot, in-process, without needing separate
configuration files or subprocess runs per combination.

## 1.10 The output artifact

The final stage should produce two things from **one** shared selection function, called once,
with its result feeding both outputs — never two independently-derived exports. If the export
and the interactive artifact are generated by separately re-implementing the filtering logic,
they will eventually drift apart as rules change, and the person using the tool will have no way
to know the two disagree.

- **A structured export** (e.g. CSV) for spreadsheets or further processing, including not just
  the final classification but the raw signals that produced it (the counts and shares used,
  which specific rule matched), so the export is itself auditable without re-running anything.
- **An interactive, offline, self-contained browsing artifact** — a single local file that opens
  directly in a browser with no server, no build step, and no network dependency, and lets a
  human explore, filter, and sort the result set live, and mark personal progress on it, without
  ever needing to re-run the pipeline. Design points that matter for this to stay usable at
  thousands of rows:
  - Pre-compute everything filterable or sortable into an in-memory structure exactly once when
    the page loads; never re-query the live document structure inside a filter or sort pass. This
    is the single biggest factor in whether the interface stays responsive as the result set
    grows into the thousands of rows.
  - Distinguish **primary thresholds** (baked into the export at generation time, requiring
    re-running stage 4 to change) from **secondary, live filters** (category buckets, a
    duplicate-count ceiling, provenance flags, a date range, a text search) that the viewer can
    toggle without regenerating anything. The initial state of the live filters is itself a
    reasonable design choice (an opinionated "good starting point"), not a hard limit — everything
    live should be adjustable wider or narrower on the spot.
  - Group near-duplicate catalog entries (§1.5) into one row with an expandable detail view
    listing the individual entries, rather than flooding the table with one row per edition.
  - Persist lightweight personal marks (a simple cyclic two- or three-state marker per work, e.g.
    unmarked → wanted → seen → unmarked) in the browser's local storage, scoped to that one
    generated file. This needs no server, no account, and no network, and survives across
    sessions for as long as the person keeps the file and the same browser profile. It should
    fail silently (not crash the page) if local storage is unavailable (private browsing modes,
    some restricted environments).
  - A category tag that's meant to bypass a live filter (for instance, a crossover-credit find
    being interesting regardless of its date) should be an explicit design decision reflected in
    the filter's logic, on a per-tag basis, rather than assumed.

## 1.11 Engineering pitfalls avoided

These are implementation-level lessons independent of any particular domain. Each is phrased as
what the system does and why, not as a story about a bug — but each corresponds to a real
failure mode worth deliberately avoiding from the outset:

- **Stream the source; never hold it all in memory.** A source too large for memory must be
  parsed with an incremental/streaming parser that discards each parsed record immediately after
  it's been read and processed, rather than building the full parsed structure in memory. This is
  a hard requirement, not an optimization, at the scale this pattern targets (tens of gigabytes,
  tens of millions of records).
- **Use fixed-width arrays, not hash maps, for per-identifier tallies at scale.** When
  aggregating a statistic per numeric identifier across a catalog with identifiers running into
  the tens of millions, a plain array indexed directly by the numeric id (grown on demand as
  larger ids are seen) is dramatically faster and more memory-efficient than a hash map keyed by
  id. For deduplicating (identifier, canonical-work) pairs specifically, packing both integers
  into one wider integer (e.g. shifting the identifier into the high bits, the work id into the
  low bits) and collecting those into a single flat set avoids needing a separate per-identifier
  set, which would not scale.
- **A destructive setup step must come after input validation, never before.** If a stage begins
  by resetting a working database (dropping and recreating its schema) and only afterward
  discovers that its required input file is missing, a previously good database is destroyed for
  nothing. Confirm every required input exists and is readable *before* any destructive
  operation.
- **Console output must not assume a modern Unicode terminal.** Some common operating
  environments default a script's standard output to a legacy, non-Unicode encoding; any output
  containing characters outside that legacy encoding's range (accented letters, non-Latin
  scripts, symbols, emoji — all realistically present in a large real-world text catalog) will
  crash the script the first time such a character appears, often deep into a long-running
  process. Force a modern encoding on standard output explicitly at startup, defensively, on
  every script that prints freeform catalog text.
- **Interactive prompts must degrade gracefully when there's no interactive session.** Any
  end-of-run "press enter to continue" convenience, and any yes/no prompt used for an optional
  action (like offering to open a browser), must detect a non-interactive context (no attached
  input stream — piped input, automation, redirected output) and skip or default rather than
  hang waiting for input that will never come, or crash on end-of-input.
- **Convenience features that depend on network access must be best-effort, with a working
  offline fallback.** Automatically finding the newest version of a periodically-updated external
  source, and offering to open a download page for a missing one, are worth building, but must
  never become hard dependencies: silently and quickly fall back to a purely local or calendar-
  based heuristic if a live check fails for any reason (no connectivity, a firewall, the remote
  service being unreachable, an unexpected response), and never block the primary workflow
  waiting on a slow or hanging network call for longer than a short, explicit timeout.
- **Validate design changes against a tiny synthetic fixture, not the real multi-gigabyte
  source.** A full run against the real source is too slow to use as a feedback loop while
  developing or changing selection logic. Maintain a small script that fabricates a tiny,
  synthetic version of the source data, deliberately constructed to exercise every rule branch at
  least once (every threshold's both sides, every excluded category, every override list, every
  edge case previously found to matter) plus enough realistic "background noise" data that
  aggregate statistics behave the way they would on real data (not every test entity in
  isolation, with no surrounding catalog to compute a realistic share against). Re-run the full
  pipeline against this fixture, end to end, after any change to the selection logic, before
  trusting the change against the real source.
- **A synthetic test fixture must obey the same identity invariants as the real source, and
  should check itself.** If the source format has a rule like "this identifier means these
  entries are the same underlying work," a hand-written synthetic fixture can easily violate it
  by accident (two unrelated fabricated test entries reusing the same made-up identifier value).
  This produces silently wrong test results that can look like either a pipeline bug or a false
  pass, depending on the accident. A fixture generator should include an automated self-check —
  run once, right after generating the fixture — that flags exactly this kind of accidental
  collision before the fixture is used for anything.

## 1.12 Worked example: applying this pattern elsewhere

To make the pattern concrete without jungle-specific baggage, here is a short sketch of applying
it to an unrelated domain — say, finding overlooked short films from independent filmmakers in a
large public film database, while also surfacing films edited or scored by an established
independent composer or editor on an otherwise-mainstream production.

- **Works** = individual film catalog entries; **canonical work id** = the database's own
  "same underlying film, different cut/release" grouping, if it has one, else a composite of
  director + normalized title + studio.
- **Creators** = directors (or the primary credited artist); **publishers** = production
  studios / distributors.
- **Target category** = a specific short-film subgenre or festival circuit tag the database
  tracks.
- **Contribution credit** = the database's own "editor" or "composer" credit field on a film.
- **Count/share model**: a director's hard-cap volume of target-category films, gated by a
  minimum share of their total filmography, exactly as in §1.4 — so a mainstream director who
  directed one film that happens to carry the target tag isn't excluded, but a director whose
  entire, large body of work is in that subgenre is treated as an established name in it.
- **Identity merging**: directors who also direct under a stage name or a production-company
  pseudonym; distributors with regional sub-labels.
- **Placeholder handling**: the database's own "Director unknown" or "Anthology / various
  directors" sentinel values, and free-text production-company fields meaning "self-distributed."
- **Manual overrides**: a director working in a closely adjacent but distinct subgenre (numbers
  can't tell "adjacent-but-different" from "the same thing," a human has to say so, as in §2.6's
  concrete examples).
- **The calibration tool and output artifact** carry over unchanged in shape — only the column
  labels change.

None of the specific *numbers* jungle uses (Part 2) would be appropriate here; they would need to
be derived the same way jungle's were: by running the ingest stage once on the real source, then
using the calibration tool (§1.9) to look at real, named borderline directors and studios in
*this* database and deciding, by inspection, where the lines should sit.

---

# Part 2 — Domain Instantiation: Jungle / Discogs

## 2.1 Domain and goal

Source catalog: Discogs, a large public, collaboratively-maintained discography database,
distributed as periodic full data dumps (XML, gzip-compressed, on the order of 10 GB for the
releases file alone, tens of millions of records). Target category: the early-1990s UK jungle
scene and its immediate neighbors — jungle itself, early/proto drum & bass, and (a narrower slice
of) breakbeat hardcore. Goal: surface small-run vinyl and CD releases from this scene that
aren't already well-known within it, plus jungle-producer remix credits that turn up on records
outside the scene entirely.

## 2.2 Concrete data-model mapping

| Generic concept (Part 1) | Discogs concrete equivalent |
|---|---|
| Work | A Discogs *release* |
| Canonical work id | Discogs `master_id` (links different pressings/editions of one release) |
| Creator | Discogs *artist* |
| Publisher | Discogs *label* |
| Category tag | Discogs *style* (e.g. "Jungle", "Drum n Bass", "Breakbeat", "Hardcore") |
| Contribution credit | A Discogs `extraartists` credit with a role matching "Remix" / "Rmx" / "Re-mix" |
| Placeholder creator | Discogs artist ids for "Various", "Unknown Artist", "No Artist" |
| Pseudo-publisher | Discogs label-name conventions: "Not On Label", "White Label", etc. |
| Identity-relationship source | Discogs' separate *artists* and *labels* dumps, which carry `<aliases>`, `<sublabels>`, and `<parentLabel>` relationships not present in the releases dump |

## 2.3 File map

- `config.py` — every tunable value, in one place, split into a section that requires a
  stage-1 re-ingest to take effect and a section applied instantly by stages 3–4.
- `common.py` — shared logic used by every stage: the count/share classification (`core_artist`,
  `core_label`), the `Stats` class (loads and merges per-entity numbers, holds the manual
  override lists, computes verdicts), the `Params` snapshot/override object, the row-selection
  function (`select_rows`) that both the calibration tool and the final export/artifact call, the
  Discogs-dump auto-discovery helpers, and small formatting/normalization utilities.
- `01_pre_filter.py` — stage 1 (ingest). Streams the releases dump once into a local SQLite
  database, filtering to the target categories and computing whole-catalog per-artist/per-label
  statistics in the same pass.
- `02_build_groups.py` — stage 2 (identity resolution, optional). Streams the separate artists
  and labels dumps, unions aliases and sublabels via a disjoint-set structure, writes merged
  group ids back into the database.
- `03_analyze_thresholds.py` — stage 3 (calibration). Read-only against the database; prints
  borderline entities, rule-removal samples, database sanity checks, and threshold sweep grids.
  Changing `config.py` and re-running this is the intended calibration loop.
- `04_build_dashboard.py` — stage 4 (select & present). Runs the shared selection function once,
  writes a CSV and a self-contained offline HTML file with the interactive browsing UI described
  in §1.10.
- `make_test_dumps.py` — the synthetic-fixture generator described in §1.11's second-to-last
  point, purpose-built to exercise every rule in this specific configuration (every threshold
  edge, every override list, every excluded format and category, alias/sublabel merging,
  compilations, reissue detection, version-count grouping, and a self-check that no two
  fabricated test entries accidentally share a `master_id`).

## 2.4 Category and date windows

| Category tag | Stored window | Notes |
|---|---|---|
| Jungle | 1992–2006 | Deliberately wide; see below |
| Drum n Bass | 1993–1995 | Narrow: only the proto-DnB period, see below |
| Breakbeat Hardcore | 1993–1995, "clean" subset only | See §2.5 |

Jungle's window runs to 2006, well past the genre's classic mid-1990s period, specifically to
include a later-2000s ragga-jungle revival wave rather than only the classic era — useful,
less-obvious compilations and revival-era productions from that later period are still legitimate
finds. Drum & Bass, by contrast, is stored only for 1993–1995: this dataset is not trying to
catalog the entire subsequent evolution of drum & bass as a mainstream genre (which would be a
vastly larger and differently-scoped project), only its earliest, jungle-adjacent period before it
diverged into its own separate scene.

The *stored* window and the *displayed default* window are intentionally different and
independently adjustable, per the general "store wide, filter narrow" principle in §1.2: the
database keeps the full 1992–2006 jungle window (cheap to keep, would be expensive to add back
later), while the interactive artifact's default view narrows to 1992–1998 (`UI_YEAR_MIN` /
`UI_YEAR_MAX` in `config.py`) to match the classic-era browsing session most users want by
default. Widening or narrowing the displayed default never requires re-running stage 1; only
widening the *stored* window would.

## 2.5 Breakbeat Hardcore's narrower scope

Breakbeat Hardcore ("BH") sits directly on the genealogical boundary between the earlier
early-90s UK hardcore rave continuum and the jungle scene this tool targets, and Discogs applies
the BH style tag broadly across several closely adjacent but musically distinct rave subgenres
of that period. Two additional restrictions keep BH scoped to material actually relevant to
jungle:

1. **Noise-style exclusion at ingestion.** A release tagged Breakbeat Hardcore is only stored if
   it does *not* also carry any of a specific set of co-tags: house, happy hardcore, euro house,
   gabber, bleep (`BH_NOISE_STYLES`). Without this, the tool would ingest large amounts of
   material from clearly different scenes that happen to share the BH tag.
2. **A positive jungle link, required at export time.** Even after the noise-style filter, a
   BH-tagged release is only kept in the final output if its artist has independently-verified
   jungle or drum & bass output of their own, *or* the release itself carries a genuine jungle
   remix credit (`BH_REQUIRE_JUNGLE_LINK`). A plain BH record with no such connection is treated
   as belonging to the broader hardcore rave continuum rather than to jungle specifically, even
   after passing the noise filter.

## 2.6 Core-artist and core-label thresholds

| Setting | Value | What it does |
|---|---|---|
| `ABS_MIN` | 4 | Minimum jungle/DnB output before any share-based rule can apply at all |
| `ARTIST_HARD_CAP` | 8 | Artists with this many jungle/DnB-tagged works are established, subject to the floor below |
| `ARTIST_HARD_MIN_PCT` | 10% | The hard cap above only fires at 10%+ jungle share |
| `ARTIST_PCT` | 30% | Below the hard cap, 4+ works at 30%+ share is also established |
| `LABEL_HARD_CAP` | 15 | Labels with this many jungle/DnB masters are established, subject to the floor below |
| `LABEL_HARD_MIN_PCT` | 5% | The label hard cap only fires at 5%+ jungle share |
| `LABEL_MID_ABS` / `LABEL_MID_PCT` | 8 / 40% | Middle tier: high share at moderate volume is also established |
| `LABEL_PCT` | 60% | Below the hard cap, 4+ masters at 60%+ share is also established |

**Why the artist floor is 10%.** Without it, a mainstream artist from an entirely different
field who has a handful of jungle-tagged bootleg remixes or one official jungle mix circulating
under their name — a realistic and fairly common pattern for well-known hip-hop, dancehall, and
pop artists from this era — would be excluded outright once their bootleg count alone crossed 8,
despite that handful representing well under 1% of their real output. Those jungle-tagged
records are exactly the crossover material this tool exists to surface, not noise to filter out.
Setting the floor equal to `NONJUNGLE_PCT` (§2.9) is deliberate: an artist the tool already
calls "non-jungle" by share should never *also* be excluded by volume alone.

**Why the label floor is lower (5%) than the artist floor (10%).** A generalist record label's
total catalog is typically orders of magnitude larger than a single artist's discography, so even
a small percentage of a large label's output can represent a meaningful, worth-surfacing amount
of genuine crossover content, while a genuinely jungle-dedicated label clears even a 5% floor by
a wide margin in practice (typically well over 90% jungle-tagged in its own catalog) — the floor
only needs to be low enough to separate "generalist label with real jungle crossover content"
from "jungle label," not high enough to be a close call either way.

**Manual override lists (`CORE_ARTISTS`, `CORE_LABELS`, `KEEP_ARTISTS`, `KEEP_LABELS`).** The
convention adopted for this dataset is that genre-*adjacent* scenes (breakcore, IDM with jungle
influence, happy hardcore, and similar) count as in-scope "jungle" for curation purposes, not as
noise to exclude. Most such adjacent entities are already correctly classified by the numeric
model on their own. The override lists exist for the residual cases the model gets wrong:

- An artist whose actual scene is genre-adjacent (e.g. happy hardcore / breakbeat hardcore)
  rather than jungle can have a low enough jungle *share* of their total output that the
  percentage-based rules don't catch them, while still being a well-known name *within* that
  adjacent scene — exactly the kind of "established name" this tool is trying to exclude, even
  though the numbers alone say otherwise. `CORE_ARTISTS` force-excludes such a name (together
  with its alias group) regardless of its share.
- A label can score close to, but on the wrong side of, the mid-tier share threshold in either
  direction, in a way that numerically resembles another label whose correct classification is
  the *opposite* one — two labels can land at similar computed shares while one is a real jungle
  label and the other is a different-but-related electronic subgenre label that only
  occasionally puts out jungle material. No numeric threshold can separate two entities sitting
  at similar computed numbers when the *correct* classification actually depends on which scene
  each one really belongs to. `KEEP_LABELS` (or `CORE_LABELS`, depending on which direction the
  correction needs to go) resolves specific named cases like this by domain knowledge instead.

Override list entries are matched by exact name (case-insensitive, ignoring Discogs' numeric
disambiguation suffix, see §2.13) or by Discogs id; name matching only works for entities that
have at least one stored record, since the match is looked up from stored release credits.

## 2.7 Format restrictions

Only vinyl and CD releases are stored; acetates, lathe-cut pressings, and CD-R are explicitly
excluded even though they otherwise pass the vinyl/CD check (a CD-R can superficially resemble a
CD entry, for instance). Acetates and lathe-cuts are one-off or test-pressing items whose
scarcity is definitional and already well understood by collectors — they aren't "overlooked" in
the sense this tool targets, they're simply always rare. CD-R is typically a burn-on-demand or
bootleg format rather than a genuine limited pressing, and is excluded for the same reason.
Cassette and purely digital formats are excluded implicitly, by the vinyl/CD-only allowlist.

## 2.8 Placeholder artists and pseudo-labels (Discogs specifics)

Discogs' fixed placeholder artist identifiers are "Various" (id 194, used for compilation
releases with no single artist), "Unknown Artist" (id 355), and "No Artist" (id 118760)
(`NON_ARTIST_IDS`, cross-checked defensively against their known display names,
`NON_ARTIST_NAMES`, so a wrong hardcoded id would still be caught).

Discogs' pseudo-label conventions are matched by a fixed list of case-insensitive name prefixes:
"Not On Label", "White Label", "No Label", "Unknown", "Private Release", "Self-Released"/"Self
Released", and "Test Pressing" (`PSEUDO_LABEL_PREFIXES`). Self-released and white-label vinyl is
extremely common in the classic jungle era — small-run dubplates and white labels are a defining
feature of the scene, not a rare edge case — so this exclusion is load-bearing: without it, these
pseudo-publisher strings would accumulate enormous raw counts across the whole catalog and
qualify as an "established label" under any volume-based rule, silently deleting the majority of
the self-released, small-run material this tool exists to surface.

## 2.9 Non-jungle tagging and the remix-source threshold

`NONJUNGLE_PCT` (10%) is the share below which an artist or label is tagged "non-jungle artist" /
"non-jungle label" in the output — a descriptive tag for browsing, distinct from (but numerically
aligned with) the artist hard-cap floor in §2.6.

`REMIXER_MIN_JUNGLE` (5) and `REMIXER_MIN_PCT` (20%) define what counts as "an established
jungle remixer" for the crossover signal (§1.7): the credited remixer must have at least 5
jungle/DnB-tagged works of their own, representing at least 20% of their own total output,
computed strictly from their own primary-artist catalog — never from the crossover credits being
evaluated (the circularity this avoids is described generically in §1.7).

## 2.10 Why untagged records are not scanned for hidden remixes

An earlier iteration of this system attempted to also search for jungle-producer remix credits on
releases that did *not* carry a jungle/DnB/BH style tag at all, on the theory that a genre-hiding
remix might not get the release re-tagged. In practice, this does not happen on Discogs: when a
jungle producer remixes a track on an otherwise different-genre release, Discogs' own tagging
convention causes the enclosing release to also be tagged with the Jungle style at the release
level. An untagged release with a genuinely hidden jungle remix essentially does not occur.
Scanning untagged records for this pattern anyway produced overwhelming numbers of false
candidates (the large majority of matches, once cross-checked against a stricter remixer
threshold, turned out not to hold up) for negligible genuine signal, because almost every
apparent match was coincidental rather than a real hidden crossover. The current system restricts
the remix/crossover search entirely to records that are already stored under one of the three
target style tags (§2.2's `select_rows` logic), which eliminates this false-positive flood while
still catching every real crossover case observed in practice, at the cost of the (in practice,
negligible) categories described in §1.7's scoping point.

## 2.11 Compilations and the remix tag

Discogs credits compilation releases to the "Various" placeholder artist, so the artist-level
core/non-core test is skipped for compilations entirely (there's no real per-artist field to
test) — compilations are judged purely by their issuing label.

A compilation carrying a genuine jungle remix credit still has that credit recorded and displayed
(it's real, potentially interesting information), but it does not, by itself, earn the "remix"
classification tag the way the same credit would on a single-artist release. In practice, on this
dataset, the large majority of "compilation contains a jungle-remix credit" cases are ordinary
genre-specific compilation samplers, where finding a well-known jungle remixer somewhere in a
jungle compilation's tracklist is the expected norm rather than a surprising find — exactly the
base-rate effect described generically in §1.7.

## 2.12 Versioning, reissues, and duplicate grouping

Discogs' `master_id` is used as the canonical work identifier (§1.5). A release without a master
id falls back to a composite key of artist + normalized title + label, so duplicate manual
entries of the same untracked release still collapse into one row; failing that, it falls back to
its own release id.

The number of distinct Discogs release entries sharing one master id — "versions," counted across
the *entire* dump regardless of format or category, not just the stored jungle subset — is
computed during stage 1 and stored per release, and used as a live, independently adjustable
filter (`EXPORT_MAX_VERSIONS` caps what's exported at all; `UI_MAX_VERSIONS` sets the dashboard's
default, narrower, view). A master re-pressed or issued in many territories has likely already
had significant commercial circulation, which runs counter to "overlooked" — but this is treated
as an adjustable filter rather than a hard rule, since it's a correlational signal, not a
certainty.

A master is separately flagged "reissued" if *any* of its associated releases' format
descriptions include the words reissue, repress, or remastered, and reissued masters are hidden
from the dashboard's default view (adjustable) for the same reason.

## 2.13 Discogs-specific data-quality handling

- **Approximate release dates.** Discogs' `released` field is frequently a partial or malformed
  string for older, less-documented releases — patterns like "199?" rather than a clean
  four-digit year, or fully blank/zeroed placeholder strings. Exact release dates for small,
  self-released vinyl from this era are often genuinely unknown even to collectors. The date
  parser recovers an approximate decade-level year from partial patterns (flagged as approximate
  for display, e.g. shown as "199?") rather than discarding the record outright; a record with no
  recoverable year information at all is dropped, since it can't be placed in any year window.
  Discarding partial-date records outright, rather than approximating, would disproportionately
  remove exactly the kind of obscure, poorly-documented release this tool exists to find.
- **Display-name disambiguation suffixes.** Discogs appends a parenthesized number (e.g. "(2)")
  to an artist or label name whenever that exact name string collides with an unrelated,
  differently-identified entity elsewhere on the site — it is a same-name collision marker, not a
  version or edition number. This suffix is stripped for display purposes only; it is never used
  in any identity or grouping decision, which are always made by Discogs numeric id.
- **Track attribution for release-level remix credits.** A remix credit can be attached either to
  a specific track (an unambiguous, structured link) or to the release as a whole with a
  free-text field listing which track(s) it applies to. The free-text field is parsed by
  tokenizing it against the release's own known track position labels; if none resolve, the raw
  free-text value is kept and shown as-is rather than the credit being discarded, per the general
  "prefer structured data, fall back to parsing semi-structured text against a known vocabulary,
  never silently drop it" principle in §1.7.

## 2.14 Presentation specifics

- **YouTube links are plain hyperlinks, never embedded players.** The generated HTML file is
  opened directly from local disk (the `file://` protocol) rather than served over HTTP.
  Embeddable video players require the browser to send an HTTP Referer header identifying the
  hosting page, which the `file://` protocol never provides; the video platform's embed check
  then fails and playback is refused, surfaced to the viewer as a generic numbered player error.
  A plain link that opens the video in a new tab sidesteps this limitation entirely, at the cost
  of an extra click instead of inline playback — an acceptable and, in this context, necessary
  trade-off given the artifact is meant to be a portable local file with no server component.
- **Dashboard default view (1992–1998, ≤4 versions, no compilations/BH/reissues).** This reflects
  a considered default rather than an arbitrary one: someone opening this tool for the first time
  is assumed to want the narrowest, most classic-era, least-circulated slice of results by
  default, with every dimension that broadens the result set (later years, more heavily pressed
  records, compilations, the adjacent breakbeat-hardcore category, reissues) available as an
  explicit, one-click opt-in rather than something they have to narrow down from a wide, noisy
  default.

## 2.15 Known open judgment calls

These are places where the current configuration reflects one reasonable choice among several,
not a settled, unquestionable answer — worth revisiting with the calibration tool (§1.9 / stage 3)
against a current data dump before assuming they're still correct:

- The 40-member alias/sublabel group-size ceiling (`MAX_ARTIST_GROUP`, `MAX_LABEL_GROUP`) is a
  heuristic tuned by inspecting which groups it dissolved versus kept on one specific dump; it is
  not derived from a principled formula, and a dump with different characteristics could call for
  a different value in either direction.
- The remixer-identification threshold (5 works, 20% share) determines the entire size of the
  crossover-discovery result set; the threshold-sweep tool shows this is a real, adjustable
  sensitivity, not a fixed law, and different collectors may reasonably want it looser or
  stricter.
- The manual override lists (§2.6) are inherently incomplete by construction — they document
  specific cases already identified by inspection, not an exhaustive classification of every
  genre-adjacent artist or label in the dataset. Expect to find more candidates for these lists
  by reading the calibration tool's borderline-entity tables against a full, current dump.
- The jungle category's stored year window (1992–2006) and the drum & bass category's narrower
  window (1993–1995) reflect a specific view of where each genre's "classic, still-searchable"
  period ends; a different collector's view of that boundary is a legitimate reason to change
  `DB_YEARS`, at the cost of a stage-1 re-ingest.

## 2.16 Orientation for continued development

To resume development on this exact tool, in order of what unlocks understanding the rest fastest:

1. Read `config.py` in full — it is the single source of truth for every tunable value, and its
   comments already explain each one's effect.
2. Read `common.py`'s `Stats` class and `select_rows` function — this is the classification and
   selection core that every other script calls into; understanding it is a prerequisite for
   understanding any of the four numbered scripts.
3. Read the four numbered scripts in their numbered order — each one's own module docstring
   states which pipeline stage (§1.2) it implements.
4. Before changing any selection logic, run `make_test_dumps.py` followed by the four numbered
   scripts in a scratch folder against the resulting tiny synthetic dump (a few seconds end to
   end) and confirm the printed record counts match its docstring's expectation, before trusting
   any change against a real multi-gigabyte Discogs dump.
