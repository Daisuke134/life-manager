fastlane documentation
----

# Installation

Make sure you have the latest version of the Xcode command line tools installed:

```sh
xcode-select --install
```

For _fastlane_ installation instructions, see [Installing _fastlane_](https://docs.fastlane.tools/#installing-fastlane)

# Available Actions

## iOS

### ios build_for_device

```sh
[bundle exec] fastlane ios build_for_device
```

Build and install on connected device

### ios build

```sh
[bundle exec] fastlane ios build
```

Build, archive, and export IPA for App Store

### ios upload

```sh
[bundle exec] fastlane ios upload
```

Upload IPA to App Store Connect

### ios release

```sh
[bundle exec] fastlane ios release
```

Build and upload only (use full_release for complete automation)

### ios wait_for_processing

```sh
[bundle exec] fastlane ios wait_for_processing
```

Wait for build processing to complete

### ios submit_review

```sh
[bundle exec] fastlane ios submit_review
```

Submit the latest build for App Store review

### ios full_release

```sh
[bundle exec] fastlane ios full_release
```

Complete automated release: build, upload, wait, and submit for review

### ios build_for_simulator

```sh
[bundle exec] fastlane ios build_for_simulator
```

Build and run on simulator

### ios test

```sh
[bundle exec] fastlane ios test
```

Run unit tests on simulator

### ios set_version

```sh
[bundle exec] fastlane ios set_version
```

Set MARKETING_VERSION across all targets

### ios test_on_device

```sh
[bundle exec] fastlane ios test_on_device
```

Quick test: build and install on device, then notify

----

This README.md is auto-generated and will be re-generated every time [_fastlane_](https://fastlane.tools) is run.

More information about _fastlane_ can be found on [fastlane.tools](https://fastlane.tools).

The documentation of _fastlane_ can be found on [docs.fastlane.tools](https://docs.fastlane.tools).
