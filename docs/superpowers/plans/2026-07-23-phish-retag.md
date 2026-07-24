# phish-retag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `bin/phish-retag`, a dry-run-by-default tool that normalizes the album tag on every audio file in canonical Phish show directories to `YYYY/MM/DD Venue, City, ST`, derived from the directory name.

**Architecture:** Single Python script in `bin/` (no `.py` extension) following the `phish-rename` house style. Per directory: parse the canonical name, skip multi-set dirs (>1 distinct album tag), resolve the venue/city boundary (cache → offline tag heuristic → livephish.com search fallback with jitter), validate every resolution with a `location_to_dots` round-trip invariant, then rewrite only the `album` tag via mutagen's easy interface.

**Tech Stack:** Python 3, mutagen (new dep), requests + beautifulsoup4 (existing), pytest with ffmpeg-generated audio fixtures.

**Spec:** `docs/superpowers/specs/2026-07-23-phish-retag-design.md`

## Global Constraints

- Script is `bin/phish-retag`, executable, no `.py` extension, shebang `#!/usr/bin/env python3`.
- Only the album tag is ever written; no other metadata, ever. Files already correct are not rewritten (preserves mtimes).
- Dry run is the default; `--execute` applies. Dry run performs full resolution including livephish queries and cache writes.
- Multi-set directories (more than one distinct album tag among audio files) are skipped with a warning listing the distinct tags.
- livephish requests use a randomized `time.sleep(random.uniform(0.5, 1.5))` after every request.
- Round-trip invariant (hard rule): a resolution is used only if `dot_normalize(location_to_dots(resolved)) == dot_normalize(location_dots)`.
- The tool never guesses: any resolution failure → *unresolved*, listed in the summary.
- Default collection path: `/data/media/Sorted/Unsorted/Music/Phish`. Default cache: `$XDG_CACHE_HOME/phish-retag.json`, falling back to `~/.cache/phish-retag.json`.
- Audio formats: `.flac`, `.m4a`, `.mp3` (case-insensitive), found recursively within each show dir.
- No live HTTP in tests. All network access mocked with `unittest.mock`.
- House test convention: load the script via `SourceFileLoader` (see `tests/test_phish_rename.py:9-19`).
- Run tests with `pytest tests/test_phish_retag.py -v` per task; full suite (`cd tests && bats *.bats && cd .. && pytest tests/`) before finishing.
- Commits on branch `ian/phish-retag`, message style `feat:`/`test:`/`docs:`, each ending with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## File Structure

- Create: `bin/phish-retag` — the whole tool (single file, house style; helpers deliberately duplicated from `phish-rename` because `bin/` tools are standalone scripts — that is the existing pattern).
- Create: `tests/test_phish_retag.py` — all pytest coverage for the tool.
- Modify: `requirements.txt` — add `mutagen`.
- Modify: `CLAUDE.md` — tool list, commands, dependencies, file structure.

---

### Task 1: Skeleton, dependency, and directory-name parsing

**Files:**
- Modify: `requirements.txt`
- Create: `bin/phish-retag`
- Create: `tests/test_phish_retag.py`

**Interfaces:**
- Produces: `parse_show_dirname(dirname: str) -> tuple[str, str, str] | None` returning `(date "YYYY-MM-DD", location_dots, release_id)`; `location_to_dots(location_str: str) -> str`; `dot_normalize(s: str) -> str`; module constants `SEARCH_URL`, `HEADERS`, `DEFAULT_PATH`, `AUDIO_EXTS`.

- [ ] **Step 1: Add mutagen to requirements.txt and install**

`requirements.txt` becomes:

```
requests
beautifulsoup4
mutagen
```

Run: `pip install -r requirements.txt`
Expected: `mutagen` installs successfully (verify with `python3 -c "import mutagen; print(mutagen.version_string)"`).

- [ ] **Step 2: Write the failing tests**

Create `tests/test_phish_retag.py`:

```python
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import mutagen
import pytest


def load_module():
    from importlib.machinery import SourceFileLoader
    path = Path(__file__).parent.parent / "bin" / "phish-retag"
    loader = SourceFileLoader("phish_retag", str(path))
    spec = importlib.util.spec_from_loader("phish_retag", loader)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pt = load_module()


class TestParseShowDirname:
    def test_canonical_name(self):
        assert pt.parse_show_dirname(
            "Phish-2026-07-22.Madison.Square.Garden.New.York.NY.[2761]"
        ) == ("2026-07-22", "Madison.Square.Garden.New.York.NY", "2761")

    def test_international_show(self):
        assert pt.parse_show_dirname(
            "Phish-2026-01-28.Moon.Palace.Resort.Riviera.Maya.MX.[2675]"
        ) == ("2026-01-28", "Moon.Palace.Resort.Riviera.Maya.MX", "2675")

    def test_non_two_letter_ending_still_parses(self):
        assert pt.parse_show_dirname(
            "Phish-2000-06-14.Drum.Logos.Fukuoka.Japan.[123]"
        ) == ("2000-06-14", "Drum.Logos.Fukuoka.Japan", "123")

    def test_live_bait_returns_none(self):
        assert pt.parse_show_dirname("Live Bait Vol. 09") is None

    def test_missing_id_returns_none(self):
        assert pt.parse_show_dirname("Phish-2024-07-20.Xfinity.Center.Mansfield.MA") is None

    def test_undated_returns_none(self):
        assert pt.parse_show_dirname("A Live One") is None


class TestLocationToDots:
    def test_venue_city_state(self):
        assert pt.location_to_dots("Xfinity Center, Mansfield, MA") == "Xfinity.Center.Mansfield.MA"

    def test_dotted_city_produces_double_dot(self):
        assert pt.location_to_dots("Chaifetz Arena, St. Louis, MO") == "Chaifetz.Arena.St..Louis.MO"


class TestDotNormalize:
    def test_collapses_repeated_dots(self):
        assert pt.dot_normalize("St..Louis.MO") == "St.Louis.MO"

    def test_leaves_single_dots_alone(self):
        assert pt.dot_normalize("New.York.NY") == "New.York.NY"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_phish_retag.py -v`
