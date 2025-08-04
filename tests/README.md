# Music Sync Tests

This directory contains comprehensive tests for the music synchronization scripts using the [Bats testing framework](https://github.com/bats-core/bats-core).

## Test Structure

- **`test_helper.bash`** - Common test utilities and helper functions
- **`sync-lib.bats`** - Unit tests for the sync library functions
- **`music-sync.bats`** - Integration tests for the main music-sync script

## Running Tests Locally

### Prerequisites

1. Install Bats testing framework:
   ```bash
   git clone https://github.com/bats-core/bats-core.git
   cd bats-core
   sudo ./install.sh /usr/local
   ```

2. Install Bats helper libraries:
   ```bash
   mkdir -p tests/helpers
   cd tests/helpers
   git clone https://github.com/bats-core/bats-support.git
   git clone https://github.com/bats-core/bats-assert.git
   ```

### Running Tests

From the repository root:

```bash
# Run all tests
cd tests
bats *.bats

# Run specific test file
bats sync-lib.bats

# Run with verbose output
bats --verbose-run *.bats

# Run a specific test
bats --filter "load_global_config" sync-lib.bats
```

## Test Coverage

### Unit Tests (`sync-lib.bats`)
- Configuration loading (global and artist configs)
- Argument parsing and validation
- Environment initialization
- Individual sync functions (NAS backup, Plex sync)
- Verification functionality

### Integration Tests (`music-sync.bats`)
- End-to-end sync workflows
- Command-line interface
- Error handling
- Dry-run functionality

## Mocking Strategy

Tests use comprehensive mocking to avoid actual file operations:

- **`mock_rsync()`** - Captures rsync calls without executing transfers
- **`mock_ssh()`** - Simulates SSH commands for verification
- **Test configurations** - Isolated config files for testing
- **Temporary directories** - All test artifacts isolated in temp space

## GitHub Actions Integration

Tests run automatically on:
- Push to `main` or `develop` branches
- Pull requests to `main`

The CI pipeline includes:
- **Unit and integration tests** using Bats
- **Shell script linting** with ShellCheck
- **Configuration validation** to ensure all configs are valid
- **Documentation checks** to verify examples work

## Writing New Tests

When adding new functionality:

1. **Add unit tests** in `sync-lib.bats` for new library functions
2. **Add integration tests** in `music-sync.bats` for end-to-end workflows
3. **Update mocks** if new external commands are used
4. **Add test configs** for new artist configurations

Example test structure:
```bash
@test "descriptive test name" {
    # Setup test conditions
    setup_test_environment
    
    # Execute the function/script
    run function_to_test arg1 arg2
    
    # Verify results
    [ "$status" -eq 0 ]
    [[ "$output" == *"expected output"* ]]
    
    # Verify side effects
    assert_rsync_called_with "expected_args"
}
```

## Debugging Tests

For test failures:

1. **Run with verbose output**: `bats --verbose-run test_file.bats`
2. **Check temp directory**: Test artifacts are in `$BATS_TMPDIR/music-sync-tests`
3. **Add debug output**: Use `echo "debug: $variable" >&3` in tests
4. **Isolate failing test**: `bats --filter "test_name" test_file.bats`

## Test Philosophy

- **Fast feedback** - Tests run quickly using mocks instead of real operations
- **Comprehensive coverage** - All major code paths and error conditions tested
- **Realistic scenarios** - Tests mirror real-world usage patterns
- **Backward compatibility** - Ensure existing workflows continue to work
- **CI/CD ready** - Tests run reliably in GitHub Actions environment