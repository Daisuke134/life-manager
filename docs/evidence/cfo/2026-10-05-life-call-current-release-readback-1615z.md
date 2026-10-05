# A1: `life-call` current release production readback (2026-10-05T16:15:47Z / 2026-10-06 01:15:47 JST)

Scope: Railway production `life-call`, its then-current successful deployment, and read-only GETs against the existing production `lm_api_cost`, `lm_wake_log`, `lm_wake_miss`, and `lm_route_cache` tables. No UID, event identifier/content, location, phone number, route/cache key, credential, or raw log message was selected or retained.

## Release and cost ledger

- Railway status at `2026-10-05T16:15:47Z`: deployment `ae2fd577-9d2d-43c1-9ec3-5ad67c4e9bec`, source SHA `4a6b08a9095de29e88f9113b4ca393682f2693ae`, `SUCCESS`, instance `RUNNING`; created at `15:58:44.469Z`.
- Read-only `lm_api_cost` window: `2026-10-05T15:58:44.469Z <= ts < 2026-10-05T16:15:47.319134Z`, filtered to the exact release SHA and `life-call-*` owners. It returned 22 rows; row `est_usd` sum USD 0.015.

| Kind / provider / feature | Outcome | Rows | Row `est_usd` sum |
|---|---|---:|---:|
| `composio_call` / `GOOGLECALENDAR_EVENTS_LIST` | success | 13 | USD 0.000 |
| `provider_usage` / `google_maps` / `geocoding` | success | 3 | USD 0.015 |
| `provider_usage` / `route_cache` / `travel_route` | cache hit / `no_route` | 6 | USD 0.000 |
| **Total** |  | **22** | **USD 0.015** |

- All 22 rows lack `loop_id` and remain partial. `est_usd` is an estimate, not an invoice or actual billed amount. No Directions failure, `gemini_live`, `telnyx_call`, or `feature=live_api` row appeared in this exact-release window.
- A separate route-cache GET for the same time window returned 2 successful entries with TTL 600 seconds. Aggregate cache-table rows are not joined to individual cost events; they do not prove event-level replay-zero.

## Wake and voice observability

- Read-only GETs in this deployment window returned 0 `lm_wake_log.called_at` rows and 0 `lm_wake_miss.occurred_at` rows. This does not prove voice spend is zero or that there was no eligible calendar event.
- Railway returned 556 log lines timestamped `16:02:26.138Z`–`16:15:30.784Z` for the requested `15:58:44`–`16:15:47` window; thus the returned log slice does not cover the first part of the deployment window. `voice reconciliation checked` matched 3; wake placement, dial failure, missed wake, carrier connection, Gemini, Telnyx, and calendar-read-error patterns matched 0 in the returned slice.
- Current main source still does not log calendar raw-item/candidate counts, and the non-strict calendar path can collapse a read failure into an empty result. No calendar contents were queried and no voice call, paid Gemini/Telnyx request, or database write was made by the verifier.

## Result

A1 remains open and is still the active cursor. This snapshot is a short exact-release estimate window, not monthly spend or actual Google billing. Natural voice occurrence and same-occurrence trace/provider/cost readback remain unobserved; do not convert absent rows or estimates into zero.
