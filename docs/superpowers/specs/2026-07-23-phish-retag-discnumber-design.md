# phish-retag — Auto-handle clean multi-set shows via discnumber

**Date:** 2026-07-23
**Status:** Approved

## Purpose

`bin/phish-retag` currently skips every directory whose audio files carry more
than one distinct album tag ("multi-set"), listing them for manual assessment
(see [`2026-07-23-phish-retag-design.md`](2026-07-23-phish-retag-design.md)).
A live scan of the real collection found 300+ such directories — too many to
be a manual-only bucket.

Most of them follow one clean, mechanical pattern: every file's album tag is
identical to the show's normal target album except for a Roman numeral marker
right after the date, marking which set the track belongs to:

```
1994/05/07 I Dallas, TX
1994/05/07 II Dallas, TX
```

This change teaches phish-retag to recognize that pattern, convert the Roman
numeral into a `discnumber` tag, and collapse the album tag to the same
uniform `YYYY/MM/DD Venue, City, ST` used everywhere else — the same way a
real multi-disc release is tagged.

The same scan also surfaced messier directories that must **not** be
auto-collapsed:

- Contamination: a track internally tagged with a wholly different date/venue
  (a misfiled bonus track from another show), e.g. a `1994-12-01` directory
  containing one file tagged `1994/11/12 II Kent, OH`.
- Non-Roman-numeral distinct tags, e.g. `... (soundcheck)` variants, or a
  same-date tag differing only by casing (`Chicago, IL` vs `Chicago, Il`).

These stay in the existing skip-and-report path, unchanged.

## Scope

- **In scope:** directories with 2+ distinct album tags where every distinct
  tag's date matches the directory's own date and every distinct tag carries
  a Roman-numeral marker (`I`, `II`, `III`, `IV`, …) immediately after the
  date.
- **Out of scope:** everything else keeps today's skip-and-report behavior —
  contaminated directories, soundcheck-only distinct tags, casing-only
  mismatches, and any directory where at least one distinct tag lacks a
  Roman-numeral marker. No "best-effort partial tag" mode: a directory is
  either fully auto-processed or fully skipped.
- **Not adding:** `disctotal`. Discussed and declined — discnumber alone
  covers the stated need, and disctotal is encoded inconsistently across
  formats (a separate tag on FLAC, but combined into the same field as
  discnumber for MP3/M4A), adding real branching for no requested benefit.

## Detection

For a directory with 2+ distinct album tags:

1. For each distinct tag, extract a leading date token. Accepts both
   `YYYY/MM/DD` and `YYYY-MM-DD` separators, and non-zero-padded month/day
   (`1996/12/6`) — compare numerically against the directory's own parsed
   date, not as a string.
2. Immediately after the date, look for a Roman-numeral token (`^[IVXLCDM]+$`,
   parsed with a small roman-to-int helper; the collection has shows up to
   `IV`, code supports the general case) followed by a word boundary before
   the rest of the location text.
3. The directory qualifies as **clean multi-set** only if step 1's date
   matches the directory's date for *every* distinct tag, and step 2 finds a
   Roman numeral for *every* distinct tag. If any distinct tag fails either
   check, the directory falls back to today's behavior entirely (counted and
   reported as before, not partially processed).

## Clean multi-set handling

Once a directory qualifies:

- **Venue/city resolution** runs once per directory, same cache → offline
  heuristic → livephish fallback flow as the single-tag case, using any one
  of the distinct tags with its Roman-numeral token stripped as the
  `album_tag` heuristic input. Same round-trip invariant, same cache keyed by
  LivePhish ID.
- **Target album** is `target_album(date, resolved)` — identical for every
  file in the directory regardless of which set it belongs to (no set marker
  in the album tag).
- **Target discnumber** is the Roman numeral converted to a plain arabic
  string: `"1"`, `"2"`, `"3"`, `"4"`, … (no zero-padding, no `/total` suffix —
  matches how `tracknumber` is already written in this collection).
- **Per-file write.** For each file, look up its current album tag's Roman
  numeral to get its target discnumber. Write (dry-run: report) only when the
  file's current `(album, discnumber)` pair differs from
  `(target_album, target_discnumber)`. Files already correct are left alone
  (mtime preserved), same as the existing single-tag logic.
- Only `album` and `discnumber` are touched — no other tags, same as today.

### Tag I/O

`discnumber` is supported by mutagen's easy interface uniformly across FLAC,
M4A, and MP3 (`audio["discnumber"] = "2"`), the same pattern already used for
`album`. No new dependency.

## Reporting

The existing `multiset` bucket splits into two for clarity:

- `multiset_clean` — auto-updated (or would-update in dry-run); rolled into
  the existing `updated` count and per-file change output, same format as
  single-tag updates (`current → target` for album, plus the discnumber
  change).
- `multiset_anomaly` — today's skip-and-report behavior, renamed in output
  from `MULTISET` to make clear these still need manual assessment (the
  contamination/soundcheck/casing cases).

End-of-run summary gains a `multiset_clean` count alongside the existing
`multiset` (now `multiset_anomaly`), `unresolved`, `already`, `skipped`
counts.

## Testing

Extends `tests/test_phish_retag.py` following existing conventions
(`SourceFileLoader`, mocked livephish HTTP, tiny ffmpeg-generated fixture
files):

- Roman numeral parsing: `I` through at least `IV`, invalid tokens rejected.
- Date-token extraction: slash and dash separators, non-zero-padded
  month/day, mismatched dates correctly rejected.
- Clean multi-set end-to-end: 2-set and 3-set directories, correct
  discnumber + uniform album written per file, already-correct files
  skipped, dry-run vs execute.
- Anomaly cases stay in the skip path: mismatched-date contamination,
  missing-Roman-numeral distinct tag (soundcheck-style), casing-only
  mismatch with no Roman numeral at all.
- Venue/city resolution reuses the same cache/heuristic/livephish-fallback
  code path — verify it's invoked once per directory, not once per file.

## Known limitations

- Soundcheck tracks mixed into an otherwise-clean multi-set directory still
  force the whole directory into the anomaly bucket (no partial handling).
- `disctotal` is not written; a future pass could add it per-format if ever
  needed.
