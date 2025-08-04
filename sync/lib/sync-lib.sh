#!/bin/bash

# Music Sync Library
# Common functions and logic for music synchronization scripts

set -euo pipefail

# Global variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${SCRIPT_DIR}/../config"
SYNC_DIR="${SCRIPT_DIR}/.."

# Load configuration files
load_global_config() {
    local global_config="${CONFIG_DIR}/global.conf"
    if [[ ! -f "$global_config" ]]; then
        echo "Error: Global configuration file not found: $global_config" >&2
        exit 1
    fi
    # shellcheck source=/dev/null
    source "$global_config"
}

load_artist_config() {
    local artist="$1"
    local artist_config="${CONFIG_DIR}/${artist}.conf"
    if [[ ! -f "$artist_config" ]]; then
        echo "Error: Artist configuration file not found: $artist_config" >&2
        echo "Available artists:" >&2
        find "${CONFIG_DIR}" -name '*.conf' -printf '%f\n' 2>/dev/null | sed 's|\.conf$||' | sort >&2
        exit 1
    fi
    # shellcheck source=/dev/null
    source "$artist_config"
}

# Confirmation prompt function
confirm_continue() {
    local prompt="${1:-Continue?}"
    local response

    if [[ "${DEFAULT_CONFIRM_PROMPTS:-true}" != "true" ]]; then
        return 0
    fi

    printf "\n%s [y/N]: " "$prompt"
    read -r response

    case "$response" in
    [yY] | [yY][eE][sS])
        return 0
        ;;
    *)
        echo "Exiting..."
        exit 0
        ;;
    esac
}

# Parse command line arguments
parse_args() {
    DRY_RUN=""
    SKIP_CONFIRM=false
    
    while getopts "ny" opt; do
        case $opt in
        n) DRY_RUN="--dry-run" ;;
        y) SKIP_CONFIRM=true ;;
        *)
            echo "Usage: $0 [-n] [-y] <artist>" >&2
            echo "  -n: Dry run (preview changes only)" >&2
            echo "  -y: Skip confirmation prompts" >&2
            exit 1
            ;;
        esac
    done
    shift $((OPTIND-1))
    
    if [[ $# -lt 1 ]]; then
        echo "Error: Artist name required" >&2
        echo "Available artists:" >&2
        find "${CONFIG_DIR}" -name '*.conf' -printf '%f\n' 2>/dev/null | sed 's|\.conf$||' | sort >&2
        exit 1
    fi
    
    ARTIST_SLUG="$1"
}

# Initialize sync environment
init_sync() {
    load_global_config
    load_artist_config "$ARTIST_SLUG"
    
    # Build full paths
    SRC="${MUSIC_SOURCE_BASE}/${SOURCE_SUBDIR}"
    if [[ "$ENABLE_NAS_BACKUP" == "true" ]]; then
        NAS="${NAS_BASE}/${NAS_SUBDIR}"
    fi
    PLEX="${PLEX_SERVER}:'${PLEX_BASE}/${PLEX_SUBDIR}'"
    
    # Exclude file path
    EXCLUDE_FILE_PATH="${SYNC_DIR}/${EXCLUDE_FILE}"
    
    # Build rsync options array
    read -ra RSYNC_OPTS_ARRAY <<< "${RSYNC_BASE_OPTS} --partial-dir=${PARTIAL_DIR}"
    if [[ -n "$DRY_RUN" ]]; then
        RSYNC_OPTS_ARRAY=("$DRY_RUN" "${RSYNC_OPTS_ARRAY[@]}")
    fi
    
    # Keep string version for display purposes
    RSYNC_OPTS="${RSYNC_OPTS_ARRAY[*]}"
    
    # Override confirmation prompts if requested
    if [[ "$SKIP_CONFIRM" == "true" ]]; then
        DEFAULT_CONFIRM_PROMPTS=false
    fi
}

# Validate configuration and environment
validate_environment() {
    # Check if exclude file exists
    if [[ ! -f "$EXCLUDE_FILE_PATH" ]]; then
        echo "Error: Exclude file not found: $EXCLUDE_FILE_PATH" >&2
        exit 1
    fi
    
    # Check if source directory exists (only if not dry run)
    if [[ -z "$DRY_RUN" && ! -d "$SRC" ]]; then
        echo "Error: Source directory not found: $SRC" >&2
        exit 1
    fi
    
    echo "Artist: $ARTIST_NAME"
    echo "Source: $SRC"
    if [[ "$ENABLE_NAS_BACKUP" == "true" ]]; then
        echo "NAS Backup: $NAS"
    fi
    echo "Plex Target: $PLEX"
    echo "Exclude File: $EXCLUDE_FILE_PATH"
    echo "Rsync Options: $RSYNC_OPTS"
}

# Perform NAS backup (if enabled)
sync_to_nas() {
    if [[ "$ENABLE_NAS_BACKUP" != "true" ]]; then
        return 0
    fi
    
    echo "=== Backing up ALL content to NAS ==="
    rsync "${RSYNC_OPTS_ARRAY[@]}" \
        "${SRC}" \
        "${NAS}"
}

# Perform Plex sync with exclusions
sync_to_plex() {
    echo -e "\n=== Syncing LIVE albums to Plex ==="
    rsync "${RSYNC_OPTS_ARRAY[@]}" \
        --delete-excluded \
        --exclude-from="${EXCLUDE_FILE_PATH}" \
        "${SRC}" \
        "${PLEX}"
}

# Run post-sync verification
run_verification() {
    if [[ -n "$DRY_RUN" ]]; then
        echo -e "\n*** DRY RUN COMPLETE - No files were actually transferred ***"
        return 0
    fi
    
    if [[ "${VERIFICATION_ENABLED:-false}" == "true" ]]; then
        echo -e "\n=== Verifying exclusions ==="
        echo "${VERIFICATION_DESC:-Verification}:"
        eval "${VERIFICATION_CMD}"
    fi
}

# Main sync function
perform_sync() {
    parse_args "$@"
    init_sync
    validate_environment
    
    confirm_continue "Continue with sync operations?"
    sync_to_nas
    sync_to_plex
    run_verification
    
    if [[ -z "$DRY_RUN" ]]; then
        echo -e "\n=== Sync completed successfully ==="
    fi
}