# RevenueCat / Apple finance coverage readback — 2026-10-04

## RevenueCat monetary coverage

- Latest `business-outcomes` records through 2026-10-03 show RevenueCat as `available` for six mobile apps. Those records do not include currency, unit, or `revenue_definition`; availability therefore does not establish a monetary MRR or a comparable revenue total.
- The persisted `subscriptions.json` projection has latest report day 2026-09-26 and integrity PASS, but Anicca and Honne are `unavailable` with `product_pack_observation_missing`. The product-pack inputs expected by the collector are absent.
- Correction: the initial search missed the active private runtime env. A later read-only check found nonempty `REVENUECAT_PROJECT_ID` and `REVENUECAT_V2_SECRET_KEY` entries there (mode 600; values never displayed); the separate credential SSOT has no RevenueCat entry. Direct official API readback is now recorded in [RevenueCat live financial readback](2026-10-04-revenuecat-live-readback.md).
- The legacy local RevenueCat snapshot is based on a 2026-05-04 MCP observation and is marked stale after 2026-05-11. It is not current CFO evidence; its monetary values are intentionally omitted here.
- The `business-outcomes` materialized rows still lack currency/`revenue_definition`; that storage gap remains. Current direct provider MRR and project proceeds measurements are recorded in the linked live-readback evidence, but do not treat them as Apple settlement or bank cash.

## Apple FINANCIAL report attribution

- ASC CLI 5.9.2 read-only retrieval returned the official fiscal `2026-12` FINANCIAL report, covering 2026-08-30..2026-09-26. It contains one JPY `Extended Partner Share` row with product type `IAY`; amount and provider identifiers are intentionally omitted from this public evidence.
- The report's Apple Identifier matched 0 of the 24 app resources in the current read-only ASC inventory. `asc apps view` could not resolve/access that app identifier, and Apple's public iTunes Lookup returned no result.
- The report title `Anicca Annual` matches a local StoreKit display name, but the configured StoreKit product ID differs. A display-name match alone does not establish app/product ownership. Keep this proceeds row unattributed and outside B7 until an official app-ID/product mapping is found.
- Apple defines `reportDate` using its fiscal month; `Extended Partner Share` is unit Partner Share multiplied by quantity after applicable taxes and commission; `IAY` denotes an iOS auto-renewable subscription. This is a proceeds line, not evidence of a bank deposit or a full calendar-September total.
- Raw report TSV, exact amount, Apple Identifier, vendor number, transaction data, and credentials were not persisted in this evidence file.

## Primary sources

- [Download financial reports](https://developer.apple.com/help/app-store-connect/getting-paid/download-financial-reports)
- [Financial report fields](https://developer.apple.com/help/app-store-connect/reference/reporting/financial-report-fields)
- [Product type identifiers](https://developer.apple.com/help/app-store-connect/reference/reporting/product-type-identifiers)
- [ASC acquisition and financial report readback](2026-10-04-asc-acquisition-readback.md)
- TODO/status source of truth → [Unified SSOT](../../superpowers/specs/2026-09-25-life-manager-unified-ssot.md)
