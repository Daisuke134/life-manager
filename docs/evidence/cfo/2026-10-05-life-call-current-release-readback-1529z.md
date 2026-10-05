# A1: `life-call` cumulative production readback (15:29:30 UTC)

Scope: Railway production `life-call`, the latest successful release, and read-only GETs against the existing production cost and wake tables. The read did not select or retain tenant IDs, run/occurrence IDs, route/cache keys, phone numbers, calendar content, or raw log messages.

## Release and cost ledger

- At `2026-10-05T15:29:30Z`, latest successful deployment remained `38b34ef2-4900-4ccc-83b8-f874bf88fac8`, source SHA `9e3fb448b6799e6f5183f087773fa245c8409778`, deployed `2026-10-05T12:34:01.656Z`.
- Read-only `lm_api_cost` window: `2026-10-05T12:34:01.656Z <= ts < 2026-10-05T15:29:30Z`; 175 rows. Exact per-row minimum/maximum timestamps were not retained in this aggregate readback.

| Kind / provider / feature | Outcome | Rows | Row `est_usd` sum |
|---|---|---:|---:|
| `composio_call` / `GOOGLECALENDAR_EVENTS_LIST` | success | 114 | USD 0.000 |
| `provider_usage` / `route_cache` / `travel_route` | cache hit | 20 | USD 0.000 |
| `provider_usage` / `google_maps` / `directions` | failure | 36 | USD 0.180 |
| `provider_usage` / `google_maps` / `geocoding` | success | 5 | USD 0.025 |
| **Total** |  | **175** | **USD 0.205** |

- All 175 rows have owner, run, occurrence, and release SHA; all 175 lack `loop_id` and remain partial. No Product Loop is inferred from the owner name.
- All 36 Directions failures are `failure_class=no_route` and `cache_hit=false`. Among the 20 route-cache cost events, 18 are tagged `no_route` and 2 success. These aggregates do not establish a per-event cache/provider join or production replay-zero.
- The sum is `est_usd`, not actual spend, an invoice, or proof of free service. Production actual/billing columns were absent in the earlier schema probe (`SQLSTATE 42703`); Google Cloud Cost Table receipt remains uncollected.

## Wake and voice observability

- GETs bounded to the deployment window through `15:29:30Z` returned 0 `lm_wake_log.called_at` rows and 0 `lm_wake_miss.occurred_at` rows. The cost ledger has 0 `gemini_live`, `telnyx_call`, or `feature=live_api` rows. This does not prove voice spend is zero or that no eligible event existed.
- The latest Railway log slice read was `15:00:59Z`–`15:06:19Z` (594 lines); `voice reconciliation checked` matched 3; wake placement, dial failure, missed wake, carrier connection, Gemini, and Telnyx categories matched 0. This log slice does not cover the remainder of the cost window through `15:29:30Z`.
- Scheduler source still omits candidate counts and silently returns on calendar-fetch exceptions. Therefore 0 wake/miss rows cannot distinguish no candidates, filtered/empty candidates, or a fetch error. Calendar content was not queried.
- No voice call, paid Gemini/Telnyx request, calendar write, or database write was made by the verifier. The read-only work was limited to cost/wake GETs, deployment/log read, and source inspection.

## Result

A1 remains open and is still the active cursor. Natural voice occurrence plus trace-linked provider/cost readback is unobserved; missing `loop_id`, actual invoice/billing fields, and event-level replay-zero remain unresolved. Do not convert estimates or absent rows into actual spend or zero. A1→A10 order is unchanged.
