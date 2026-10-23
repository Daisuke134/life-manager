# Anicca iOS

This is the canonical in-repository copy of the Anicca iOS source. It was
imported from `Daisuke134/anicca-products`, subdirectory `aniccaios`, revision
`a9ab8a17c7dee9af8c3f2ad752a902ce26e7d1d3`.

## Private build inputs

The checked-in `Configs/*.example` files document the required Xcode settings.
Copy the appropriate example to the ignored `Configs/Production.xcconfig` or
`Configs/Staging.xcconfig` and fill it from the private credential/state store.
Apple signing identities, provisioning profiles, App Store Connect keys,
`.env.ios`, `ExportOptions.plist`, and build output are intentionally not source
files and must remain outside Git.

The Xcode project and test targets use paths relative to this directory. No
external checkout is required for source editing.

## Xcode Cloud release builds

Use the existing Anicca product with repository `Daisuke134/life-manager`,
container `apps/mobile/anicca-ios/aniccaios.xcodeproj`, and scheme `aniccaios`.
Set the secret product environment variable `ANICCA_PRODUCTION_XCCONFIG_B64`
to the Base64 encoding of the verified private production configuration from
the credential SSOT. Never commit the encoded value or print it in build logs.

The executable `ci_scripts/ci_post_clone.sh` writes
`Configs/Production.xcconfig` with mode `0600` before the Release archive.
Missing, malformed, or empty input fails the hook and preserves an existing
configuration. Staging builds still require their separate private input.
This follows Apple's [custom build script placement](https://developer.apple.com/documentation/xcode/writing-custom-build-scripts).

Run the isolated hook checks with:

```sh
python3 apps/mobile/anicca-ios/scripts/tests/test_cloud_build_config.py
```
