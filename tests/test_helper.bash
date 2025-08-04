#!/usr/bin/env bash

# Test helper functions for music sync tests

# Setup test environment variables
export BATS_TEST_DIRNAME="${BATS_TEST_DIRNAME:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
export PROJECT_ROOT="${BATS_TEST_DIRNAME}/.."
export SYNC_DIR="${PROJECT_ROOT}/sync"
export TEST_FIXTURES_DIR="${BATS_TEST_DIRNAME}/fixtures"
export TEST_TMP_DIR="${BATS_TMPDIR:-/tmp}/music-sync-tests"

# Create temporary directory for tests
setup_test_environment() {
    mkdir -p "${TEST_TMP_DIR}"
    export TMPDIR="${TEST_TMP_DIR}"
}

# Clean up test environment
teardown_test_environment() {
    if [[ -d "${TEST_TMP_DIR}" ]]; then
        rm -rf "${TEST_TMP_DIR}"
    fi
}

# Mock rsync command for testing
mock_rsync() {
    cat > "${TEST_TMP_DIR}/rsync" << 'EOF'
#!/bin/bash
# Mock rsync for testing
echo "MOCK_RSYNC: $*" >> "${TEST_TMP_DIR}/rsync.log"
exit 0
EOF
    chmod +x "${TEST_TMP_DIR}/rsync"
    export PATH="${TEST_TMP_DIR}:${PATH}"
}

# Mock ssh command for testing
mock_ssh() {
    cat > "${TEST_TMP_DIR}/ssh" << 'EOF'
#!/bin/bash
# Mock ssh for testing
echo "MOCK_SSH: $*" >> "${TEST_TMP_DIR}/ssh.log"
if [[ "$*" == *"ls -d"* ]]; then
    echo "None found (correct!)"
fi
exit 0
EOF
    chmod +x "${TEST_TMP_DIR}/ssh"
    export PATH="${TEST_TMP_DIR}:${PATH}"
}

# Create test configuration files
create_test_configs() {
    mkdir -p "${TEST_TMP_DIR}/config"
    mkdir -p "${TEST_TMP_DIR}/source/Test Artist"
    
    # Test global config - use TEST_TMP_DIR for paths so directories actually exist
    cat > "${TEST_TMP_DIR}/config/global.conf" << EOF
MUSIC_SOURCE_BASE="${TEST_TMP_DIR}/source"
NAS_BASE="${TEST_TMP_DIR}/nas"
PLEX_SERVER="test-server"
PLEX_BASE="/test/plex"
PARTIAL_DIR="${TEST_TMP_DIR}/partial"
RSYNC_BASE_OPTS="--archive --verbose"
DEFAULT_CONFIRM_PROMPTS=false
DEFAULT_ENABLE_NAS_BACKUP=false
EOF

    # Test artist config
    cat > "${TEST_TMP_DIR}/config/test-artist.conf" << 'EOF'
ARTIST_NAME="Test Artist"
ARTIST_SLUG="test-artist"
SOURCE_SUBDIR="Test Artist/"
ENABLE_NAS_BACKUP=false
PLEX_SUBDIR="Test Artist/Live/"
EXCLUDE_FILE="test-excludes.txt"
VERIFICATION_ENABLED=false
EOF

    # Test exclude file
    cat > "${TEST_TMP_DIR}/test-excludes.txt" << 'EOF'
Studio Album 1/
Studio Album 2/
EOF
}

# Load sync library with test overrides
load_test_sync_lib() {
    # Create a test-specific version of the sync library
    cat > "${TEST_TMP_DIR}/sync-lib-test.sh" << EOF
#!/bin/bash

# Test version of sync library with overridden paths
set -euo pipefail

# Global variables - override for testing
SCRIPT_DIR="${TEST_TMP_DIR}"
CONFIG_DIR="${TEST_TMP_DIR}/config"
SYNC_DIR="${TEST_TMP_DIR}"

# Load configuration files
load_global_config() {
    local global_config="\${CONFIG_DIR}/global.conf"
    if [[ ! -f "\$global_config" ]]; then
        echo "Error: Global configuration file not found: \$global_config" >&2
        exit 1
    fi
    source "\$global_config"
}

load_artist_config() {
    local artist="\$1"
    local artist_config="\${CONFIG_DIR}/\${artist}.conf"
    if [[ ! -f "\$artist_config" ]]; then
        echo "Error: Artist configuration file not found: \$artist_config" >&2
        echo "Available artists:" >&2
        ls "\${CONFIG_DIR}"/*.conf 2>/dev/null | sed 's|.*/||; s|\.conf\$||' | sort >&2
        exit 1
    fi
    source "\$artist_config"
}

# Copy the rest of the functions from the original library
$(sed -n '35,$p' "${PROJECT_ROOT}/sync/lib/sync-lib.sh")
EOF

    source "${TEST_TMP_DIR}/sync-lib-test.sh"
}

# Assert rsync was called with expected arguments
assert_rsync_called_with() {
    local expected="$1"
    if [[ ! -f "${TEST_TMP_DIR}/rsync.log" ]]; then
        echo "rsync was not called" >&2
        return 1
    fi
    
    if ! grep -F -- "$expected" "${TEST_TMP_DIR}/rsync.log" >/dev/null; then
        echo "Expected rsync call not found: $expected" >&2
        echo "Actual calls:" >&2
        cat "${TEST_TMP_DIR}/rsync.log" >&2
        return 1
    fi
}

# Assert file exists
assert_file_exists() {
    local file="$1"
    if [[ ! -f "$file" ]]; then
        echo "File does not exist: $file" >&2
        return 1
    fi
}

# Load bats helpers if available
if [[ -f "${BATS_TEST_DIRNAME}/helpers/bats-support/load.bash" ]]; then
    load helpers/bats-support/load
fi

if [[ -f "${BATS_TEST_DIRNAME}/helpers/bats-assert/load.bash" ]]; then
    load helpers/bats-assert/load
fi