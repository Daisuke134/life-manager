# Maestro E2E Tests for Anicca iOS

This directory contains Maestro E2E UI tests for the Anicca iOS app.

## Prerequisites

### Install Maestro CLI

```bash
# macOS (Homebrew)
brew tap mobile-dev-inc/tap
brew install maestro

# Verify installation
maestro --version
```

### iOS Simulator

Ensure you have Xcode installed and an iOS Simulator available:

```bash
# List available simulators
xcrun simctl list devices available

# Boot a simulator (if not already running)
xcrun simctl boot "iPhone 15"
```

### Build the App

Build the app for the simulator before running tests:

```bash
cd aniccaios
xcodebuild -scheme aniccaios \
  -destination 'platform=iOS Simulator,name=iPhone 15' \
  -derivedDataPath ./build \
  build
```

## Test Scenarios

| File | Description |
|------|-------------|
| `01-onboarding.yaml` | Complete onboarding flow from first launch |
| `02-paywall.yaml` | Paywall display and dismiss |
| `03-session-start.yaml` | Voice session start and end |

## Running Tests

### Run All Tests

```bash
# From project root
maestro test maestro/

# Or use the helper script
./scripts/run-maestro-e2e.sh
```

### Run Individual Tests

```bash
# Onboarding flow
maestro test maestro/01-onboarding.yaml

# Paywall display
maestro test maestro/02-paywall.yaml

# Voice session
maestro test maestro/03-session-start.yaml
```

### Debug Mode

For detailed logging when tests fail:

```bash
maestro test --debug maestro/01-onboarding.yaml
```

## Test Design Notes

### Text-Based Taps

All tests use text-based element selection (`text:` instead of `id:`) to avoid requiring `accessibilityIdentifier` additions to the iOS codebase. This means:

- Tests are more fragile to UI text changes
- Tests support localization by changing the text values
- No Swift code modifications are needed

### Optional Assertions

Many assertions use `optional: true` to handle:
- Permission dialogs that may or may not appear
- UI variations between iOS versions
- State that depends on previous test runs

### Test Dependencies

- **01-onboarding.yaml**: Can run standalone (clears app state)
- **02-paywall.yaml**: Requires user to be signed in
- **03-session-start.yaml**: Requires user to be signed in with microphone permission

## CI Integration

Tests run automatically on:
- Pull requests to `main`
- Pushes to `main`
- Manual trigger via `workflow_dispatch`

See `.github/workflows/maestro-e2e.yml` for the CI configuration.

## Troubleshooting

### Simulator Not Found

```bash
# List available simulators
xcrun simctl list devices available

# Create a new simulator if needed
xcrun simctl create "iPhone 15" "iPhone 15" iOS17.0
```

### App Not Installed

The app must be built and installed on the simulator:

```bash
# Build and install
xcodebuild -scheme aniccaios \
  -destination 'platform=iOS Simulator,name=iPhone 15' \
  build

# Or install a pre-built .app
xcrun simctl install booted path/to/aniccaios.app
```

### Element Not Found

- Run with `--debug` to see detailed logs
- Check if the text matches exactly (case-sensitive)
- Increase timeout values for slow operations
- Verify the element is visible on screen

## Adding New Tests

1. Create a new file: `maestro/NN-description.yaml` (NN = sequential number)
2. Follow the YAML structure from existing tests
3. Use text-based taps with `optional: true` for unreliable elements
4. Add to this README

## References

- [Maestro Documentation](https://maestro.mobile.dev/)
- [Maestro YAML Reference](https://maestro.mobile.dev/reference)
- [Maestro GitHub](https://github.com/mobile-dev-inc/maestro)

