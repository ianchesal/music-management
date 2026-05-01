# phish-rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `bin/phish-rename`, a CLI tool that renames Phish live show directories from freeform `YYYY-MM-DD <location>` or `YYYY_MM_DD <location>` format to the canonical `Phish-YYYY-MM-DD.Dot.Separated.Location.[LivePhishID]` format by looking up each show on livephish.com.

**Architecture:** Single Python script at `bin/phish-rename` following the style of `phish-merge`. It reads directories from a given path, identifies non-conforming show dirs by date, queries the livephish.com search endpoint, parses the HTML response with BeautifulSoup to extract the release ID (from product URL `/LP-{id}.html`) and canonical location (from img alt text `"MM/DD/YY Venue, City, ST"`), then renames each directory.

**Tech Stack:** Python 3, `requests` (HTTP), `beautifulsoup4` (HTML parsing), pytest (tests)

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `requirements.txt` | Create | Pin `requests` and `beautifulsoup4` |
| `bin/phish-rename` | Create | Main CLI script |
| `tests/test_phish_rename.py` | Create | pytest test suite |

---

### Task 1: Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `bin/phish-rename`
- Create: `tests/test_phish_rename.py`

- [ ] **Step 1: Create requirements.txt**

Create `requirements.txt` at repo root with this exact content:

```
requests
beautifulsoup4
```

- [ ] **Step 2: Create the initial script scaffold**

Create `bin/phish-rename` with this content:

```python
#!/usr/bin/env python3
"""
phish-rename — Rename new Phish live show downloads to canonical LivePhish format.

Scans PATH for directories matching YYYY-MM-DD or YYYY_MM_DD naming patterns,
looks up each show on livephish.com, and renames to:
  Phish-YYYY-MM-DD.Dot.Separated.Location.[LivePhishID]

Usage:
  phish-rename PATH
  phish-rename PATH --dry-run
  phish-rename PATH --execute

Options:
  PATH          Directory containing show subdirectories (required)
  --dry-run     Print planned renames, touch nothing [default]
  --execute     Perform the actual renames
  -h, --help    Show this message
"""

import os
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ── Terminal ───────────────────────────────────────────────────────────────────

try:
    COLS = min(os.get_terminal_size().columns, 160)
except OSError:
    COLS = 120

USE_COLOR = sys.stdout.isatty()


def _ansi(code, s):
    return f"\033[{code}m{s}\033[0m" if USE_COLOR else s


def bold(s):   return _ansi("1",  s)
def dim(s):    return _ansi("2",  s)
def yellow(s): return _ansi("93", s)
def green(s):  return _ansi("92", s)


# ── Constants ──────────────────────────────────────────────────────────────────

SEARCH_URL = (
    "https://www.livephish.com/on/demandware.store/"
    "Sites-LivePhish-Site/default/Search-Show"
    "?search-button=&q={date}&lang=default"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
```

- [ ] **Step 3: Create the test harness**

Create `tests/test_phish_rename.py` with this content:

```python
import importlib.util
import sys
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


def load_module():
    from importlib.machinery import SourceFileLoader
    path = Path(__file__).parent.parent / "bin" / "phish-rename"
    loader = SourceFileLoader("phish_rename", str(path))
    spec = importlib.util.spec_from_loader("phish_rename", loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pr = load_module()
```

- [ ] **Step 4: Install dependencies**

```bash
pip install requests beautifulsoup4
```

- [ ] **Step 5: Verify the harness loads without error**

```bash
cd /home/ian/src/ianchesal/music-management
pytest tests/test_phish_rename.py -v
```

Expected: `no tests ran` (0 items collected, no import errors)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt bin/phish-rename tests/test_phish_rename.py
git commit -m "feat: scaffold phish-rename with test harness"
```

---

### Task 2: `date_from_dirname()` and `is_conforming()`

**Files:**
- Modify: `bin/phish-rename`
- Modify: `tests/test_phish_rename.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_phish_rename.py`:

```python
class TestDateFromDirname:
    def test_yyyy_dash_mm_dd(self):
        assert pr.date_from_dirname("2024-07-20 Xfinity Center Mansfield MA") == "2024-07-20"

    def test_yyyy_underscore_mm_dd(self):
        assert pr.date_from_dirname("2024_07_20 Xfinity Center Mansfield MA") == "2024-07-20"

    def test_single_digit_month(self):
        assert pr.date_from_dirname("1994_6_19 Somewhere") == "1994-06-19"

    def test_single_digit_day(self):
        assert pr.date_from_dirname("1994-12-6 Goleta, CA") == "1994-12-06"

    def test_conforming_name_returns_none(self):
        assert pr.date_from_dirname("Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]") is None

    def test_undated_returns_none(self):
        assert pr.date_from_dirname("Live Bait Vol 10") is None


