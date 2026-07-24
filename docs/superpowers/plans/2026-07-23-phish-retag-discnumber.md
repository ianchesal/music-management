# phish-retag Disc-Number Tagging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach `bin/phish-retag` to auto-handle the common "clean" multi-set
Phish show — one whose distinct album tags differ only by a Roman-numeral set
marker right after the date — by converting the marker into a `discnumber`
tag and collapsing the album tag to the same uniform format used everywhere
else, while routing anything messier (contamination, missing markers, or
disagreeing venue text) to the existing manual-review path unchanged.

**Architecture:** Three small, independently-testable pure functions
(`parse_date_token`, `match_set_marker`, `classify_clean_multiset`) implement
detection. Two small tag-I/O functions (`read_discnumber`, `write_discnumber`)
mirror the existing `read_album`/`write_album` pair. `main_logic`'s existing
`if len(distinct) > 1:` branch is replaced to call the classifier and, on a
clean result, resolve venue/city exactly as the single-tag path does before
writing per-file `(album, discnumber)` pairs.

**Tech Stack:** Python 3, `mutagen` (already a dependency), `pytest`
(`SourceFileLoader`-based test loading, per existing `tests/test_phish_retag.py`
conventions). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-23-phish-retag-discnumber-design.md`

## Global Constraints

- Only `album` and `discnumber` tags are ever touched — no other tag, no
  `disctotal`. (spec: Scope, Clean multi-set handling)
- Set markers are a **literal allow-list** `I`, `II`, `III`, `IV`, `V` —
  never a general Roman-numeral parse (`^[IVXLCDM]+$`). This is the fix for
  the reviewed corruption path against the real
  `Phish-2013-10-27.XL.Center.Hartford.CT.[804]` directory. (spec: Detection
  step 2)
- `discnumber` values are plain arabic strings — `"1"`, `"2"`, … — no
  zero-padding, no `/total` suffix. (spec: Clean multi-set handling)
- No "best-effort partial" mode: a directory is either fully auto-processed
  (every distinct tag qualifies) or fully routed to the anomaly bucket.
  (spec: Scope)
- Existing house conventions apply: `bin/phish-retag` has no `.py`
  extension; tests load it via `SourceFileLoader` (see
  `tests/test_phish_retag.py:13-20`); dry-run is the default, `--execute`
  applies changes; new pytest tests live in `tests/test_phish_retag.py`
  alongside the behavior they cover (repo `CLAUDE.md`, Test Development
  Notes).

---

### Task 0: Create the feature branch

**Files:** none (repo state only)

- [ ] **Step 1: Create and switch to the feature branch**

```bash
git checkout -b phish-retag-discnumber
```

- [ ] **Step 2: Confirm clean starting state**

```bash
git status --short
```
Expected: no output (clean tree, branch is `phish-retag-discnumber`).

---

### Task 1: Date-token parsing

**Files:**
- Modify: `bin/phish-retag` (add near `SHOW_DIR_RE`, in the "Name parsing"
  section, after `dot_normalize` around line 97)
- Test: `tests/test_phish_retag.py` (new `TestParseDateToken` class, after
  `TestDotNormalize`, before `TestSplitVenueCity` — insert after line 66)

**Interfaces:**
- Produces: `DATE_TOKEN_RE` (compiled regex), `parse_date_token(tag: str) -> tuple[int, int, int] | None`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_phish_retag.py` after the `TestDotNormalize` class (after
line 66, before `class TestSplitVenueCity:`):

```python
class TestParseDateToken:
    def test_slash_separated(self):
        assert pt.parse_date_token("1994/05/07 I Dallas, TX") == (1994, 5, 7)

    def test_dash_separated(self):
        assert pt.parse_date_token("1992-12-01 I Denison University") == (1992, 12, 1)

    def test_non_zero_padded_day(self):
        assert pt.parse_date_token("1996/12/6 I Las Vegas, NV") == (1996, 12, 6)

    def test_no_leading_date_returns_none(self):
        assert pt.parse_date_token("XL Center, Hartford, CT") is None

    def test_empty_string_returns_none(self):
        assert pt.parse_date_token("") is None

    def test_none_returns_none(self):
        assert pt.parse_date_token(None) is None

    def test_date_must_be_followed_by_boundary(self):
        # "19940507" glued to more digits isn't a recognizable date token.
        assert pt.parse_date_token("19940507extra Dallas, TX") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd tests && pytest test_phish_retag.py::TestParseDateToken -v
```
Expected: FAIL with `AttributeError: module 'phish_retag' has no attribute 'parse_date_token'`

