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
