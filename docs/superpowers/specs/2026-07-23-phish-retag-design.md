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

Multi-set shows collapse to one album per show date — the set numeral is
dropped and all files in the directory receive the same album tag. No other
metadata (artist, title, track/disc numbers, art) is touched, and files whose
album tag is already correct are not rewritten (preserves mtimes).

## Scope

- **In scope:** directories matching `Phish-YYYY-MM-DD.<Dot.Separated.Location>.[ID]`
- **Out of scope / skipped and reported:** everything else (`Live Bait Vol. *`,
  `A Live One`, etc.), and non-audio files
- **Audio formats:** FLAC, M4A (ALAC), MP3 — the three formats present in the collection

## Architecture

Single Python script `bin/phish-retag` (no `.py` extension, like the other
`bin/` tools), sharing the house conventions of `phish-rename` /
`phish-compare` / `phish-merge`:

- Default collection path `/data/media/Sorted/Unsorted/Music/Phish`, overridable
  with `--path`
- Dry-run by default; `--execute` to apply changes
- livephish.com requests reuse the request pattern from `phish-rename`
  (same headers, 1-second delay between requests)

### Tag I/O: mutagen

New Python dependency `mutagen` (added to `requirements.txt`). It reads/writes
tags in place for all three formats without re-encoding or re-muxing audio.
Album tag fields per format:

| Format | Container | Album field |
|--------|-----------|-------------|
| FLAC   | Vorbis comments | `ALBUM` |
| M4A    | MP4 atoms | `©alb` |
| MP3    | ID3v2 | `TALB` |

### Per-directory pipeline

For each subdirectory of the collection root:

1. **Filter.** Skip (and report) directories not matching
   `^Phish-\d{4}-\d{2}-\d{2}\..+\.\[\d+\]$`.
2. **Parse.** Extract date (`YYYY-MM-DD`), dot-separated location tokens, and
   LivePhish ID from the directory name.
3. **Resolve the venue/city boundary** (see below) to get
   `Venue`, `City`, `ST`.
4. **Compute target album:** `YYYY/MM/DD Venue, City, ST` with the date's
   dashes converted to slashes.
5. **Compare and act.** For each audio file: read the current album tag;
   if it already equals the target, count as *already correct*; otherwise
   report the change (dry-run) or write it (`--execute`).

### Venue/city boundary resolution

The directory name loses the boundary (`phish-rename` strips commas from
livephish's `Venue, City, ST` string). Resolution order:

1. **Cache lookup.** JSON cache keyed by LivePhish ID at
   `~/.cache/phish-retag.json` (overridable with `--cache`). Hit → done.
2. **Existing-tag heuristic (offline).** Scan the album tags already on the
   directory's files for a `City, ST` pattern whose two-letter code matches
   the final token of the directory name. Convert the city to dot form and
   match it against the tail of the location tokens (immediately before the
   state token). If it matches, the tokens before the city are the venue.
3. **livephish.com fallback.** Fetch `https://www.livephish.com/LP-<ID>.html`
   and extract the comma-separated `Venue, City, ST` location string.
   1-second delay between requests; failures (HTTP error, page gone,
   unparseable) mark the show **unresolved** — the tool never guesses.
4. **Persist.** Every successful resolution (from step 2 or 3) is written to
   the cache immediately, so interrupted runs keep their progress.

**Dry-run performs full resolution**, including livephish queries and cache
writes. This is deliberate: a dry run tells you (a) which albums need
correcting and (b) whether each correction is knowable, and it warms the cache
so a subsequent `--execute` run does no network work.

### CLI

```
phish-retag [--path DIR] [--cache FILE] [--execute]
```

- Default (no flags): dry run. Per-show output showing current → target album
  (or *already correct* / *skipped* / *unresolved*).
- `--execute`: apply the tag writes.
- End-of-run summary: counts of updated (or would-update), already-correct,
  skipped, unresolved — with unresolved directories listed for manual handling.

### Error handling

- Unreadable/corrupt audio file: report and continue; never abort the run.
- Directory with no audio files: report as skipped.
- Mixed or missing tags in a directory don't block resolution — the heuristic
  only needs one usable tag, and livephish is the fallback.
- Cache file corrupt/missing: start with an empty cache; never fatal.
- Network failure during fallback: show marked unresolved; run continues.

## Testing

Pytest, following the existing `tests/test_phish_*.py` conventions:

- Script loaded via `SourceFileLoader` (no `.py` extension).
- livephish HTTP mocked with `unittest.mock` — no live requests in tests.
- Tiny real FLAC/M4A/MP3 fixture files generated in-test (mutagen can create
  minimal valid files) to exercise actual tag read/write per format.
- Coverage: directory-name parsing, canonical-dir filtering, tag heuristic
  (single-word and multi-word cities, MX shows, set-numeral tags), livephish
  fallback + unresolved path, cache round-trip, already-correct skip,
  dry-run vs execute behavior.

## Known limitations

- Shows where no file tag yields a usable `City, ST` **and** the livephish
  page is unavailable land in the unresolved bucket for manual handling.
- The tool trusts the directory name's date and location tokens; directories
  with wrong contents (e.g. the `2026-07-19` dir currently holding a copy of
  the 07-18 show) will be tagged per their directory name. That data issue is
  out of scope.
