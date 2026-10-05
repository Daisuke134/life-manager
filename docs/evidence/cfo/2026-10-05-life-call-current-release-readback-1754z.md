# A1: `life-call` current release production readback (2026-10-05T17:54:24Z / 2026-10-06 02:54 JST)

Scope: Railway production `life-call` deployment `dd3e9583-6894-444a-a00b-0da6bf952ae6`, its exact source SHA, redacted aggregate logs, and read-only GETs against the existing `lm_api_cost`, `lm_wake_log`, and `lm_wake_miss` tables. No calendar content, user identifiers, phone numbers, route/cache keys, credentials, account numbers, or raw provider payloads were retained.

## Release and exact-release cost ledger

- PR #6695 was merged to main at `2026-10-05T16:48:27Z`; source SHA is `6247a0663fb2f6d5ae48431a33d89ee1986731e0`.
- Railway deployment `dd3e9583-6894-444a-a00b-0da6bf952ae6` remains `SUCCESS/RUNNING`.
- Read-only window: `2026-10-05T16:48:29.184Z <= ts < 2026-10-05T17:54:24Z`, filtered to the deployed release SHA.

| Feature and outcome | Rows | Row `est_usd` sum |
|---|---:|---:|
| Google Calendar list / success | 48 | USD 0.000 |
| Google Maps geocoding / success | 5 | USD 0.025 |
| Google Directions / failure, `no_route` | 12 | USD 0.060 |
| Route cache / cache hit | 12 | USD 0.000 |
| **Total** | **77** | **USD 0.085** |

- All 77 rows have `runtime_trace`; all 77 lack `loop_id`. Estimates are not actual billed amounts or a Google invoice.
- The 12 Directions rows carry 12 distinct runtime occurrence IDs, one row per occurrence. Without an event ID join, they do not prove that the underlying calendar events were distinct.
- Read-only `lm_wake_log.called_at` and `lm_wake_miss.occurred_at` queries returned 0 rows. This is not evidence of zero voice spend.

## Wake diagnostics

Twelve aggregate scans were observed through `2026-10-05T17:52:28Z`. Every scan had `calendar_read_success=eligible_users`, `calendar_read_failed=0`, and `due_candidates=0`:

| Log time (UTC) | Users seen | Eligible | Calendar items / events / candidates | Due | Read failures |
|---|---:|---:|---:|---:|---:|
| 2026-10-05 16:56:31.626 | 24 | 6 | 6 | 0 | 0 |
| 2026-10-05 17:01:37.385 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:06:41.953 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:11:48.962 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:16:58.577 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:21:57.159 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:27:02.619 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:32:15.934 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:37:17.122 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:42:25.861 | 20 | 5 | 5 | 0 | 0 |
| 2026-10-05 17:47:31.639 | 20 | 5 | 8 | 0 | 0 |
| 2026-10-05 17:52:28.630 | 20 | 5 | 10 | 0 | 0 |

No due voice occurrence or same-occurrence provider/cost receipt was observed.

## Directions and route-cache diagnosis

- All 12 Google Directions rows have `failure_class=no_route`; the row estimate is USD 0.005 each, USD 0.060 total. Their 12 `runtime_trace.occurrence_id` values are distinct, with one Directions row per occurrence. They are runtime-call IDs, not calendar event IDs; event-level distinctness is unverified.
- The cost ledger grew from 59 rows at `17:43:28Z` to 77 at `17:54:24Z`; Google estimate remained USD 0.085. The increase was 12 Calendar list success rows and 6 route-cache-hit rows; no additional Directions or geocoding rows appeared in that interval.
- A separate `lm_route_cache` GET over the same time window returned 14 table rows: 12 `transit` / `negative` / `no_route` / 1,800-second TTL and 2 `transit` / `success` / 600-second TTL. The table has no release SHA/occurrence key, so this aggregate is not an exact join to the release cost rows or the 12 cache-hit records.
- Current source computes routes for physical reminder candidates before the reminder due-time check, then makes one Google fallback when the free transit result is not usable. A negative `no_route` result is cached for 30 minutes. The cost ledger does not record free-transit attempts or the fallback reason, so it cannot show whether the 12 fallbacks followed transit `no_route`, provider failure, or another unusable response.

## Result and effects

- A1 remains open until a natural due voice occurrence has same-occurrence wake/provider/cost receipt and readback. Do not test-call or infer zero from absent rows.
- The verifier made only read-only deployment/log/table reads: no test call, calendar-content query, provider mutation, database write, or report send.

## Later exact-release refresh (2026-10-05T18:15:32Z)

A later read-only cost-ledger query against the same running deployment and exact source SHA returned 86 rows / USD 0.085 in row-level estimates:

| Feature and outcome | Rows | Row `est_usd` sum |
|---|---:|---:|
| Google Calendar list / success | 57 | USD 0.000 |
| Google Maps geocoding / success | 5 | USD 0.025 |
| Google Directions / failure, `no_route` | 12 | USD 0.060 |
| Route cache / cache hit | 12 | USD 0.000 |
| **Total** | **86** | **USD 0.085** |

