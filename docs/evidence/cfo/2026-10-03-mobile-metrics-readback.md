# Mobile metrics readback — 2026-10-03

Status: `partial` / fail-closed. ASC access is restored; the settled-financial row is not joined to a current app.

## Tooling and source status

- Rork `asc` 5.9.2 is installed and checksum-verified.
- `asc web agreements status`: `pending=false`; Apple Developer Program License Agreement version 5031 is `active`, accepted `2026-10-03T10:14:32Z`.
- `asc apps list`: succeeds with 24 app records. `asc account status` reports API access `ok` for app `6755129214`.
- The ASC API key can read current apps. Web-session auth is also active for the Account Holder Apple Account.
- RevenueCat snapshots are in `~/.local/state/life-manager/marketing-metrics-daily/state/business-outcomes.jsonl`; latest six CFO-bound product rows are business date `2026-10-02`, observed `2026-10-03`.

## Latest RevenueCat observations

The six RevenueCat sources are `available` for business date `2026-10-02`, captured between `2026-10-03T11:54:18Z` and `2026-10-03T11:55:21Z`. Currency is absent, so all amounts remain **currency UNKNOWN**.

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

## ASC acquisition readback

The persisted snapshot `object://sha256/2725deab49ff9f211c5487e4be2372d2938e8ab77e6dc1b810c110cb12f6e2a8` is retained as immutable historical evidence but superseded for current rate claims because it mixed report windows. A fresh read-only `collectProduct` call was run after the date-intersection fix; it was not persisted.

| product | aligned ASC window | first-time downloads | unique impressions | unique page views | impression → page view | page view → install | impression → install | install → paid |
|---|---|---:|---:|---:|---:|---:|---:|---|
| anicca-ios | 2026-10-01 | 0 | 5 | 0 | measured 0/5 = 0% | unavailable: `denominator_zero` | measured 0/5 = 0% | unavailable: `paid_customer_cohort_unavailable` |
| honne-ai | unavailable: `report_window_mismatch` | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable | unavailable: `paid_customer_cohort_unavailable` |

These are store totals, not campaign-attributed installs. Product-level paid cohort, campaign attribution, activation, and retention are not connected.

## ASC settled financial readback

- Command: `asc finance reports --report-type FINANCE_DETAIL --region Z1 --date 2026-12 --decompress` (`2026-12` is Apple's fiscal month; the returned period is `2026-08-30`–`2026-09-26`).
- The report contains one sale: Apple Identifier `6762049696`, SKU `ai.anicca.app.ios.yearly.b`, transaction and settlement date `2026-09-12`, partner share `JPY 4,250`.
- Report SHA-256: `cbe1dc9242aca2cf049b7ced284a08601bddcef7eafa0a0c4553ea5e53957070`.
- `asc apps view --id 6762049696` returns “no resource”; the ID is absent from the current 24-app inventory and removed-app list, and public lookup returns app not found. Looking up the reported SKU under current Anicca app `6755129214` returns zero IAP records.
- Therefore the JPY 4,250 row is real vendor-level settled proceeds but cannot be attributed to a current product. It is not counted as Anicca iOS or Honne revenue. The report has no transaction rows for their current app IDs.

## Remaining gaps

- Distribution comes first: reconcile all six canonical app IDs against the 24 ASC records, then find official Analytics request/report IDs for the four uncovered products and read aligned daily windows back.
- Resolve the active B7 subscription projection with an end-to-end test for staggered but fresh source timestamps, and obtain explicit RevenueCat currency from the producer/API. Until then, B7 MRR remains unknown.
- Add the repeatable Finance Detail import into `business-outcomes`/CFO with fiscal period, currency, transaction/settlement dates, row identity, and report hash. Count only exact app-ID matches; current adapters have no live producer.
- Keep `6762049696` unassigned unless an authoritative historical mapping is found. Dais has no required Apple approval/auth action; recognizing the ID is optional evidence only.
- Connect a same-app, same-window paid-customer cohort for `install_to_paid`; the field is already shown unavailable with `paid_customer_cohort_unavailable`.
- Campaign install attribution and product activation/retention remain unavailable until their source joins exist.
