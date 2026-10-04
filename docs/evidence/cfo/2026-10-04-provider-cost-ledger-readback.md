# Tenant provider-cost ledger readback — 2026-10-04

Status: `estimate_only` / source-complete for the queried time window, but not a settled bill or loop-attributed COGS.

## Read contract

- Read window: 2026-10-01 00:00 JST through 2026-10-04 08:44 JST (`2026-09-30T15:00:00Z` through `2026-10-03T23:44:33Z`).
- Source: the current CFO LaunchAgent's configured tenant scope, read-only `lm_api_cost` GET via the existing `readCostLedger` path, plus the existing `lm_financial_cost_totals` stable summary RPC. The tenant identifier, Supabase URL/key, raw rows, and receipt IDs are intentionally omitted.
- The tenant-filtered scan returned 5,814 rows since the start boundary. After applying the exact fixed end boundary, 5,812 rows remained; `lm_financial_cost_totals.period_rows` independently returned 5,812 for the same window. The two rows after the fixed end were excluded from the comparison.

## Cost estimates

These are `est_usd` values in the usage ledger, not provider invoices or settlement receipts.

| event kind | rows in window | estimated USD |
|---|---:|---:|
| `provider_usage` | 4,653 | 4.531654750000 |
| `telnyx_call` | 18 | 0.064926366667 |
| `gemini_live` | 18 | 0 |
| `composio_call` | 1,120 | 0 |
| `composio_poll` | 3 | 0 |
| **all recorded kinds** | **5,812** | **4.596581116667** |

Provider-usage estimate breakdown:

- `google_maps` / Directions: 659 failed request events, USD 3.295 estimate.
- `google_maps` / Geocoding: 91 successful request events, USD 0.455 estimate.
- `gemini` / Live API: 18 events, USD 0.74665475 estimate.
- `google_search_grounding`: 1 event, USD 0.035 estimate.
- `route_cache`: 3,884 cache-hit events, USD 0 estimate.

Do not treat failed Directions requests as settled billable usage; the ledger amount is an estimate and the official October Cost Table invoice has not issued.

## Attribution and production gap

- The tenant-scoped `lm_provider_lane_summary` request returned HTTP 404 / `PGRST202`: PostgREST's schema cache does not contain `public.lm_provider_lane_summary(p_period_end, p_period_start, p_tenant_id)`. This does not distinguish a missing production migration from an unapplied schema-cache refresh.
- The existing `lm_financial_cost_totals` RPC works and reconciles the fixed-window row count, but only returns a total; it cannot show provider lanes.
- `lm_api_cost.meta` has no `loop_id` or `actual_status` key in this window. Therefore these estimates cannot yet be attributed to a product loop or reconciled to actual provider billing.
- No Google October settlement receipt, actual-vs-estimate status, or seven-period natural observation is proven by this read.

This was a read-only query. No usage ledger, tenant binding, deployment, report, or external provider state was changed.

## Supplemental production-release read — 2026-10-04 10:22 JST

- Source: the active CFO LaunchAgent's configured tenant UID and read-only `readCostLedger` / `lm_financial_cost_totals` paths in release `b7fb1dfa5a`. The direct tenant scan and stable RPC used the identical half-open window, 2026-10-01 00:00 through 2026-10-04 10:22 JST.
- Direct scan returned 6,031 rows / USD 4.656581116667 estimated; the stable RPC returned 6,031 / USD 4.656581116666667. The row counts match and the decimal difference is below one cent.
- Kind totals: `provider_usage` 4,846 / USD 4.59165475; `telnyx_call` 18 / USD 0.064926366667; `gemini_live` 18 / USD 0; `composio_call` 1,145 / USD 0; `composio_poll` 4 / USD 0.
- Within `provider_usage`: Google Maps 762 / USD 3.81 estimated, consisting of Directions 671 / USD 3.355 with `outcome=failure` and `failure_class=no_route`, plus Geocoding 91 / USD 0.455 with `outcome=success`; Gemini 18 / USD 0.74665475; Google Search Grounding 1 / USD 0.035; route cache 4,065 / USD 0.
- The ledger metadata still has no `loop_id` or `actual_status`. These estimates are not provider settlements, do not prove failed Directions attempts are billable, and do not establish total Google Cloud invoice cost.
- This was read-only. No report was generated or sent, and no ledger, tenant, or provider state was changed.
