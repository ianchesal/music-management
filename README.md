# Music Management Tools

A collection of command-line tools for managing music collections, specifically focused on live show archiving and media synchronization. Features a modern, configuration-driven architecture that's portable and easily extensible.

## Features

- **Live Show Focus**: Prioritizes live recordings over studio albums for streaming libraries
- **Multi-Destination Sync**: Backup to NAS and sync filtered content to Plex server
- **Configuration-Driven**: Portable setup using environment configs rather than hard-coded paths
- **Artist-Specific Rules**: Per-artist exclude lists for studio album filtering
- **Phish Collection Tools**: Dedicated Python tools for comparing, renaming, and merging Phish live show collections
- **Audio Processing**: FLAC to ALAC conversion with metadata correction
- **Comprehensive Testing**: Full test suite with GitHub Actions CI/CD

## Quick Start

Note: `pyenv` is the best way to work with Python code in this project. It is assumed to be
in use throughout this README when referencing Python commands.

### 1. Clone and Setup
```bash
git clone https://github.com/ianchesal/music-management.git
cd music-management
```

### 2. Install Python Dependencies (for `bin/` tools)
```bash
pip install -r requirements.txt
```

### 3. Configure for Your Environment
Edit `sync/config/global.conf` with your paths:
```bash
MUSIC_SOURCE_BASE="/your/music/library/path"
NAS_BASE="/your/nas/backup/path"
PLEX_SERVER="your-plex-server"
PLEX_BASE="/your/plex/music/path"
```

### 4. Add Artists
Copy and customize artist configs in `sync/config/`:
```bash
cp sync/config/phish.conf sync/config/your-artist.conf
# Edit with your artist's details
```

### 5. Run Sync
```bash
# Preview what will be synced (dry run)
./sync/music-sync -n your-artist

# Actually perform the sync
./sync/music-sync your-artist
```

## Tools Overview

### Phish Collection Tools (`bin/`)

Python tools for working with Phish live show collections alongside a LivePhish torrent download:

- **`phish-rename`** — Rename downloaded show directories to canonical LivePhish format by looking up each show on livephish.com. Produces names like `Phish-YYYY-MM-DD.Dot.Separated.Location.[LivePhishID]`.
- **`phish-compare`** — Compare an existing Phish collection against a torrent download. Reports matched shows, unique shows on each side, studio album cross-references, and undated items.
- **`phish-merge`** — Merge an existing Phish live show collection with a torrent download. Runs four phases: NAS backup, copy new shows, replace matched shows with canonical torrent copies, rename existing-only shows to torrent naming style.

**Typical workflow:**

```bash
# Step 1: Rename new downloads to canonical format
bin/phish-rename /data/torrents/Phish-Live.Phish.Project-2002-2026 --dry-run
bin/phish-rename /data/torrents/Phish-Live.Phish.Project-2002-2026 --execute

# Step 2: Compare what you have against the torrent
bin/phish-compare

# Step 3: Merge the torrent into your collection
bin/phish-merge --dry-run
bin/phish-merge --execute --nas /mnt/nas/Phish-backup
```

**`phish-rename` options:**
```
phish-rename PATH [--dry-run | --execute]
```

**`phish-compare` options:**
```
phish-compare [--existing PATH] [--torrent PATH] [--studio PATH]
```

**`phish-merge` options:**
```
phish-merge [--dry-run | --execute --nas PATH]
phish-merge --existing PATH --torrent PATH --execute --nas PATH
phish-merge --phase N [--dry-run | --execute --nas PATH]
  Phases: 1=backup  2=copy-new  3=replace  4=rename
```

### Music Sync Scripts (`sync/`)

Modern, unified approach to synchronizing music collections:

- **`music-sync`** - Main unified script supporting all artists
- **`sync/config/`** - Environment and artist-specific configurations
- **`sync/lib/sync-lib.sh`** - Shared library with all common functionality

**Key Features:**
- Two-phase sync: complete backup to NAS, filtered sync to Plex
- Studio album exclusion for live-only libraries
- Dry-run mode for safe preview
- Progress reporting and verification

```bash
# Show help and available artists
./sync/music-sync --help

# Interactive sync with prompts
./sync/music-sync phish

# Dry run (preview only, no changes)
./sync/music-sync -n billy-strings

# Skip confirmation prompts
./sync/music-sync -y trey-anastasio
```

### Audio Functions (`zsh/functions/`)

Shell functions for audio processing:

- **`flac2alac`** - Convert FLAC to ALAC with tag correction
- **`flacinfo`** - Display FLAC/ALAC metadata in tabular format

## Local Development Setup

### Prerequisites

Install required tools:
```bash
# Core sync dependencies
brew install rsync ffmpeg jq  # macOS
# or
sudo apt-get install rsync ffmpeg jq  # Ubuntu/Debian

# Python dependencies (for bin/ tools)
pip install -r requirements.txt

# For running bats tests locally
git clone https://github.com/bats-core/bats-core.git
cd bats-core && sudo ./install.sh /usr/local
cd .. && rm -rf bats-core
```

### Running Tests

The repo has two test suites that together cover all functionality.

**Bats tests** (sync scripts):
```bash
cd tests
bats *.bats                       # Run all bats tests (28 tests)
bats sync-lib.bats                # Unit tests (19 tests)
bats music-sync.bats              # Integration tests (9 tests)
bats --verbose-run *.bats         # Verbose output for debugging
bats --filter "load_global_config" sync-lib.bats
```

