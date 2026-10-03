# Mobile source production refresh — 2026-10-04

Status: `partial`; Marketing Metrics captured source rows, but no settled App Store Finance Detail row or complete mobile CFO report is present in production.

## Marketing Metrics occurrence

- Owner `marketing-metrics-daily` ran on release `9c03543e5dc51f7bc54f8e132a264964a0e40f6d`; occurrence `18db284644292100-79072` ended `pass` / exit 0 at 2026-10-03 23:20:43Z (2026-10-04 08:20 JST). The occurrence has no provider receipt; success means the local collection process completed, not that a financial report was delivered.
- The production `business-outcomes.jsonl` now has eight rows for business date 2026-10-03, observed through `2026-10-03T23:20:40Z`.
- Six legacy CFO-bound mobile rows have RevenueCat `available` status but still omit persisted currency. Their six legacy `app_store_sales` reads remain `unavailable/provider_query_failed`.
- ASC Analytics is `available` for Anicca and Honne; the four remaining legacy products have `provider_query_failed`. These are not the six-public-app acquisition roster.
- A full-file query finds zero `app_store_financial` rows. The JPY 4,250 Finance Detail row remains branch-only and is not in production B7/Financial Manager.

## CFO owner status

- `life-manager-cfo-hourly` remains installed on release `5fc226d9eec06232ef33c5fd49d337bafe5736a3`.
- Its latest occurrence `18db2736b884a0a8-40862` was capacity-blocked at 2026-10-03 22:59:53Z (2026-10-04 07:59:53 JST), exit 75, with no provider receipt or official readback. No subsequent CFO report was produced in this read.
- No owner was manually triggered; no production pointer or source data was changed.
