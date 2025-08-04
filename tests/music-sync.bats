#!/usr/bin/env bats

# Integration tests for music-sync main script

load test_helper

setup() {
    setup_test_environment
    create_test_configs
    mock_rsync
    mock_ssh
    load_test_sync_lib
    
    # Create a test version of music-sync that uses our test library
    cat > "${TEST_TMP_DIR}/music-sync" << EOF
#!/bin/bash
set -euo pipefail
SCRIPT_DIR="${TEST_TMP_DIR}"
LIB_DIR="${TEST_TMP_DIR}"
source "\${LIB_DIR}/sync-lib-test.sh"

show_usage() {
    echo "Music Sync - Unified script for syncing music collections"
    echo ""
    echo "Usage: \$0 [-n] [-y] <artist>"
    echo ""
    echo "Options:"
    echo "  -n    Dry run (preview changes only)"
    echo "  -y    Skip confirmation prompts"
    echo ""
    echo "Available artists:"
    ls "\${CONFIG_DIR}"/*.conf 2>/dev/null | sed 's|.*/||; s|\.conf\$||' | sort | sed 's/^/  /'
    echo ""
}

if [[ \$# -eq 0 ]] || [[ "\$1" == "-h" ]] || [[ "\$1" == "--help" ]]; then
    show_usage
    exit 0
fi

perform_sync "\$@"
EOF
    chmod +x "${TEST_TMP_DIR}/music-sync"
}

teardown() {
    teardown_test_environment
}

@test "music-sync shows help when called with no arguments" {
    run "${TEST_TMP_DIR}/music-sync"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Music Sync - Unified script"* ]]
    [[ "$output" == *"Usage:"* ]]
    [[ "$output" == *"Available artists:"* ]]
    [[ "$output" == *"test-artist"* ]]
}

@test "music-sync shows help with -h flag" {
    run "${TEST_TMP_DIR}/music-sync" -h
    [ "$status" -eq 0 ]
    [[ "$output" == *"Music Sync - Unified script"* ]]
    [[ "$output" == *"Usage:"* ]]
}

@test "music-sync shows help with --help flag" {
    run "${TEST_TMP_DIR}/music-sync" --help
    [ "$status" -eq 0 ]
    [[ "$output" == *"Music Sync - Unified script"* ]]
    [[ "$output" == *"Usage:"* ]]
}

@test "music-sync executes sync for valid artist" {
    run "${TEST_TMP_DIR}/music-sync" -y test-artist
    [ "$status" -eq 0 ]
    [[ "$output" == *"Artist: Test Artist"* ]]
    [[ "$output" == *"Source: ${TEST_TMP_DIR}/source/Test Artist/"* ]]
    [[ "$output" == *"Plex Target: test-server:/test/plex/Test Artist/Live/"* ]]
    assert_rsync_called_with "${TEST_TMP_DIR}/source/Test Artist/"
}

@test "music-sync handles dry run flag" {
    run "${TEST_TMP_DIR}/music-sync" -ny test-artist
    [ "$status" -eq 0 ]
    [[ "$output" == *"DRY RUN COMPLETE"* ]]
    assert_rsync_called_with "--dry-run"
}

@test "music-sync fails with invalid artist" {
    run "${TEST_TMP_DIR}/music-sync" -y nonexistent-artist
    [ "$status" -eq 1 ]
    [[ "$output" == *"Artist configuration file not found"* ]]
    [[ "$output" == *"Available artists:"* ]]
}

@test "music-sync fails with invalid flag" {
    run "${TEST_TMP_DIR}/music-sync" -x test-artist
    [ "$status" -eq 1 ]
    [[ "$output" == *"Usage:"* ]]
}

@test "music-sync handles combined flags correctly" {
    run "${TEST_TMP_DIR}/music-sync" -ny test-artist
    [ "$status" -eq 0 ]
    [[ "$output" == *"Artist: Test Artist"* ]]
    [[ "$output" == *"DRY RUN COMPLETE"* ]]
    assert_rsync_called_with "--dry-run"
}

@test "music-sync executes full sync workflow" {
    # Create the source directory for this test
    mkdir -p "${TEST_TMP_DIR}/source/Full Test"
    
    # Create a config with NAS backup and verification enabled
    cat > "${TEST_TMP_DIR}/config/full-test.conf" << 'EOF'
ARTIST_NAME="Full Test Artist"
ARTIST_SLUG="full-test"
SOURCE_SUBDIR="Full Test/"
ENABLE_NAS_BACKUP=true
NAS_SUBDIR="Full Test/"
PLEX_SUBDIR="Full Test/Live/"
EXCLUDE_FILE="test-excludes.txt"
VERIFICATION_ENABLED=true
VERIFICATION_CMD="ssh test-server 'echo verification complete'"
VERIFICATION_DESC="Full test verification"
EOF

    run "${TEST_TMP_DIR}/music-sync" -y full-test
    [ "$status" -eq 0 ]
    
    # Check that both NAS and Plex syncs occurred
    assert_rsync_called_with "${TEST_TMP_DIR}/source/Full Test/"
    assert_rsync_called_with "${TEST_TMP_DIR}/nas/Full Test/"
    assert_rsync_called_with "test-server:/test/plex/Full Test/Live/"
    
    # Check verification ran
    [[ "$output" == *"Full test verification"* ]]
    assert_file_exists "${TEST_TMP_DIR}/ssh.log"
    
    # Check completion message
    [[ "$output" == *"Sync completed successfully"* ]]
}