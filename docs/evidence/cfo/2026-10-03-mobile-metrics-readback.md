# Mobile metrics readback — 2026-10-03

Status: `partial` / fail-closed. ASC access is restored; the settled-financial row is not joined to a current app.

## Tooling and source status

- Rork `asc` 5.9.2 is installed and checksum-verified.
- `asc web agreements status`: `pending=false`; Apple Developer Program License Agreement version 5031 is `active`, accepted `2026-10-03T10:14:32Z`.
- `asc apps list`: succeeds with 24 app records. `asc account status` reports API access `ok` for app `6755129214`.
- The ASC API key can read current apps. Web-session auth is also active for the Account Holder Apple Account.
- RevenueCat snapshots are in `~/.local/state/life-manager/marketing-metrics-daily/state/business-outcomes.jsonl`; latest six CFO-bound product rows are business date `2026-10-02`, observed `2026-10-03`.

## Latest RevenueCat observations

Currency is absent from the snapshots, so amounts below are **currency UNKNOWN**.

| product | MRR | active | daily RevenueCat revenue | new customers | 7-day paid conversion |
|---|---:|---:|---:|---:|---:|
| anicca-ios | 20.34 | 5 | 0 | 1 | 0% |
| honne-ai | 0 | 0 | 0 | 1 | 0% |
| breath-reset | 0 | 0 | 0 | unavailable | unavailable |
| sleep-ritual | 0 | 0 | 0 | 1 | 0% |
| desk-stretch-timer | 0 | 0 | 0 | 1 | 0% |
| micro-mood | 0 | 0 | 0 | 1 | 0% |

These are RevenueCat observations, not App Store settled proceeds.
The CFO adapter defines six product/app bindings in `skills/cfo/adapters/capafy_mobile.py`; `loop_pnl.py` now uses all six by default. The live P&L readback has six available RevenueCat rows, total MRR 20.34 (currency UNKNOWN), daily RevenueCat revenue 0 across all six, and no revenue entries for that day.

## ASC acquisition readback

Persisted snapshot: `object://sha256/2725deab49ff9f211c5487e4be2372d2938e8ab77e6dc1b810c110cb12f6e2a8` (`created=true`, report day `2026-10-03`).

| product | ASC window | first-time downloads | unique impressions | unique page views | impression → page view | page view → install | impression → install |
|---|---|---:|---:|---:|---:|---:|---:|
| anicca-ios | 2026-09-30–2026-10-01 | 0 | 11 | 0 | measured 0/11 = 0% | unavailable: zero page-view denominator | measured 0/11 = 0% |
| honne-ai | 2026-09-29–2026-09-30 | 2 | 6 | 0 | measured 0/6 = 0% | unavailable: zero page-view denominator | measured 2/6 = 33.33% |

The windows differ because Apple's latest complete reports differ by product. These are store totals, not campaign-attributed installs. Campaign attribution remains unavailable; product analytics and an observed paid-install cohort are also missing.

## ASC settled financial readback

- Command: `asc finance reports --report-type FINANCE_DETAIL --region Z1 --date 2026-12 --decompress` (`2026-12` is Apple's fiscal month; the returned period is `2026-08-30`–`2026-09-26`).
- The report contains one sale: Apple Identifier `6762049696`, SKU `ai.anicca.app.ios.yearly.b`, transaction and settlement date `2026-09-12`, partner share `JPY 4,250`.
- Report SHA-256: `cbe1dc9242aca2cf049b7ced284a08601bddcef7eafa0a0c4553ea5e53957070`.
- `asc apps view --id 6762049696` returns “no resource”; the ID is absent from the current 24-app inventory. Looking up the reported SKU under current Anicca app `6755129214` returns zero IAP records.
- Therefore the JPY 4,250 row is real vendor-level settled proceeds but cannot be attributed to a current product. It is not counted as Anicca iOS or Honne revenue. The report has no transaction rows for their current app IDs.

## Remaining gaps

- Reconcile the historical/unlisted Apple Identifier and SKU to a current or retired product using an authoritative provider record; keep it unassigned until then.
- Add a repeatable Finance Detail import into `business-outcomes`/CFO so matched app rows carry the report period, currency, transaction/settlement dates, and report hash. Current adapters consume `app_store_financial`, but no live producer was found.
- Acquisition collection currently covers only Anicca iOS and Honne. Find the official Analytics request/report IDs for the other four mapped products before extending it.
- Reconcile the 24 ASC records against the six CFO bindings; identify inactive/test apps before extending acquisition coverage.
- `install_to_paid` is specified but not implemented because no same-app, same-window paid-customer cohort is connected.
- Product activation/retention and campaign-level install attribution remain unavailable.