**Pytest tests** (Python bin/ tools):
```bash
pytest tests/                     # Run all Python tests (65+ tests)
pytest tests/test_phish_rename.py # Tests for phish-rename
pytest tests/test_phish_merge.py  # Tests for phish-merge
pytest -v tests/                  # Verbose output
```

**All tests:**
```bash
cd tests && bats *.bats && cd .. && pytest tests/
```

**What gets tested:**
- All library functions (argument parsing, config loading, etc.)
- End-to-end sync workflows with the unified `music-sync` script
- Error handling and edge cases
- Dry-run functionality and confirmation prompts
- Mock rsync/ssh calls (no actual file transfers)
- Configuration validation and path resolution
- Phish show date extraction and name normalization
- LivePhish search and best-match selection
- Merge phase logic (backup, copy, replace, rename)
- Collision detection and dry-run accuracy

**Test Architecture:**
- **Bats tests** — Isolated environments with mocked rsync/ssh; tests use actual config files with test data
- **Pytest tests** — Pure Python unit tests with mocked HTTP calls; no external requests made during tests

### Shell Script Linting

```bash
# Install ShellCheck
brew install shellcheck  # macOS
# or
sudo apt-get install shellcheck  # Ubuntu/Debian

# Lint all scripts
find sync -name "*.sh" -o -name "music-sync" | xargs shellcheck
```

## Configuration

### Global Configuration (`sync/config/global.conf`)
```bash
MUSIC_SOURCE_BASE="/path/to/your/music"
NAS_BASE="/path/to/nas/backup"
PLEX_SERVER="your-server-name"
PLEX_BASE="/path/on/plex/server"
PARTIAL_DIR="/path/for/partial/transfers"
RSYNC_BASE_OPTS="--archive --compress --verbose --human-readable --delete --progress --partial"
DEFAULT_CONFIRM_PROMPTS=true
DEFAULT_ENABLE_NAS_BACKUP=false
```

### Artist Configuration (`sync/config/<artist>.conf`)
```bash
ARTIST_NAME="Artist Name"
ARTIST_SLUG="artist-slug"
SOURCE_SUBDIR="Artist Directory/"
ENABLE_NAS_BACKUP=true
NAS_SUBDIR="Artist/"
PLEX_SUBDIR="Artist/"
EXCLUDE_FILE="artist-excludes.txt"
VERIFICATION_ENABLED=true
VERIFICATION_CMD="ssh server 'verification command'"
VERIFICATION_DESC="Description of verification"
```

### Adding New Artists

1. **Create artist config:**
   ```bash
   cp sync/config/phish.conf sync/config/new-artist.conf
   # Edit with artist details
   ```

2. **Create exclude file:**
   ```bash
   touch sync/new-artist-excludes.txt
   # Add studio albums to exclude, one per line ending with /
   ```

3. **Test the configuration:**
   ```bash
   ./sync/music-sync -n new-artist
   ```

### Audio Functions

Add to your zsh setup:
```bash
# Add to ~/.zshrc
fpath=("/path/to/music-management/zsh/functions" $fpath)
autoload -Uz /path/to/music-management/zsh/functions/*(:t)
```

Then use:
```bash
flac2alac "Artist Name" "Album Name"
flacinfo *.flac
```

## CI/CD

GitHub Actions automatically run on pull requests:

- **Unit & Integration Tests** — Bats tests covering sync scripts
- **Python Tests** — Pytest covering bin/ tools
- **Shell Script Linting** — Code quality checks with ShellCheck
- **Configuration Validation** — Ensures all configs are valid bash syntax

## Architecture

```
bin/                             # Phish collection Python tools
├── phish-rename                # Rename downloads to canonical LivePhish format
├── phish-compare               # Compare existing collection vs torrent
└── phish-merge                 # Merge torrent into existing collection

sync/
├── config/                    # Configuration files
│   ├── global.conf           # Environment settings
│   └── *.conf               # Per-artist configurations
├── lib/
│   └── sync-lib.sh          # Shared library functions
├── music-sync               # Unified entry point
└── *-excludes.txt          # Studio album exclude lists

tests/                        # Test suite
├── *.bats                   # Bats tests for sync scripts (28 tests)
├── test_phish_*.py          # Pytest tests for bin/ tools (65+ tests)
├── test_helper.bash         # Bats test utilities
└── README.md                # Testing documentation

zsh/functions/               # Audio processing utilities
├── flac2alac
└── flacinfo
```

## Dependencies

- **bash** 4.0+ (for sync scripts)
- **rsync** (for file synchronization)
- **ssh** (for remote server access)
- **ffmpeg** and **ffprobe** (for audio processing functions)
- **jq** (for JSON metadata parsing)
- **zsh** (for audio processing functions)
- **python3** with `requests` and `beautifulsoup4` (for bin/ tools — see `requirements.txt`)
- **bats** (for running bats tests locally)
- **pytest** (for running Python tests locally)

## Contributing

1. **Fork and clone** the repository
2. **Create a feature branch** for your changes
3. **Add tests** for new functionality
4. **Run the full test suite** locally:
   ```bash
   cd tests && bats *.bats && cd .. && pytest tests/
   ```
5. **Lint your scripts**: `shellcheck sync/your-script`
6. **Submit a pull request** — tests run automatically

## License

This project is released under the MIT License. See the code as a starting point for your own music management workflows.

## See Also

- [My dotfiles](https://github.com/ianchesal/dotfiles) - More command-line productivity tools
- [Bats Testing Framework](https://github.com/bats-core/bats-core) - Used for sync script tests
- [rsync documentation](https://rsync.samba.org/) - Core sync functionality
- [LivePhish](https://www.livephish.com/) - Official Phish live recordings
