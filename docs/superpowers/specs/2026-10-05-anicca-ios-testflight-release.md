# ANICCA iOS TestFlight release

## Goal

Release the onboarding and paywall fixes as an installable ANICCA iOS TestFlight build, then deliver the public TestFlight link and successful Maestro video/screenshots to Dais's Telegram Saved Messages.

## Source and release state

- Life Manager `main` is the app source of truth. PR [#6619](https://github.com/Daisuke134/life-manager/pull/6619) merged at `46fa60d619f31dd7719083e891b001ba372c4871`; latest observed Life Manager `main` is `6247a0663fb2f6d5ae48431a33d89ee1986731e0`.
- App Store Connect Xcode Cloud is still connected to `Daisuke134/anicca-products`. PR [#418](https://github.com/Daisuke134/anicca-products/pull/418) mirrors the release-relevant ANICCA source and Maestro flow and merged as `6168d52cef4770cf6213c44d3d9aabf5c225e1e5`.
- The merged release source sets all 12 app, widget, and notification-service configurations to marketing version `1.9.6`, build `391`; the existing provider bootstrap is preserved.
- ASC workflow `Default` is enabled and locked for editing, targets `main`, and has one required `Archive - iOS` action for scheme `aniccaios` with `APP_STORE_ELIGIBLE` distribution. Its linked repository is `Daisuke134/anicca-products`; the registered `refs/heads/main` SCM reference is `43a2fbce-80a8-424b-a5ab-a68becb7e747`. Run `#802` (`5056c6f4-0b79-4ebd-ba1f-50e946f4e20e`) is `COMPLETE/ERRORED` with no source SHA, build action, build, artifact, or log bundle; `doctor` and issues readback provide no cause. A single main-ref diagnostic run `#803` (`79e20a6d-b2af-467f-9184-4c8c82ed52e3`) was created at `2026-10-06T03:47:30Z`. At the fresh `2026-10-06 03:58:54 UTC` readback it remains `PENDING`, with no source SHA, action, or build. The bounded 5-minute doctor wait ended with `last status=PENDING`; this timeout is not a terminal run state. ASC reports all 51 developer services operational. The App Store Connect repository `lastAccessedDate` remains `2026-06-04T20:03:44.419Z`; this suggests stale source access but does not prove the cause. GitHub independently serves `anicca-products/main` at commit `1a8f5a30d27135f0c4d28f61adde0be9b3b469d8`.
- **Web-only SCM readback boundary:** the registered browser session lacked Apple cookies. The saved `apple-app-store` credential was accepted through the password step, then Apple required 2FA. The code supplied in-session was rejected; it was not stored. The local credential record has no TOTP field and TapKit reports no connected phone, so the web-only connection status remains unread. Do not copy credentials or codes into the repo, logs, or chat.
- A fresh exact ASC query for version `1.9.6`, build `391`, platform `IOS` returns `data=[]`. No current `1.9.6 (391)` build is available for TestFlight. A historical `1.8.6 (391)` upload failed on `2026-05-06`.
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
- Cursor order update: the original order was (2) read the web-only SCM connection and repair if needed, then (3) start one replacement run. After run #802 terminated and ASC confirmed the workflow/repository/main reference while no run was active, one explicit main-ref diagnostic run (#803) was started to test source acquisition directly. The new order is (2) observe the existing #803 run until source SHA/action or terminal evidence appears; (3) if it ends without source access, read and repair the web-only SCM connection before creating another run; then (4) validate the uploaded build. No further run is to be created while #803 is pending. Item 1 is complete with Telegram readback; send an installable TestFlight link only after the requested build is approved.

## Remaining work, in order

1. DONE: send the successful Maestro MP4 and all 13 screenshots to Dais's Saved Messages; readback confirmed the text, video, and 13 photos. This is not TestFlight or purchase evidence.
2. Observe the existing Xcode Cloud run #803 with official readback. It is still `PENDING` and has no source SHA/action/build. Do not cancel, replay, or create another run.
3. If #803 reaches Archive, verify its source commit is the expected `anicca-products/main` revision and continue. If it terminates without source access, read the official web-only SCM connection state and repair the existing GitHub link through Apple's supported flow before creating another run. The repo's June `lastAccessedDate` is a clue, not a confirmed cause. A fresh Apple 2FA challenge is required to read the web-only state; no code is stored locally.
4. Read back the uploaded ASC build and require version `1.9.6`, build `391` (or the next available number if 391 is consumed), processing state `VALID`, and resolved encryption compliance. Do not treat Xcode Cloud run number `803` as the app build number.
5. Assign the exact valid build to external beta group `73c905e3-b70a-4479-b385-b99f982fa1c0`, submit it for beta review, and verify Apple's approval and group attachment.
6. Confirm the public TestFlight link opens the newly approved build, then deliver that installable link to Dais and read it back. Until then, do not describe the existing public link as installable.

## Completed so far

The onboarding/paywall source is merged to Life Manager main and mirrored to `anicca-products` main. The Staging Maestro E2E video and all 13 screenshots are in Telegram Saved Messages with successful readback. Purchase, restore, and production subscription behavior remain untested because Staging has no RevenueCat offerings.

The TestFlight release is **not complete**: run #802 is `ERRORED` without a specific ASC diagnostic, replacement run #803 remains `PENDING` without a source SHA or action, ASC has no `1.9.6 (391)` build, and the enabled public link is not verified against the requested release. Do not report it as an installable link until the target build is assigned and approved.
