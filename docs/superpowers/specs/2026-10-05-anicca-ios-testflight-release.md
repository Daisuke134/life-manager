# ANICCA iOS TestFlight and mobile growth

## Goal

Deliver the merged ANICCA onboarding/paywall changes in an installable TestFlight build, then build a measured growth loop for the six published iOS apps, starting with Anicca. The business target is USD 10,000 verified net MRR; it is not achieved and must not be reported as achieved.

This lane uses App Store Connect CLI/API and TestFlight. TapKit is not a dependency.

## Source, ownership, and current readback

Read-only provider checks were made on 2026-10-06 13:11–13:14 UTC. The app source of truth remains Life Manager main. PR #6619 contains the onboarding/paywall source; PR #418 mirrors the release source and Maestro flow to anicca-products main. The target source sets app, widget, and notification-service targets to version 1.9.6, build 391.

The separate mobile-metrics implementation remains on branch feat/lm-mobile-metrics-20261003 in its own worktree, with no open PR in the 2026-10-06 readback. It owns those Life Manager acquisition/CFO ingestion edits; this TestFlight lane consumes its read-only provider results and does not edit its files or worktree.

## Published portfolio

ASC lists 24 app records, of which 6 are published across 175 territories. The other 18 records are not in ASC's published-app set and must not be counted as live acquisition products.

| Published app | ASC app ID | Bundle ID | Current verified state |
|---|---:|---|---|
| Daily Affirmations - Anicca | 6755129214 | ai.anicca.app.ios | Public version 1.9.4; 1.9.5 is rejected |
| Honne | 6759667221 | app.rork.hon-ne-honyaku-ai | Public version 1.0.3; 1.0.4 is developer-rejected |
| Dhamma Quotes | 6757726663 | com.dailydhamma.app | Published; latest aligned acquisition window unavailable |
| For Better Sleep - Sleep Reset | 6762143790 | app.rork.vcinrjbl3ke00f07gtlzf | Published; acquisition report pending |
| STUDIO CHERIE | 6766485903 | app.rork.xhozd938ie79zdqd5plem | Published; small 2026-10-03 acquisition sample |
| Thankful - Gratitude Journal | 6759514159 | app.rork.thankful-gratitude-app | Published; acquisition report pending |

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

Latest aligned ASC Analytics data for Anicca is 2026-10-04: 1 first-time download, 7 unique impressions, and 0 unique product-page views. The raw impression-to-download ratio is 1/7 (14.3%) on a sample of seven; page-view-to-install is unavailable because its denominator is zero. This is store-total data, not social/campaign attribution. The mature 2026-09-28 D7 cohort has only 3 first-time downloads; install-to-paid remains unavailable because the ASC web-cohort read returned asc_web_session_expired.

| App | Latest acquisition result |
|---|---|
| Anicca | 2026-10-04 common data date: 1 first-time download / 7 unique impressions / 0 unique product-page views |
| Honne | Download and engagement reports have no common data date; unavailable, not zero |
| Dhamma Quotes | Latest downloads and engagement reports have no common data date; unavailable |
| For Better Sleep | ASC acquisition report pending |
| STUDIO CHERIE | 2026-10-03 common data date: 1 first-time download / 15 unique impressions / 0 unique product-page views; too small for a stable rate |
| Thankful | ASC acquisition report pending |

Campaign-specific downloads/impressions are not configured. Social views, article visits, store impressions, installs, and paid customers are not joined. The current sample is too small for a useful product-page experiment.

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

## TestFlight release cursor

ASC workflow Default is enabled on main with Archive - iOS as the required action. Run #802 is COMPLETE/ERRORED without source SHA, archive, or diagnostic artifact. Existing main-ref run #803 is still PENDING on the latest 2026-10-06 13:12 UTC readback; its source commit/actions/build are empty. The exact ASC query for Anicca 1.9.6 (391) returns no build. The existing public join link has not been verified against that build.

The ASC SCM API records a GitHub Cloud connection to Daisuke134/anicca-products, but its last-access date is old and does not prove the grant works. ASC web-only connection status was previously unauthenticated/session-expired. If #803 ends without source access, diagnose through ASC/Xcode Cloud readbacks and use Apple's supported Xcode Cloud/GitHub authorization flow only if needed; do not use TapKit. Do not cancel, replay, or create a second run while #803 is pending.

## Remaining TODO, in order

### TestFlight release

1. Observe existing run #803 using ASC CLI read-only status/actions/doctor readbacks. Leave it pending; do not duplicate its external effect.
2. At terminal state, verify the source commit and archive result. If no source was fetched, diagnose the ASC/GitHub Cloud connection using direct ASC and Apple's supported flow without TapKit; start at most one replacement only after #803 is terminal and no competing run exists.
3. Verify the resulting version/build is 1.9.6 (391), or the next available build number if 391 was consumed; require VALID processing, correct source SHA, and resolved encryption state.
4. Attach that exact build to external beta group anicca-beta, obtain Beta App Review approval, and verify the public link resolves to that build.
5. Run Maestro on that exact TestFlight binary. Cover onboarding, soft-paywall close, subscription purchase, restore, and subscription state with actual sandbox offerings. Send the installable TestFlight link and E2E evidence to the Cloud Life Manager Telegram chat and read back delivery.

### Anicca growth

1. Keep distribution first: create channel/creative-specific App Store links and publish measurable social/article distribution. The tracking tag and the content publish together; do not wait for a new analytics vendor.
2. Reconcile the Mixpanel purchase/trial events to RevenueCat customer/entitlement events and the corresponding Apple financial rows. Define a 7-day install-to-paid cohort from an exact ASC download cohort; until the official matching numerator is available, keep that rate unavailable.
3. Read acquisition daily by the same data date for all six published products. Resolve report_window_mismatch/report_pending and the missing RevenueCat app bindings without treating either as zero.
4. After sufficient exposure, run the first Apple Product Page Optimization test with one screenshot hypothesis and its tagged Custom Product Page campaign links.
5. Use Mixpanel cohorts to test the largest early onboarding drop and paywall design; add no private text or health/affirmation content to event properties and review PostHog image masking.
6. Reconcile subscription proceeds, refunds, fees, and direct variable costs per app and period; track D7/D30 retention and monthly churn alongside MRR.
7. Replicate the validated Anicca acquisition/onboarding/economics loop across the other five published apps. The $10,000 net MRR target remains open until official same-period evidence proves it.

## Completion boundary

This lane is not complete until a valid TestFlight build containing the intended source is approved and installable from the verified link, Maestro evidence covers that exact binary, and Anicca's live acquisition/onboarding/purchase funnel can be read by app, cohort, and period. The TestFlight release task can complete before the business target; $10,000 verified net MRR cannot be claimed from RevenueCat MRR or Mixpanel event counts alone.
