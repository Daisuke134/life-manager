# Mobile app metrics and revenue funnel design

## Goal

Give each mobile app a daily, source-separated funnel from store exposure to settled revenue so distribution and product changes can be evaluated without converting missing metrics to zero.

## Source contract

| metric | authoritative source | truth boundary |
|---|---|---|
| first-time downloads, impressions, product-page views | App Store Connect Analytics via Rork `asc` | measured only when the report is complete and app identity matches |
| MRR, active subscriptions, trials, churn, RevenueCat revenue chart | RevenueCat charts API | observed subscription/revenue estimate; not store settlement |
| store proceeds | App Store Connect Sales/Finance reports | settled revenue only when report receipt is available |
| paid customers for install-to-paid rate | product-owned paid-customer cohort | same app, cohort, and report window as ASC downloads; missing join stays unavailable |
| activation and retention | product analytics snapshot | measured only when cohort definition and source receipt exist |
| social distribution | platform-owned daily snapshots | reach evidence; never install attribution without campaign identity |

## Required derived metrics

For each product and same reporting window:

- `impression_to_page_view = unique_product_page_views / unique_impressions`
- `page_view_to_install = first_time_downloads / unique_product_page_views`
- `impression_to_install = first_time_downloads / unique_impressions`
- `install_to_paid = paid_customers / first_time_downloads`

Each rate is `{status: measured|unavailable, value, reason, numerator, denominator, source_refs}`. A zero denominator is `unavailable`, never `0`.

## Current verified state

### Provider observations

- Rork `asc` 5.9.2 is installed and checksum-verified. The Account Holder agreement is active (`pending=false`, accepted 2026-10-03T10:14:32Z); the API returns 24 app records.
- A fresh, read-only ASC acquisition collection intersects download and engagement report dates before calculating totals. For `anicca-ios`, the common window is 2026-10-01: 0 first-time downloads, 5 unique impressions, 0 unique product-page views; impression→page view is 0%, page view→install is unavailable (`denominator_zero`), and impression→install is 0%. `install_to_paid` is unavailable (`paid_customer_cohort_unavailable`).
- `honne-ai` currently has no common date between the downloaded reports, so all acquisition metrics are unavailable (`report_window_mismatch`). The older persisted snapshot that mixed different report windows is superseded; its immutable object was not rewritten.
- RevenueCat is `available` for all six CFO-bound products for business date 2026-10-02 (observed 2026-10-03 11:54–11:55 UTC). MRR is `20.34` for `anicca-ios` and `0` for the other five; RevenueCat daily `Revenue` is `0` for all six. Currency is absent, so these MRR values are currency `UNKNOWN` and are observations, not settled proceeds.
- The latest available Apple Finance Detail report (Apple fiscal month 2026-12; report period 2026-08-30–09-26) contains one settled JPY 4,250 proceeds row for Apple Identifier `6762049696`, SKU `ai.anicca.app.ios.yearly.b`. The identifier is absent from the current inventory, removed-app list, and public lookup; the SKU has no matching IAP under current Anicca app `6755129214`. Keep the proceeds unassigned; do not count them as Anicca or Honne revenue.

### CFO integration status

- The active CLI path is `loop_pnl.main` → `build_b7_projection` → `collect_b7_records` → `capafy_mobile.adapt_mobile`. The older `mobile_apps_entries()` helper is not the active B7 path and does not prove that the CFO report contains six products.
- The active collector filters the mixed business-outcomes JSONL to the six canonical mobile product IDs and recognizes the current RevenueCat evidence-hash/period shape. The current branch stamps coverage assessment at the B7 projection time while retaining source observation times in the source data; a fresh projection no longer reports the false `stale_readback`. It still has zero settled receipts and zero MRR snapshots: no `app_store_financial` rows exist for these six products, and RevenueCat currency is absent. Current B7 status is unknown with `missing_coverage` for settled proceeds and `unsupported_currency` for MRR. The strict B0 subscription-snapshot timestamp behavior still needs an active-path test with a valid explicit currency before MRR can be called verified.
- The canonical six-product mapping exists, but ASC inventory reconciliation and daily Analytics report coverage are complete for only Anicca iOS and Honne. Four mapped products still need official request/report IDs.
- The output now includes `install_to_paid` as explicitly unavailable until a paid-customer cohort is joined to the same app and report window. Campaign attribution, activation, and retention are also unavailable.

No further Apple agreement or 2FA action is required. If the owner recognizes historical Apple Identifier `6762049696`, that identity can be supplied as optional evidence; absent that mapping, it stays unassigned.

## Observability

- Each product/source reports its status, reason when unavailable, report window, source/evidence reference, and source observation time.
- Download and engagement totals and derived rates use only intersecting report dates. A mismatch is unavailable, never a mixed-window rate.
- The CFO projection preserves the original source observation time and distinguishes recent-but-usable data from stale data; it must not turn a valid recent read into `stale_readback` only because the projection ran later.
- Unknown currency, missing settlement, missing cohort, and missing report coverage remain visible as gaps; they never become zero-valued verified revenue.

## Acceptance

1. ASC preflight records CLI version and redacted auth/source status; credentials never enter snapshots.
2. Acquisition snapshots expose all four derived rates. The three store-total rates use aligned ASC report dates; `install_to_paid` is measured only from a same-app, same-window paid-customer cohort, otherwise unavailable with a reason.
3. RevenueCat MRR/revenue observations stay separate from ASC settled proceeds and are excluded from settled P&L; the same proceeds are never counted twice.
4. The daily marketing summary shows per-app acquisition metrics and source status for all six canonical bindings; the B7 CFO projection reports the mobile-apps aggregate with covered product identities, observation time, and explicit gaps. It accepts the producer's verified current payload shape without false stale classification and still rejects genuinely stale data.
5. ASC settled rows count only when the official Apple Identifier matches a canonical app binding and the report is complete; unmatched rows stay unassigned.
6. Relevant source suites pass. This slice does not submit apps, change paywalls/prices, publish marketing, or invent campaign attribution.
