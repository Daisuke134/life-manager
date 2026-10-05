# ANICCA iOS TestFlight release

## Goal

Release the onboarding and paywall fixes as an installable ANICCA iOS TestFlight build, then deliver the public TestFlight link and successful Maestro video/screenshots to Dais's Telegram Saved Messages.

## Source and release state

- Life Manager `main` is the app source of truth. PR [#6619](https://github.com/Daisuke134/life-manager/pull/6619) merged at `46fa60d619f31dd7719083e891b001ba372c4871`; latest observed Life Manager `main` is `cd5b63901e83189692d4c36dd0c2b4eba5f76ec8`.
- App Store Connect Xcode Cloud is still connected to `Daisuke134/anicca-products`. PR [#418](https://github.com/Daisuke134/anicca-products/pull/418) mirrors the release-relevant ANICCA source and Maestro flow and merged as `6168d52cef4770cf6213c44d3d9aabf5c225e1e5`.
- The merged release source sets all 12 app, widget, and notification-service configurations to marketing version `1.9.6`, build `391`; the existing provider bootstrap is preserved.
- ASC workflow `Default` is enabled for `main` and App Store eligible. Manual Xcode Cloud run `#802` (`5056c6f4-0b79-4ebd-ba1f-50e946f4e20e`) is `PENDING` as of `2026-10-05 07:14 UTC`; it has no actions or artifacts yet, and ASC has not exposed its source commit. ASC reports build number `391` unused; no App Store Connect build `1.9.6 (391)` exists yet.
- Spec PR [#6625](https://github.com/Daisuke134/life-manager/pull/6625) is open. Its `OSS self-contained boundary` check reports `manifest_inventory_mismatch skills/capafy-autopublish`; the same failure appears on main CI run `37275422749` for main commit `cd5b639`. This is a separate main-branch integrity failure; it is not treated as a pass or bypassed.
- External beta group `anicca-beta` is enabled with public link `https://testflight.apple.com/join/5j9nuumu`. The link is not yet installable because no new build is assigned or approved.

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
2. Keep observing Xcode Cloud run #802 until it reaches a terminal state. Confirm its source commit is `6168d52cef4770cf6213c44d3d9aabf5c225e1e5`. If it fails, diagnose the run's issue/log evidence and fix through a new main-derived PR; do not duplicate a still-pending run.
3. Read back the uploaded ASC build and require version `1.9.6`, build `391`, processing state `VALID`, and resolved encryption compliance. Do not treat the Xcode Cloud run number `802` as the app build number.
4. Assign that exact build to external beta group `73c905e3-b70a-4479-b385-b99f982fa1c0` and submit it for beta review. Wait for Apple approval and verify the approved build is attached to the public group.
5. Confirm the public TestFlight link opens the newly approved build, then send that installable link to Saved Messages and read it back. Until then, do not describe the existing public link as installable.

## Done

The TestFlight link exposes build `1.9.6 (391)` to external testers, and Telegram Saved Messages contains the link, MP4, and all 13 screenshots with a successful readback. The Staging E2E result remains separate from production purchase validation and does not establish paid conversion or MRR.
