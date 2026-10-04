# Google Cloud Cost Table readback — 2026-10-04

Status: the private 2026-09 invoice export is readable and its account total matches ¥27,889. The file is an invoice/billing record, not proof of cash payment or loop-level cost allocation. Production B6 does not currently consume it.

## Source and provenance

- `LM_CFO_GOOGLE_BILLING_CSV` and `LM_CFO_GOOGLE_BILLING_INVOICE_MONTH` are present in the private Life Manager environment; the file path and raw CSV remain outside Git.
- The file is 14,797 bytes, modified 2026-10-02T08:53:37.312Z. Read at 2026-10-04T03:42:26.193Z for invoice month `2026-09`, JPY.
- Receipt content digest: `google-billing://sha256/c5157075fe3e8331fa2a72d3b33fc98bbacb8b84a0ee2cfc945051ee87f66c64`.
- Parsing used the read-only candidate parser from branch `docs/lm-cfo-cost-observability-spec-20261002` at `5befe4538e3f14e140cab375c0a2f79eb9ef9327`. Its focused unit tests passed 4/4; the live-file cross-month line-item check below found a case those tests miss.

## Invoice totals

| Measure | JPY |
|---|---:|
| All invoice usage line items, before tax | 25,354.451251 |
| Invoice tax | 2,535 |
| Rounding adjustment | -0.451251 |
| Invoice total | 27,889 |

The total matches the user's September invoice image. Cash-payment status was not checked.

## Project and service attribution

The CSV contains three distinct project IDs. One project name, `anicca`, matches the currently configured gcloud project; identifiers are omitted.

| Configured project service | Quantity | JPY, before tax |
|---|---:|---:|
| Places API (multiple SKUs, including Text Search, Atmosphere, and Contact Data) | mixed | 9,419.856821 |
| Geocoding API | 19,403 | 7,493.014626 |
| Directions API | 14,105 | 3,271.171127 |
| **Configured project subtotal** |  | **20,184.042574** |

The other two projects account for JPY 5,170.408677 before tax; their Life Manager ownership is unverified. Account-level tax has not been allocated to projects. The project subtotal is billed-provider cost, not yet attributed to individual Life Manager loops.

Across the full invoice, service totals before tax are Gemini API ¥5,160.873099; Places API ¥9,419.856821; Geocoding API ¥7,493.014626; Directions API ¥3,271.171127; Cloud KMS ¥9.530434; Cloud Storage ¥0.005144; and Cloud Run ¥0. These service totals sum to the invoice usage amount above.

## October estimate-only usage ledger readback — 2026-10-04 13:05 JST

- Source: the installed release's existing `readCostLedger` tenant-scoped GET, using the UID and env-file path already configured on the CFO LaunchAgent. The stable `lm_financial_cost_totals` read RPC was queried for the same fixed half-open window; no report, state, or ledger write occurred.
- Window: 2026-10-01 00:00 JST through 2026-10-04 13:05:01 JST. Direct GET and RPC both report 6,147 rows. The precise direct sum is USD 4.776581116666666657638; the RPC returns USD 4.776581116666667 (difference 3.42362e-16 from numeric serialization).
- `meta.provider` estimates: `google_maps` USD 3.93, `google_search_grounding` USD 0.035, `gemini` USD 0.74665474999999998764, and `route_cache` USD 0. The remaining USD 0.064926366666666669998 is in rows without `meta.provider`, so its provider attribution is unknown. Google-related recorded estimate is USD 4.71165474999999998764.
- No row has an `actual_status` key in `meta`; the reader selects `est_usd`, not actual billed amounts. These are usage-ledger estimates only; October's invoice has not been read. A straight-line 30-day pace would be about USD 40.42 across all recorded providers, or USD 39.87 for the Google-labeled rows. This is an inference from 3.545 days, not a forecast or settled bill.

## Current estimate-only usage ledger readback — 2026-10-04 13:54 JST