- [ ] **Step 3: Implement `parse_date_token`**

In `bin/phish-retag`, add after `dot_normalize` (after line 97, before the
`# ── Venue/city resolution ──` section header on line 100):

```python
# A leading date token: 'YYYY/MM/DD' or 'YYYY-MM-DD', non-zero-padded
# month/day allowed ('1996/12/6'), must be followed by whitespace or end.
DATE_TOKEN_RE = re.compile(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?=\s|$)")


def parse_date_token(tag):
    """Return (year, month, day) as ints from a leading date token in tag,
    or None if tag doesn't start with one."""
    m = DATE_TOKEN_RE.match(tag or "")
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd tests && pytest test_phish_retag.py::TestParseDateToken -v
```
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add bin/phish-retag tests/test_phish_retag.py
git commit -m "feat: add date-token parsing for multi-set detection"
```

---

### Task 2: Set-marker parsing

**Files:**
- Modify: `bin/phish-retag` (add directly after Task 1's `parse_date_token`)
- Test: `tests/test_phish_retag.py` (new `TestMatchSetMarker` class, directly
  after `TestParseDateToken`)

**Interfaces:**
- Consumes: nothing from Task 1 (operates on a plain string — caller strips
  the date token first via a helper added in this task)
- Produces: `SET_MARKER_TO_DISC` (dict), `strip_date_token(tag: str) -> str | None`,
  `match_set_marker(remainder: str) -> tuple[int, str] | None`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_phish_retag.py` directly after the `TestParseDateToken`
class:

```python
class TestStripDateToken:
    def test_strips_date_and_leading_space(self):
        assert pt.strip_date_token("1994/05/07 I Dallas, TX") == "I Dallas, TX"

    def test_no_date_returns_none(self):
        assert pt.strip_date_token("XL Center, Hartford, CT") is None


class TestMatchSetMarker:
    def test_marker_i(self):
        assert pt.match_set_marker("I Providence, RI") == (1, "Providence, RI")

    def test_marker_ii(self):
        assert pt.match_set_marker("II Providence, RI") == (2, "Providence, RI")

    def test_marker_iii(self):
        assert pt.match_set_marker("III Rosemont, IL") == (3, "Rosemont, IL")

    def test_marker_iv(self):
        assert pt.match_set_marker("IV Super Ball IX, NY") == (4, "Super Ball IX, NY")

    def test_marker_v(self):
        assert pt.match_set_marker("V Something, ZZ") == (5, "Something, ZZ")

    def test_xl_is_not_a_marker(self):
        # "XL" is a technically-valid Roman numeral (40) but not in the
        # allow-list — regression for the real XL Center Hartford directory.
        assert pt.match_set_marker("XL Center, Hartford, CT") is None

    def test_marker_must_be_whole_token(self):
        # "III" glued to more letters isn't a marker.
        assert pt.match_set_marker("IIIrd Anniversary, Boston, MA") is None

    def test_no_marker_at_all(self):
        assert pt.match_set_marker("Chicago, IL (soundcheck)") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd tests && pytest test_phish_retag.py::TestStripDateToken test_phish_retag.py::TestMatchSetMarker -v
```
Expected: FAIL with `AttributeError: module 'phish_retag' has no attribute 'strip_date_token'`

- [ ] **Step 3: Implement `strip_date_token` and `match_set_marker`**

In `bin/phish-retag`, add directly after `parse_date_token` (from Task 1):

