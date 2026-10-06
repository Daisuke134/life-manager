# ANICCA iOS TestFlight and mobile growth

## Goal

Deliver the merged ANICCA onboarding/paywall changes in an installable TestFlight build, then build a measured growth loop for the six published iOS apps, starting with Anicca. The business target is USD 10,000 verified net MRR; it is not achieved and must not be reported as achieved.

This lane uses App Store Connect CLI/API and TestFlight. TapKit is not a dependency.

## Source, ownership, and current readback

The app source of truth remains Life Manager main. PR #6619 contains the onboarding/paywall source; PR #418 mirrors the release source and Maestro flow to anicca-products main. The target source sets app, widget, and notification-service targets to version 1.9.6, build 391. Fresh readbacks in this update were taken on 2026-10-07 JST (2026-10-06 21:45–21:47 UTC); where this section differs from the earlier dated snapshots below, this readback is current.

The separate mobile-metrics implementation remains on branch feat/lm-mobile-metrics-20261003 in its own worktree, with no open PR in the 2026-10-06 readback. It owns those Life Manager acquisition/CFO ingestion edits; this TestFlight lane consumes its read-only provider results and does not edit its files or worktree.

## Published portfolio

ASC lists 24 app records, of which 6 are published across 175 territories. The other 18 records are not in ASC's published-app set and must not be counted as live acquisition products.

| Published app | ASC app ID | Bundle ID | Current verified state |
|---|---:|---|---|
| Daily Affirmations - Anicca | 6755129214 | ai.anicca.app.ios | Public 1.9.4; 1.9.5 rejected; latest build 365 expired |
| Honne | 6759667221 | app.rork.hon-ne-honyaku-ai | Public 1.0.3; 1.0.4 developer-rejected; latest 1.0.4 build is VALID but still processing for internal TestFlight |
| Dhamma Quotes | 6757726663 | com.dailydhamma.app | Public 1.1.0 |
| For Better Sleep - Sleep Reset | 6762143790 | app.rork.vcinrjbl3ke00f07gtlzf | Public 1.0.1 |
| STUDIO CHERIE | 6766485903 | app.rork.xhozd938ie79zdqd5plem | Public 1.0 |
| Thankful - Gratitude Journal | 6759514159 | app.rork.thankful-gratitude-app | Public 1.0.1 |

Anicca and Honne each have zero ratings in the US public listing readback. The public TestFlight join URL exists at https://testflight.apple.com/join/5j9nuumu, but it is not evidence that the intended 1.9.6 build is installable.

## Money: what is verified now

| App/source | Latest verified observation | Meaning |
|---|---|---|
| Anicca, RevenueCat | USD 20.34 MRR and 5 active subscriptions; latest complete chart point is 2026-10-05 UTC | Current provider-observed subscription run rate, not reconciled net proceeds |
| Honne, RevenueCat | USD 0 MRR and 0 actives; latest complete chart point is 2026-10-05 UTC | Current result for this mapped RevenueCat app, not lifetime revenue |
| Apple Finance Detail | The latest completed report covers 2026-08-30–2026-09-26. It contains one Anicca Annual sale: partner share JPY 4,250, quantity 1, transaction and settlement date 2026-09-12. No Honne row appears in this report. | Official Apple financial row; no matching bank receipt or expense reconciliation was verified here |
| Other four published apps | No current RevenueCat app/product binding was found in the verified project crosswalk | Their MRR is unknown, not zero |

The exact attribution is ASC subscription child record 6762049696 plus SKU ai.anicca.app.ios.yearly.b under Anicca parent app 6755129214. This corrects the 2026-10-05 SSOT note that left the row unassigned after comparing the child record ID directly to the parent app ID. The row remains Apple partner share, not a bank receipt or company net result.

The current mobile-portfolio net MRR is unknown. RevenueCat MRR, Apple partner share, bank payout, refunds, platform fees, and direct app/provider costs are different measures and are not yet joined for one common period.