Expected: FAIL — the loader cannot find `bin/phish-retag` (FileNotFoundError) or, once the file exists empty, `AttributeError`.

- [ ] **Step 4: Write the skeleton implementation**

Create `bin/phish-retag` (mark executable):

```python
#!/usr/bin/env python3
"""
phish-retag — Normalize album tags on Phish show audio files.

Scans PATH for canonical show directories
(Phish-YYYY-MM-DD.Dot.Separated.Location.[LivePhishID]) and rewrites the
album tag on every audio file to:
  YYYY/MM/DD Venue, City, ST

Only the album tag is touched. Multi-set directories (more than one distinct
album tag) are skipped with a warning. Venue/city boundaries are resolved
from existing tags when possible, falling back to livephish.com; results are
cached so repeat runs make no network requests.

Usage:
  phish-retag [PATH]
  phish-retag [PATH] --execute
  phish-retag [PATH] --cache FILE

Options:
  PATH          Collection directory [default: /data/media/Sorted/Unsorted/Music/Phish]
  --execute     Apply tag changes (default is dry run)
  --cache FILE  Location cache [default: $XDG_CACHE_HOME/phish-retag.json]
  -h, --help    Show this message
"""

import json
import os
import random
import re
import sys
import time
from pathlib import Path

import mutagen
import requests
from bs4 import BeautifulSoup

# ── Terminal ───────────────────────────────────────────────────────────────────

USE_COLOR = sys.stdout.isatty()


def _ansi(code, s):
    return f"\033[{code}m{s}\033[0m" if USE_COLOR else s


def bold(s):   return _ansi("1",  s)
def dim(s):    return _ansi("2",  s)
def yellow(s): return _ansi("93", s)
def green(s):  return _ansi("92", s)


# ── Constants ──────────────────────────────────────────────────────────────────

DEFAULT_PATH = Path("/data/media/Sorted/Unsorted/Music/Phish")

AUDIO_EXTS = {".flac", ".m4a", ".mp3"}

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

SHOW_DIR_RE = re.compile(r"^Phish-(\d{4}-\d{2}-\d{2})\.(.+)\.\[(\d+)\]$")

# ── Name parsing ───────────────────────────────────────────────────────────────

def parse_show_dirname(dirname: str):
    """Return (date, location_dots, release_id) for a canonical show dir, else None."""
    m = SHOW_DIR_RE.match(dirname)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def location_to_dots(location_str: str) -> str:
    # Same transform phish-rename uses to build directory names.
    name = location_str.strip()
    name = name.replace(",", "")
    name = re.sub(r"\s+", ".", name.strip())
    return name.strip(".")


def dot_normalize(s: str) -> str:
    # "St. Louis" dots to "St..Louis" while directory names carry "St.Louis";
    # collapse runs so the two compare equal.
    return re.sub(r"\.{2,}", ".", s)


def main():
    pass


if __name__ == "__main__":
    main()
```

Run: `chmod +x bin/phish-retag`

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_phish_retag.py -v`
Expected: 10 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add requirements.txt bin/phish-retag tests/test_phish_retag.py
git commit -m "feat: add phish-retag skeleton with dirname parsing

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Offline venue/city heuristic and round-trip invariant

**Files:**
- Modify: `bin/phish-retag` (append after `dot_normalize`)
- Modify: `tests/test_phish_retag.py` (append)

**Interfaces:**
- Consumes: `location_to_dots`, `dot_normalize` (Task 1).
- Produces: `split_venue_city(location_dots: str, album_tag: str | None) -> str | None` returning `"Venue, City, ST"`; `round_trip_ok(resolved: str, location_dots: str) -> bool`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_phish_retag.py`:

```python
class TestSplitVenueCity:
    def test_simple_city(self):
        assert pt.split_venue_city(
            "Ruoff.Music.Center.Noblesville.IN", "2026/07/12 Noblesville, IN"
        ) == "Ruoff Music Center, Noblesville, IN"

    def test_multi_word_city_longest_match_wins(self):
        # Shortest-suffix matching would wrongly split "...Garden New, York, NY".
        assert pt.split_venue_city(
            "Madison.Square.Garden.New.York.NY", "2026/07/22 New York, NY"
        ) == "Madison Square Garden, New York, NY"

    def test_mexico_show(self):
        assert pt.split_venue_city(
            "Moon.Palace.Resort.Riviera.Maya.MX", "2026/01/28 Riviera Maya, MX"
        ) == "Moon Palace Resort, Riviera Maya, MX"

    def test_messy_tag_with_prefix_and_trailing_junk(self):
        assert pt.split_venue_city(
            "Empower.Federal.Credit.Union.Amphitheater.at.Lakeview.Syracuse.NY",
            "Phish - Phish - 2026_07_21 Syracuse, NY (Phis)",
        ) == "Empower Federal Credit Union Amphitheater at Lakeview, Syracuse, NY"

    def test_set_numeral_tag(self):
        assert pt.split_venue_city(
            "Providence.Civic.Center.Providence.RI", "1994/12/29 I Providence, RI"
        ) == "Providence Civic Center, Providence, RI"

    def test_two_comma_tag_city_is_last_segment(self):
        # City must be "Hampton", not "Hampton Coliseum, Hampton".
        assert pt.split_venue_city(
            "Hampton.Coliseum.Hampton.VA", "1997/11/22 Hampton Coliseum, Hampton, VA"
        ) == "Hampton Coliseum, Hampton, VA"

    def test_dotted_city_st_louis(self):
        assert pt.split_venue_city(
            "Chaifetz.Arena.St.Louis.MO", "2024/07/30 St. Louis, MO"
        ) == "Chaifetz Arena, St. Louis, MO"

    def test_state_mismatch_returns_none(self):
        assert pt.split_venue_city(
            "Ruoff.Music.Center.Noblesville.IN", "2026/07/12 Noblesville, NY"
        ) is None

    def test_city_not_in_dirname_returns_none(self):
        assert pt.split_venue_city(
            "Ruoff.Music.Center.Noblesville.IN", "2026/07/12 Indianapolis, IN"
        ) is None

    def test_non_two_letter_ending_returns_none(self):
        assert pt.split_venue_city(
            "Drum.Logos.Fukuoka.Japan", "2000/06/14 Fukuoka, Japan"
        ) is None

    def test_no_tag_returns_none(self):
        assert pt.split_venue_city("Ruoff.Music.Center.Noblesville.IN", None) is None
        assert pt.split_venue_city("Ruoff.Music.Center.Noblesville.IN", "") is None

    def test_empty_venue_returns_none(self):
        # The whole location is the city — no venue to split off.
        assert pt.split_venue_city("Noblesville.IN", "2026/07/12 Noblesville, IN") is None


class TestRoundTripOk:
    def test_exact_round_trip(self):
        assert pt.round_trip_ok(
            "Madison Square Garden, New York, NY",
            "Madison.Square.Garden.New.York.NY",
        ) is True

    def test_dotted_city_round_trip(self):
        assert pt.round_trip_ok(
            "Chaifetz Arena, St. Louis, MO", "Chaifetz.Arena.St.Louis.MO"
        ) is True

    def test_wrong_location_fails(self):
        assert pt.round_trip_ok(
            "Hampton Coliseum, Hampton, VA", "Madison.Square.Garden.New.York.NY"
        ) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_phish_retag.py -v -k "SplitVenueCity or RoundTrip"`
