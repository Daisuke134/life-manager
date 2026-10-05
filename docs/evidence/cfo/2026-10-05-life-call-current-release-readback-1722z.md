# A1: `life-call` current release production readback (2026-10-05T17:22:10Z / 2026-10-06 02:22 JST)

Scope: Railway production `life-call` deployment `dd3e9583-6894-444a-a00b-0da6bf952ae6`, its exact source SHA, redacted aggregate logs, and read-only GETs against the existing `lm_api_cost`, `lm_wake_log`, and `lm_wake_miss` tables. No calendar content, user identifiers, phone numbers, route/cache keys, credentials, account numbers, or raw provider payloads were retained.

## Release and exact-release cost ledger

- PR #6695 was merged to main at `2026-10-05T16:48:27Z`; source SHA is `6247a0663fb2f6d5ae48431a33d89ee1986731e0`.
- Railway deployment `dd3e9583-6894-444a-a00b-0da6bf952ae6` is the running deployment for that SHA.
- Read-only window: `2026-10-05T16:48:29.184Z <= ts < 2026-10-05T17:22:10Z`, filtered to the deployed release SHA.

| Feature | Rows | Row `est_usd` sum |
|---|---:|---:|
| Google Calendar list invocation | 25 | USD 0.000 |
| Google Maps geocoding | 4 | USD 0.020 |
| Route cache | 6 | USD 0.000 |
| **Total** | **35** | **USD 0.020** |

- All 35 rows have `runtime_trace`; all 35 lack `loop_id`. These `est_usd` values are estimates, not an invoice or actual billed amount.
- Read-only `lm_wake_log.called_at` and `lm_wake_miss.occurred_at` queries returned 0 rows in this window. This does not prove voice spend is zero.

## Wake diagnostics

The same deployment emitted six aggregate scans:

| Log time (UTC) | Users seen | Eligible / read-success | Calendar items / events / candidates | Due candidates | Read failures |
|---|---:|---:|---:|---:|---:|
| 2026-10-05 16:56:31.626 | 24 | 6 | 6 | 0 | 0 |
| 2026-10-05 17:01:37.385 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:06:41.953 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:11:48.962 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:16:58.577 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:21:57.159 | 20 | 5 | 5 | 0 | 0 |

Calendar reads succeeded for each eligible user in these samples, but no event reached the due-wake threshold. No natural voice occurrence or same-occurrence provider/cost receipt was observed. Absence of a due candidate or ledger row is not proof of zero voice billing.

## Result and effects

- A1 remains open; its cursor is a natural due voice occurrence followed by same-occurrence trace/provider/cost readback. Do not test-call or infer zero from absent rows.
- The verifier used read-only deployment status/log/GET reads. It made no test call, calendar-content query, provider mutation, database write, or report send.