At Anicca's current RevenueCat ratio, USD 20.34 / 5 is about USD 4.07 MRR per active subscription. USD 10,000 / USD 20.34 is about 492 times the present provider-observed MRR; the same observed mix would require about 2,459 active-subscription equivalents. This is a scale calculation, not a forecast or net-MRR proof. The Apple JPY 4,250 report row is not monthly MRR and must not be divided by 12 to claim MRR.

## Acquisition and store-page funnel

The latest read-only run of the main ASC acquisition collector was processed on 2026-10-06. For Anicca, its download and discovery reports cover 2026-10-04–2026-10-05: 3 first-time downloads, 25 unique impressions, and 0 unique product-page views. The descriptive store-total ratio is 3/25 (12.0%) on only 25 impressions; it is not campaign attribution or a stable conversion estimate. Page-view-to-install and install-to-paid remain unavailable. For Honne, the collector returns 1 first-time download over 2026-10-02–2026-10-05 and 114 unique impressions / 0 unique product-page views over that reported window, but the source report processing dates differ (2026-10-04 vs 2026-10-06), so do not calculate a matched conversion rate. The current main collector registers only Anicca and Honne; it does not produce fresh rows for the other four published apps. The ASC web-cohort read for Anicca previously returned asc_web_session_expired; no install-to-paid numerator is verified.

| App | Latest acquisition result |
|---|---|
| Anicca | 2026-10-04–05: 3 first-time downloads / 25 unique impressions / 0 unique product-page views; 12.0% descriptive ratio, small sample |
| Honne | Reported 2026-10-02–05: 1 first-time download / 114 unique impressions / 0 unique product-page views; source processing dates differ, so matched rate unavailable |
| Dhamma Quotes | No current row from the main collector; current acquisition unknown |
| For Better Sleep | No current row from the main collector; current acquisition unknown |
| STUDIO CHERIE | No current row from the main collector; current acquisition unknown |
| Thankful | No current row from the main collector; current acquisition unknown |

Anicca has no campaign configured. Honne's configured campaign currently returns no measured campaign counts (zero vs privacy-suppressed is unknown). Social views, article visits, store impressions, installs, and paid customers are not joined. The current sample is too small for a useful product-page experiment.

## Product analytics and onboarding

Mixpanel export for 2026-09-08 through 2026-10-06 contains 2,790 events and includes a partial final UTC day. The events are predominantly from public app version 1.9.4, build 390.

| Mixpanel event | Event count | Distinct IDs |
|---|---:|---:|
| onboarding_started | 128 | 28 |
| onboarding_step_advanced | 584 | 20 |
| onboarding_completed | 52 | 17 |
| paywall_primer_viewed | 497 | 23 |
| paywall_plan_selection_viewed | 214 | 19 |
| purchase_completed | 206 | 5 |
| onboarding_paywall_purchased | 6 | 1 |
| trial_started | 0 | 0 |
| rc_initial_purchase_event | 1 | 1 |

A small exploratory seven-day cohort of 20 distinct IDs that started onboarding between 2026-09-08 and 2026-09-28 shows 14 users reaching the first recorded onboarding advance, 12 completing onboarding, 12 reaching the plan-selection paywall, 2 emitting purchase_completed, 1 emitting onboarding_paywall_purchased, and 0 emitting trial_started within seven days. This is an event-defined Mixpanel cohort, not an App Store install cohort or proof of payment. In particular, 206 purchase_completed events across 5 distinct IDs do not mean 206 paying users; reconcile client events to RevenueCat entitlements and Apple Finance Detail before using purchase conversion or revenue.

Mixpanel and RevenueCat SDKs are already integrated in the Anicca source. Mixpanel currently receives events, so do not add a new analytics vendor as the first action. Use ASC for impressions/downloads/settlement, Mixpanel for app events, and RevenueCat for subscription state; join by a defined app and cohort identity. Source code also configures PostHog feature flags/session replay, but a current PostHog event readback was not verified. Session replay is enabled in the source with text inputs masked and images unmasked; review image masking and ensure affirmation/mood content is not exposed before expanding replay.