Expected: FAIL with `AttributeError: module 'phish_retag' has no attribute 'split_venue_city'`.

- [ ] **Step 3: Implement**

Append to `bin/phish-retag` after `dot_normalize`:

```python
# ── Venue/city resolution ──────────────────────────────────────────────────────

# Last "<segment>, XX" in a tag: the city candidate and its state/country code.
CITY_STATE_RE = re.compile(r"([^,]+),\s*([A-Z]{2})(?![A-Za-z])")


def split_venue_city(location_dots: str, album_tag):
    """Split a dot-separated location into "Venue, City, ST" using the City, ST
    already present in an album tag. Returns None when the tag doesn't yield a
    usable, verifiable split (caller falls back to livephish)."""
    m = re.match(r"^(.+)\.([A-Z]{2})$", location_dots)
    if not m:
        return None
    loc_head, state = m.group(1), m.group(2)

    matches = CITY_STATE_RE.findall(album_tag or "")
    if not matches:
        return None
    city_text, tag_state = matches[-1]
    if tag_state != state:
        return None

    norm_head = dot_normalize(loc_head)
    # The tag's city segment may carry prefix junk ("Phish - 2026_07_21 Syracuse").
    # Try the longest word-suffix first so multi-word cities win over their own
    # tails ("New York" must beat "York").
    words = city_text.split()
    for start in range(len(words)):
        candidate = " ".join(words[start:]).strip()
        city_dots = dot_normalize(location_to_dots(candidate))
        if not city_dots:
            continue
        if norm_head == city_dots:
            return None  # venue would be empty
        if norm_head.endswith("." + city_dots):
            venue = norm_head[: -(len(city_dots) + 1)].replace(".", " ")
            return f"{venue}, {candidate}, {state}"
    return None


def round_trip_ok(resolved: str, location_dots: str) -> bool:
    """Hard invariant: re-dotting the resolved location must reproduce the
    directory's location string — that is exactly how dir names were built."""
    return dot_normalize(location_to_dots(resolved)) == dot_normalize(location_dots)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_phish_retag.py -v`
