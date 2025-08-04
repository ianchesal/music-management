#!/usr/bin/env bats

# Unit tests for sync-lib.sh functions

load test_helper

setup() {
    setup_test_environment
    create_test_configs
    mock_rsync
    mock_ssh
    load_test_sync_lib
}

teardown() {
    teardown_test_environment
}

@test "load_global_config loads configuration successfully" {
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && load_global_config && echo MUSIC_SOURCE_BASE=\$MUSIC_SOURCE_BASE && echo NAS_BASE=\$NAS_BASE && echo PLEX_SERVER=\$PLEX_SERVER"
    [ "$status" -eq 0 ]
    [[ "$output" == *"MUSIC_SOURCE_BASE=${TEST_TMP_DIR}/source"* ]]
    [[ "$output" == *"NAS_BASE=${TEST_TMP_DIR}/nas"* ]]
    [[ "$output" == *"PLEX_SERVER=test-server"* ]]
}

@test "load_global_config fails with missing config file" {
    rm "${TEST_TMP_DIR}/config/global.conf"
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && load_global_config"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Global configuration file not found"* ]]
}

@test "load_artist_config loads artist configuration successfully" {
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && load_artist_config test-artist && echo ARTIST_NAME=\$ARTIST_NAME && echo SOURCE_SUBDIR=\$SOURCE_SUBDIR && echo ENABLE_NAS_BACKUP=\$ENABLE_NAS_BACKUP"
    [ "$status" -eq 0 ]
    [[ "$output" == *"ARTIST_NAME=Test Artist"* ]]
    [[ "$output" == *"SOURCE_SUBDIR=Test Artist/"* ]]
    [[ "$output" == *"ENABLE_NAS_BACKUP=false"* ]]
}

@test "load_artist_config fails with missing artist config" {
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && load_artist_config nonexistent-artist"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Artist configuration file not found"* ]]
    [[ "$output" == *"Available artists:"* ]]
}

@test "parse_args handles dry run flag" {
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && parse_args -n test-artist && echo DRY_RUN=\$DRY_RUN && echo ARTIST_SLUG=\$ARTIST_SLUG"
    [ "$status" -eq 0 ]
    [[ "$output" == *"DRY_RUN=--dry-run"* ]]
    [[ "$output" == *"ARTIST_SLUG=test-artist"* ]]
}

@test "parse_args handles skip confirmation flag" {
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && parse_args -y test-artist && echo SKIP_CONFIRM=\$SKIP_CONFIRM && echo ARTIST_SLUG=\$ARTIST_SLUG"
    [ "$status" -eq 0 ]
    [[ "$output" == *"SKIP_CONFIRM=true"* ]]
    [[ "$output" == *"ARTIST_SLUG=test-artist"* ]]
}

@test "parse_args handles combined flags" {
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && parse_args -ny test-artist && echo DRY_RUN=\$DRY_RUN && echo SKIP_CONFIRM=\$SKIP_CONFIRM && echo ARTIST_SLUG=\$ARTIST_SLUG"
    [ "$status" -eq 0 ]
    [[ "$output" == *"DRY_RUN=--dry-run"* ]]
    [[ "$output" == *"SKIP_CONFIRM=true"* ]]
    [[ "$output" == *"ARTIST_SLUG=test-artist"* ]]
}

@test "parse_args fails without artist argument" {
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && parse_args -n"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Artist name required"* ]]
}

@test "parse_args fails with invalid flag" {
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && parse_args -x test-artist"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Usage:"* ]]
}

@test "init_sync initializes environment correctly" {
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && parse_args test-artist && init_sync && echo SRC=\$SRC && echo PLEX=\$PLEX && echo EXCLUDE_FILE_PATH=\$EXCLUDE_FILE_PATH"
    [ "$status" -eq 0 ]
    [[ "$output" == *"SRC=${TEST_TMP_DIR}/source/Test Artist/"* ]]
    [[ "$output" == *"PLEX=test-server:/test/plex/Test Artist/Live/"* ]]
    [[ "$output" == *"EXCLUDE_FILE_PATH=${TEST_TMP_DIR}/test-excludes.txt"* ]]
}