The v7 onboarding/soft-paywall Maestro flow passed 1/1 on Staging in 46.038 seconds. The 46-second MP4 is at /Users/anicca/.local/state/life-manager/maestro-evidence/anicca-ios/20261005T140737/maestro/2026-10-05_151457/ANICCA v7 Onboarding and Soft Paywall/startRecording/anicca-onboarding-v7.mp4. It was resent to Telegram chat Cloud Life Manager on 2026-10-06 and read back as message 107093. Its caption says Staging, not TestFlight or purchase/restore evidence. The 13 screenshots were previously sent to Saved Messages, not resent to Cloud Life Manager. Staging has no RevenueCat offerings.

## Growth direction

1. Distribution is the first growth lever, with attribution tags configured as each asset is published. Run consistent social posts and articles around one concrete Anicca outcome; give each channel/creative its own App Store campaign or Custom Product Page URL, then read back impressions, page views, and downloads by source.
2. Improve the store page after traffic is flowing. Test a single screenshot/icon/app-preview hypothesis at a time. Apple Product Page Optimization supports up to three treatments and reports impression/conversion/confidence; wait for meaningful traffic and at least 90% confidence before choosing a winner. Apple Custom Product Pages provide distinct URLs and per-page acquisition/engagement reporting. These are measurement tools, not a promised lift.
3. Use the live Mixpanel funnel to find onboarding exits by distinct-user cohort, not event totals. The current small cohort points to testing the first value step and first paywall exposure: show a personalized affirmation quickly, defer notification permission until its benefit is clear, and keep recurring price, trial terms, close, and restore behavior explicit. The v7 soft paywall is a candidate, not a validated winner. Decide hard versus soft paywall only from a properly assigned cohort.
4. Track trial start, verified first purchase, restore, cancellation/refund, and D1/D7/D30 retention. Retention cannot be postponed entirely in a subscription business because churn determines whether MRR accumulates.
5. Reconcile settled Apple proceeds and variable provider/acquisition costs for Anicca before calling the $10,000 target net MRR. Once Anicca's channel, conversion, retention, and positive net contribution are repeatable, apply the same template to the other five published apps. Do not scale the 18 unpublished ASC records as if they were live products.

