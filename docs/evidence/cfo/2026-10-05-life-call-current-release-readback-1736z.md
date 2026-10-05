# A1: `life-call` current release production readback (2026-10-05T17:36:57Z / 2026-10-06 02:36 JST)

Scope: Railway production `life-call` deployment `dd3e9583-6894-444a-a00b-0da6bf952ae6`, its exact source SHA, redacted aggregate logs, and read-only GETs against the existing `lm_api_cost`, `lm_wake_log`, and `lm_wake_miss` tables. No calendar content, user identifiers, phone numbers, route/cache keys, credentials, account numbers, or raw provider payloads were retained.

## Release and exact-release cost ledger

- PR #6695 was merged to main at `2026-10-05T16:48:27Z`; source SHA is `6247a0663fb2f6d5ae48431a33d89ee1986731e0`.
- Railway deployment `dd3e9583-6894-444a-a00b-0da6bf952ae6` was `SUCCESS/RUNNING` in the latest deployment status read at `2026-10-05T17:36:57Z`.
- Read-only window: `2026-10-05T16:48:29.184Z <= ts < 2026-10-05T17:36:57Z`, filtered to the deployed release SHA.

| Feature and outcome | Rows | Row `est_usd` sum |
|---|---:|---:|
| Google Calendar list / success | 34 | USD 0.000 |
| Google Maps geocoding / success | 5 | USD 0.025 |
| Google Directions / failure, `no_route` | 12 | USD 0.060 |
| Route cache / cache hit | 6 | USD 0.000 |
| **Total** | **57** | **USD 0.085** |

- All 57 rows have `runtime_trace`; all 57 lack `loop_id`. The estimates are not actual billed amounts or a Google invoice.
- The 12 Directions rows carry 12 distinct runtime occurrence IDs, one row per occurrence. Those IDs are generated per runtime call; without an event ID join, they do not prove that the underlying calendar events were distinct.
- Read-only `lm_wake_log.called_at` and `lm_wake_miss.occurred_at` queries returned 0 rows. This is not evidence of zero voice spend.

## Wake diagnostics

The same release emitted eight aggregate scans. Each had successful reads for every eligible user, 0 read failures, item/event/wake-candidate counts equal to eligible users, and `due_candidates=0`:

| Log time (UTC) | Users seen | Eligible/read-success | Items/events/candidates | Due | Read failures |
|---|---:|---:|---:|---:|---:|
| 2026-10-05 16:56:31.626 | 24 | 6 | 6 | 0 | 0 |
| 2026-10-05 17:01:37.385 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:06:41.953 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:11:48.962 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:16:58.577 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:21:57.159 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:27:02.619 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:32:15.934 | 20 | 5 | 5 | 0 | 0 |

No due voice occurrence or same-occurrence provider/cost receipt was observed.

## Directions failure and cache diagnosis

- All 12 Directions rows have `failure_class=no_route`; the row estimate is USD 0.005 each, USD 0.060 total.
- The existing `lm_route_cache` table read for the same time window returned 14 aggregate rows: 12 `transit` / `negative` / `no_route` / 1,800-second TTL and 2 `transit` / `success` / 600-second TTL. The table has no release SHA/occurrence key, so this read is not an exact join to the cost ledger; do not assert one-to-one correspondence with its 6 cache-hit rows.
- Current source computes routes for physical reminder candidates before the reminder due-time check, then makes one Google fallback when the free transit result is not usable. A negative `no_route` result is cached for 30 minutes. The cost ledger does not record free-transit attempts or the fallback reason, so it cannot show whether the 12 fallbacks followed transit `no_route`, provider failure, or another unusable response.
- No repeated paid request for the same runtime occurrence is visible in the cost rows. Whether multiple occurrences refer to the same calendar event remains unverified because event IDs are not joined.

## Result and effects

- A1 remains open until a natural due voice occurrence has same-occurrence wake/provider/cost receipt and readback. Do not test-call or infer zero from absent rows.
- The verifier made only read-only deployment/log/table reads: no test call, calendar-content query, provider mutation, database write, or report send.
