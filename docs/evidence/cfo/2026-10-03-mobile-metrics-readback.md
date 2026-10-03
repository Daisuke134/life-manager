# Mobile metrics readback — 2026-10-03

Status: `partial` / fail-closed. ASC access is restored; the settled-financial row is not joined to a current app.

## Tooling and source status

- Rork `asc` 5.9.2 is installed and checksum-verified.
- `asc web agreements status`: `pending=false`; Apple Developer Program License Agreement version 5031 is `active`, accepted `2026-10-03T10:14:32Z`.
- `asc apps list`: succeeds with 24 app records. `asc account status` reports API access `ok` for app `6755129214`.
- The ASC API key can read current apps. Web-session auth is also active for the Account Holder Apple Account.
- RevenueCat snapshots are in `~/.local/state/life-manager/marketing-metrics-daily/state/business-outcomes.jsonl`; latest six CFO-bound product rows are business date `2026-10-02`, observed `2026-10-03`.

## Published app inventory crosswalk

The official ASC audit examined all 24 app records and found six published in 175 territories each. The table is the current live acquisition denominator; it is not the previous six-product CFO map.

| public product | ASC ID | bundle ID | current RevenueCat app binding | ongoing ASC request |
|---|---:|---|---|---|
| Anicca | `6755129214` | `ai.anicca.app.ios` | `app511ef26659` | `04c74879-547f-4e35-b231-1fafd485801d` |
| Honne | `6759667221` | `app.rork.hon-ne-honyaku-ai` | `app3bbd298d22` | `c7c05836-181e-49cc-ae71-b57b7a0b466e` |
| Dhamma Quotes | `6757726663` | `com.dailydhamma.app` | absent from configured project | `25b5906d-025b-4b9d-8226-dc1ea25bd13f` |
| For Better Sleep - Sleep Reset | `6762143790` | `app.rork.vcinrjbl3ke00f07gtlzf` | absent from configured project | `f4f4e486-d5cd-4b16-9d06-a1850fc9a477` |
| STUDIO CHERIE | `6766485903` | `app.rork.xhozd938ie79zdqd5plem` | absent from configured project | `b1c18c4e-77f3-4b63-bee4-259353531c3d` |
| Thankful - Gratitude Journal | `6759514159` | `app.rork.thankful-gratitude-app` | absent from configured project | `a1149f87-b22a-42cb-85a8-324eb54d2f1a` |

The four new ASC requests were read back as `ONGOING` and `stoppedDueToInactivity=false`. Their report definitions include the required `r3` and `r15` report IDs, but official instance-link queries currently return zero daily instances; direct collection reports `report_pending` for all four. They are not zero-install apps yet.

The old CFO map also has four RevenueCat App Store entries, but ASC's published audit excludes them: `BreathCalm Test` (`6760253231`), `SleepRitual` (`6759916261`), `Desk Stretch Timer` (`6760048397`), and `Micro-Mood` (`6759877003`). The configured RevenueCat project contains these records, one RC Billing app, and one Test Store; it does not contain the four other published bundles above. Keep prelaunch RevenueCat observations separate from the live published-app denominator.

## Legacy CFO-bound RevenueCat observations

The previous six-product RevenueCat mapping is `available` for business date `2026-10-02`, captured between `2026-10-03T11:54:18Z` and `2026-10-03T11:55:21Z`. It includes four unpublished ASC records and is not the current public portfolio. Currency is absent, so all amounts remain **currency UNKNOWN**.

| product | observed MRR | RevenueCat daily Revenue |
|---|---:|---:|
| anicca-ios | 20.34 | 0 |
| honne-ai | 0 | 0 |
| breath-reset | 0 | 0 |
| sleep-ritual | 0 | 0 |
| desk-stretch-timer | 0 | 0 |
| micro-mood | 0 | 0 |

These are provider observations, not settled App Store proceeds. They are not currently verified in the active B7 CFO projection because currency is missing.

## Active B7 CFO readback