- Relative to the 17:54:24Z snapshot, the nine added rows are Calendar-list successes; there are no added geocoding or Directions rows, and the estimate total is unchanged.
- All 86 rows have a runtime trace and all lack `loop_id`. The 12 Directions rows remain one per 12 distinct runtime occurrence IDs; event-level distinctness remains unverified. Row estimates are not actual bills or an invoice.
- The latest aggregate scan read at `2026-10-05T18:12:51Z` reports 16 scans since 16:56Z; all had successful Calendar reads and zero due candidates. The latest counts were 20 users, 5 eligible users, and 10 Calendar items/events/candidates. No natural voice occurrence was observed.
- This refresh was read-only: no test call, Calendar-content query, provider mutation, database write, or report send.

## Source promotion and production deployment readback (2026-10-05T18:48:42Z)

- PR #6705 merged at `2026-10-05T18:43:49Z` as main merge commit `a09d0ad40b4eddfcaa65ca03b9804604ba692557`.
- Railway `life-call` deployment `8af6ae6a-0240-472a-9e02-06c663c1a90c` reports `SUCCESS` with `meta.commitHash` equal to the merge commit. A separate `railway status` read reports the `life-call` service `Online` in production.
- The exact cost-ledger and wake-diagnostics snapshot above predates this deployment. A post-deployment exact-release cost/wake occurrence readback has not yet been captured, so the USD 0.085 estimate is not attributed to the new release and is not actual billing.
- This promotion check was read-only after the merge: no test call, Calendar-content query, provider mutation, database write, or report send. A1 remains open until a natural due voice occurrence has same-occurrence wake/provider/cost receipt and readback.


## A1 post-deployment exact-release cost and wake readback (2026-10-05T19:09:30Z)

Scope: exact Railway release SHA `a09d0ad40b4eddfcaa65ca03b9804604ba692557`, starting at deployment creation `2026-10-05T18:43:51.815Z`. Cost and wake tables were queried with read-only GETs. Deployment logs were separately read at `2026-10-05T19:10:16Z` and reduced to aggregate wake counters only.

| Kind / provider / feature / outcome | Rows | Row `est_usd` sum |
|---|---:|---:|
| `composio_call` / success | 24 | USD 0.000 |
| `provider_usage` / Google Maps / geocoding / success | 3 | USD 0.015 |
| `provider_usage` / route cache / travel_route / cache_hit (`no_route`) | 6 | USD 0.000 |
| **Total** | **33** | **USD 0.015** |

- All 33 exact-release rows have an occurrence ID. None has a `loop_id`, a fully linked runtime trace, `actual_usd`, or a provider receipt ID. These missing actual/billing fields are unknown, not actual spend of USD 0.
- The exact release has no Google Directions or voice cost row in this window, so the deployed `route_mode`/`fallback_reason` metadata has not yet been exercised by a natural Google fallback.
- Read-only GETs returned zero `lm_wake_log.called_at` rows and zero `lm_wake_miss.occurred_at` rows since deployment. Four aggregate `[wake] scan` records were present in the deployment logs; all had `calendar_read_failed=0` and `due_candidates=0`. The latest was users/eligible/items/events/candidates/due=`20/5/10/10/10/0`; the earliest of the four was `24/6/12/12/12/0`.
- No test call, Calendar-content query, provider mutation, database write, or report send was performed. A1 remains open until a natural due voice occurrence has same-occurrence wake/provider/cost receipt and readback.

## A1 transit-timeout production readback (2026-10-05T19:29:46Z)

Scope: exact Railway release SHA `a09d0ad40b4eddfcaa65ca03b9804604ba692557`, from deployment creation `2026-10-05T18:43:51.815Z`. Two sequential read-only GETs to `lm_api_cost` returned the same 59 unique row IDs and the same estimate. No row IDs, tenant IDs, event IDs, addresses, or raw provider payloads are retained.

| Kind / provider / feature / outcome | Rows | Row `est_usd` sum |
|---|---:|---:|
| `composio_call` / success | 36 | USD 0.000 |
| `provider_usage` / Google Maps / geocoding / success | 5 | USD 0.025 |
| `provider_usage` / route cache / travel_route / cache_hit (`no_route`) | 6 | USD 0.000 |
| `provider_usage` / Google Maps / directions / failure (`no_route`, route mode `transit`, fallback `transit_timeout`) | 12 | USD 0.060 |
| **Total** | **59** | **USD 0.085** |

