# ANICCA iOS TestFlight release

## Goal

Release the onboarding and paywall fixes as an installable ANICCA iOS TestFlight build, then deliver the public TestFlight link and successful Maestro video/screenshots to Dais's Telegram Saved Messages.

## Source and release state

- Life Manager `main` is the app source of truth. PR [#6619](https://github.com/Daisuke134/life-manager/pull/6619) merged at `46fa60d619f31dd7719083e891b001ba372c4871`; latest observed Life Manager `main` is `6247a0663fb2f6d5ae48431a33d89ee1986731e0`.
- App Store Connect Xcode Cloud is still connected to `Daisuke134/anicca-products`. PR [#418](https://github.com/Daisuke134/anicca-products/pull/418) mirrors the release-relevant ANICCA source and Maestro flow and merged as `6168d52cef4770cf6213c44d3d9aabf5c225e1e5`.
- The merged release source sets all 12 app, widget, and notification-service configurations to marketing version `1.9.6`, build `391`; the existing provider bootstrap is preserved.
- ASC workflow `Default` is enabled, locked for editing, App Store eligible, and configured for `main`; its repository is `Daisuke134/anicca-products`, and ASC exposes `refs/heads/main` as SCM ref `43a2fbce-80a8-424b-a5ab-a68becb7e747`. Run `#802` (`5056c6f4-0b79-4ebd-ba1f-50e946f4e20e`) was `PENDING` at the older `2026-10-05 16:51 UTC` readback. Fresh readback at `2026-10-05 21:59 UTC` reports `executionProgress=COMPLETE`, `completionStatus=ERRORED`; the run has no source commit SHA, actions, artifacts, or log bundles. `asc xcode-cloud doctor` concludes the run failed without a more specific diagnostic, and the official issues query cannot resolve an issue because no build action exists. The SCM API lists the GitHub Cloud provider, repository, and `main` ref, but the web-only SCM connection-status read remains unavailable because the cached Apple web session expired. Do not infer the cause or create a replacement run before inspecting this failure boundary.
- ASC reports `latestProcessedBuildNumber=365`, `latestUploadBuildNumber=390`, and `nextBuildNumber=391`. A fresh exact query, `asc builds list --app ai.anicca.app.ios --version 1.9.6 --build-number 391 --platform IOS`, returns `data=[]`. A historical `1.8.6 (391)` upload failed on `2026-05-06`; no current `1.9.6 (391)` build is attached to run #802 or available for TestFlight.
- Spec PR [#6625](https://github.com/Daisuke134/life-manager/pull/6625) merged as `8b782c20c221784367de1fc9acec572594bf175b1`; PR [#6626](https://github.com/Daisuke134/life-manager/pull/6626) also merged as `ee27ac09fe2bbfc2d8757028b071ef85c675c503` after refreshing the Capafy inventory digest. These historical checks are complete.
- External beta group `anicca-beta` remains public-link-enabled at `https://testflight.apple.com/join/5j9nuumu` and has 19 existing build relationships. This does not prove the requested `1.9.6 (391)` build is attached or installable; that build is absent.

## Verified evidence

- Life Manager PR #6619 and release-mirror PR #418 both passed read-only review; the latter's final review found no actionable issue. The release-mirror repo has no GitHub CI run for this PR; CodeRabbit reports manual review required and skips.
- The current Maestro v7 onboarding and soft-paywall flow passed 1/1 on Staging in 46.038 seconds. It records a 46-second MP4 and 13 screenshots at `~/.local/state/life-manager/maestro-evidence/anicca-ios/20261005T140737/maestro/2026-10-05_151457/ANICCA v7 Onboarding and Soft Paywall/`.
- The successful-run E2E text, MP4, and all 13 screenshots were sent to Dais's Saved Messages. Telegram readback confirmed the text, video, and 13 photo messages (15 messages total).
- Four onboarding/paywall source files and the Maestro flow match Life Manager `main`; YAML parsing, all 12 version/build settings, and `git diff --check` passed.
- Staging has no RevenueCat offerings. The Maestro run verifies onboarding, paywall presentation, soft close, and main-feed arrival; it does not verify purchase, restore, or production subscription products.

## Cursor order update

- Reason: the successful Staging E2E media is complete and independent of the queued Xcode Cloud build, so delivering it now shortens the time until Dais can inspect the flow.
- Old order: wait for Cloud → validate ASC build → beta review → verify link → send link and E2E media together.
- New order: send E2E media now → wait for Cloud → validate ASC build → beta review → verify and send installable link.
- Current cursor: item 2. Item 1 completed with Telegram readback; send the TestFlight link only after the build is approved.

## Remaining work, in order

1. DONE: send the successful Maestro MP4 and all 13 screenshots to Dais's Saved Messages; readback confirmed the text, video, and 13 photos. This is not TestFlight or purchase evidence.
2. Diagnose run #802 after its terminal `ERRORED` readback: recheck the official Xcode Cloud workflow/SCM connection and source binding, because ASC exposes no source SHA, build action, issue, artifact, or log bundle. Do not duplicate or cancel the run. If the connection/source configuration is wrong, fix it through a main-derived PR; only then start one replacement workflow run.
3. Read back the uploaded ASC build and require version `1.9.6`, build `391`, processing state `VALID`, and resolved encryption compliance. Do not treat the Xcode Cloud run number `802` as the app build number. If ASC rejects the version/build tuple, increment to the next available build number through a main-derived PR before starting a replacement run.
4. Assign that exact build to external beta group `73c905e3-b70a-4479-b385-b99f982fa1c0` and submit it for beta review. Wait for Apple approval and verify the approved build is attached to the public group.
5. Confirm the public TestFlight link opens the newly approved build, then send that installable link to Saved Messages and read it back. Until then, do not describe the existing public link as installable.

## Completed so far

The onboarding/paywall source is merged to Life Manager main and mirrored to `anicca-products` main. The Staging Maestro E2E video and all 13 screenshots are in Telegram Saved Messages with successful readback. Purchase, restore, and production subscription behavior remain untested because Staging has no RevenueCat offerings.

The TestFlight release is **not complete**: Xcode Cloud run #802 is `ERRORED` without a specific ASC diagnostic, ASC has no `1.9.6 (391)` build, and the enabled public link is not verified against the requested release. Do not report it as an installable link until the target build is assigned and approved.
