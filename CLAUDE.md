# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is a collection of music management tools for handling live show collections and media synchronization. The codebase consists of:

1. **Sync Scripts** (`sync/`): Bash scripts that use rsync to synchronize music collections between local storage, NAS backup, and Plex media server
2. **ZSH Functions** (`zsh/functions/`): Audio conversion and metadata utilities

## Key Architecture Patterns

### Sync Script Pattern
All sync scripts follow a common pattern:
- Hard-coded paths specific to the owner's environment (source: iTunes, destination: NAS + Plex server)
- Configuration via exclude files to filter studio albums vs live shows
- Interactive confirmation prompts before execution
- Support for dry-run mode via `-n` flag
- Common rsync options with progress reporting
- Two-phase sync: full backup to NAS, filtered sync to Plex

### Audio Processing Functions
- `flac2alac`: Converts FLAC files to ALAC format with tag correction
- `flacinfo`: Displays metadata for FLAC/ALAC files in tabular format

## Common Development Commands

### Running Sync Scripts

**New Unified Approach (Recommended):**
```bash
# Unified sync command for all artists
./sync/music-sync phish              # Interactive sync with prompts
./sync/music-sync -n billy-strings   # Dry run preview
./sync/music-sync -y trey-anastasio  # Skip confirmation prompts

# Show available artists and usage
./sync/music-sync --help
```

### Audio Functions (from zsh/functions/)
```bash
# Convert FLAC to ALAC with corrected tags
flac2alac "Artist Name" "Album Name"

# Display track information
flacinfo *.flac
```

## Dependencies

Required external tools:
- `ffmpeg` and `ffprobe` - Audio processing and metadata extraction
- `rsync` - File synchronization
- `jq` - JSON processing for metadata parsing
- `ssh` - Remote server access for verification

## File Structure

- `sync/` - Music synchronization scripts and configurations
  - `config/` - Configuration files (global environment settings and per-artist configs)
  - `lib/` - Shared library functions (sync-lib.sh)
  - `music-sync` - Unified sync script for all artists
  - `*-excludes.txt` - Lists of studio albums/folders to exclude from live-only syncs
- `zsh/functions/` - Audio utility functions designed for zsh
- `tests/` - Comprehensive test suite using Bats framework

## Important Notes

- Environment-specific paths are now configured in `sync/config/global.conf` for portability
- Scripts include interactive confirmation prompts to prevent accidental execution (can be skipped with `-y`)
- The codebase prioritizes live shows over studio releases for Plex synchronization
- Error handling uses `set -euo pipefail` in bash scripts for strict mode
- Comprehensive test suite ensures reliability and prevents regressions

## Testing

The codebase has a comprehensive test suite (28 tests) that covers all functionality:

### Running Tests Locally
```bash
cd tests
bats *.bats                    # Run all 28 tests
bats sync-lib.bats            # Run unit tests (19 tests)
bats music-sync.bats          # Run integration tests (9 tests)
bats --verbose-run *.bats     # Verbose output for debugging
```

### Test Architecture
- **Isolated environments**: Each test runs in temporary directories
- **Comprehensive mocking**: rsync and ssh commands are mocked for safety
- **Real configuration testing**: Tests use actual config files with test data
- **Fast execution**: All tests complete in seconds

### What's Tested
- Configuration loading and validation (global + artist configs)
- Command-line argument parsing and error handling
- Environment initialization and path resolution
- Sync functionality (NAS backup, Plex sync, exclusions)
- Dry-run mode and confirmation prompts
- End-to-end workflows via the `music-sync` script

### CI/CD Integration
Tests run automatically on pull requests via GitHub Actions:
- Unit and integration tests with Bats
- Shell script linting with ShellCheck
- Configuration validation 
- Documentation verification

**All tests must pass (28/28) before merging changes.**

### Test Development Notes
- Tests use Bats framework with custom helper functions in `tests/test_helper.bash`
- Each test runs in isolated temporary directories (`$TEST_TMP_DIR`)
- Mock commands (rsync, ssh) log their calls for assertion testing
- Use `bash -c "source test-lib && function"` pattern for testing library functions
- Test configs use `TEST_TMP_DIR` paths so directories actually exist for validation
- Use `assert_rsync_called_with` and `assert_file_exists` helpers for common assertions
