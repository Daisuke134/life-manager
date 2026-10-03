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

## Remaining gaps

- Distribution comes first: reconcile all six canonical app IDs against the 24 ASC records, then find official Analytics request/report IDs for the four uncovered products and read aligned daily windows back.
- Resolve the active B7 subscription projection with an end-to-end test for staggered but fresh source timestamps, and obtain explicit RevenueCat currency from the producer/API. Until then, B7 MRR remains unknown.
- Add the repeatable Finance Detail import into `business-outcomes`/CFO with fiscal period, currency, transaction/settlement dates, row identity, and report hash. Resolve each raw Apple Identifier + SKU to an official subscription/IAP record and parent app ID before counting it.
- The `6762049696` row is mapped to Anicca Annual but is not yet imported into B7/Financial Manager. Dais has no required Apple approval/auth action.
- Connect a same-app, same-window paid-customer cohort for `install_to_paid`; the field is already shown unavailable with `paid_customer_cohort_unavailable`.
- Campaign install attribution and product activation/retention remain unavailable until their source joins exist.
