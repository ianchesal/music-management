# phish-retag — Normalize album tags for Phish show directories

**Date:** 2026-07-23
**Status:** Approved

## Purpose

Album tags across the Phish collection (`/data/media/Sorted/Unsorted/Music/Phish/`,
~921 show directories) are inconsistent:

- Good-but-incomplete: `2026/07/22 New York, NY` (no venue)
- Messy: `Phish - Phish - 2026_07_21 Syracuse, NY (Phis)`
- Per-set albums within one show: `1995/12/31 I New York, NY`, `...II...`, `...III...`

`bin/phish-retag` rewrites the **album tag only** on every audio file in each
canonical show directory to a single consistent format derived from the
directory name:

```
YYYY/MM/DD Venue, City, ST
```

Examples:

- `2026/07/22 Madison Square Garden, New York, NY`
- `2026/01/28 Moon Palace Resort, Riviera Maya, MX` (international shows work identically)

No metadata other than the album tag (artist, title, track/disc numbers, art)
is touched, and files whose album tag is already correct are not rewritten
(preserves mtimes).

**Multi-set shows are skipped, not collapsed.** If a directory's audio files
carry more than one distinct album tag (e.g. `1994/12/29 I Providence, RI` and
`1994/12/29 II Providence, RI`), collapsing them into one album could produce
colliding track numbers (each set often restarts at 1) without disc-number
fixes this tool deliberately doesn't make. These directories are skipped with
a warning listing the distinct tags found, for manual assessment. A directory
whose files all share one album tag is in scope even if that tag contains a
set numeral — retagging a single uniform album can't change grouping or order.

## Scope

- **In scope:** directories matching `Phish-YYYY-MM-DD.<Dot.Separated.Location>.[ID]`
- **Out of scope / skipped and reported:** everything else (`Live Bait Vol. *`,
  `A Live One`, etc.), and non-audio files
- **Audio formats:** FLAC, M4A (ALAC), MP3 — the three formats present in the collection

## Architecture

Single Python script `bin/phish-retag` (no `.py` extension, like the other
`bin/` tools), sharing the house conventions of `phish-rename` /
`phish-compare` / `phish-merge`:

- Optional positional `PATH` argument (like `phish-rename`), defaulting to
  `/data/media/Sorted/Unsorted/Music/Phish`
- Dry-run by default; `--execute` to apply changes
- livephish.com requests reuse `phish-rename`'s `search_livephish()` /
  `parse_search_results()` flow (same URL, headers, and parser), with a
  randomized delay of 0.5–1.5 s between requests (`random.uniform`) to add
  jitter rather than a fixed cadence

### Tag I/O: mutagen

New Python dependency `mutagen` (added to `requirements.txt`). It reads/writes
tags in place for all three formats without re-encoding or re-muxing audio.
The implementation uses `mutagen.File(path, easy=True)`, which exposes a
uniform `album` key across all three formats — one code path, not three.
For reference, the underlying fields:

| Format | Container | Album field |
|--------|-----------|-------------|
| FLAC   | Vorbis comments | `ALBUM` |
| M4A    | MP4 atoms | `©alb` |
| MP3    | ID3v2 | `TALB` |

### Per-directory pipeline

For each subdirectory of the collection root:

1. **Filter.** Skip (and report) directories not matching
   `^Phish-\d{4}-\d{2}-\d{2}\..+\.\[\d+\]$`.
2. **Parse.** Extract date (`YYYY-MM-DD`), the dot-separated location string,
   and LivePhish ID from the directory name.
3. **Multi-set check.** Read the album tags of all audio files in the
   directory. If more than one distinct album tag is present, skip the
   directory with a warning listing the distinct tags (see Scope).
4. **Resolve the venue/city boundary** (see below) to get the comma-separated
   location (`Venue, City, ST`).
5. **Compute target album:** `YYYY/MM/DD` (date's dashes converted to
   slashes) + the resolved comma-separated location.
6. **Compare and act.** For each audio file: read the current album tag;
   if it already equals the target, count as *already correct*; otherwise
   report the change (dry-run) or write it (`--execute`).

### Venue/city boundary resolution