class TestIsConforming:
    def test_canonical_name_is_conforming(self):
        assert pr.is_conforming("Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]") is True

    def test_old_dash_format_is_not_conforming(self):
        assert pr.is_conforming("2024-07-20 Mansfield MA") is False

    def test_missing_id_is_not_conforming(self):
        assert pr.is_conforming("Phish-2024-07-20.Xfinity.Center.Mansfield.MA") is False

    def test_underscore_format_is_not_conforming(self):
        assert pr.is_conforming("2024_07_20 Xfinity Center Mansfield MA") is False
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_phish_rename.py -v
```

Expected: `ERROR` — `AttributeError: module 'phish_rename' has no attribute 'date_from_dirname'`

- [ ] **Step 3: Add implementations to `bin/phish-rename`**

Add after the `HEADERS` constant block:

```python
# ── Core functions ─────────────────────────────────────────────────────────────

def date_from_dirname(dirname: str):
    m = re.match(r'^(\d{4})[-_](\d{1,2})[-_](\d{1,2})\b', dirname)
    if m:
        y, mo, d = m.group(1), int(m.group(2)), int(m.group(3))
        return f"{y}-{mo:02d}-{d:02d}"
    return None


def is_conforming(dirname: str) -> bool:
    return bool(re.match(r'^Phish-\d{4}-\d{2}-\d{2}\..+\.\[\d+\]$', dirname))
```

- [ ] **Step 4: Run to confirm passing**

```bash
pytest tests/test_phish_rename.py -v
```

Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add bin/phish-rename tests/test_phish_rename.py
git commit -m "feat: add date_from_dirname and is_conforming"
```

---

### Task 3: `location_to_dots()` and `to_canonical_name()`

**Files:**
- Modify: `bin/phish-rename`
- Modify: `tests/test_phish_rename.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_phish_rename.py`:

```python
class TestLocationToDots:
    def test_venue_city_state(self):
        assert pr.location_to_dots("Xfinity Center, Mansfield, MA") == "Xfinity.Center.Mansfield.MA"

    def test_multi_word_venue(self):
        assert pr.location_to_dots("Madison Square Garden, New York, NY") == "Madison.Square.Garden.New.York.NY"

    def test_trailing_space_stripped(self):
        assert pr.location_to_dots("Red Rocks Amphitheatre, Morrison, CO ") == "Red.Rocks.Amphitheatre.Morrison.CO"

    def test_times_union_center(self):
        assert pr.location_to_dots("Times Union Center, Albany, NY") == "Times.Union.Center.Albany.NY"


class TestToCanonicalName:
    def test_assembles_correctly(self):
        assert pr.to_canonical_name("2024-07-20", "Xfinity.Center.Mansfield.MA", "2259") == \
            "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]"

    def test_albany_show(self):
        assert pr.to_canonical_name("2009-11-27", "Times.Union.Center.Albany.NY", "515") == \
            "Phish-2009-11-27.Times.Union.Center.Albany.NY.[515]"
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_phish_rename.py -v
```

Expected: `ERROR` — `AttributeError: module 'phish_rename' has no attribute 'location_to_dots'`

- [ ] **Step 3: Add implementations to `bin/phish-rename`**

Add after `is_conforming`:

```python
def location_to_dots(location_str: str) -> str:
    name = location_str.strip()
    name = name.replace(",", "")
    name = re.sub(r"\s+", ".", name.strip())
    return name.strip(".")


def to_canonical_name(date: str, location: str, release_id: str) -> str:
    return f"Phish-{date}.{location}.[{release_id}]"
```

- [ ] **Step 4: Run to confirm passing**

```bash
pytest tests/test_phish_rename.py -v
```

Expected: `16 passed`

- [ ] **Step 5: Commit**

```bash
git add bin/phish-rename tests/test_phish_rename.py
git commit -m "feat: add location_to_dots and to_canonical_name"
```

---

### Task 4: `parse_search_results()`

**Files:**
- Modify: `bin/phish-rename`
- Modify: `tests/test_phish_rename.py`

The livephish.com search response contains `<a href="/LP-{id}.html">` tags. The ones wrapping an `<img>` are the product image links; the img's `alt` attribute is `"MM/DD/YY Venue, City, ST "`. 4K video variants include "4k" in their alt text and must be filtered out.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_phish_rename.py` (above the first `class` definition):