```python
def strip_date_token(tag):
    """Return tag's text after its leading date token (leading whitespace
    stripped), or None if tag doesn't start with one."""
    m = DATE_TOKEN_RE.match(tag or "")
    if not m:
        return None
    return tag[m.end():].lstrip()


# Literal allow-list, not a general Roman-numeral parse: a general parse
# would accept "XL" (= 40), which is the venue name in the real directory
# Phish-2013-10-27.XL.Center.Hartford.CT.[804], not a set marker. A Phish
# show having more than 5 sets is not a real scenario.
SET_MARKER_TO_DISC = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5}
SET_MARKER_RE = re.compile(r"^(I|II|III|IV|V)(?=\s|$)")


def match_set_marker(remainder):
    """remainder is tag text with the leading date token already stripped
    (see strip_date_token). Returns (disc_number, location_text) where
    location_text is what follows the marker (leading whitespace stripped),
    or None if remainder doesn't start with a recognized set marker."""
    m = SET_MARKER_RE.match(remainder)
    if not m:
        return None
    return SET_MARKER_TO_DISC[m.group(1)], remainder[m.end():].lstrip()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd tests && pytest test_phish_retag.py::TestStripDateToken test_phish_retag.py::TestMatchSetMarker -v
```
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add bin/phish-retag tests/test_phish_retag.py
git commit -m "feat: add set-marker parsing with I-V allow-list"
```

---

### Task 3: Clean multi-set classifier

**Files:**
- Modify: `bin/phish-retag` (add directly after Task 2's `match_set_marker`)
- Test: `tests/test_phish_retag.py` (new `TestClassifyCleanMultiset` class,
  directly after `TestMatchSetMarker`)

**Interfaces:**
- Consumes: `parse_date_token`, `strip_date_token`, `match_set_marker`,
  `SET_MARKER_TO_DISC` (Tasks 1–2)
- Produces: `classify_clean_multiset(distinct_tags: list[str], date: str) -> dict[str, int] | None`
  — `date` is `"YYYY-MM-DD"` (as returned by `parse_show_dirname`). Return
  value maps each input tag to its disc number; `None` means "route to the
  anomaly bucket."

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_phish_retag.py` directly after `TestMatchSetMarker`:

```python
class TestClassifyCleanMultiset:
    def test_two_set_show(self):
        assert pt.classify_clean_multiset(
            ["1994/05/07 I Dallas, TX", "1994/05/07 II Dallas, TX"],
            "1994-05-07",
        ) == {"1994/05/07 I Dallas, TX": 1, "1994/05/07 II Dallas, TX": 2}

    def test_three_set_show(self):
        assert pt.classify_clean_multiset(
            ["1995/12/31 I New York, NY", "1995/12/31 II New York, NY",
             "1995/12/31 III New York, NY"],
            "1995-12-31",
        ) == {"1995/12/31 I New York, NY": 1, "1995/12/31 II New York, NY": 2,
              "1995/12/31 III New York, NY": 3}

    def test_four_set_show(self):
        # Real show: Super Ball IX, 2011-07-02, four sets.
        tags = ["2011/07/02 I Super Ball IX, NY", "2011/07/02 II Super Ball IX, NY",
                "2011/07/02 III Super Ball IX, NY", "2011/07/02 IV Super Ball IX, NY"]
        result = pt.classify_clean_multiset(tags, "2011-07-02")
        assert result == {tags[0]: 1, tags[1]: 2, tags[2]: 3, tags[3]: 4}

    def test_non_zero_padded_date_still_matches(self):
        assert pt.classify_clean_multiset(
            ["1996/12/6 I Las Vegas, NV", "1996/12/6 II Las Vegas, NV"],
            "1996-12-06",
        ) == {"1996/12/6 I Las Vegas, NV": 1, "1996/12/6 II Las Vegas, NV": 2}

    def test_mismatched_date_is_anomaly(self):
        # Real contamination shape: a bonus track from a different show/date.
        tags = ["1994/12/01 I Salem, OR", "1994/12/01 II Salem, OR",
                "1994/11/12 II Kent, OH"]
        assert pt.classify_clean_multiset(tags, "1994-12-01") is None

    def test_missing_marker_is_anomaly(self):
        # Soundcheck-style tag alongside otherwise-clean sets.
        tags = ["1994/06/18 Chicago, IL (soundcheck)",
                "1994/06/18 I Chicago, IL", "1994/06/18 II Chicago, IL"]
        assert pt.classify_clean_multiset(tags, "1994-06-18") is None

    def test_xl_center_style_tags_are_anomaly(self):
        # Regression: two distinct tags on the real XL Center directory
        # shape, neither a genuine set marker.
        tags = ["2013/10/27 XL Center, Hartford, CT",
                "2013/10/27 XL Center, Hartford, CT (soundcheck)"]
        assert pt.classify_clean_multiset(tags, "2013-10-27") is None

    def test_remainder_mismatch_is_anomaly(self):
        # Valid markers on both, but they disagree on venue/city text.
        tags = ["1994/05/07 I Dallas, TX", "1994/05/07 II Fort Worth, TX"]
        assert pt.classify_clean_multiset(tags, "1994-05-07") is None

    def test_casing_only_difference_with_no_marker_is_anomaly(self):
        # Real data: two files differing only by tag casing, no set marker.
        tags = ["2017/07/14 Chicago, IL", "2017/07/14 Chicago, Il"]
        assert pt.classify_clean_multiset(tags, "2017-07-14") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd tests && pytest test_phish_retag.py::TestClassifyCleanMultiset -v
```
Expected: FAIL with `AttributeError: module 'phish_retag' has no attribute 'classify_clean_multiset'`