- All 59 rows have a runtime occurrence ID, but none has `loop_id`, a fully linked trace, `actual_usd`, or a provider receipt ID. These are missing actual/billing fields, not actual spend of USD 0.
- The 12 Directions rows have 12 distinct occurrence IDs and run IDs, with no repeated occurrence ID. The cost table has no Calendar event ID, so distinctness at event level is unverified. Each row carries `fallback_reason=transit_timeout`.
- Read-only wake GETs at `2026-10-05T19:29:46Z` returned zero `lm_wake_log` and `lm_wake_miss` rows. A log read at `19:30:29Z` found seven `[wake] scan` aggregates from this deployment; all had successful Calendar reads, zero read errors, and zero due candidates. The latest counts were users/eligible/items/events/candidates/due=`20/5/10/10/10/0`.
- **Read consistency anomaly:** single exact-window GETs at `19:20:30Z` and `19:21:10Z` returned 49 and 48 rows, respectively. Later repeated GET pairs returned stable identical row-ID sets at 50, 51, 56, and 59 rows. The inspected repository and migrations contain no `lm_api_cost` delete/update path, but the 49→48 discrepancy's cause is unresolved; it is not treated as zero or silently discarded.
- No test call, Calendar-content query, provider mutation, database write, or report send was performed. These row estimates are not invoices or monthly actual cost. A1 remains open until a natural due voice occurrence has same-occurrence wake/provider/cost receipt and readback.

## A1 corrected fixed-window snapshot (2026-10-05T19:40:57Z)

Window: `2026-10-05T18:43:51.815Z <= ts < 2026-10-05T19:40:57Z`. Two sequential strict read-only GETs for release SHA `a09d0ad40b4eddfcaa65ca03b9804604ba692557` returned the same 62-row ID set and USD 0.085 in row estimates.

**Correction:** the earlier 65-row figure counted every release in the time window. Three `composio_call` rows belonged to a different release SHA; they are not part of this target-release total. The 65-row all-release count and 62-row strict release count are both valid for their respective scopes.

| Kind / provider / feature / outcome | Rows | Row `est_usd` sum |
|---|---:|---:|
| `composio_call` / success | 39 | USD 0.000 |
| `provider_usage` / Google Maps / geocoding / success | 5 | USD 0.025 |
| `provider_usage` / route cache / travel_route / cache_hit (`no_route`) | 6 | USD 0.000 |
| `provider_usage` / Google Maps / directions / failure (`no_route`, `transit_timeout`) | 12 | USD 0.060 |
| **Target release total** | **62** | **USD 0.085** |

- The 12 Directions rows have 12 distinct runtime occurrence IDs and run IDs, with no same-occurrence duplicate. Calendar event IDs are absent, so event-level distinctness is unverified. All 62 rows have occurrence IDs; `loop_id`, fully linked trace, `actual_usd`, and provider receipt ID are absent. These are estimate rows, not actual billing.
- Exact-deployment, fixed-window `[wake] scan` reads returned 10 aggregates twice. All had successful Calendar reads, `calendar_read_failed=0`, and `due_candidates=0`; a default/unfiltered limited read returned only five and was incomplete. The latest counts were users/eligible/items/events/candidates/due=`20/5/10/10/10/0`. `lm_wake_log` and `lm_wake_miss` GETs returned zero rows.
- The earlier 49→48 single-read divergence remains unexplained and stays on A2's repeat-read consistency cursor.
- No test call, Calendar-content query, provider mutation, database write, or report send was performed. A1 remains open until a natural due voice occurrence has same-occurrence wake/provider/cost receipt and readback.

## A1 latest strict-release snapshot (2026-10-05T19:52:09Z)

Window: `2026-10-05T18:43:51.815Z <= ts < 2026-10-05T19:52:09Z`. Two sequential strict read-only GETs for SHA `a09d0ad40b4eddfcaa65ca03b9804604ba692557` returned the same 80-row ID set and USD 0.085 in row estimates. The same fixed window without a release filter returned 83 rows: 3 rows belong to other or missing release SHA and are excluded from this target-release total.

| Kind / provider / feature / outcome | Rows | Row `est_usd` sum |
|---|---:|---:|
| `composio_call` / success | 51 | USD 0.000 |
| `provider_usage` / Google Maps / geocoding / success | 5 | USD 0.025 |
| `provider_usage` / route cache / travel_route / cache_hit | 12 | USD 0.000 |
| `provider_usage` / Google Maps / directions / failure (`transit_timeout`) | 12 | USD 0.060 |
| **Target release total** | **80** | **USD 0.085** |

- The exact-release readback contains 77 distinct runtime occurrence IDs and 77 distinct run IDs; all 80 rows lack `loop_id`, and zero rows carry a provider receipt. The 12 Directions timeout rows remain distinct by occurrence/run, but no Calendar event ID join exists. USD 0.085 is the row-estimate sum, not a Google invoice or actual billed amount.
- Railway still reports deployment `8af6ae6a-0240-472a-9e02-06c663c1a90c` / SHA `a09d0ad40b4eddfcaa65ca03b9804604ba692557` as `SUCCESS`, with its instance `RUNNING`. Twelve exact-deployment scans through `2026-10-05T19:47:07Z` had `calendar_read_failed=0` and `due_candidates=0`; the latest users/eligible/items/events/candidates/due counts were `20/5/10/10/10/0`. `lm_wake_log` and `lm_wake_miss` had zero rows in the deployment window.
- No test call, Calendar-content query, provider mutation, database write, or report send was performed. A1 remains open until a natural due voice occurrence has same-occurrence wake/provider/cost receipt and readback.