- Source: installed release `1a7a8e2f` tenant-scoped `readCostLedger` GET and the existing `lm_financial_cost_totals` `STABLE` SQL read RPC. The RPC definition only aggregates `lm_api_cost`; no report, state, or ledger write occurred.
- Fixed half-open window: 2026-10-01 00:00 JST through 2026-10-04 13:54:43.340 JST. The GET returned 6,171 rows and the RPC returned 6,171 rows / USD 4.816581116666667. The direct GET estimate rounds to USD 4.816581116667.
- Provider estimates: `google_maps` USD 3.97 / 794 rows; `google_search_grounding` USD 0.035 / 1 row; `gemini` USD 0.74665475 / 18 rows; `route_cache` USD 0 / 4,125 rows; and USD 0.064926366667 / 1,233 rows without `meta.provider`. Google-labeled estimate is USD 4.75165475.
- All 6,171 rows lack `meta.loop_id` and `meta.actual_status`. This remains usage-estimate telemetry, not settled billing or per-loop cost attribution; the October invoice is not available in this readback.
- Compared with 13:05 JST, 24 rows were added and the Google-labeled estimate rose by USD 0.04. The earlier readback remains above for audit; neither reading is an invoice or a promise of future spend.

## Parser discrepancy

The candidate Japanese CSV parser filters usage rows by the calendar month in `使用開始日`. This invoice includes a Cloud Storage usage row starting 2026-08-31, cost ¥0.000300, in the 2026-09 invoice total. The parser excludes that row from its service subtotal while reading the invoice total, producing JPY 25,354.450951 of selected usage instead of JPY 25,354.451251; its Cloud Storage service total is low by ¥0.000300. The official invoice total remains ¥27,889. This needs a regression test and parser correction before the adapter is used as a reconciled total.

## Production consumption and safety

- The installed CFO release remains `1a7a8e2faf1eb34931f05287d846fc036bc9eec0`. The environment contains the CSV path/month variables, but `LM_CFO_ACTUAL_COST_READBACK` and `LM_CFO_ACTUAL_COST` are absent; production B6 therefore still reports `read_failed`, and B7 totals remain `unknown`.
- `life-manager-cfo-hourly` occurrence `life-manager-cfo-hourly:18db34272d7a0b30-4548` exited 0 at 2026-10-04 11:57 JST, but message effect is `unknown` with no provider receipt/readback. Do not replay it.
- `life-manager-financial-report` occurrence `life-manager-financial-report:18db36a3800b1438-85710` was blocked at 12:42 JST with `host_admission_deferred:resource_capacity_busy`, effect `none`, next action `retry_after_eligibility`. Do not manually restart it.
- Issue #6549 was still `OPEN` with no comments/reactions at the 12:42 JST readback. No source code was changed; the repository's source-change gate remains unsatisfied.
- No raw CSV, invoice number, account ID, project ID, credential, or payment detail is stored here.

## Subsequent natural-owner status readback — 2026-10-04 13:08 JST

- `life-manager-cfo-hourly` occurrence `life-manager-cfo-hourly:18db376ed82b6930-7811` was deferred at 12:57 JST with `host_admission_deferred:resource_capacity_busy`, effect `not_applicable`, and no provider receipt. This pre-effect defer does not resolve the earlier 11:57 occurrence whose message effect remains `unknown`.
- `life-manager-financial-report` occurrence `life-manager-financial-report:18db3804bd6c7350-26281` was deferred at 13:07 JST for the same capacity reason, effect `none`, next action `retry_after_eligibility`.
- Both diagnostics report the installed release SHA `1a7a8e2faf1eb34931f05287d846fc036bc9eec0`. No manual retry, restart, report, or send was performed.
- Issue #6549 remained `OPEN` with zero comments/reactions on the subsequent read. Source changes remain gated.

## Current estimate-only usage ledger readback — 2026-10-04 17:50 JST

- Source: installed immutable release `1a7a8e2f` `readCostLedger` tenant-scoped GET plus the existing `lm_financial_cost_totals` `STABLE` SQL read RPC. The RPC definition is read-only; no report, state, ledger, or Telegram write occurred.
- Fixed half-open window: 2026-10-01 00:00 JST through 2026-10-04 17:50:19 JST. Direct GET and RPC both returned 6,265 rows; the GET estimate sum was USD 5.011581116667 and the RPC returned USD 5.011581116666667.
- Provider estimates: `google_maps` USD 4.13 / 826 rows; `google_search_grounding` USD 0.07 / 2 rows; `gemini` USD 0.74665475 / 18 rows; `route_cache` USD 0 / 4,137 rows; and USD 0.064926366667 / 1,282 rows without `meta.provider`. Google-labeled estimate is USD 4.94665475.
- All 6,265 rows lack `meta.loop_id` and `meta.actual_status`. The values come from `est_usd`, not actual invoice charges. October's Google invoice is still unavailable in this readback.
- Compared with the 13:54 JST observation, 94 rows were added and the Google-labeled estimate rose by USD 0.195. This is observed usage-estimate change, not a month-end forecast.