- [ ] **Step 3: Implement `classify_clean_multiset`**

In `bin/phish-retag`, add directly after `match_set_marker`:

```python
def classify_clean_multiset(distinct_tags, date):
    """distinct_tags: the directory's distinct album tags. date: the
    directory's own date, 'YYYY-MM-DD' (as returned by parse_show_dirname).

    Returns {tag: disc_number} for every tag if this is a clean multi-set
    show — every tag's date matches the directory's date, every tag has a
    set marker (I-V) right after the date, and the location text after the
    marker is identical across every tag. Returns None otherwise (caller
    routes the directory to the anomaly bucket)."""
    want = tuple(int(p) for p in date.split("-"))
    result = {}
    remainders = set()
    for tag in distinct_tags:
        if parse_date_token(tag) != want:
            return None
        marker = match_set_marker(strip_date_token(tag))
        if marker is None:
            return None
        disc, remainder = marker
        result[tag] = disc
        remainders.add(remainder)
    if len(remainders) != 1:
        return None
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd tests && pytest test_phish_retag.py::TestClassifyCleanMultiset -v
```
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add bin/phish-retag tests/test_phish_retag.py
git commit -m "feat: add clean multi-set classifier with remainder-consistency check"
```

---

### Task 4: discnumber tag I/O

**Files:**
- Modify: `bin/phish-retag` (add directly after `write_album`, in the "Tag
  I/O" section, after line 283)
- Test: `tests/test_phish_retag.py` (extend `TestTagIO`, after line 357)

**Interfaces:**
- Consumes: `_open_audio` (existing private helper, `bin/phish-retag:256-261`)
- Produces: `read_discnumber(path: Path) -> str | None`,
  `write_discnumber(path: Path, discnumber: str) -> bool`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_phish_retag.py`'s `TestTagIO` class (after
`test_unreadable_file_returns_none`, line 357):

```python
    @pytest.mark.parametrize("ext", ["flac", "m4a", "mp3"])
    def test_write_then_read_discnumber(self, audio_fixtures, tmp_path, ext):
        f = make_show_file(audio_fixtures, tmp_path, f"track.{ext}")
        assert pt.write_discnumber(f, "2") is True
        assert pt.read_discnumber(f) == "2"

    @pytest.mark.parametrize("ext", ["flac", "m4a", "mp3"])
    def test_missing_discnumber_reads_empty_string(self, audio_fixtures, tmp_path, ext):
        f = make_show_file(audio_fixtures, tmp_path, f"track.{ext}")
        assert pt.read_discnumber(f) == ""

    def test_discnumber_write_preserves_album(self, audio_fixtures, tmp_path):
        f = make_show_file(audio_fixtures, tmp_path, "track.flac",
                           album="1994/05/07 Dallas, TX")
        pt.write_discnumber(f, "1")
        assert pt.read_album(f) == "1994/05/07 Dallas, TX"
        assert pt.read_discnumber(f) == "1"

    def test_unreadable_file_discnumber_returns_none(self, tmp_path):
        junk = tmp_path / "junk.flac"
        junk.write_bytes(b"not audio at all")
        assert pt.read_discnumber(junk) is None
        assert pt.write_discnumber(junk, "1") is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd tests && pytest test_phish_retag.py::TestTagIO -v
```
Expected: FAIL with `AttributeError: module 'phish_retag' has no attribute 'write_discnumber'`

