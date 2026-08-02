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
  tag's date matches the directory's own date, every distinct tag carries a
  set marker (`I`–`V`) immediately after the date, and the location text
  after the marker is identical across all of them (see Detection below).
- **Out of scope:** everything else keeps today's skip-and-report behavior —
  contaminated directories, soundcheck-only distinct tags, casing-only
  mismatches, any directory where at least one distinct tag lacks a set
  marker, and any directory where set-marker tokens are present but the
  surrounding location text disagrees. No "best-effort partial tag" mode: a
  directory is either fully auto-processed or fully skipped.
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
2. Immediately after the date, look for a set marker: **one of the literal
   tokens `I`, `II`, `III`, `IV`, `V`** (not a general Roman-numeral parse),
   followed by a word boundary before the rest of the location text. This is
   a fixed allow-list, not `^[IVXLCDM]+$` — a general parser accepts strings
   like `XL`, and the collection contains a real directory,
   `Phish-2013-10-27.XL.Center.Hartford.CT.[804]`, where "XL" is the venue
   name, not a set marker. A Phish show having more than 5 sets is not a
   real scenario worth designing for, so the allow-list closes this off
   entirely rather than bounding a general parser's output after the fact.
3. After stripping the date and set-marker token, the **remaining location
   text must be identical (dot-normalized) across every distinct tag** —
   i.e. the tags disagree *only* in their set marker, nothing else. This
   guards the case where two distinct tags both happen to carry a valid
   step-2 token but for unrelated reasons (a genuine data-quality problem,
   or an accidental token match against different venue text) — that
   directory is not a clean same-show multi-set and must not be collapsed.
4. The directory qualifies as **clean multi-set** only if step 1's date
   matches the directory's date for *every* distinct tag, step 2 finds a
   set-marker token for *every* distinct tag, and step 3's remainder check
   passes. If any distinct tag fails any check, the directory falls back to
   today's behavior entirely (counted and reported as before, not partially
   processed).

## Clean multi-set handling

Once a directory qualifies:

- **Venue/city resolution** runs once per directory, same cache → offline
  heuristic → livephish fallback flow as the single-tag case, using the
  distinct tag with the **lowest set marker** (`I`) with its token stripped
  as the `album_tag` heuristic input — pinned down deterministically so
  behavior doesn't depend on dict/set iteration order and tests can assert
  on it directly. (Detection step 3 already guarantees every distinct tag's
  remainder is identical, so any tag would in principle resolve the same
  way; picking `I` just makes the choice explicit and reproducible.)
- **Target album** is `target_album(date, resolved)` — identical for every
  file in the directory regardless of which set it belongs to (no set marker
  in the album tag).
- **Target discnumber** is the set marker converted to a plain arabic
  string: `"1"`, `"2"`, `"3"`, `"4"`, `"5"` (no zero-padding, no `/total`
  suffix — matches how `tracknumber` is already written in this
  collection).
- **Per-file write.** For each file, look up its current album tag's Roman
  numeral to get its target discnumber. Write (dry-run: report) only when the
  file's current `(album, discnumber)` pair differs from
  `(target_album, target_discnumber)`. Files already correct are left alone
  (mtime preserved), same as the existing single-tag logic.
- Only `album` and `discnumber` are touched — no other tags, same as today.

### Tag I/O

`discnumber` is supported by mutagen's easy interface across FLAC, M4A, and
MP3 (`audio["discnumber"] = "2"`), the same pattern already used for `album`.
No new dependency. Verified directly (not just by analogy to `tracknumber`):
FLAC/Vorbis stores it as a plain string comment; ID3 (MP3) writes the literal
string into the `TPOS` frame; M4A's `EasyMP4Tags` registers `discnumber` as
an int-pair key and parses the write into the `disk` atom's `(N, total)`
tuple — meaning a bare `"2"` (no `/total`) still round-trips correctly on
M4A, but this format-specific parsing is exactly why the Testing section
below requires an explicit read-back assertion per format rather than
trusting the write not to raise.

## Reporting

The existing `multiset` bucket splits into two for clarity:

- `multiset_clean` — auto-updated (or would-update in dry-run); rolled into
  the existing `updated` count. Per-directory output prints **one line per
  detected set**, not one line per file (a set can be a dozen-plus tracks;
  they all share the same before/after values, so per-file lines would be
  pure noise) — sorted by set marker ascending:
  ```
  Phish-1994-05-07.The.Bomb.Factory.Dallas.TX.[496]
      Disc 1: 1994/05/07 I Dallas, TX → 1994/05/07 Dallas, TX
      Disc 2: 1994/05/07 II Dallas, TX → 1994/05/07 Dallas, TX
  ```
  The per-file write/compare loop underneath is unchanged (still skips files
  already at the target `(album, discnumber)` pair); the line above is
  reported once per distinct source tag regardless of how many files share
  it.
- `multiset_anomaly` — today's skip-and-report behavior, renamed in output
  from `MULTISET` to make clear these still need manual assessment (the
  contamination/soundcheck/casing cases, and now also directories that have
  a set-marker token on every distinct tag but fail the step-3 remainder
  check).

End-of-run summary gains a `multiset_clean` count alongside the existing
`multiset` (now `multiset_anomaly`), `unresolved`, `already`, `skipped`
counts.

## Testing

Extends `tests/test_phish_retag.py` following existing conventions
(`SourceFileLoader`, mocked livephish HTTP, tiny ffmpeg-generated fixture
files):

- Set-marker allow-list: `I` through `V` accepted; a token like `XL` is
  rejected even though it's a technically-valid Roman numeral — regression
  test using the real `XL Center` directory name/tag shape to pin this down.
- Date-token extraction: slash and dash separators, non-zero-padded
  month/day, mismatched dates correctly rejected.
- Remainder-consistency check (Detection step 3): distinct tags with valid
  set markers but differing location text are routed to the anomaly bucket,
  not collapsed.
- Clean multi-set end-to-end: 2-set and 3-set directories, correct
  discnumber + uniform album written per file, already-correct files
  skipped, dry-run vs execute, output format matches the one-line-per-set
  shape above.
- Anomaly cases stay in the skip path: mismatched-date contamination,
  missing-set-marker distinct tag (soundcheck-style), casing-only mismatch
  with no set marker at all, and the XL-Center-style accidental-token case.
- Venue/city resolution reuses the same cache/heuristic/livephish-fallback
  code path — verify it's invoked once per directory (using the `I`-marked
  tag), not once per file.
- `discnumber` read-back verified explicitly on all three formats (FLAC,
  M4A, MP3) — not inferred from the write not raising.

## Known limitations

- Soundcheck tracks mixed into an otherwise-clean multi-set directory still
  force the whole directory into the anomaly bucket (no partial handling).
- `disctotal` is not written; a future pass could add it per-format if ever
  needed.
