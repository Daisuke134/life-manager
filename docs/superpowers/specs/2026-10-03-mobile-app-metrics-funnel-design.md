# Mobile app metrics and revenue funnel design

## Goal

Give each mobile app a daily, source-separated funnel from store exposure to settled revenue so distribution and product changes can be evaluated without converting missing metrics to zero.

## Source contract

| metric | authoritative source | truth boundary |
|---|---|---|
| first-time downloads, impressions, product-page views | App Store Connect Analytics via Rork `asc` | measured only when the report is complete and app identity matches |
| MRR, active subscriptions, trials, churn, RevenueCat revenue chart | RevenueCat charts API | observed subscription/revenue estimate; not store settlement |
| store proceeds | App Store Connect Sales/Finance reports | settled revenue only when report receipt is available |
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
- Latest ASC inventory/acquisition is unavailable because `asc apps list` returns the account-wide required-agreement-missing/expired error; this is not treated as zero or as a generic 403.
- RevenueCat is available for latest local snapshots; the current CFO loop counts only `anicca-ios` and `honne-ai` RevenueCat chart revenue and records currency as UNKNOWN.
- Campaign attribution is not configured, so install-to-impression attribution rates remain unavailable even when store totals exist.

## Acceptance

1. ASC CLI preflight records version and a redacted auth/source status; no credentials are stored in snapshots.
2. Acquisition snapshots expose totals and all four derived rates with fail-closed denominator handling.
3. RevenueCat observations remain separate from ASC settled proceeds and never double-count revenue.
4. The CFO report shows per-product source status, MRR/subscriptions, installs/impressions, rates, settled proceeds, and explicit gaps.
5. Existing full suites remain green; no app submission, paywall, price, or external marketing mutation occurs in this slice.