The directory name loses the boundary (`phish-rename` strips commas from
livephish's `Venue, City, ST` string via `location_to_dots()`). Resolution
order:

1. **Cache lookup.** JSON cache keyed by LivePhish ID at
   `$XDG_CACHE_HOME/phish-retag.json` (default `~/.cache/phish-retag.json`,
   overridable with `--cache`). Hit → done (still subject to the round-trip
   invariant below).
2. **Existing-tag heuristic (offline).** Applies only when the directory's
   final location token is a two-letter uppercase code. Take the directory's
   (single, per the multi-set check) album tag and extract the city as the
   **last** comma-separated segment before the state code, ignoring any
   leading date junk and trailing junk after the code (e.g.
   `Phish - Phish - 2026_07_21 Syracuse, NY (Phis)` → city `Syracuse`,
   code `NY`; `1997/11/22 Hampton Coliseum, Hampton, VA` → city `Hampton`,
   not `Hampton Coliseum, Hampton`). The code must match the directory's
   final token. Convert the city with `location_to_dots()` and compare it as
   a **dot-normalized string suffix** against the location string immediately
   before the state token — collapse repeated dots on both sides before
   comparing, so a tag city of `St. Louis` (→ `St..Louis`) still matches the
   directory's `St.Louis`. Never split the location into a token list for
   this comparison. On a match, everything before the city is the venue.
3. **livephish.com fallback.** Reuse `phish-rename`'s proven flow: search by
   the directory's date (`search_livephish`), parse candidates with
   `parse_search_results`, and pick the candidate whose release ID equals the
   directory's `[ID]`. That candidate's location string is the same
   comma-separated `Venue, City, ST` string the directory name was built
   from, so the round-trip is exact by construction. Randomized 0.5–1.5 s
   delay between requests. Failures (HTTP error, no matching ID, unparseable)
   mark the show **unresolved** — the tool never guesses. This path also
   handles directories whose final token is not a two-letter code
   (`...Fukuoka.Japan.[...]`, `...Barcelona.Spain.[...]`, `...CZE...` — about
   a dozen exist in the collection); for those the target album is simply
   `YYYY/MM/DD` + the location string as livephish gives it.
4. **Round-trip invariant (hard rule).** Every resolution — heuristic,
   network, or cache hit — must satisfy:
   `location_to_dots(resolved_location)` equals the directory's location
   string (dot-normalized comparison). Because that is exactly how directory
   names are generated, any mismatch means the resolution is wrong for this
   directory (mislabeled tags, stale cache, coincidental city match) → mark
   unresolved rather than write a plausible-but-wrong tag.
5. **Persist.** Every successful resolution (from step 2 or 3) is written to
   the cache immediately, so interrupted runs keep their progress.

**Dry-run performs full resolution**, including livephish queries and cache
writes. This is deliberate: a dry run tells you (a) which albums need
correcting and (b) whether each correction is knowable, and it warms the cache
so a subsequent `--execute` run does no network work.

### CLI

```
phish-retag [PATH] [--cache FILE] [--execute]
```

- Default (no flags): dry run. Per-show output showing current → target album
  (or *already correct* / *skipped* / *multi-set* / *unresolved*).
- `--execute`: apply the tag writes.
- End-of-run summary: counts of updated (or would-update), already-correct,
  skipped, multi-set, unresolved — with multi-set and unresolved directories
  listed for manual handling.

### Error handling

- Unreadable/corrupt audio file: report and continue; never abort the run.
- Directory with no audio files: report as skipped.
- Missing/unusable album tags don't block resolution — livephish is the
  fallback. (Mixed tags are the multi-set case: skip + warn.)
- Cache file corrupt/missing: start with an empty cache; never fatal.
- Network failure during fallback: show marked unresolved; run continues.

## Testing

Pytest, following the existing `tests/test_phish_*.py` conventions:

- Script loaded via `SourceFileLoader` (no `.py` extension).
- livephish HTTP mocked with `unittest.mock` — no live requests in tests.
- Tiny real FLAC/M4A/MP3 fixture files generated once per test session with
  ffmpeg (already a repo dependency; mutagen can only edit existing files,
  not create them): `ffmpeg -f lavfi -i anullsrc=r=8000:cl=mono -t 0.1 f.flac`
  — verified to produce 0.5–8.3 KB files. A `tmp_path_factory` session fixture
  generates them; each test copies what it needs.
- Coverage: directory-name parsing, canonical-dir filtering, tag heuristic
  (single-word and multi-word cities, MX shows, `St. Louis`-style dotted
  cities, two-comma tags like `... Hampton Coliseum, Hampton, VA`, trailing
  junk after the state code), multi-set skip + warning, non-two-letter final
  token routed to the network path, round-trip invariant rejection, livephish
  fallback + unresolved path, cache round-trip, already-correct skip,
  dry-run vs execute behavior.

## Documentation updates

Implementation includes updating `CLAUDE.md` (Phish tools list, common
commands, dependencies, file structure) and adding `mutagen` to
`requirements.txt`.

## Known limitations

- Shows where no file tag yields a usable `City, ST` **and** the livephish
  lookup fails land in the unresolved bucket for manual handling.
- Multi-set directories (more than one distinct album tag) are not retagged;
  they're listed for manual assessment. A future pass could collapse them by
  also rewriting disc/track numbers, but that's out of scope here.
- The tool trusts the directory name's date and location tokens; directories
  with wrong contents (e.g. the `2026-07-19` dir currently holding a copy of
  the 07-18 show) will be tagged per their directory name. That data issue is
  out of scope.