- Active path: `loop_pnl.main` → `build_b7_projection` → `collect_b7_records` → `capafy_mobile.adapt_mobile`; `mobile_apps_entries()` is legacy and not the active CLI path.
- At projection `2026-10-03T12:46:40Z`, the six source captures were approximately 51–52 minutes earlier. The collector produced no settled receipt and no verified subscription snapshot.
- Current projected status is `unknown`: historical/trailing settled proceeds have `missing_coverage`; MRR has `unsupported_currency`. The branch now timestamps the coverage assessment at the projection snapshot, so this run no longer reports a false `stale_readback`; source capture times remain in the business-outcomes records.
- MRR cannot yet be confirmed in the B0 projection with realistic staggered source times until a valid explicit currency payload is available and the end-to-end snapshot freshness rule is exercised.

## Scheduled Financial Manager delivery readback

- The scheduled owner-facing path is `life-manager-cfo-hourly` → `skills/cfo/run.sh` → `apps/life-manager/scripts/cfo-hourly-local.js`; it reads the same `marketing-metrics-daily/state/business-outcomes.jsonl` source and has not imported Finance Detail yet.
- `lm-loop status life-manager-cfo-hourly` reports the latest terminal event at `2026-10-03T13:58:17Z` as `pass`, exit 0, but `effect_status=unknown`, `provider_receipt_id=null`, and `official_readback_ref=null`. The loop is loaded-idle on release `80cccc6f92069b7a8d259af619b87e47bef9861c`.
- `last-result.json` records `status=sent`, `delivered=true`, `providerMessageId=102289`; the durable `last-delivered-snapshot.json` still identifies reporting date `2026-09-26`, provider message `94946`, delivered `2026-09-25T15:38:21Z`. The latest send claim is not correlated to the current loop occurrence, so delivery remains unverified. It also does not show the JPY 4,250 row.

## ASC acquisition readback

The persisted snapshot `object://sha256/2725deab49ff9f211c5487e4be2372d2938e8ab77e6dc1b810c110cb12f6e2a8` is retained as immutable historical evidence but superseded for current rate claims because it mixed report windows. A fresh read-only `collectProduct` call was run for the six published apps; it was not persisted because the report-day pointer is immutable.

| live product | current report readback | aligned window | installs / unique impressions / unique page views | reason/status |
|---|---|---|---|---|
| Anicca (`6755129214`) | measured | 2026-10-01 | 0 / 5 / 0 | page-view→install `denominator_zero`; install→paid `paid_customer_cohort_unavailable` |
| Honne (`6759667221`) | unavailable | none | unavailable | `report_window_mismatch` |
| Dhamma Quotes (`6757726663`) | unavailable | none | unavailable | `report_pending` (no ASC daily instances yet) |
| For Better Sleep (`6762143790`) | unavailable | none | unavailable | `report_pending` (no ASC daily instances yet) |
| STUDIO CHERIE (`6766485903`) | unavailable | none | unavailable | `report_pending` (no ASC daily instances yet) |
| Thankful (`6759514159`) | unavailable | none | unavailable | `report_pending` (no ASC daily instances yet) |

Anicca's measured rates are impression→page view 0/5 = 0%, page view→install unavailable (`denominator_zero`), and impression→install 0/5 = 0%. These are store totals, not campaign-attributed installs. Product-level paid cohort, campaign attribution, activation, and retention are not connected.

## ASC settled financial readback

