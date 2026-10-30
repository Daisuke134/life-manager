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

The RevenueCat package lock uses `5.78.0`, which includes the official
[Xcode 27 initializer compilation fix](https://github.com/RevenueCat/purchases-ios/pull/6949).
Other package pins remain unchanged.

Run the isolated hook checks with:

```sh
python3 apps/mobile/anicca-ios/scripts/tests/test_cloud_build_config.py
```

## App Review purchases

The plan screen opens after onboarding and from Feed → Settings → Subscribe.
It prefers the configured `anicca_variant_b` offering so a shared legacy
`current` offering cannot hide its Lifetime product. StoreKit supplies the
available products and localized prices; there is no language/Japan-only gate.

Run Maestro `maestro/v1.8.0/11-app-review-purchases.yaml` on a clean simulator
to check onboarding, all three plans, free dismissal and the Settings entry.
Then run `12-storekit-cancel-restore.yaml` on the same simulator to check
Apple purchase authentication, cancellation and return from Restore Purchases.
The latter does not authenticate a Sandbox Apple Account or prove a completed
purchase/paid-entitlement restoration. Maestro requires Java 17 or newer.