Expected: all tests PASS (Task 1's included).

- [ ] **Step 5: Commit**

```bash
git add bin/phish-retag tests/test_phish_retag.py
git commit -m "feat: add offline venue/city heuristic with round-trip invariant

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Location cache

**Files:**
- Modify: `bin/phish-retag` (append)
- Modify: `tests/test_phish_retag.py` (append)

**Interfaces:**
- Produces: `default_cache_path() -> Path`; `load_cache(path: Path) -> dict`; `save_cache(path: Path, cache: dict) -> None`. Cache maps release_id (str) → resolved location (str).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_phish_retag.py`:

```python
class TestCache:
    def test_default_path_honors_xdg_cache_home(self, monkeypatch, tmp_path):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        assert pt.default_cache_path() == tmp_path / "phish-retag.json"

    def test_default_path_falls_back_to_home_cache(self, monkeypatch):
        monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
        assert pt.default_cache_path() == Path.home() / ".cache" / "phish-retag.json"

    def test_round_trip(self, tmp_path):
        cache_file = tmp_path / "sub" / "cache.json"
        pt.save_cache(cache_file, {"2761": "Madison Square Garden, New York, NY"})
        assert pt.load_cache(cache_file) == {"2761": "Madison Square Garden, New York, NY"}

    def test_missing_file_returns_empty(self, tmp_path):
        assert pt.load_cache(tmp_path / "nope.json") == {}

    def test_corrupt_file_returns_empty(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        assert pt.load_cache(bad) == {}

    def test_non_dict_json_returns_empty(self, tmp_path):
        bad = tmp_path / "list.json"
        bad.write_text("[1, 2]")
        assert pt.load_cache(bad) == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_phish_retag.py -v -k TestCache`
Expected: FAIL with `AttributeError: ... no attribute 'default_cache_path'`.

- [ ] **Step 3: Implement**

Append to `bin/phish-retag`:

```python
# ── Cache ──────────────────────────────────────────────────────────────────────

def default_cache_path() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "phish-retag.json"


def load_cache(path: Path) -> dict:
    try:
        with open(path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_cache(path: Path, cache: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w") as f:
        json.dump(cache, f, indent=2, sort_keys=True)
    tmp.replace(path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_phish_retag.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bin/phish-retag tests/test_phish_retag.py
git commit -m "feat: add phish-retag location cache with XDG default path

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: livephish.com fallback with jitter

**Files:**
- Modify: `bin/phish-retag` (append)
- Modify: `tests/test_phish_retag.py` (append)

**Interfaces:**
- Consumes: `SEARCH_URL`, `HEADERS` (Task 1).
- Produces: `search_livephish(date: str) -> str` (HTML); `parse_search_results(html: str) -> list[tuple[str, str]]` of `(release_id, location_raw)`; `livephish_location(date: str, release_id: str) -> str | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_phish_retag.py`. The HTML fixture mirrors the real livephish markup already proven in `tests/test_phish_rename.py`:

```python
FIXTURE_HTML_SEARCH = """
<html><body>
<a href="/LP-2761.html"><img alt="07/22/26 Madison Square Garden, New York, NY " title="..."></a>
<a href="/LP-2761.html">Phish</a>
<a href="/LP-2762.html"><img alt="07/22/26 Madison Square Garden 4k, New York 4k, NY " title="..."></a>
<a href="/LP-2762.html">Phish</a>
<a href="/LP-9999.html"><img alt="07/22/26 Some Other Venue, Elsewhere, CA " title="..."></a>
<a href="/LP-9999.html">Phish</a>
</body></html>
"""


class TestLivephishLocation:
    def test_returns_location_for_matching_id(self):
        with patch.object(pt, "search_livephish", return_value=FIXTURE_HTML_SEARCH), \
             patch.object(pt.time, "sleep") as mock_sleep:
            loc = pt.livephish_location("2026-07-22", "2761")
        assert loc == "Madison Square Garden, New York, NY"
        mock_sleep.assert_called_once()

    def test_jitter_delay_is_within_bounds(self):
        with patch.object(pt, "search_livephish", return_value=FIXTURE_HTML_SEARCH), \
             patch.object(pt.time, "sleep") as mock_sleep:
            pt.livephish_location("2026-07-22", "2761")
        (delay,), _ = mock_sleep.call_args
        assert 0.5 <= delay <= 1.5

    def test_no_matching_id_returns_none(self):
        with patch.object(pt, "search_livephish", return_value=FIXTURE_HTML_SEARCH), \
             patch.object(pt.time, "sleep"):
            assert pt.livephish_location("2026-07-22", "1234") is None

    def test_http_error_returns_none(self):
        with patch.object(pt, "search_livephish", side_effect=Exception("boom")), \
             patch.object(pt.time, "sleep") as mock_sleep:
            assert pt.livephish_location("2026-07-22", "2761") is None
        mock_sleep.assert_called_once()  # still polite after a failed request

    def test_4k_variants_are_skipped(self):
        with patch.object(pt, "search_livephish", return_value=FIXTURE_HTML_SEARCH), \
             patch.object(pt.time, "sleep"):
            assert pt.livephish_location("2026-07-22", "2762") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_phish_retag.py -v -k TestLivephishLocation`
Expected: FAIL with `AttributeError: ... no attribute 'livephish_location'`.

- [ ] **Step 3: Implement**

Append to `bin/phish-retag`. `search_livephish` and `parse_search_results` are copied verbatim from `bin/phish-rename:90-116` (standalone-script house pattern):

```python
# ── livephish.com fallback ─────────────────────────────────────────────────────

def search_livephish(date: str) -> str:
    url = SEARCH_URL.format(date=date)
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.text


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
        release_id = re.search(r"/LP-(\d+)\.html", a["href"]).group(1)
        if release_id in seen_ids:
            continue
        seen_ids.add(release_id)
        location_raw = re.sub(r"^\d{1,2}/\d{1,2}/\d{2,4}\s*", "", alt).strip()
        candidates.append((release_id, location_raw))

    return candidates


def livephish_location(date: str, release_id: str):
    """Search livephish by date and return the location string for release_id,
    or None. Sleeps a jittered 0.5-1.5s after every request."""
    try:
        html = search_livephish(date)
    except Exception as e:
        print(f"  {yellow('WARN')} {date}: livephish HTTP error — {e}", file=sys.stderr)
        return None
    finally:
        time.sleep(random.uniform(0.5, 1.5))

    for cand_id, location_raw in parse_search_results(html):
        if cand_id == release_id:
            return location_raw
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_phish_retag.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bin/phish-retag tests/test_phish_retag.py
git commit -m "feat: add livephish fallback lookup with jittered rate limiting

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Resolution orchestrator and target album

**Files:**
- Modify: `bin/phish-retag` (append)
- Modify: `tests/test_phish_retag.py` (append)

**Interfaces:**
- Consumes: `split_venue_city`, `round_trip_ok` (Task 2); `load_cache`/`save_cache` (Task 3); `livephish_location` (Task 4).
- Produces: `resolve_location(date: str, location_dots: str, release_id: str, album_tag: str | None, cache: dict, cache_path: Path) -> str | None` (mutates `cache` and persists on success); `target_album(date: str, location: str) -> str`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_phish_retag.py`:

```python
class TestTargetAlbum:
    def test_formats_date_with_slashes(self):
        assert pt.target_album("2026-07-22", "Madison Square Garden, New York, NY") \
            == "2026/07/22 Madison Square Garden, New York, NY"


class TestResolveLocation:
    LOC = "Madison.Square.Garden.New.York.NY"
    RESOLVED = "Madison Square Garden, New York, NY"

    def test_valid_cache_hit_skips_network(self, tmp_path):
        cache = {"2761": self.RESOLVED}
        with patch.object(pt, "livephish_location") as mock_lp:
            out = pt.resolve_location("2026-07-22", self.LOC, "2761",
                                      None, cache, tmp_path / "c.json")
        assert out == self.RESOLVED
        mock_lp.assert_not_called()

    def test_stale_cache_entry_is_discarded_and_reresolved(self, tmp_path):
        cache = {"2761": "Wrong Venue, Elsewhere, CA"}
        with patch.object(pt, "livephish_location", return_value=self.RESOLVED):
            out = pt.resolve_location("2026-07-22", self.LOC, "2761",
                                      None, cache, tmp_path / "c.json")
        assert out == self.RESOLVED
        assert cache["2761"] == self.RESOLVED

    def test_heuristic_resolves_offline(self, tmp_path):
        cache = {}
        with patch.object(pt, "livephish_location") as mock_lp:
            out = pt.resolve_location("2026-07-22", self.LOC, "2761",
                                      "2026/07/22 New York, NY", cache,
                                      tmp_path / "c.json")
        assert out == self.RESOLVED
        mock_lp.assert_not_called()

    def test_resolution_is_persisted_to_cache_file(self, tmp_path):
        cache_file = tmp_path / "c.json"
        pt.resolve_location("2026-07-22", self.LOC, "2761",
                            "2026/07/22 New York, NY", {}, cache_file)
        assert json.loads(cache_file.read_text())["2761"] == self.RESOLVED

    def test_falls_back_to_livephish_when_heuristic_fails(self, tmp_path):
        with patch.object(pt, "livephish_location", return_value=self.RESOLVED) as mock_lp:
            out = pt.resolve_location("2026-07-22", self.LOC, "2761",
                                      "garbage tag", {}, tmp_path / "c.json")
        assert out == self.RESOLVED
        mock_lp.assert_called_once_with("2026-07-22", "2761")

    def test_livephish_result_failing_round_trip_is_unresolved(self, tmp_path):
        with patch.object(pt, "livephish_location",
                          return_value="Some Other Place, Elsewhere, CA"):
            assert pt.resolve_location("2026-07-22", self.LOC, "2761",
                                       None, {}, tmp_path / "c.json") is None

    def test_livephish_miss_is_unresolved(self, tmp_path):
        with patch.object(pt, "livephish_location", return_value=None):
            assert pt.resolve_location("2026-07-22", self.LOC, "2761",
                                       None, {}, tmp_path / "c.json") is None

    def test_non_two_letter_ending_uses_livephish(self, tmp_path):
        loc = "Drum.Logos.Fukuoka.Japan"
        resolved = "Drum Logos, Fukuoka, Japan"
        with patch.object(pt, "livephish_location", return_value=resolved):
            out = pt.resolve_location("2000-06-14", loc, "123",
                                      "2000/06/14 Fukuoka, Japan", {},
                                      tmp_path / "c.json")
        assert out == resolved
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_phish_retag.py -v -k "TestResolveLocation or TestTargetAlbum"`
Expected: FAIL with `AttributeError: ... no attribute 'resolve_location'`.

- [ ] **Step 3: Implement**

Append to `bin/phish-retag`:

```python
def resolve_location(date: str, location_dots: str, release_id: str,
                     album_tag, cache: dict, cache_path: Path):
    """Resolve the comma-separated location for a show. Order: cache →
    offline tag heuristic → livephish. Every result must pass the round-trip
    invariant; failures return None (unresolved). Successes are persisted to
    the cache immediately."""
    cached = cache.get(release_id)
    if cached is not None:
        if round_trip_ok(cached, location_dots):
            return cached
        del cache[release_id]  # stale entry for this directory — re-resolve

    resolved = split_venue_city(location_dots, album_tag)
    if resolved is None:
        resolved = livephish_location(date, release_id)

    if resolved is None or not round_trip_ok(resolved, location_dots):
        return None

    cache[release_id] = resolved
    save_cache(cache_path, cache)
    return resolved


def target_album(date: str, location: str) -> str:
    return f"{date.replace('-', '/')} {location}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_phish_retag.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add bin/phish-retag tests/test_phish_retag.py
git commit -m "feat: add location resolution orchestrator with cache persistence

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Tag I/O via mutagen and audio fixtures

**Files:**
- Modify: `bin/phish-retag` (append)
- Modify: `tests/test_phish_retag.py` (append)

**Interfaces:**
- Produces: `collect_audio(dir_path: Path) -> list[Path]` (sorted, recursive); `read_album(path: Path) -> str | None` (None = unreadable, `""` = no album tag); `write_album(path: Path, album: str) -> bool` (False = unreadable).
- Test helpers other tests reuse: session fixture `audio_fixtures` (dict ext → Path) and `make_show_file(fixtures, dest_dir, name, album=None)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_phish_retag.py`:

```python
# ── Audio fixtures ─────────────────────────────────────────────────────────────
# mutagen can only edit existing containers, not create them; generate tiny
# real files once per session with ffmpeg (a required repo dependency).

@pytest.fixture(scope="session")
def audio_fixtures(tmp_path_factory):
    src = tmp_path_factory.mktemp("audio-fixtures")
    paths = {}
    for ext in ("flac", "m4a", "mp3"):
        out = src / f"fixture.{ext}"
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
             "-i", "anullsrc=r=8000:cl=mono", "-t", "0.1", str(out)],
            check=True, capture_output=True,
        )
        paths[ext] = out
    return paths


def make_show_file(fixtures, dest_dir, name, album=None):
    dest = Path(dest_dir) / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixtures[name.rsplit(".", 1)[1]], dest)
    if album is not None:
        audio = mutagen.File(str(dest), easy=True)
        if audio.tags is None:
            audio.add_tags()
        audio["album"] = album
        audio.save()
    return dest


class TestTagIO:
    @pytest.mark.parametrize("ext", ["flac", "m4a", "mp3"])
    def test_write_then_read_album(self, audio_fixtures, tmp_path, ext):
        f = make_show_file(audio_fixtures, tmp_path, f"track.{ext}")
        assert pt.write_album(f, "2026/07/22 Madison Square Garden, New York, NY") is True
        assert pt.read_album(f) == "2026/07/22 Madison Square Garden, New York, NY"

    @pytest.mark.parametrize("ext", ["flac", "m4a", "mp3"])
    def test_missing_album_reads_empty_string(self, audio_fixtures, tmp_path, ext):
        f = make_show_file(audio_fixtures, tmp_path, f"track.{ext}")
        assert pt.read_album(f) == ""

    def test_write_preserves_other_tags(self, audio_fixtures, tmp_path):
        f = make_show_file(audio_fixtures, tmp_path, "track.flac")
        audio = mutagen.File(str(f), easy=True)
        audio["title"] = "Tweezer"
        audio["artist"] = "Phish"
        audio["tracknumber"] = "5"
        audio.save()
        pt.write_album(f, "New Album")
        audio = mutagen.File(str(f), easy=True)
        assert audio["title"] == ["Tweezer"]
        assert audio["artist"] == ["Phish"]
        assert audio["tracknumber"] == ["5"]
        assert audio["album"] == ["New Album"]

    def test_unreadable_file_returns_none(self, tmp_path):
        junk = tmp_path / "junk.flac"
        junk.write_bytes(b"not audio at all")
        assert pt.read_album(junk) is None
        assert pt.write_album(junk, "x") is False


class TestCollectAudio:
    def test_finds_audio_recursively_and_sorted(self, audio_fixtures, tmp_path):
        make_show_file(audio_fixtures, tmp_path, "b.flac")
        make_show_file(audio_fixtures, tmp_path, "a.mp3")
        make_show_file(audio_fixtures, tmp_path / "disc2", "c.m4a")
        (tmp_path / "folder.jpg").write_bytes(b"\xff")
        (tmp_path / "notes.txt").write_text("setlist")
        found = pt.collect_audio(tmp_path)
        assert [p.name for p in found] == ["a.mp3", "b.flac", "c.m4a"]

    def test_uppercase_extensions_are_found(self, audio_fixtures, tmp_path):
        f = make_show_file(audio_fixtures, tmp_path, "track.flac")
        f.rename(tmp_path / "TRACK.FLAC")
        assert [p.name for p in pt.collect_audio(tmp_path)] == ["TRACK.FLAC"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_phish_retag.py -v -k "TestTagIO or TestCollectAudio"`
Expected: FAIL with `AttributeError: ... no attribute 'write_album'`.

- [ ] **Step 3: Implement**

Append to `bin/phish-retag`:

```python
# ── Tag I/O ────────────────────────────────────────────────────────────────────

def collect_audio(dir_path: Path) -> list:
    return sorted(
        p for p in dir_path.rglob("*")
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS
    )


def _open_audio(path: Path):
    # easy=True exposes a uniform "album" key across FLAC/M4A/MP3.
    try:
        return mutagen.File(str(path), easy=True)
    except Exception:
        return None


def read_album(path: Path):
    """Album tag of an audio file: None if unreadable, "" if untagged."""
    audio = _open_audio(path)
    if audio is None:
        return None
    if audio.tags is None:
        return ""
    values = audio.get("album")
    return values[0] if values else ""


def write_album(path: Path, album: str) -> bool:
    audio = _open_audio(path)
    if audio is None:
        return False
    if audio.tags is None:
        audio.add_tags()
    audio["album"] = album
    audio.save()
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_phish_retag.py -v`
Expected: all PASS (a corrupt `.mp3` may log a mutagen warning; the junk-file test uses `.flac` which reliably returns None/raises inside `_open_audio`).

- [ ] **Step 5: Commit**

```bash
git add bin/phish-retag tests/test_phish_retag.py
git commit -m "feat: add album tag I/O via mutagen with ffmpeg test fixtures

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Main loop, CLI, and integration tests

**Files:**
- Modify: `bin/phish-retag` (replace the placeholder `main()` at the bottom; append `main_logic` and `parse_args` before it)
- Modify: `tests/test_phish_retag.py` (append)

**Interfaces:**
- Consumes: everything above.
- Produces: `main_logic(path: Path, execute: bool, cache_path: Path) -> dict` returning counters `{"updated": int, "already": int, "multiset": int, "unresolved": int, "skipped": int}` (dirs, except `updated`/`already` which also drive per-file counts internally); `parse_args(argv) -> (Path, bool execute, Path cache_path)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_phish_retag.py`:

```python
def build_collection(audio_fixtures, root):
    """A miniature collection covering every per-directory outcome."""
    # Needs retag (heuristic-resolvable from its own tag)
    d1 = root / "Phish-2026-07-21.Empower.Federal.Credit.Union.Amphitheater.at.Lakeview.Syracuse.NY.[2760]"
    make_show_file(audio_fixtures, d1, "t1.flac",
                   album="Phish - Phish - 2026_07_21 Syracuse, NY (Phis)")
    make_show_file(audio_fixtures, d1, "t2.flac",
                   album="Phish - Phish - 2026_07_21 Syracuse, NY (Phis)")
    # Already correct
    d2 = root / "Phish-2026-07-12.Ruoff.Music.Center.Noblesville.IN.[2754]"
    make_show_file(audio_fixtures, d2, "t1.flac",
                   album="2026/07/12 Ruoff Music Center, Noblesville, IN")
    # Multi-set: two distinct tags
    d3 = root / "Phish-1994-12-29.Providence.Civic.Center.Providence.RI.[498]"
    make_show_file(audio_fixtures, d3, "s1.flac", album="1994/12/29 I Providence, RI")
    make_show_file(audio_fixtures, d3, "s2.flac", album="1994/12/29 II Providence, RI")
    # Unresolvable: garbage tag, livephish will be mocked to miss
    d4 = root / "Phish-1999-12-31.Big.Cypress.Seminole.Reservation.Big.Cypress.FL.[100]"
    make_show_file(audio_fixtures, d4, "t1.flac", album="Big Cypress New Years")
    # Non-canonical: skipped
    d5 = root / "Live Bait Vol. 09"
    make_show_file(audio_fixtures, d5, "t1.flac", album="Live Bait Vol. 09")
    return d1, d2, d3, d4, d5


class TestMainLogic:
    def _run(self, root, cache_file, execute):
        with patch.object(pt, "livephish_location", return_value=None):
            return pt.main_logic(root, execute=execute, cache_path=cache_file)

    def test_dry_run_reports_but_does_not_write(self, audio_fixtures, tmp_path, capsys):
        root = tmp_path / "col"
        d1, *_ = build_collection(audio_fixtures, root)
        counts = self._run(root, tmp_path / "c.json", execute=False)
        assert counts == {"updated": 1, "already": 1, "multiset": 1,
                          "unresolved": 1, "skipped": 1}
        # Tags untouched in dry run
        assert pt.read_album(d1 / "t1.flac") == "Phish - Phish - 2026_07_21 Syracuse, NY (Phis)"
        out = capsys.readouterr().out
        assert "2026/07/21 Empower Federal Credit Union Amphitheater at Lakeview, Syracuse, NY" in out

    def test_dry_run_warms_cache(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        build_collection(audio_fixtures, root)
        cache_file = tmp_path / "c.json"
        self._run(root, cache_file, execute=False)
        cache = json.loads(cache_file.read_text())
        assert cache["2760"] == "Empower Federal Credit Union Amphitheater at Lakeview, Syracuse, NY"

    def test_execute_writes_album_tags(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        d1, d2, d3, d4, d5 = build_collection(audio_fixtures, root)
        self._run(root, tmp_path / "c.json", execute=True)
        want = "2026/07/21 Empower Federal Credit Union Amphitheater at Lakeview, Syracuse, NY"
        assert pt.read_album(d1 / "t1.flac") == want
        assert pt.read_album(d1 / "t2.flac") == want
        # multiset, unresolved, and non-canonical dirs untouched
        assert pt.read_album(d3 / "s1.flac") == "1994/12/29 I Providence, RI"
        assert pt.read_album(d4 / "t1.flac") == "Big Cypress New Years"
        assert pt.read_album(d5 / "t1.flac") == "Live Bait Vol. 09"

    def test_already_correct_files_keep_mtime_on_execute(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        _, d2, *_ = build_collection(audio_fixtures, root)
        f = d2 / "t1.flac"
        before = f.stat().st_mtime_ns
        self._run(root, tmp_path / "c.json", execute=True)
        assert f.stat().st_mtime_ns == before

    def test_multiset_warning_lists_distinct_tags(self, audio_fixtures, tmp_path, capsys):
        root = tmp_path / "col"
        build_collection(audio_fixtures, root)
        self._run(root, tmp_path / "c.json", execute=False)
        err = capsys.readouterr().err
        assert "1994/12/29 I Providence, RI" in err
        assert "1994/12/29 II Providence, RI" in err

    def test_summary_lists_multiset_and_unresolved_dirs(self, audio_fixtures, tmp_path, capsys):
        root = tmp_path / "col"
        build_collection(audio_fixtures, root)
        self._run(root, tmp_path / "c.json", execute=False)
        out = capsys.readouterr().out
        assert "Phish-1994-12-29.Providence.Civic.Center.Providence.RI.[498]" in out
        assert "Phish-1999-12-31.Big.Cypress.Seminole.Reservation.Big.Cypress.FL.[100]" in out

    def test_empty_dir_counts_as_skipped(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        (root / "Phish-2026-07-22.Madison.Square.Garden.New.York.NY.[2761]").mkdir(parents=True)
        counts = self._run(root, tmp_path / "c.json", execute=False)
        assert counts == {"updated": 0, "already": 0, "multiset": 0,
                          "unresolved": 0, "skipped": 1}


class TestParseArgs:
    def test_defaults(self):
        path, execute, cache = pt.parse_args(["phish-retag"])
        assert path == pt.DEFAULT_PATH
        assert execute is False
        assert cache == pt.default_cache_path()

    def test_positional_path_and_execute(self, tmp_path):
        path, execute, cache = pt.parse_args(["phish-retag", str(tmp_path), "--execute"])
        assert path == tmp_path
        assert execute is True

    def test_cache_flag(self, tmp_path):
        _, _, cache = pt.parse_args(["phish-retag", str(tmp_path), "--cache", "/tmp/x.json"])
        assert cache == Path("/tmp/x.json")

    def test_unknown_flag_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            pt.parse_args(["phish-retag", str(tmp_path), "--bogus"])
```

Note: `parse_args` validates that an explicitly given PATH exists (`tmp_path` does), but must NOT validate `DEFAULT_PATH` at parse time in tests — see implementation: existence is only checked for the path actually used, and the defaults test runs on a machine where `DEFAULT_PATH` may not exist, so validation happens in `main()`, not `parse_args()`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_phish_retag.py -v -k "TestMainLogic or TestParseArgs"`
Expected: FAIL with `AttributeError: ... no attribute 'main_logic'`.

- [ ] **Step 3: Implement**

In `bin/phish-retag`, replace the placeholder `main()` block at the bottom of the file with:

```python
# ── Main logic ─────────────────────────────────────────────────────────────────

def main_logic(path: Path, execute: bool, cache_path: Path) -> dict:
    counts = {"updated": 0, "already": 0, "multiset": 0,
              "unresolved": 0, "skipped": 0}
    multiset_dirs = []
    unresolved_dirs = []
    files_updated = 0
    cache = load_cache(cache_path)

    entries = sorted(path.iterdir(), key=lambda e: e.name.lower())
    for entry in entries:
        if not entry.is_dir() or entry.name.startswith("."):
            continue

        parsed = parse_show_dirname(entry.name)
        if parsed is None:
            counts["skipped"] += 1
            print(f"  {dim('SKIP')}      {entry.name} (not a canonical show dir)")
            continue
        date, location_dots, release_id = parsed

        files = collect_audio(entry)
        if not files:
            counts["skipped"] += 1
            print(f"  {dim('SKIP')}      {entry.name} (no audio files)")
            continue

        albums = {}
        for f in files:
            album = read_album(f)
            if album is None:
                print(f"  {yellow('WARN')} unreadable audio file: {f}", file=sys.stderr)
                continue
            albums[f] = album

        distinct = sorted(set(albums.values()))
        if len(distinct) > 1:
            counts["multiset"] += 1
            multiset_dirs.append(entry.name)
            print(f"  {yellow('MULTISET')}  {entry.name} — skipped, distinct album tags:",
                  file=sys.stderr)
            for tag in distinct:
                print(f"      {tag or '(no album tag)'}", file=sys.stderr)
            continue

        current = distinct[0] if distinct else ""
        resolved = resolve_location(date, location_dots, release_id,
                                    current or None, cache, cache_path)
        if resolved is None:
            counts["unresolved"] += 1
            unresolved_dirs.append(entry.name)
            print(f"  {yellow('UNRESOLVED')} {entry.name}", file=sys.stderr)
            continue

        target = target_album(date, resolved)
        if current == target:
            counts["already"] += 1
            continue

        counts["updated"] += 1
        prefix = "[DRY RUN] " if not execute else ""
        print(f"  {prefix}{entry.name}")
        print(f"      {current or '(no album tag)'} → {green(target)}")
        for f in files:
            if albums.get(f) == target:
                continue
            if execute:
                if not write_album(f, target):
                    print(f"  {yellow('WARN')} could not write tag: {f}", file=sys.stderr)
                    continue
            files_updated += 1

    print()
    print(f"  {bold('SUMMARY')}")
    verb = "updated" if execute else "would update"
    print(f"  {green(str(counts['updated']))}  shows {verb} ({files_updated} files)")
    print(f"  {dim(str(counts['already']))}  already correct")
    print(f"  {yellow(str(counts['multiset']))}  multi-set (skipped, fix manually)")
    print(f"  {yellow(str(counts['unresolved']))}  unresolved")
    print(f"  {dim(str(counts['skipped']))}  skipped (non-canonical or no audio)")
    if multiset_dirs:
        print(f"\n  {bold('MULTI-SET DIRECTORIES')} (manual assessment needed)")
        for name in multiset_dirs:
            print(f"      {name}")
    if unresolved_dirs:
        print(f"\n  {bold('UNRESOLVED DIRECTORIES')} (location could not be verified)")
        for name in unresolved_dirs:
            print(f"      {name}")
    print()
    return counts


# ── Argument parsing ───────────────────────────────────────────────────────────

def parse_args(argv):
    path = None
    execute = False
    cache_path = None

    args = argv[1:]
    i = 0
    while i < len(args):
        if args[i] in ("-h", "--help"):
            print(__doc__)
            sys.exit(0)
        elif args[i] == "--execute":
            execute = True
            i += 1
        elif args[i] == "--dry-run":
            execute = False
            i += 1
        elif args[i] == "--cache":
            if i + 1 >= len(args):
                print("Error: --cache requires a file argument", file=sys.stderr)
                sys.exit(1)
            cache_path = Path(args[i + 1])
            i += 2
        elif not args[i].startswith("-"):
            path = Path(args[i])
            i += 1
        else:
            print(f"Unknown argument: {args[i]}", file=sys.stderr)
            sys.exit(1)

    if path is None:
        path = DEFAULT_PATH
    if cache_path is None:
        cache_path = default_cache_path()

    return path, execute, cache_path


def main():
    path, execute, cache_path = parse_args(sys.argv)
    if not path.is_dir():
        print(f"Error: PATH does not exist: {path}", file=sys.stderr)
        sys.exit(1)
    mode = "EXECUTE" if execute else "DRY RUN"
    print(f"\n  {bold('PHISH RETAG')}  [{mode}]")
    print(f"  {dim('Path:')}   {path}")
    print(f"  {dim('Cache:')}  {cache_path}")
    print()
    main_logic(path, execute, cache_path)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_phish_retag.py -v`
Expected: all PASS.

- [ ] **Step 5: Sanity-check the CLI help**

Run: `bin/phish-retag --help`
Expected: prints the docstring usage text, exit 0.

- [ ] **Step 6: Commit**

```bash
git add bin/phish-retag tests/test_phish_retag.py
git commit -m "feat: add phish-retag main loop, CLI, and integration tests

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Documentation and full-suite verification

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: the finished tool.

- [ ] **Step 1: Update CLAUDE.md**

Four edits:

1. Under "Key Architecture Patterns → Phish Collection Tools", after the `phish-merge` bullet, add:

```markdown
- **`phish-retag`** — Normalizes the album tag on every audio file in canonical show directories to `YYYY/MM/DD Venue, City, ST`, derived from the directory name. Venue/city boundaries resolve from existing tags when possible, falling back to livephish.com (jittered requests, results cached in `$XDG_CACHE_HOME/phish-retag.json`). Multi-set directories (more than one distinct album tag) are skipped with a warning. Only the album tag is touched. Requires `mutagen`.
```

2. Under "Common Development Commands → Phish Tools", add:

```bash
# Normalize album tags (dry run resolves + caches; --execute applies)
bin/phish-retag
bin/phish-retag --execute
bin/phish-retag /some/other/collection --cache /tmp/cache.json
```

3. Under "Dependencies", change the python3 line to include mutagen:

```markdown
- `python3` with `requests`, `beautifulsoup4`, and `mutagen` — Required by `bin/` tools (`pip install -r requirements.txt`)
```

4. Under "File Structure → `bin/`", after the `phish-merge` line, add:

```markdown
  - `phish-retag` — Normalize album tags to YYYY/MM/DD Venue, City, ST
```

Also update the pytest bullet in "Testing" ("65+ tests" count and the note about which files load via `SourceFileLoader`) to mention `test_phish_retag.py`.

- [ ] **Step 2: Run the full test suite**

Run: `cd tests && bats *.bats && cd .. && pytest tests/`
Expected: all 28 bats tests pass; all pytest tests (existing + new) pass.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document phish-retag in CLAUDE.md

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
