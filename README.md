# Music Management Tools

A collection of command-line tools for managing music collections, specifically focused on live show archiving and media synchronization. Features a modern, configuration-driven architecture that's portable and easily extensible.

## Features

- **🎵 Live Show Focus**: Prioritizes live recordings over studio albums for streaming libraries
- **🔄 Multi-Destination Sync**: Backup to NAS and sync filtered content to Plex server
- **⚙️ Configuration-Driven**: Portable setup using environment configs rather than hard-coded paths  
- **🎯 Artist-Specific Rules**: Per-artist exclude lists for studio album filtering
- **🔧 Audio Processing**: FLAC to ALAC conversion with metadata correction
- **✅ Comprehensive Testing**: Full test suite with GitHub Actions CI/CD

## Quick Start

### 1. Clone and Setup
```bash
git clone https://github.com/ianchesal/music-management.git
cd music-management
```

### 2. Configure for Your Environment
Edit `sync/config/global.conf` with your paths:
```bash
# Your music source directory
MUSIC_SOURCE_BASE="/your/music/library/path"

# Your NAS backup location  
NAS_BASE="/your/nas/backup/path"

# Your Plex server details
PLEX_SERVER="your-plex-server"
PLEX_BASE="/your/plex/music/path"
```

### 3. Add Artists
Copy and customize artist configs in `sync/config/`:
```bash
cp sync/config/phish.conf sync/config/your-artist.conf
# Edit with your artist's details
```

### 4. Run Sync
```bash
# Preview what will be synced (dry run)
./sync/music-sync -n your-artist

# Actually perform the sync
./sync/music-sync your-artist
```

## Tools Overview

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

# For running tests locally
git clone https://github.com/bats-core/bats-core.git
cd bats-core && sudo ./install.sh /usr/local
cd .. && rm -rf bats-core
```

### Setup Test Environment

```bash
# Install test helpers (optional - tests work without these)
cd tests
mkdir -p helpers && cd helpers
git clone https://github.com/bats-core/bats-support.git
git clone https://github.com/bats-core/bats-assert.git
cd ../..

# Make scripts executable
chmod +x sync/music-sync sync/sync-*-to-plex
```

### Running Tests

```bash
# Run all tests (28 tests total)
cd tests && bats *.bats

# Run specific test file
bats sync-lib.bats              # Unit tests (19 tests)
bats music-sync.bats            # Integration tests (9 tests)

# Verbose output for debugging
bats --verbose-run *.bats

# Run specific test by name
bats --filter "load_global_config" sync-lib.bats
```

**What gets tested:**
- ✅ All library functions (argument parsing, config loading, etc.)
- ✅ End-to-end sync workflows with the unified `music-sync` script
- ✅ Error handling and edge cases
- ✅ Dry-run functionality and confirmation prompts
- ✅ Mock rsync/ssh calls (no actual file transfers)
- ✅ Configuration validation and path resolution

**Test Architecture:**
- **Isolated environments** - Each test runs in a temporary directory
- **Comprehensive mocking** - rsync and ssh commands are mocked for safety
- **Real config testing** - Tests use actual config files with test data
- **Fast execution** - All 28 tests complete in seconds

### Shell Script Linting

```bash
# Install ShellCheck
brew install shellcheck  # macOS
# or  
sudo apt-get install shellcheck  # Ubuntu/Debian

# Lint all scripts
find sync -name "*.sh" -o -name "music-sync" -o -name "sync-*-to-plex" | xargs shellcheck
```

## Configuration

### Global Configuration (`sync/config/global.conf`)
Environment-specific paths and settings:
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
Per-artist settings:
```bash
ARTIST_NAME="Artist Name"
ARTIST_SLUG="artist-slug"
SOURCE_SUBDIR="Artist Directory/"
ENABLE_NAS_BACKUP=true
NAS_SUBDIR="Artist/"
PLEX_SUBDIR="Artist/Live/"
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

## Usage Examples

### Music Sync

```bash
# Show help and available artists
./sync/music-sync --help

# Interactive sync with prompts
./sync/music-sync phish

# Dry run (preview only, no changes)
./sync/music-sync -n billy-strings

# Skip confirmation prompts  
./sync/music-sync -y trey-anastasio

# Combined flags
./sync/music-sync -ny dead-and-company
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
# Convert FLAC to ALAC with corrected tags
flac2alac "Artist Name" "Album Name"

# Display track information
flacinfo *.flac
```

## CI/CD

GitHub Actions automatically run on pull requests:

- **Unit & Integration Tests** - 28 tests covering all functionality with Bats
- **Shell Script Linting** - Code quality checks with ShellCheck  
- **Configuration Validation** - Ensures all configs are valid bash syntax
- **Documentation Verification** - Tests that examples work

**Test Results**: All tests pass (28/28) ✅

## Architecture

```
sync/
├── config/                    # Configuration files
│   ├── global.conf           # Environment settings
│   └── *.conf               # Per-artist configurations
├── lib/
│   └── sync-lib.sh          # Shared library functions
├── music-sync               # Unified entry point
└── *-excludes.txt          # Studio album exclude lists

tests/                        # Comprehensive test suite
├── *.bats                   # Test files
├── test_helper.bash        # Test utilities
└── README.md               # Testing documentation

zsh/functions/               # Audio processing utilities
├── flac2alac
└── flacinfo
```

## Contributing

1. **Fork and clone** the repository
2. **Create a feature branch** for your changes
3. **Add tests** for new functionality in `tests/`
4. **Run the test suite** locally: `cd tests && bats *.bats`
5. **Lint your scripts**: `shellcheck sync/your-script`
6. **Submit a pull request** - tests run automatically

### Development Workflow

```bash
# Make changes to scripts
vim sync/lib/sync-lib.sh

# Add corresponding tests  
vim tests/sync-lib.bats

# Run tests locally (all 28 tests should pass)
cd tests && bats *.bats

# Run specific test file during development
bats sync-lib.bats

# Lint your changes
shellcheck sync/lib/sync-lib.sh

# Commit and push - CI runs automatically
git add . && git commit -m "your changes"
git push origin your-branch
```

## Requirements

- **bash** 4.0+ (for scripts)
- **rsync** (for file synchronization)  
- **ssh** (for remote server access)
- **ffmpeg** and **ffprobe** (for audio processing functions)
- **jq** (for JSON metadata parsing)
- **zsh** (for audio processing functions)
- **bats** (for running tests locally)

## License

This project is released under the MIT License. See the code as a starting point for your own music management workflows.

## See Also

- [My dotfiles](https://github.com/ianchesal/dotfiles) - More command-line productivity tools
- [Bats Testing Framework](https://github.com/bats-core/bats-core) - Used for our test suite
- [rsync documentation](https://rsync.samba.org/) - Core sync functionality
