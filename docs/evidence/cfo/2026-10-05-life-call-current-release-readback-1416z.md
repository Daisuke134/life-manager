# A1: `life-call` cumulative production readback (14:16 UTC)

Scope: Railway production `life-call`, its exact active source release, and read-only GETs against the existing production `lm_api_cost`, `lm_wake_log`, and `lm_wake_miss` tables. This is not a company-wide invoice or actual-spend report. No UID, tenant ID, run/occurrence ID, call ID, phone number, calendar event, or raw log message was selected or retained.

## Release

- Railway deployment list readback during this audit: latest successful `life-call` deployment remains `38b34ef2-4900-4ccc-83b8-f874bf88fac8`, source SHA `9e3fb448b6799e6f5183f087773fa245c8409778`, created at `2026-10-05T12:34:01.656Z`. The later main deployment for merge SHA `035f1d4c15cc6c474a7ce529adcda517180ed6a5` was `SKIPPED` at `2026-10-05T14:04:27.372Z` (`No changes to watched files`).

## Cost ledger

- Read-only GET at `2026-10-05T14:16:46Z`, filtered to the exact release SHA and the half-open window `2026-10-05T12:34:01.656Z <= ts < 2026-10-05T14:16:46Z`. It returned 113 rows, timestamp range `2026-10-05T12:36:13.084567Z`–`2026-10-05T14:16:15.24148Z`.
- All 113 rows contain owner, run, occurrence, and release SHA; all 113 lack `loop_id`, so all remain partial and cannot be assigned to a Product Loop by name alone.

| Kind / provider / feature | Outcome | Rows | Row `est_usd` sum |
|---|---|---:|---:|
| `composio_call` / `GOOGLECALENDAR_EVENTS_LIST` | success | 70 | USD 0.000 |
| `provider_usage` / `route_cache` / `travel_route` | cache hit | 14 | USD 0.000 |
| `provider_usage` / `google_maps` / `directions` | failure | 24 | USD 0.120 |
| `provider_usage` / `google_maps` / `geocoding` | success | 5 | USD 0.025 |
| **Total** |  | **113** | **USD 0.145** |

- Compared with the previous fixed snapshot ending at `13:52:04.283Z`, 22 additional rows were observed: 16 Calendar list calls and 6 route-cache hits. Their row `est_usd` sums are USD 0. The cumulative USD 0.145 remains an estimate only, not actual spend, invoice, or proof of free usage. Production actual/billing fields remain absent per the earlier schema probe.

## Wake and voice occurrence

- Production GET bounded to the same deployment window returned 0 `lm_wake_log.called_at` rows and 0 `lm_wake_miss.occurred_at` rows.
- The cumulative ledger categories contain no `gemini_live`, `telnyx_call`, or `feature=live_api` rows through this readback.
- Railway logs were classified locally for `2026-10-05T13:52:04.283Z`–`14:16:46Z`; 1,012 lines were counted. `voice reconciliation checked` matched 5 lines. Scheduler start, wake start, wake placement, dial failure, missed wake, carrier connection, Gemini, and Telnyx categories each matched 0. Raw log bodies were not saved.
- The verifier made no voice call, Calendar write, billable Gemini/Telnyx invocation, or database write; it performed only read-only GETs and log reads. The absence of a natural voice occurrence does not prove voice spend is zero.

## Result

A1 remains open. Continue with read-only observation until a natural voice occurrence, then read back its Gemini/Telnyx cost rows and provider outcome. Do not create a test call or treat estimated zeros as actual spend. Keep the established A1→A10 CFO order.
