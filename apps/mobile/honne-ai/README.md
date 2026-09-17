# Honne AI

This is the canonical in-repository copy of the Honne AI mobile app and its
small backend. It was imported from the private `honne-ai` repository at
revision `b57928bb13ef1f9a1e774e4bca2467e3059c9eac`.

The app source and Xcode project are self-contained under this directory.
Runtime configuration is supplied through private build inputs. The following
values must never be committed: RevenueCat keys, toolkit URLs or credentials,
Apple App Store Connect IDs/keys, provisioning profiles, `ExportOptions.plist`,
and build output. `Config.swift` reads these values from process environment or
bundle build settings. The backend reads its toolkit URL from its environment.
