# phish-rename Design

**Date:** 2026-05-01
**Status:** Approved

## Overview

`phish-rename` is a CLI tool that renames newly-downloaded Phish live show directories from a freeform date-prefixed format to the canonical LivePhish naming convention used by the rest of the collection.

**Input formats (non-conforming):**
```
YYYY-MM-DD <location string>
YYYY_MM_DD <location string>
```

**Output format (canonical):**
```
Phish-YYYY-MM-DD.Dot.Separated.Location.[LivePhishID]
```

Example: `2024-07-20 Mansfield MA` → `Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2260]`

---

## CLI

```
phish-rename PATH [--dry-run | --execute]
```

| Argument    | Description                                          |
|-------------|------------------------------------------------------|
| `PATH`      | Required. Directory containing show subdirectories.  |
| `--dry-run` | Default. Print planned renames, touch nothing.       |
| `--execute` | Perform the actual renames.                          |
| `-h/--help` | Show usage.                                          |

`PATH` is always required; there is no default.

---

## Architecture

Single Python script at `bin/phish-rename`. Follows the same single-file style as `phish-merge` and `phish-compare`. Dependencies: `requests`, `beautifulsoup4`.

### Functions

| Function | Purpose |
|---|---|
| `parse_args(argv)` | Parse CLI args; return `(path, dry_run)` |
| `date_from_dirname(dirname)` | Extract `YYYY-MM-DD` from `YYYY-MM-DD …` or `YYYY_MM_DD …`; return `None` if no match |
| `is_conforming(dirname)` | Return `True` if dirname already matches `Phish-YYYY-MM-DD.*\.\[\d+\]$` |
| `search_livephish(date)` | GET the search URL, return raw HTML |
| `parse_search_results(html)` | Parse HTML with BeautifulSoup; return list of `(release_id, location_str)` candidates |
| `pick_best_match(candidates)` | Select the right release; in practice the first result for a given date |
| `location_to_dots(location_str)` | Convert venue/city string to `Dot.Separated.Form` |
| `to_canonical_name(date, location, release_id)` | Assemble `Phish-{date}.{location}.[{release_id}]` |
| `main_logic(path, dry_run)` | Iterate directories; coordinate lookup and rename |
| `main()` | Entry point |

---

## Web Scraping

### Search endpoint

```
https://www.livephish.com/on/demandware.store/Sites-LivePhish-Site/default/Search-Show?search-button=&q={date}&lang=default
```

`{date}` is `YYYY-MM-DD`. The response is HTML containing product tiles for releases matching the search query.

### Parsing

BeautifulSoup parses the response HTML. From each product tile:
- **Release ID** — extracted from the product URL or a `data-` attribute on the tile element
- **Location string** — extracted from the product title (e.g., `"Phish Live at Xfinity Center, Mansfield, MA"`)

The scraping logic is isolated in `search_livephish()` so selector changes can be fixed in one place. The exact selectors will be determined during implementation by inspecting a live response.

### Rate limiting

`time.sleep(0.5)` between requests.

### Location normalization

The raw location string from livephish.com is normalized to dot-separated form:
1. Strip the `"Phish"` prefix and date/live boilerplate (e.g., `"Phish Live at "`)
2. Strip commas
3. Replace spaces with dots
4. Preserve state abbreviations as-is

Example: `"Phish Live at Xfinity Center, Mansfield, MA"` → `Xfinity.Center.Mansfield.MA`

---

## Directory Scanning

`main_logic` iterates the **top-level** entries of `PATH` (non-recursive). For each directory entry:

| Condition | Action |
|---|---|
| Already conforming (`Phish-YYYY-MM-DD.*.[####]`) | Skip silently |
| Date not extractable from name | Skip silently |
| Date found, livephish.com returns no match | Skip with warning |
| HTTP error / timeout | Skip with warning |
| Match found | Dry-run: print `mv {old} → {new}`; Execute: rename and print confirmation |

### Summary output

After processing all directories, print counts:
- Renamed
- Skipped (already conforming)
- Skipped (not found on livephish.com)
- Skipped (unrecognized name format)

---

## Error Handling

- HTTP errors (non-200 status, timeout) → skip the directory with a warning; do not abort the run
- No results from livephish.com for a date → skip with warning
- LivePhish only carries official soundboard recordings; multiple results for the same date are not expected but if they occur, the first result is used

---

## Testing

`tests/test_phish_rename.py` using pytest, matching the style of `tests/test_phish_merge.py`. All HTTP calls are mocked; no test hits livephish.com.

### Test coverage

| Area | Cases |
|---|---|
| `date_from_dirname()` | `YYYY-MM-DD` format, `YYYY_MM_DD` format, non-matching names return `None` |
| `is_conforming()` | Already-canonical names pass, old-format names fail |
| `location_to_dots()` | Comma stripping, space→dot, state abbreviation preservation, edge cases |
| `to_canonical_name()` | Full name assembly |
| `parse_search_results()` (via `search_livephish()`) | Fixture HTML → correct ID and location extracted |
| `main_logic()` dry-run | No filesystem changes; correct output printed |
| `main_logic()` execute | Directories renamed correctly |
| `main_logic()` skip conforming | Conforming dirs are left untouched |
| `main_logic()` not-found warning | Warning printed when livephish.com returns no match |

---

## Dependencies

```
requests
beautifulsoup4
```

Both are standard scraping dependencies. They should be documented in a `requirements.txt` or equivalent if one exists in the repo (currently there is none; one should be created).