```python
FIXTURE_HTML_TWO_RESULTS = """
<html><body>
<a href="/LP-2259.html"><img alt="07/20/24 Xfinity Center, Mansfield, MA " title="..."></a>
<a href="/LP-2259.html">Phish</a>
<a href="/LP-2351.html"><img alt="07/20/24 Xfinity Center 4k, Mansfield 4k, MA " title="..."></a>
<a href="/LP-2351.html">Phish</a>
</body></html>
"""

FIXTURE_HTML_ONE_RESULT = """
<html><body>
<a href="/LP-515.html"><img alt="11/27/09 Times Union Center, Albany, NY " title="..."></a>
<a href="/LP-515.html">Phish</a>
</body></html>
"""

FIXTURE_HTML_NO_RESULTS = """
<html><body><p>No results found for your search.</p></body></html>
"""
```

Then add the test class:

```python
class TestParseSearchResults:
    def test_returns_non_4k_result(self):
        results = pr.parse_search_results(FIXTURE_HTML_TWO_RESULTS)
        assert len(results) == 1
        assert results[0] == ("2259", "Xfinity Center, Mansfield, MA")

    def test_filters_4k_results(self):
        results = pr.parse_search_results(FIXTURE_HTML_TWO_RESULTS)
        ids = [r[0] for r in results]
        assert "2351" not in ids

    def test_single_result(self):
        results = pr.parse_search_results(FIXTURE_HTML_ONE_RESULT)
        assert len(results) == 1
        assert results[0] == ("515", "Times Union Center, Albany, NY")

    def test_no_results_returns_empty(self):
        results = pr.parse_search_results(FIXTURE_HTML_NO_RESULTS)
        assert results == []

    def test_location_strips_date_prefix(self):
        results = pr.parse_search_results(FIXTURE_HTML_ONE_RESULT)
        _, location = results[0]
        assert not location.startswith("11/")
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_phish_rename.py -v
```

Expected: `ERROR` — `AttributeError: module 'phish_rename' has no attribute 'parse_search_results'`

- [ ] **Step 3: Add implementation to `bin/phish-rename`**

Add after `to_canonical_name`:

```python
def parse_search_results(html: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    candidates = []
    seen_ids = set()

    for a in soup.find_all("a", href=re.compile(r"^/LP-(\d+)\.html$")):
        img = a.find("img")
        if img is None:
            continue
        alt = img.get("alt", "").strip()
        if "4k" in alt.lower():
            continue
        m = re.search(r"/LP-(\d+)\.html", a["href"])
        if not m:
            continue
        release_id = m.group(1)
        if release_id in seen_ids:
            continue
        seen_ids.add(release_id)
        location_raw = re.sub(r"^\d{1,2}/\d{1,2}/\d{2,4}\s*", "", alt).strip()
        candidates.append((release_id, location_raw))

    return candidates
```

- [ ] **Step 4: Run to confirm passing**

```bash
pytest tests/test_phish_rename.py -v
```

Expected: `21 passed`

- [ ] **Step 5: Commit**

```bash
git add bin/phish-rename tests/test_phish_rename.py
git commit -m "feat: add parse_search_results with 4k filtering"
```

---

### Task 5: `search_livephish()` and `pick_best_match()`

**Files:**
- Modify: `bin/phish-rename`
- Modify: `tests/test_phish_rename.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_phish_rename.py`:

```python
class TestSearchLivephish:
    def test_calls_correct_url(self):
        mock_resp = MagicMock()
        mock_resp.text = FIXTURE_HTML_ONE_RESULT
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp) as mock_get:
            result = pr.search_livephish("2009-11-27")
        url = mock_get.call_args[0][0]
        assert "q=2009-11-27" in url
        assert result == FIXTURE_HTML_ONE_RESULT

    def test_raises_on_http_error(self):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("404")
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(Exception, match="404"):
                pr.search_livephish("2024-01-01")


class TestPickBestMatch:
    def test_returns_first_candidate(self):
        candidates = [("2259", "Xfinity Center, Mansfield, MA"), ("9999", "Other Venue")]
        assert pr.pick_best_match(candidates) == ("2259", "Xfinity Center, Mansfield, MA")

    def test_returns_none_for_empty(self):
        assert pr.pick_best_match([]) is None
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_phish_rename.py -v
```

Expected: `ERROR` — `AttributeError: module 'phish_rename' has no attribute 'search_livephish'`

- [ ] **Step 3: Add implementations to `bin/phish-rename`**

Add after `parse_search_results`:

```python
def search_livephish(date: str) -> str:
    url = SEARCH_URL.format(date=date)
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.text


def pick_best_match(candidates: list):
    return candidates[0] if candidates else None
```

- [ ] **Step 4: Run to confirm passing**

```bash
pytest tests/test_phish_rename.py -v
```

Expected: `25 passed`

- [ ] **Step 5: Commit**

```bash
git add bin/phish-rename tests/test_phish_rename.py
git commit -m "feat: add search_livephish and pick_best_match"
```

---

### Task 6: `main_logic()`

**Files:**
- Modify: `bin/phish-rename`
- Modify: `tests/test_phish_rename.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_phish_rename.py`:

```python
class TestMainLogic:
    def _make_dir(self, parent, name):
        d = Path(parent) / name
        d.mkdir()
        return d

    def test_dry_run_prints_rename_no_filesystem_change(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "2024-07-20 Xfinity Center Mansfield MA")
            with patch.object(pr, "search_livephish", return_value=FIXTURE_HTML_TWO_RESULTS):
                with patch("time.sleep"):
                    pr.main_logic(Path(tmp), dry_run=True)
            captured = capsys.readouterr()
            assert "DRY RUN" in captured.out
            assert "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]" in captured.out
            assert (Path(tmp) / "2024-07-20 Xfinity Center Mansfield MA").exists()

    def test_execute_renames_directory(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "2024-07-20 Xfinity Center Mansfield MA")
            with patch.object(pr, "search_livephish", return_value=FIXTURE_HTML_TWO_RESULTS):
                with patch("time.sleep"):
                    pr.main_logic(Path(tmp), dry_run=False)
            assert not (Path(tmp) / "2024-07-20 Xfinity Center Mansfield MA").exists()
            assert (Path(tmp) / "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]").exists()

    def test_skips_conforming_silently(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]")
            with patch.object(pr, "search_livephish") as mock_search:
                pr.main_logic(Path(tmp), dry_run=True)
            mock_search.assert_not_called()
            captured = capsys.readouterr()
            assert "DRY RUN" not in captured.out

    def test_warns_when_not_found(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "2024-07-20 Xfinity Center Mansfield MA")
            with patch.object(pr, "search_livephish", return_value=FIXTURE_HTML_NO_RESULTS):
                with patch("time.sleep"):
                    pr.main_logic(Path(tmp), dry_run=True)
            captured = capsys.readouterr()
            assert "not found" in captured.out

    def test_skips_unrecognized_silently(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "Live Bait Vol 10")
            with patch.object(pr, "search_livephish") as mock_search:
                pr.main_logic(Path(tmp), dry_run=True)
            mock_search.assert_not_called()

    def test_underscore_date_format(self, capsys):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_dir(tmp, "2024_07_20 Xfinity Center Mansfield MA")
            with patch.object(pr, "search_livephish", return_value=FIXTURE_HTML_TWO_RESULTS):
                with patch("time.sleep"):
                    pr.main_logic(Path(tmp), dry_run=False)
            assert (Path(tmp) / "Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]").exists()
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_phish_rename.py -v
```

Expected: `ERROR` — `AttributeError: module 'phish_rename' has no attribute 'main_logic'`

- [ ] **Step 3: Add implementation to `bin/phish-rename`**

Add after `pick_best_match`:

```python
# ── Main logic ─────────────────────────────────────────────────────────────────

def main_logic(path: Path, dry_run: bool):
    renamed = 0
    skipped_conforming = 0
    skipped_not_found = 0
    skipped_unrecognized = 0

    entries = sorted(path.iterdir(), key=lambda e: e.name.lower())
    for entry in entries:
        if not entry.is_dir() or entry.name.startswith('.'):
            continue

        if is_conforming(entry.name):
            skipped_conforming += 1
            continue

        date = date_from_dirname(entry.name)
        if date is None:
            skipped_unrecognized += 1
            continue

        try:
            html = search_livephish(date)
            time.sleep(0.5)
        except Exception as e:
            print(f"  {yellow('WARN')} {entry.name}: HTTP error — {e}", file=sys.stderr)
            skipped_not_found += 1
            continue

        candidates = parse_search_results(html)
        match = pick_best_match(candidates)

        if match is None:
            print(f"  {yellow('WARN')} {entry.name}: not found on livephish.com")
            skipped_not_found += 1
            continue

        release_id, location_raw = match
        location = location_to_dots(location_raw)
        new_name = to_canonical_name(date, location, release_id)

        src = path / entry.name
        dst = path / new_name

        if dry_run:
            print(f"  [DRY RUN] mv {entry.name} → {new_name}")
        else:
            print(f"  Renaming  {entry.name} → {new_name}")
            src.rename(dst)
        renamed += 1

    print()
    print(f"  {bold('SUMMARY')}")
    print(f"  {green(str(renamed))}  renamed")
    print(f"  {dim(str(skipped_conforming))}  skipped (already conforming)")
    print(f"  {yellow(str(skipped_not_found))}  skipped (not found on livephish.com)")
    print(f"  {dim(str(skipped_unrecognized))}  skipped (unrecognized format)")
    print()
```