@test "init_sync sets NAS path when backup enabled" {
    # Create config with NAS backup enabled
    cat > "${TEST_TMP_DIR}/config/test-artist.conf" << 'EOF'
ARTIST_NAME="Test Artist"
ARTIST_SLUG="test-artist"
SOURCE_SUBDIR="Test Artist/"
ENABLE_NAS_BACKUP=true
NAS_SUBDIR="Test Artist/"
PLEX_SUBDIR="Test Artist/Live/"
EXCLUDE_FILE="test-excludes.txt"
VERIFICATION_ENABLED=false
EOF

    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && parse_args test-artist && init_sync && echo NAS=\$NAS"
    [ "$status" -eq 0 ]
    [[ "$output" == *"NAS=${TEST_TMP_DIR}/nas/Test Artist/"* ]]
}

@test "validate_environment passes with valid setup" {
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && parse_args test-artist && init_sync && validate_environment"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Artist: Test Artist"* ]]
    [[ "$output" == *"Source: ${TEST_TMP_DIR}/source/Test Artist/"* ]]
}

@test "validate_environment fails with missing exclude file" {
    rm "${TEST_TMP_DIR}/test-excludes.txt"
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && parse_args test-artist && init_sync && validate_environment"
    [ "$status" -eq 1 ]
    [[ "$output" == *"Exclude file not found"* ]]
}

@test "sync_to_nas skips when NAS backup disabled" {
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && parse_args test-artist && init_sync && sync_to_nas"
    [ "$status" -eq 0 ]
    [ ! -f "${TEST_TMP_DIR}/rsync.log" ]
}

@test "sync_to_nas executes when NAS backup enabled" {
    # Create config with NAS backup enabled
    cat > "${TEST_TMP_DIR}/config/test-artist.conf" << 'EOF'
ARTIST_NAME="Test Artist"
ARTIST_SLUG="test-artist"
SOURCE_SUBDIR="Test Artist/"
ENABLE_NAS_BACKUP=true
NAS_SUBDIR="Test Artist/"
PLEX_SUBDIR="Test Artist/Live/"
EXCLUDE_FILE="test-excludes.txt"
VERIFICATION_ENABLED=false
EOF

    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && parse_args test-artist && init_sync && sync_to_nas"
    [ "$status" -eq 0 ]
    assert_rsync_called_with "${TEST_TMP_DIR}/source/Test Artist/"
    assert_rsync_called_with "${TEST_TMP_DIR}/nas/Test Artist/"
}

@test "sync_to_plex executes rsync with exclusions" {
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && parse_args test-artist && init_sync && sync_to_plex"
    [ "$status" -eq 0 ]
    assert_rsync_called_with "--delete-excluded"
    assert_rsync_called_with "--exclude-from=${TEST_TMP_DIR}/test-excludes.txt"
    assert_rsync_called_with "${TEST_TMP_DIR}/source/Test Artist/"
    assert_rsync_called_with "test-server:/test/plex/Test Artist/Live/"
}

@test "run_verification skips in dry run mode" {
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && parse_args -n test-artist && init_sync && run_verification"
    [ "$status" -eq 0 ]
    [[ "$output" == *"DRY RUN COMPLETE"* ]]
}

@test "run_verification skips when verification disabled" {
    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && parse_args test-artist && init_sync && run_verification"
    [ "$status" -eq 0 ]
    [ ! -f "${TEST_TMP_DIR}/ssh.log" ]
}

@test "run_verification executes when enabled" {
    # Create config with verification enabled
    cat > "${TEST_TMP_DIR}/config/test-artist.conf" << 'EOF'
ARTIST_NAME="Test Artist"
ARTIST_SLUG="test-artist"
SOURCE_SUBDIR="Test Artist/"
ENABLE_NAS_BACKUP=false
PLEX_SUBDIR="Test Artist/Live/"
EXCLUDE_FILE="test-excludes.txt"
VERIFICATION_ENABLED=true
VERIFICATION_CMD="ssh test-server 'echo verification test'"
VERIFICATION_DESC="Test verification"
EOF

    run bash -c "source '${TEST_TMP_DIR}/sync-lib-test.sh' && parse_args test-artist && init_sync && run_verification"
    [ "$status" -eq 0 ]
    [[ "$output" == *"Test verification"* ]]
    assert_file_exists "${TEST_TMP_DIR}/ssh.log"
}