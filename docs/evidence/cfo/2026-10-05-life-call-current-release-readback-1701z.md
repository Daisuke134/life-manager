# A1: `life-call` current release production readback (2026-10-05T17:01:39.217010Z / 2026-10-06 02:01 JST)

Scope: Railway production `life-call` deployment `dd3e9583-6894-444a-a00b-0da6bf952ae6`, its exact source SHA, redacted aggregate logs, and read-only GETs against the existing `lm_api_cost`, `lm_wake_log`, and `lm_wake_miss` tables. No calendar content, user identifiers, phone numbers, route/cache keys, credentials, account numbers, or raw provider payloads were retained.

## Release

- PR #6695 was merged to main at `2026-10-05T16:48:27Z`; merge/source SHA is `6247a0663fb2f6d5ae48431a33d89ee1986731e0`.
- Railway `life-call` deployment `dd3e9583-6894-444a-a00b-0da6bf952ae6` was `SUCCESS`, with one `RUNNING` instance; created at `2026-10-05T16:48:29.184Z`.

## Exact-release cost ledger

Read-only window: `2026-10-05T16:48:29.184Z <= ts < 2026-10-05T17:01:39.217010Z`, filtered to the deployed release SHA.

| Feature | Rows | Row `est_usd` sum |
|---|---:|---:|
| Google Calendar list invocation | 10 | USD 0.000 |
| Google Maps geocoding | 3 | USD 0.015 |
| Route cache | 6 | USD 0.000 |
| **Total** | **19** | **USD 0.015** |

- All 19 rows have a `runtime_trace`; all 19 lack `loop_id`. The `est_usd` values are estimates, not a Google invoice or actual billed amount. No invoice-level billing receipt was read in this query.
- Read-only `lm_wake_log.called_at` and `lm_wake_miss.occurred_at` queries returned 0 rows in the same window. This does not prove voice spend is zero.

## Wake diagnostics

The production aggregate log at `2026-10-05T16:56:31.626788615Z` reported:

```text
[wake] scan users_seen=24 eligible_users=6 calendar_read_success=6 calendar_read_failed=0 calendar_items=6 calendar_events=6 wake_candidates=6 due_candidates=0
```

This confirms the deployed path distinguished successful calendar reads and found candidate events; none was due in this diagnostic interval. It is not a completed voice occurrence, and it does not establish that Gemini/Telnyx billing was zero. No same-occurrence wake receipt, provider usage row, and provider/cost readback were observed.

## Result and effects

- A1 remains open; its active cursor is a natural due voice occurrence followed by same-occurrence trace/provider/cost readback. Do not test-call or infer zero from absent rows.
- The verifier used read-only status/log/GET reads. It made no test call, calendar-content query, provider mutation, database write, or report send.
