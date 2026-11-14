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

## Initial affirmation experience

The active first-run journey is welcome → goal → optional name → optional birth
context → mood baseline → pain points → up to two selected deep-dive modules →
frequency → belief themes → tone → life context → routine anchors → prior attempts
→ an optional follow-up on unhelpful methods → starting reason → quiet hours → a
saveable personalized preview → reminder schedule → optional notification
permission → soft paywall → first intervention → today's affirmation.
Modules follow stress, anxiety, self-doubt, procrastination, sleep priority,
independent of selection order. Sleep asks reason, bedtime and wake time separately.
The journey has 20–24 screens through the first intervention, including the name
step and at least one selected pain point, depending on answers;
actual completion time must be measured on the simulator/device.

Answers persist in `UserProfile.personalization`, migrating the old separate
profile on first load. A local `SyntheticUser` record built from enumerated answer
IDs conditions selection and notification schedules, with intervention history
preserved across answer changes. The separate name question supplies the on-device
form of address in the first intervention; saved step 9 resumes at that question.
Raw names and birth dates never enter the synthetic record or eval cases. Decision records use
`managerbench-cases.jsonl`: situation → stimulus → measured response, with explicit
nulls for unobserved outcomes and the actual assignment probability. Notifications
without sender assignment metadata remain pending observations, not complete eval
cases. Quiet hours suppress conflicting delivery slots, including an
empty schedule when all preset times are blocked. The remote APNs sender must
honor the synchronized schedule; server receipt/delivery is a separate readback.
The home keeps one affirmation for the local day and language, starting with the
exact first intervention. A tapped notification takes priority. Legacy persisted
step values remain stable and map into this journey.

The native journey regression can run without Xcode:

```sh
swiftc -swift-version 5 aniccaios/Onboarding/OnboardingStep.swift \
  scripts/tests/OnboardingJourneyTests.swift -o /tmp/anicca-onboarding-tests
/tmp/anicca-onboarding-tests
```

This checks the production routing policy. It does not replace a simulator build
or the Maestro first-run/permission/restore coverage.

The notification-body regression compiles the production coordinator directly,
without building the Xcode project:

```sh
swiftc -swift-version 5 aniccaios/Services/QuoteNavigationCoordinator.swift \
  scripts/tests/QuoteNavigationTestSupport.swift \
  scripts/tests/QuoteNavigationTests.swift -o /tmp/anicca-quote-navigation-tests
/tmp/anicca-quote-navigation-tests
```

This covers cold-start body-only delivery, unknown IDs, case-insensitive catalog
matches, text added around a catalog quote, and replacing an existing feed quote
with the tapped notification body. The visible text must remain the body supplied
by the tapped notification.

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

## Phase 1 UI/UX audit capture

Run `.github/workflows/anicca-ios-build.yml` with `run_maestro=false` for the build
and unit tests, then separately with `run_maestro=true` for the real simulator
journey. The delegated fixes are documented in `PHASE1-UIUX-FIX-NOTES.md`.
The canonical runner `scripts/run-soft-paywall-maestro.sh` writes screenshots
01–13 to the evidence artifact's `frames/` directory. Additional frames cover
welcome, name, alternative plans, selected theme after relaunch, settings, and
notification settings. Round two adds branches 01c–01d, 02b–02h and 03b–03i.
The runner first captures `02-adaptive-modules.yaml` (stress/self-doubt and
procrastination), then the canonical anxiety/sleep journey. Either flow failing
fails the job. These captures require the real CI run; local source
checks are not screenshots or E2E evidence. This workflow does not submit to the
App Store.
