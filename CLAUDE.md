# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a collection of music management tools for handling live show collections and media synchronization. The codebase consists of:

1. **Phish Collection Tools** (`bin/`): Python scripts for comparing, renaming, and merging Phish live show collections
2. **Sync Scripts** (`sync/`): Bash scripts that use rsync to synchronize music collections between local storage, NAS backup, and Plex media server
3. **ZSH Functions** (`zsh/functions/`): Audio conversion and metadata utilities

## Key Architecture Patterns

### Phish Collection Tools (`bin/`)

Three Python tools designed to work together as a pipeline when integrating a LivePhish torrent download with an existing collection:

- **`phish-rename`** — Queries livephish.com to rename show directories from any date-based format to `Phish-YYYY-MM-DD.Dot.Separated.Location.[LivePhishID]`. Requires `requests` and `beautifulsoup4`.
- **`phish-compare`** — Read-only diagnostic: shows matched/unmatched shows, studio album cross-references, and undated items in both the existing collection and torrent.
- **`phish-merge`** — Performs the actual merge in up to four phases: (1) rsync backup to NAS, (2) copy torrent-only shows, (3) replace matched shows with canonical torrent copies, (4) rename existing-only shows to torrent naming style. Supports `--dry-run` and `--phase N`.

All three tools share the same date-extraction logic and default paths:
- `DEFAULT_EXISTING = /data/media/Sorted/Unsorted/Music/Phish`
- `DEFAULT_TORRENT  = /data/torrents/Phish-Live.Phish.Project-2002-2026`

Python deps: `pip install -r requirements.txt` (`requests`, `beautifulsoup4`).

### Sync Script Pattern
All sync scripts follow a common pattern:
- Configuration via `sync/config/global.conf` (environment-specific paths) and per-artist `*.conf` files
- Studio album exclusion via `*-excludes.txt` files
- Interactive confirmation prompts before execution (skippable with `-y`)
- Support for dry-run mode via `-n` flag
- Common rsync options with progress reporting
- Two-phase sync: full backup to NAS, filtered sync to Plex

### Audio Processing Functions
- `flac2alac`: Converts FLAC files to ALAC format with tag correction
- `flacinfo`: Displays metadata for FLAC/ALAC files in tabular format

## Common Development Commands

### Phish Tools
```bash
# Rename new downloads to canonical format (dry run first)
bin/phish-rename /data/torrents/Phish-Live.Phish.Project-2002-2026
bin/phish-rename /data/torrents/Phish-Live.Phish.Project-2002-2026 --execute

# Compare existing collection vs torrent
bin/phish-compare

# Merge torrent into existing collection
bin/phish-merge --dry-run
bin/phish-merge --execute --nas /mnt/nas/Phish-backup

# Run only a specific phase
bin/phish-merge --phase 4 --dry-run
```

### Sync Scripts
```bash
# Unified sync command for all artists
./sync/music-sync phish              # Interactive sync with prompts
./sync/music-sync -n billy-strings   # Dry run preview
./sync/music-sync -y trey-anastasio  # Skip confirmation prompts
./sync/music-sync --help             # Show available artists and usage
```

### Audio Functions (from zsh/functions/)
```bash
flac2alac "Artist Name" "Album Name"   # Convert FLAC to ALAC with corrected tags
flacinfo *.flac                         # Display track information
```

## Testing

The repo has two test suites. All tests must pass before merging.

### Bats Tests (sync scripts — 28 tests)
```bash
cd tests
bats *.bats                    # Run all 28 bats tests
bats sync-lib.bats            # Unit tests (19 tests)
bats music-sync.bats          # Integration tests (9 tests)
bats --verbose-run *.bats     # Verbose output for debugging
```

### Pytest Tests (Python bin/ tools — 65+ tests)
```bash
pytest tests/                        # Run all Python tests
pytest tests/test_phish_rename.py    # Tests for phish-rename
pytest tests/test_phish_merge.py     # Tests for phish-merge
pytest -v tests/                     # Verbose output
```

### Running All Tests
```bash
cd tests && bats *.bats && cd .. && pytest tests/
```

### Test Architecture
- **Bats tests** — Each test runs in isolated temporary directories; rsync and ssh commands are mocked for safety; tests use actual config files with test data
- **Pytest tests** — Pure Python unit tests; HTTP calls to livephish.com are mocked via `unittest.mock`; no external requests made during test runs

### Test Development Notes
- Bats tests use custom helper functions in `tests/test_helper.bash`
- Bats test configs use `TEST_TMP_DIR` paths so directories actually exist for validation
- Use `assert_rsync_called_with` and `assert_file_exists` helpers for common bats assertions
- Pytest tests load `bin/phish-rename` and `bin/phish-merge` as modules using `SourceFileLoader` (files have no `.py` extension)
- When adding new phish-merge or phish-rename behavior, add pytest tests alongside; when adding sync-lib behavior, add bats tests

## Dependencies

Required external tools:
- `ffmpeg` and `ffprobe` — Audio processing and metadata extraction
- `rsync` — File synchronization
- `jq` — JSON processing for metadata parsing
- `ssh` — Remote server access for verification
- `python3` with `requests` and `beautifulsoup4` — Required by `bin/` tools (`pip install -r requirements.txt`)
- `bats` — For running bats tests locally
- `pyenv` — For managing Python version
- `pytest` — For running Python tests locally

## File Structure

- `bin/` — Phish collection Python tools
  - `phish-rename` — Rename downloads to canonical LivePhish format
  - `phish-compare` — Compare existing collection vs torrent (read-only)
  - `phish-merge` — Merge torrent into existing collection
- `sync/` — Music synchronization scripts and configurations
  - `config/` — Configuration files (global environment settings and per-artist configs)
  - `lib/` — Shared library functions (sync-lib.sh)
  - `music-sync` — Unified sync script for all artists
  - `*-excludes.txt` — Lists of studio albums/folders to exclude from live-only syncs
- `zsh/functions/` — Audio utility functions designed for zsh
- `tests/` — Test suite
  - `*.bats` — Bats tests for sync scripts
  - `test_phish_*.py` — Pytest tests for bin/ tools
  - `test_helper.bash` — Bats test utilities
- `requirements.txt` — Python dependencies for bin/ tools

## Important Notes

- Environment-specific paths are now configured in `sync/config/global.conf` for portability
- Scripts include interactive confirmation prompts to prevent accidental execution (can be skipped with `-y`)
- The codebase prioritizes live shows over studio releases for Plex synchronization
- Error handling uses `set -euo pipefail` in bash scripts for strict mode
- The `bin/` tools use hard-coded default paths pointing to the owner's environment — override with CLI flags for other setups
- `phish-rename` makes live HTTP requests to livephish.com; rate-limit awareness is built in (1-second delay between requests)
