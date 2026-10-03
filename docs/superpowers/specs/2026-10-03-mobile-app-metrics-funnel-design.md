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

## Current gaps

- Local `asc` is Rork 5.9.2 (checksum verified).
- Account Holder agreement is active (`pending=false`, accepted 2026-10-03T10:14:32Z); `asc apps list` now succeeds with 24 app records.
- Latest acquisition snapshot is persisted for Anicca iOS (2026-09-30–10-01) and Honne (2026-09-29–30). Page views are 0 in both windows; page-view-to-install is unavailable because its denominator is 0. These are store totals, not campaign attribution.
- September's latest available Apple fiscal detail (FY2026 month 12; 2026-08-30–09-26) contains one JPY 4,250 proceeds row for Apple Identifier 6762049696 / SKU `ai.anicca.app.ios.yearly.b`. That identifier is absent from current ASC inventory and cannot be mapped to the current Anicca or Honne app; do not attribute it to either product.
- RevenueCat is available for the latest six CFO-bound product snapshots; MRR is `20.34` for `anicca-ios` and `0` for the other five, with daily RevenueCat revenue `0` for all six. Currency is absent and remains UNKNOWN.
- `skills/cfo/adapters/capafy_mobile.py` defines six product/app bindings and `skills/cfo/loop_pnl.py` now sums all six. `marketing-revenuecat-subscriptions.js` and ASC acquisition still produce records for only Anicca iOS and Honne.
- ASC inventory has 24 records, including test or inactive apps; use the six CFO bindings as the initial product set and reconcile each before extending acquisition collection.
- `install_to_paid` is required but not implemented until a same-app, same-window paid-customer cohort is connected. Campaign attribution, activation, and retention also remain unavailable.

## Acceptance

1. ASC CLI preflight records version and a redacted auth/source status; no credentials are stored in snapshots.
2. Acquisition snapshots expose totals and all four derived rates with fail-closed denominator handling; `install_to_paid` stays unavailable until its paid-customer cohort joins the same app and window.
3. RevenueCat observations remain separate from ASC settled proceeds and never double-count revenue.
4. The CFO report covers all six canonical mobile product bindings and shows per-product source status, MRR/subscriptions, installs/impressions, rates, settled proceeds, and explicit gaps.
5. Existing full suites remain green; no app submission, paywall, price, or external marketing mutation occurs in this slice.