- [ ] **Step 3: Implement `read_discnumber` and `write_discnumber`**

In `bin/phish-retag`, add directly after `write_album` (after line 283,
before the `# ── Main logic ──` section header):

```python
def read_discnumber(path: Path):
    """Discnumber tag of an audio file: None if unreadable, "" if untagged."""
    audio = _open_audio(path)
    if audio is None:
        return None
    if audio.tags is None:
        return ""
    values = audio.get("discnumber")
    return values[0] if values else ""


def write_discnumber(path: Path, discnumber: str) -> bool:
    audio = _open_audio(path)
    if audio is None:
        return False
    if audio.tags is None:
        audio.add_tags()
    audio["discnumber"] = discnumber
    audio.save()
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd tests && pytest test_phish_retag.py::TestTagIO -v
```
Expected: all pass (existing + 7 new)

- [ ] **Step 5: Commit**

```bash
git add bin/phish-retag tests/test_phish_retag.py
git commit -m "feat: add discnumber tag read/write, verified across FLAC/M4A/MP3"
```

---

### Task 5: Wire clean multi-set handling into `main_logic`

**Files:**
- Modify: `bin/phish-retag` (module docstring lines 1–26; `main_logic`
  lines 288–378)
- Test: `tests/test_phish_retag.py` (`build_collection` lines 376–398;
  `TestMainLogic` class lines 401–466)

**Interfaces:**
- Consumes: `classify_clean_multiset` (Task 3), `read_discnumber` /
  `write_discnumber` (Task 4), and all pre-existing `main_logic`
  dependencies (`resolve_location`, `target_album`, `collect_audio`,
  `read_album`, `write_album`).
- Produces: `main_logic` now returns a counts dict with keys `updated`,
  `already`, `multiset_clean`, `multiset_anomaly`, `unresolved`, `skipped`
  (was: `updated`, `already`, `multiset`, `unresolved`, `skipped`) — this is
  a breaking rename any other caller of `main_logic` must account for (none
  exist outside this file and its tests).

This task has two parts done together, since the new fixture behavior can
only be verified once the wiring exists: (1) rewrite `main_logic`'s
multi-set branch, (2) update the test fixture and assertions that assumed
the old skip-everything behavior. Steps interleave both files.

- [ ] **Step 1: Update the module docstring**

In `bin/phish-retag`, replace lines 10–13:

```python
Only the album tag is touched. Multi-set directories (more than one distinct
album tag) are skipped with a warning. Venue/city boundaries are resolved
from existing tags when possible, falling back to livephish.com; results are
cached so repeat runs make no network requests.
```

with:

```python
Only the album and discnumber tags are touched. A "clean" multi-set show —
one whose distinct album tags differ only by a set marker (I-V) right after
the date, with matching venue/city text otherwise — has its set marker
converted to a discnumber tag and its album collapsed to the same uniform
format. Messier multi-set directories (contamination, missing markers,
disagreeing venue text) are skipped with a warning, same as before. Venue/
city boundaries are resolved from existing tags when possible, falling back
to livephish.com; results are cached so repeat runs make no network
requests.
```

- [ ] **Step 2: Update `build_collection` in the test file**

In `tests/test_phish_retag.py`, replace the `build_collection` function
(lines 376–398):

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
    # Clean multi-set: two distinct tags differing only by set marker
    d3 = root / "Phish-1994-12-29.Providence.Civic.Center.Providence.RI.[498]"
    make_show_file(audio_fixtures, d3, "s1.flac", album="1994/12/29 I Providence, RI")
    make_show_file(audio_fixtures, d3, "s2.flac", album="1994/12/29 II Providence, RI")
    # Unresolvable: garbage tag, livephish will be mocked to miss
    d4 = root / "Phish-1999-12-31.Big.Cypress.Seminole.Reservation.Big.Cypress.FL.[100]"
    make_show_file(audio_fixtures, d4, "t1.flac", album="Big Cypress New Years")
    # Non-canonical: skipped
    d5 = root / "Live Bait Vol. 09"
    make_show_file(audio_fixtures, d5, "t1.flac", album="Live Bait Vol. 09")
    # Multi-set anomaly: real contamination shape — a track internally
    # tagged with a different date/venue mixed into an otherwise-clean pair.
    d6 = root / "Phish-1994-12-01.Salem.Armory.Salem.OR.[359]"
    make_show_file(audio_fixtures, d6, "s1.flac", album="1994/12/01 I Salem, OR")
    make_show_file(audio_fixtures, d6, "s2.flac", album="1994/12/01 II Salem, OR")
    make_show_file(audio_fixtures, d6, "bonus.flac", album="1994/11/12 II Kent, OH")
    return d1, d2, d3, d4, d5, d6