Apple references: [Product Page Optimization](https://developer.apple.com/app-store/product-page-optimization/), [Custom Product Pages](https://developer.apple.com/app-store/custom-product-pages/), [Xcode Cloud with GitHub](https://developer.apple.com/documentation/xcode/connecting-xcode-cloud-to-github), [RevenueCat API v2](https://www.revenuecat.com/docs/api-v2), [Mixpanel iOS SDK](https://docs.mixpanel.com/docs/tracking-methods/sdks/swift), [PostHog iOS SDK](https://posthog.com/docs/libraries/ios).

## TestFlight release cursor — current readback

ASC `Default` workflow is enabled on `main`, with required `Archive - iOS` action, scheme `aniccaios`, and project `aniccaios/aniccaios.xcodeproj`. Runs #802 and #803 are both terminal `COMPLETE/ERRORED`; latest #803 has an empty source commit, 0 actions, 0 builds, 0 issues, 0 artifacts, and 0 log bundles. `asc xcode-cloud doctor` has no more specific diagnostic. The exact ASC query for Anicca 1.9.6 (391) returns no build. No active run is listed on the enabled Default workflow. The public join URL `https://testflight.apple.com/join/5j9nuumu` is not verified against the target build.

ASC currently lists GitHub Cloud and repository `Daisuke134/anicca-products`; repository listing and the presence of Git references do not prove the workflow's active GitHub grant can fetch `main`. The last ASC web-auth readback (2026-10-06) was unauthenticated. Direct Apple/ASC/Xcode Cloud diagnostics and Apple's supported GitHub authorization are the next path; TapKit is excluded. Do not start a replacement run until the source grant is read back valid and the build number is confirmed unused.

## Remaining atomic TODOs

Growth measurement and distribution are independent of the Xcode Cloud recovery, so these two lanes can progress in parallel. Distribution remains the first revenue-growth lever; the TestFlight lane remains the release cursor.

### Growth lane — start now

1. **Acquire full ASC coverage (owner: mobile-metrics lane):** verify the exact ASC analytics request/report mapping for Dhamma Quotes, Sleep Reset, STUDIO CHERIE, and Thankful; add/read their rows through that lane without editing its active worktree here. Done when all six published apps have a current data-date row or an explicit provider error/next observation, and every download/impression comparison uses aligned dates.
2. **Create tracked distribution links (owner: mobile growth):** create distinct Apple campaign or Custom Product Page URLs for each channel and creative. Done when every planned social/article asset has a stored URL and campaign identity before publication.
3. **Publish and read back distribution:** publish the approved social posts/articles against those links. Done when post URLs/IDs are recorded and the corresponding official ASC impressions, page views, and first-time downloads are read after processing; absent attribution stays unknown.
4. **Refresh the user funnel (owner: mobile-metrics lane):** query Mixpanel by distinct users for onboarding start → steps → completion → paywall → trial/purchase/restore and exact UTC cohorts; reconcile purchase/trial events to RevenueCat entitlements and Apple rows. Done when event counts, unique users, date range, identity join rate, and missing fields are reported separately.
5. **Close analytics privacy gap:** verify PostHog image masking before expanding session replay; keep affirmation, mood, and other private text out of event properties. Done when settings and a safe test event/session readback match the policy.
6. **Run one store-page experiment:** after enough traffic, test one screenshot hypothesis using Apple Product Page Optimization and its tagged page link. Done when ASC experiment exposure, conversion, and confidence are read back; do not call a small sample a winner.
7. **Run one onboarding/paywall experiment:** assign a matched install cohort to the current flow and one focused change (including the soft-paywall option only as a test). Measure completion, verified trial/purchase, restore, refund/cancel, and D7/D30 retention. Done when cohort denominators and provider-confirmed subscription outcomes are available; Mixpanel `purchase_completed` alone is not payment proof.
8. **Prove Anicca unit economics:** join same-period Apple proceeds, refunds, fees and bank settlement with RevenueCat subscription state and actual app/provider/acquisition costs. Done when net contribution and net MRR are calculated without estimates/unknowns being treated as zero.
9. **Scale only a repeatable loop:** after Anicca shows repeatable attributed acquisition, conversion, retention, and positive net contribution, apply the measured playbook to the other five published apps. Done when each app has its own source-linked acquisition and same-period net economics; the USD 10,000 net-MRR goal remains open until verified.

### TestFlight lane — current release blocker

1. **Diagnose the failed source fetch:** read back the enabled workflow's repository relationship, `main` reference, run #803 available issues/actions/artifacts, and GitHub Cloud grant state. Done when the exact missing permission, source mapping, or provider failure boundary is recorded; current ASC report itself has no diagnostic log.
2. **Repair and verify the official source connection:** use Apple's supported ASC/Xcode Cloud ↔ GitHub authorization flow only, without TapKit. Done when ASC readback confirms the `Daisuke134/anicca-products` repository and `main` grant are active for the exact workflow.
3. **Preflight a single build:** confirm no active run, confirm 1.9.6/build 391 is unused or select the next unused number, and verify the intended main source SHA. Done when the exact SHA/version/build tuple is recorded.
4. **Run one archive and verify it:** start one Default workflow run only after steps 1–3; read back the run's source SHA, required Archive action, resulting build, `VALID` processing, and encryption status. On failure, diagnose before another run.
5. **Obtain external TestFlight availability:** attach that exact build to `anicca-beta`, complete Beta App Review, and read back approved group/build membership plus the public join link resolving to the same build.
6. **Test and deliver the exact build:** run Maestro on the installed TestFlight binary for onboarding, paywall close, sandbox purchase, restore, and entitlement state; capture video/screenshots and send the link/evidence to Cloud Life Manager Telegram, then read back delivery.

## Completion boundary

The TestFlight lane is not complete until a valid build containing the intended source is approved and installable from the verified link, Maestro evidence covers that exact binary, and the link/evidence delivery is read back. The growth lane is not complete until acquisition and onboarding can be read by app/cohort/period and same-period net economics are verified. The release task can complete before the business target; USD 10,000 verified net MRR cannot be claimed from RevenueCat MRR or Mixpanel event counts alone.
