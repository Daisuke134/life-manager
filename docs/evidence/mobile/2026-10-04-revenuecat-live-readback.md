# RevenueCat live financial readback — 2026-10-04

## Read boundary

- Read-only GETs used the existing `skills/earn/marketing-engine/measure/business_outcomes.py` helper and the nonempty `REVENUECAT_PROJECT_ID` / `REVENUECAT_V2_SECRET_KEY` entries in the private runtime env. Its mode is 600. Secret value, project ID, app IDs, customer rows, and raw response bodies were not printed or persisted.
- The active key is absent from the separate credential SSOT; no credential was created, copied, or changed. No collector persistence, ledger write, report send, or Apple settlement operation occurred.
- Primary docs: [RevenueCat API v2 — Charts and metrics](https://www.revenuecat.com/docs/api-v2/charts-and-metrics).

## Current Mobile MRR

| App scope | Latest complete period | MRR | Currency |
|---|---:|---:|---|
| Anicca iOS | 2026-10-03 | 3,196.91 | JPY |
| Honne AI | 2026-10-03 | 0 | JPY |
| Breath Reset | 2026-10-03 | 0 | JPY |
| Sleep Ritual | 2026-10-03 | 0 | JPY |
| Desk Stretch Timer | 2026-10-03 | 0 | JPY |
| Micro Mood | 2026-10-03 | 0 | JPY |
| **Six configured App Store apps** | **2026-10-03** | **3,196.91** | **JPY** |

- RevenueCat chart options contained eight app filters. All six configured mobile app IDs matched; the two additional options were Anicca Web Billing and Test Store, each with MRR 0. The project-wide MRR chart and six app-filtered MRR values reconciled to JPY 3,196.91.
- A second request for the same latest period with `currency=USD` returned USD 20.34. The project `metrics/overview` returned rounded MRR `$20`, active subscriptions 5, active trials 0, and Revenue `$32` for its `P28D` period; the overview response has no explicit currency code or as-of timestamp, so the dated chart is the stronger MRR observation.
- The chart response reports `yaxis_currency=JPY` for the JPY query but still labels `yaxis` and measure `unit` as `$`. The currency parameter changes the measured value (`JPY 3,196.91` vs `USD 20.34`), while that display label does not. Consumers must use the explicit `yaxis_currency`/currency field, not the symbol-only unit label.
- Project-wide MRR response SHA-256: `2ad5386f233493b5e3bc69d59989154bd951f828da802a74798538ed568554a4`.

## September RevenueCat proceeds metric

- Official `GET /v2/projects/{project_id}/metrics/revenue` for inclusive 2026-09-01..2026-09-30, `currency=JPY`, `revenue_type=proceeds` returned **JPY 3,363.77**. RevenueCat documents `proceeds` as revenue net of taxes and store commission.
- This metric is project-wide, across all eight app filters. The app-filtered revenue chart selected `revenue_type=proceeds`; Anicca iOS summed to JPY 3,363.77 and the other seven app-filter responses shared the zero-response hash. The chart again returned explicit `yaxis_currency=JPY` with symbol-only unit `$`; do not derive currency from the symbol.
- The project metric response SHA-256 is `573316a07271ffb76a9452ba4ead75215c64f16c0e0a818d0ed18774da6e342`.
- This is a RevenueCat provider metric, not an Apple FINANCIAL report, settlement receipt, or bank deposit. It is not added to settled B7 revenue or combined with the October 3 MRR stock measure.

## CFO effect

- The direct source now provides a dated Mobile MRR observation and a completed-month project proceeds metric. The existing `business-outcomes.jsonl` projection still omits currency and `revenue_definition`, and the source values were not persisted into the CFO ledger/report.
- Company-wide settled revenue, net profit, MRR across all business streams, and Apple-to-bank payout remain unknown. The existing CFO source-coverage gaps remain open until the direct metrics are correctly integrated and joined with settlement receipts.
- TODO/status source of truth → [Unified SSOT](../../superpowers/specs/2026-09-25-life-manager-unified-ssot.md).