```

- [ ] **Step 3: Update `TestMainLogic` assertions to expect the new counts shape and rewritten fixture**

In `tests/test_phish_retag.py`, replace the entire `TestMainLogic` class
(lines 401–466):

```python
class TestMainLogic:
    def _run(self, root, cache_file, execute):
        with patch.object(pt, "livephish_location", return_value=None):
            return pt.main_logic(root, execute=execute, cache_path=cache_file)

    def test_dry_run_reports_but_does_not_write(self, audio_fixtures, tmp_path, capsys):
        root = tmp_path / "col"
        d1, _, d3, *_ = build_collection(audio_fixtures, root)
        counts = self._run(root, tmp_path / "c.json", execute=False)
        assert counts == {"updated": 2, "already": 1, "multiset_clean": 1,
                          "multiset_anomaly": 1, "unresolved": 1, "skipped": 1}
        # Tags untouched in dry run
        assert pt.read_album(d1 / "t1.flac") == "Phish - Phish - 2026_07_21 Syracuse, NY (Phis)"
        assert pt.read_album(d3 / "s1.flac") == "1994/12/29 I Providence, RI"
        assert pt.read_discnumber(d3 / "s1.flac") == ""
        out = capsys.readouterr().out
        assert "2026/07/21 Empower Federal Credit Union Amphitheater at Lakeview, Syracuse, NY" in out
        assert "Disc 1: 1994/12/29 I Providence, RI" in out
        assert "Disc 2: 1994/12/29 II Providence, RI" in out

    def test_dry_run_warms_cache(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        build_collection(audio_fixtures, root)
        cache_file = tmp_path / "c.json"
        self._run(root, cache_file, execute=False)
        cache = json.loads(cache_file.read_text())
        assert cache["2760"] == "Empower Federal Credit Union Amphitheater at Lakeview, Syracuse, NY"

    def test_execute_writes_album_tags(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        d1, d2, d3, d4, d5, d6 = build_collection(audio_fixtures, root)
        self._run(root, tmp_path / "c.json", execute=True)
        want = "2026/07/21 Empower Federal Credit Union Amphitheater at Lakeview, Syracuse, NY"
        assert pt.read_album(d1 / "t1.flac") == want
        assert pt.read_album(d1 / "t2.flac") == want
        # clean multi-set: album collapsed, discnumber set per set
        want_multiset = "1994/12/29 Providence Civic Center, Providence, RI"
        assert pt.read_album(d3 / "s1.flac") == want_multiset
        assert pt.read_discnumber(d3 / "s1.flac") == "1"
        assert pt.read_album(d3 / "s2.flac") == want_multiset
        assert pt.read_discnumber(d3 / "s2.flac") == "2"
        # unresolved, non-canonical, and multi-set-anomaly dirs untouched
        assert pt.read_album(d4 / "t1.flac") == "Big Cypress New Years"
        assert pt.read_album(d5 / "t1.flac") == "Live Bait Vol. 09"
        assert pt.read_album(d6 / "s1.flac") == "1994/12/01 I Salem, OR"
        assert pt.read_album(d6 / "bonus.flac") == "1994/11/12 II Kent, OH"

    def test_already_correct_files_keep_mtime_on_execute(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        _, d2, *_ = build_collection(audio_fixtures, root)
        f = d2 / "t1.flac"
        before = f.stat().st_mtime_ns
        self._run(root, tmp_path / "c.json", execute=True)
        assert f.stat().st_mtime_ns == before

    def test_multiset_clean_second_run_is_noop(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        d3 = root / "Phish-1994-12-29.Providence.Civic.Center.Providence.RI.[498]"
        make_show_file(audio_fixtures, d3, "s1.flac", album="1994/12/29 I Providence, RI")
        make_show_file(audio_fixtures, d3, "s2.flac", album="1994/12/29 II Providence, RI")
        cache_file = tmp_path / "c.json"
        self._run(root, cache_file, execute=True)
        f = d3 / "s1.flac"
        before = f.stat().st_mtime_ns
        counts = self._run(root, cache_file, execute=True)
        assert counts["already"] == 1
        assert counts["multiset_clean"] == 0
        assert f.stat().st_mtime_ns == before

    def test_multiset_anomaly_warning_lists_distinct_tags(self, audio_fixtures, tmp_path, capsys):
        root = tmp_path / "col"
        build_collection(audio_fixtures, root)
        self._run(root, tmp_path / "c.json", execute=False)
        err = capsys.readouterr().err
        assert "1994/12/01 I Salem, OR" in err
        assert "1994/12/01 II Salem, OR" in err
        assert "1994/11/12 II Kent, OH" in err

    def test_summary_lists_multiset_anomaly_and_unresolved_dirs(self, audio_fixtures, tmp_path, capsys):
        root = tmp_path / "col"
        build_collection(audio_fixtures, root)
        self._run(root, tmp_path / "c.json", execute=False)
        out = capsys.readouterr().out
        assert "Phish-1994-12-01.Salem.Armory.Salem.OR.[359]" in out
        assert "Phish-1999-12-31.Big.Cypress.Seminole.Reservation.Big.Cypress.FL.[100]" in out

    def test_empty_dir_counts_as_skipped(self, audio_fixtures, tmp_path):
        root = tmp_path / "col"
        (root / "Phish-2026-07-22.Madison.Square.Garden.New.York.NY.[2761]").mkdir(parents=True)
        counts = self._run(root, tmp_path / "c.json", execute=False)
        assert counts == {"updated": 0, "already": 0, "multiset_clean": 0,
                          "multiset_anomaly": 0, "unresolved": 0, "skipped": 1}
```

- [ ] **Step 4: Run the updated tests to verify they fail against the old `main_logic`**

```bash
cd tests && pytest test_phish_retag.py::TestMainLogic -v
```
Expected: FAIL — `test_dry_run_reports_but_does_not_write` and others fail
on the counts-dict `KeyError`/mismatch (old code still uses the `multiset`
key and skips Providence unconditionally).

- [ ] **Step 5: Rewrite `main_logic`**

In `bin/phish-retag`, replace the entire `main_logic` function (lines
288–378) with:

```python
def main_logic(path: Path, execute: bool, cache_path: Path) -> dict:
    counts = {"updated": 0, "already": 0, "multiset_clean": 0,
              "multiset_anomaly": 0, "unresolved": 0, "skipped": 0}
    multiset_anomaly_dirs = []
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
            clean = classify_clean_multiset(distinct, date)
            if clean is None:
                counts["multiset_anomaly"] += 1
                multiset_anomaly_dirs.append(entry.name)
                print(f"  {yellow('MULTISET-ANOMALY')}  {entry.name} — skipped, distinct album tags:",
                      file=sys.stderr)
                for tag in distinct:
                    print(f"      {tag or '(no album tag)'}", file=sys.stderr)
                continue

            source_tag = next(tag for tag, disc in clean.items() if disc == 1)
            resolved = resolve_location(date, location_dots, release_id,
                                        source_tag, cache, cache_path)
            if resolved is None:
                counts["unresolved"] += 1
                unresolved_dirs.append(entry.name)
                print(f"  {yellow('UNRESOLVED')} {entry.name}", file=sys.stderr)
                continue

            target = target_album(date, resolved)
            all_correct = all(
                albums[f] == target and read_discnumber(f) == str(clean[albums[f]])
                for f in files if f in albums
            )
            if all_correct:
                counts["already"] += 1
                continue

            counts["updated"] += 1
            counts["multiset_clean"] += 1
            prefix = "[DRY RUN] " if not execute else ""
            print(f"  {prefix}{entry.name}")
            for tag in sorted(clean, key=clean.get):
                print(f"      Disc {clean[tag]}: {tag} → {green(target)}")
            for f in files:
                if f not in albums:
                    continue
                tag = albums[f]
                disc_str = str(clean[tag])
                if albums.get(f) == target and read_discnumber(f) == disc_str:
                    continue
                if execute:
                    if not write_album(f, target):
                        print(f"  {yellow('WARN')} could not write tag: {f}", file=sys.stderr)
                        continue
                    if not write_discnumber(f, disc_str):
                        print(f"  {yellow('WARN')} could not write discnumber: {f}", file=sys.stderr)
                        continue
                files_updated += 1
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
            if f not in albums:
                continue
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
    print(f"  {green(str(counts['multiset_clean']))}  multi-set shows auto-fixed (set marker → disc)")
    print(f"  {yellow(str(counts['multiset_anomaly']))}  multi-set anomalies (skipped, fix manually)")
    print(f"  {yellow(str(counts['unresolved']))}  unresolved")
    print(f"  {dim(str(counts['skipped']))}  skipped (non-canonical or no audio)")
    if multiset_anomaly_dirs:
        print(f"\n  {bold('MULTI-SET ANOMALIES')} (manual assessment needed)")
        for name in multiset_anomaly_dirs:
            print(f"      {name}")
    if unresolved_dirs:
        print(f"\n  {bold('UNRESOLVED DIRECTORIES')} (location could not be verified)")
        for name in unresolved_dirs:
            print(f"      {name}")
    print()
    return counts
```

- [ ] **Step 6: Run the full test file to verify everything passes**

```bash
cd tests && pytest test_phish_retag.py -v
```
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add bin/phish-retag tests/test_phish_retag.py
git commit -m "feat: auto-handle clean multi-set shows via discnumber tagging"
```

---

### Task 6: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md` (the `phish-retag` bullet under "Phish Collection
  Tools")

**Interfaces:** none (documentation only)

- [ ] **Step 1: Update the phish-retag description**

In `CLAUDE.md`, find the line:

```
- **`phish-retag`** — Normalizes the album tag on every audio file in canonical show directories to `YYYY/MM/DD Venue, City, ST`, derived from the directory name. Venue/city boundaries resolve from existing tags when possible, falling back to livephish.com (jittered requests, results cached in `$XDG_CACHE_HOME/phish-retag.json`). Multi-set directories (more than one distinct album tag) are skipped with a warning. Only the album tag is touched. Requires `mutagen`.
```

Replace it with:

```
- **`phish-retag`** — Normalizes the album tag on every audio file in canonical show directories to `YYYY/MM/DD Venue, City, ST`, derived from the directory name. Venue/city boundaries resolve from existing tags when possible, falling back to livephish.com (jittered requests, results cached in `$XDG_CACHE_HOME/phish-retag.json`). Clean multi-set directories — distinct album tags differing only by a set marker (`I`-`V`) right after the date, with otherwise-matching venue text — get the marker converted to a `discnumber` tag and the album collapsed to the uniform format. Messier multi-set directories (contamination, missing markers, disagreeing venue text) are skipped with a warning. Only the album and discnumber tags are touched. Requires `mutagen`.
```

- [ ] **Step 2: Verify the file still reads correctly**

```bash
grep -A2 "phish-retag\*\*" CLAUDE.md | head -5
```
Expected: shows the updated bullet.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for phish-retag discnumber handling"
```

---

### Task 7: Full test suite run

**Files:** none (verification only)

- [ ] **Step 1: Run the full pytest suite**

```bash
cd tests && pytest -v
```
Expected: all tests pass (existing 130+ plus the new tests from Tasks 1–5).

- [ ] **Step 2: Run the full bats suite (sync scripts are untouched, but confirm no regressions)**

```bash
cd tests && bats *.bats
```
Expected: all 28 tests pass.

- [ ] **Step 3: Manual dry-run smoke test against a small directory (optional but recommended)**

If a real or synthetic Phish collection directory is available locally:

```bash
bin/phish-retag /path/to/small/test/collection
```
Expected: output includes `Disc 1: ... → ...` / `Disc 2: ... → ...` lines for
any clean multi-set directories present, and `MULTISET-ANOMALY` for messy
ones — no crashes.