- [ ] **Step 4: Run to confirm passing**

```bash
pytest tests/test_phish_rename.py -v
```

Expected: `31 passed`

- [ ] **Step 5: Commit**

```bash
git add bin/phish-rename tests/test_phish_rename.py
git commit -m "feat: add main_logic with dry-run support"
```

---

### Task 7: `parse_args()`, `main()`, and final wiring

**Files:**
- Modify: `bin/phish-rename`
- Modify: `tests/test_phish_rename.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_phish_rename.py`:

```python
class TestParseArgs:
    def test_path_and_dry_run_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, dry_run = pr.parse_args(["phish-rename", tmp])
        assert str(path) == tmp
        assert dry_run is True

    def test_explicit_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, dry_run = pr.parse_args(["phish-rename", tmp, "--dry-run"])
        assert dry_run is True

    def test_execute_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, dry_run = pr.parse_args(["phish-rename", tmp, "--execute"])
        assert dry_run is False

    def test_missing_path_exits(self):
        with pytest.raises(SystemExit):
            pr.parse_args(["phish-rename"])

    def test_nonexistent_path_exits(self):
        with pytest.raises(SystemExit):
            pr.parse_args(["phish-rename", "/nonexistent/path/xyz"])

    def test_unknown_arg_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(SystemExit):
                pr.parse_args(["phish-rename", tmp, "--unknown"])
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_phish_rename.py -v
```

Expected: `ERROR` — `AttributeError: module 'phish_rename' has no attribute 'parse_args'`

- [ ] **Step 3: Add `parse_args` and `main` to `bin/phish-rename`**

Add after `main_logic`:

```python
# ── Argument parsing ───────────────────────────────────────────────────────────

def parse_args(argv):
    path = None
    dry_run = True

    args = argv[1:]
    i = 0
    while i < len(args):
        if args[i] in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        elif args[i] == "--dry-run":
            dry_run = True
            i += 1
        elif args[i] == "--execute":
            dry_run = False
            i += 1
        elif not args[i].startswith("-"):
            path = Path(args[i])
            i += 1
        else:
            print(f"Unknown argument: {args[i]}", file=sys.stderr)
            sys.exit(1)

    if path is None:
        print("Error: PATH is required", file=sys.stderr)
        sys.exit(1)

    if not path.exists():
        print(f"Error: PATH does not exist: {path}", file=sys.stderr)
        sys.exit(1)

    return path, dry_run


def main():
    path, dry_run = parse_args(sys.argv)
    mode = "DRY RUN" if dry_run else "EXECUTE"
    print(f"\n  {bold('PHISH RENAME')}  [{mode}]")
    print(f"  {dim('Path:')}  {path}")
    print()
    main_logic(path, dry_run)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to confirm passing**

```bash
pytest tests/test_phish_rename.py -v
```

Expected: `37 passed`

- [ ] **Step 5: Make the script executable**

```bash
chmod +x bin/phish-rename
```

- [ ] **Step 6: Smoke test against livephish.com**

```bash
mkdir -p /tmp/phish-test-shows
mkdir "/tmp/phish-test-shows/2024-07-20 Xfinity Center Mansfield MA"
bin/phish-rename /tmp/phish-test-shows --dry-run
```

Expected output (dry-run, no filesystem changes):
```
  PHISH RENAME  [DRY RUN]
  Path:  /tmp/phish-test-shows

  [DRY RUN] mv 2024-07-20 Xfinity Center Mansfield MA → Phish-2024-07-20.Xfinity.Center.Mansfield.MA.[2259]

  SUMMARY
  1  renamed
  0  skipped (already conforming)
  0  skipped (not found on livephish.com)
  0  skipped (unrecognized format)
```

Clean up: `rm -rf /tmp/phish-test-shows`

- [ ] **Step 7: Commit**

```bash
git add bin/phish-rename tests/test_phish_rename.py
git commit -m "feat: complete phish-rename with arg parsing and main entry point"
```
