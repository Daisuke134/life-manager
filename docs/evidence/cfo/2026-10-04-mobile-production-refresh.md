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

## Latest CFO occurrence reread — 2026-10-04 09:18 JST

- `life-manager-cfo-hourly` is installed on main release `b7fb1dfa5a2ca1c8fb561a69536b7ad9061edbfc`.
- Its latest natural occurrence `18db2a5616cdbc40-72786` ran at `2026-10-03T23:57:09Z` (2026-10-04 08:57:09 JST) and was admission-blocked by `host_admission_deferred:resource_capacity_busy`, exit 75. `provider_receipt_id` and `official_readback_ref` are null; there is no new CFO report.
- The durable `last-result-report.json` still has modification time `2026-10-03T22:10:43Z` and points to the earlier 07:10 occurrence; this local sent record is not a new official receipt/readback.
- No owner was manually triggered, and no production data, scheduler state, or provider state was changed.

## Candidate B7 correction and official Finance Detail readback — 2026-10-04

- In the candidate branch only, B7 now defaults to the existing Marketing Metrics `business-outcomes.jsonl` when `LM_CFO_MOBILE_APPS_BUSINESS_OUTCOMES` is not configured. RED reproduced `app-store-connect-financial:read_failed`; after the change the same existing but incomplete file is correctly classified as `missing_coverage`, never zero. Commit `b6f23428bbf1495ba27e22296fb283284491039c`; `python3 -m unittest skills.cfo.test_loop_pnl -v` passed 44/44 and the source-boundary check passed. Independent read-only review found no Critical/Important issue; it noted only that empty-override/explicit-override behavior is not separately asserted. The fix is not production-loaded.
- Installed Rork `asc` CLI was `5.9.2`, matching the [latest published release](https://github.com/rorkai/App-Store-Connect-CLI/releases/tag/5.9.2). A read-only `FINANCE_DETAIL`, region `Z1`, report for `2026-09` returned two sales rows with partner share JPY 592 each (JPY 1,184 total). The rows use SKU `ai.anicca.app.ios.monthly` and title `Monthly Subscription`; their Apple identifiers matched neither the six B7 app bindings nor the 24 apps returned by the current ASC app list. The amount remains unattributed and is excluded from B7/company mobile totals. Apple documents `Z1` as the detailed financial report region: [financial-report regions and currencies](https://developer.apple.com/help/app-store-connect/reference/financial-report-regions-and-currencies/).
- The downloaded report SHA-256 was `ee1618889cb8155c1a665e87c6ad167d02083cc5c9cb36b214c5d5b27246426f`. The raw report lived only in a mode-700 temporary directory and was removed by cleanup; no report, credential, provider state, app record, or production data was written.
- The local `business-outcomes.jsonl` has 124 valid JSONL rows; its latest business date is 2026-10-03 with eight product rows. Six latest RevenueCat rows are `available` but have no currency; the file contains no `app_store_financial` rows. Therefore RevenueCat's untagged chart values and the separate direct MRR observation are not merged into a settled mobile revenue/MRR total until product, currency, and definition are reconciled.