- Command: `asc finance reports --report-type FINANCE_DETAIL --region Z1 --date 2026-12 --decompress` (`2026-12` is Apple's fiscal month; the returned period is `2026-08-30`–`2026-09-26`).
- The report contains one sale: Apple Identifier `6762049696`, SKU `ai.anicca.app.ios.yearly.b`, title `Anicca Annual`, Product Type `IAY`, transaction and settlement date `2026-09-12`, partner share `JPY 4,250`.
- Report SHA-256: `cbe1dc9242aca2cf049b7ced284a08601bddcef7eafa0a0c4553ea5e53957070`.
- Official `asc subscriptions list --app 6755129214` returns subscription ID `6762049696`, name `Anicca Annual`, Product ID `ai.anicca.app.ios.yearly.b`, state `APPROVED`, period `ONE_YEAR`. This exact child-record ID + SKU join maps the proceeds to Anicca.
- `asc apps view --id 6762049696` returning “no resource” and public app lookup returning not found are expected because `6762049696` is a subscription record ID, not an app ID. The earlier interpretation that the row was unassigned was incorrect.
- The JPY 4,250 is a real settled Anicca proceeds row, but it is not yet counted in B7/Financial Manager because no live Finance Detail producer is connected. Future identity validation must join the report Apple Identifier/SKU to an ASC subscription or IAP record and then to its parent app; it must not compare the raw subscription ID directly to the app ID.

## Remaining gaps in the original 2026-10-03 snapshot

This section records the original readback-time gaps. Tasks 6, 9, and 10 have since reached source-disposition completion on the feature branch; the current production/promotion cursor is in the 2026-10-04 addendum below and the implementation plan.

- Distribution comes first: reconcile all six canonical app IDs against the 24 ASC records, then find official Analytics request/report IDs for the four uncovered products and read aligned daily windows back.
- Resolve the active B7 subscription projection with an end-to-end test for staggered but fresh source timestamps, and obtain explicit RevenueCat currency from the producer/API. Until then, B7 MRR remains unknown.
- Add the repeatable Finance Detail import into `business-outcomes`/CFO with fiscal period, currency, transaction/settlement dates, row identity, and report hash. Resolve each raw Apple Identifier + SKU to an official subscription/IAP record and parent app ID before counting it.
- The `6762049696` row is mapped to Anicca Annual but is not yet imported into B7/Financial Manager. Dais has no required Apple approval/auth action.
- Connect a same-app, same-window paid-customer cohort for `install_to_paid`; the field is already shown unavailable with `paid_customer_cohort_unavailable`.
- Campaign install attribution and product activation/retention remain unavailable until their source joins exist.

## 2026-10-04 production readback delta

Observed at approximately 2026-10-04 04:51–04:58 JST using read-only `bin/lm-loop status` and the production source files. This addendum supersedes older runtime-status statements above; historical ASC, RevenueCat, and Finance Detail observations remain unchanged.

- `marketing-metrics-daily` is loaded-idle on release `9c03543e5dc51f7bc54f8e132a264964a0e40f6d`. Its latest natural run `18db1cd8910049c8-68721` passed at `2026-10-03T19:51:21Z`; the run used the existing production release, not the feature branch.
- The production `business-outcomes.jsonl` has mobile rows for business date `2026-10-03`, observed around `19:50–19:51Z`. Anicca and Honne ASC source reads are available; legacy mobile App Store Sales reads report `provider_query_failed`. RevenueCat sources are present but persisted currency is still absent. PostHog has `missing_project_read_credential`; Anicca product analytics has raw event counts without a purchase event or user-level cohort denominator. A full-file query found zero `app_store_financial` rows.
- `life-manager-cfo-hourly` is loaded-idle on release `be2b181bfaa40ca13f1e893777437055224f4f2f`. Latest occurrence `life-manager-cfo-hourly:18db1a3dbbbd6d28-51694` has terminal status `pass`, but `last_exit=78`, `effect_status=unknown`, no `provider_receipt_id`, and no `official_readback_ref`.
- The durable delivered snapshot still says reporting date `2026-09-26`, provider message `94946`, delivered `2026-09-25T15:38:21.745Z`. `last-result.json` claims reporting date `2026-10-04`, status `sent`, provider message `102459`. They do not correlate to the same occurrence; current delivery is unverified, not confirmed failed or confirmed delivered.
- The feature branch HEAD is `fe6e5888` while fetched `origin/main` is `655b2cf2`; merge-base is `80cccc6f`, with nine main-only and sixteen branch-only commits. The feature has not been promoted. Before promotion, merge current main into the existing branch without rewriting it, rerun full acceptance, and obtain the plan's fresh whole-branch review.

### Latest runtime reread (2026-10-04 05:39 JST)

- `marketing-metrics-daily` remains loaded-idle on release `9c03543e5dc51f7bc54f8e132a264964a0e40f6d`; natural run `18db1eed6eb4f2f8-66574` passed at `2026-10-03T20:29:56Z`. It is not the feature branch.
- The production JSONL's latest mobile rows are business date `2026-10-03`, observed at `20:28–20:29Z`. All six legacy mobile App Store Sales sources report `provider_query_failed`; RevenueCat currency is absent; a full-file query found zero `app_store_financial` source rows.
- `life-manager-cfo-hourly` is loaded-idle on release `655b2cf2001ad54ce70cb975910f363091052651`; occurrence `18db1d3cfc8351e0-82300` is terminal `blocked`, exit 78, `host_admission_deferred:resource_capacity_busy`, with no provider receipt or official readback. Last success remains `2026-10-03T19:02:14Z`.
- The durable snapshot remains `2026-09-26` / provider message `94946`, while `last-result.json` claims `2026-10-04` / provider message `102459`; no occurrence correlation was found, so delivery remains unverified.
- Current feature branch is pushed at `e46284c351`, includes latest main commit `3e1e30a6`, and has no open PR. It is still not loaded or applied to production.

### Latest runtime reread (2026-10-04 06:07 JST)

- `marketing-metrics-daily` is loaded-idle on release `9c03543e5dc51f7bc54f8e132a264964a0e40f6d`; its latest natural run remains `18db1eed6eb4f2f8-66574`, passed at `2026-10-03T20:29:56Z`. The next scheduled local run has not occurred yet. The production JSONL has eight rows for business date `2026-10-03`, observed at `20:28–20:29Z`; all six legacy mobile `app_store_sales` rows are `unavailable/provider_query_failed`, the six RevenueCat rows have no persisted currency, and there are zero `app_store_financial` rows. The production release is not this feature branch.
- `life-manager-cfo-hourly` is loaded-idle on installed main release `3e1e30a61d32762ec004f7511e1c4838f6050cdc`. Its latest occurrence is `18db208358508a30-55308`, executed on that same release and blocked at admission with `host_admission_deferred:resource_capacity_busy`; both occurrence `exit_code` and runtime `last_exit` are 75. No provider receipt or official readback exists; last successful occurrence remains `18db1a3dbbbd6d28-51694` at `2026-10-03T19:02:14Z`.
- `last-result-report.json` claims status `sent`, provider message `102459`, and occurrence `18db1a3dbbbd6d28-51694`; that occurrence ID matches the 2026-10-03 19:02Z successful event. However, the event has no structured provider receipt/readback, an exact Telegram history lookup of message `102459` in the recipient-hash-matched chat returned no message, and `last-delivered-snapshot.json` remains at 2026-09-26 / message `94946`. Do not treat local sent state as proof of current delivery; do not replay while delivery remains uncertain.
- Correction to the earlier 05:39 JST note: local `last-result-report.json` does correlate by occurrence ID to the successful 19:02Z loop event; the part still unverified is provider delivery/readback, not occurrence identity.
- Since the previous readback, CFO had one more natural hourly occurrence (`18db208358508a30-55308`); it was admission-blocked on resource capacity, so no new CFO report was generated. Marketing Metrics' next local 07:00 run has not occurred yet.
- Repository promotion is also gated: `CONTRIBUTING.md` requires an issue and maintainer 👍 before coding, and `.github/PULL_REQUEST_TEMPLATE.md` requires the related issue and 👍 before PR. This implementation branch predates that approval, so the maintainer must accept this branch as the intended route before PR. Read-only `gh` searches found no matching issue or PR; none was created.
- Latest-main sync: `origin/main` advanced to `ede6efa47d` (`fix: reconcile guarded retirement before fleet owners (#6543)`) and was merged without conflict as `bb9ae35844`. It changes the shared release-retirement reconciler and its runtime test, not mobile/CFO source; the focused regression suite passed 22/22 after merge.
