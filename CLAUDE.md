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
```bash
# Dry run to preview changes
./sync/sync-phish-to-plex -n
./sync/sync-billy-strings-to-plex -n

# Execute actual sync
./sync/sync-phish-to-plex
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

- `sync/` - Artist-specific sync scripts and exclude files
- `sync/*-excludes.txt` - Lists of studio albums/folders to exclude from live-only syncs
- `zsh/functions/` - Audio utility functions designed for zsh

## Important Notes

- All paths are hard-coded for the original owner's environment
- Scripts include interactive confirmation prompts to prevent accidental execution
- The codebase prioritizes live shows over studio releases for Plex synchronization
- Error handling uses `set -euo pipefail` in bash scripts for strict mode