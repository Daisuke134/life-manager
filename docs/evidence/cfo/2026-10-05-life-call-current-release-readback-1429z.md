# A1: `life-call` cumulative production readback (14:29 UTC)

Scope: Railway production `life-call`, the latest successful release, and read-only GETs against existing production cost/wake tables. No UID, tenant ID, run/occurrence ID, call ID, phone number, calendar event content, or raw log message was selected or retained.

## Release

- Railway deployment list readback at `2026-10-05T14:29:10Z`: latest successful deployment remains `38b34ef2-4900-4ccc-83b8-f874bf88fac8`, source SHA `9e3fb448b6799e6f5183f087773fa245c8409778`, created `2026-10-05T12:34:01.656Z`. The main deployment for merge SHA `fbc535b56b526393eb1e3ef88d77218492f8bf7a` was `SKIPPED` at `2026-10-05T14:26:52.461Z` (`No changes to watched files`).

## Cost ledger

- Read-only GET at `2026-10-05T14:29:44Z`, exact release SHA, half-open window `2026-10-05T12:34:01.656Z <= ts < 2026-10-05T14:29:44Z`: 118 rows, timestamp range `2026-10-05T12:36:13.084567Z`–`2026-10-05T14:23:11.225785Z`.
- All 118 rows contain owner, run, occurrence, and release SHA; all 118 lack `loop_id` and remain partial.

| Kind / provider / feature | Outcome | Rows | Row `est_usd` sum |
|---|---|---:|---:|
| `composio_call` / `GOOGLECALENDAR_EVENTS_LIST` | success | 75 | USD 0.000 |
| `provider_usage` / `route_cache` / `travel_route` | cache hit | 14 | USD 0.000 |
| `provider_usage` / `google_maps` / `directions` | failure | 24 | USD 0.120 |
| `provider_usage` / `google_maps` / `geocoding` | success | 5 | USD 0.025 |
| **Total** |  | **118** | **USD 0.145** |

- Compared with the previous snapshot ending at `2026-10-05T14:16:46Z`, five additional Calendar list rows were observed; their row estimates total USD 0. The cumulative USD 0.145 is an estimate, not actual spend, an invoice, or proof of free usage. Production actual/billing columns remain absent per the earlier schema probe.

## Wake and voice occurrence

- GETs bounded to the same release window returned 0 `lm_wake_log.called_at` rows and 0 `lm_wake_miss.occurred_at` rows. The cumulative ledger has no `gemini_live`, `telnyx_call`, or `feature=live_api` rows.
- Railway logs classified locally for `2026-10-05T14:16:46Z`–`14:29:44Z`: 508 lines; `voice reconciliation checked` matched 3. Wake placement, dial failure, missed wake, carrier connection, Gemini, and Telnyx categories each matched 0. Raw messages were not saved.
- Source inspection: after each `wakeTick` finishes, the loop schedules its next start 60 seconds later; this is not a fixed start-to-start cadence. Only paid users with explicit `call_enabled=true`, a callable E.164 phone, and daily automation not explicitly opted out enter the call path. The fetch uses a six-hour future horizon; the dial requires a timed non-helper event and a due T-10/T-5 level. The current fetch-error catch returns silently, and the path does not record an eligible-event count. Therefore zero wake/miss records do not prove that there was no qualifying calendar event; they also cannot distinguish an empty/filtered result from a swallowed fetch error.
- The verifier did not query calendar content, initiate a voice call, or write to the database. It used read-only cost/wake GETs, Railway deployment/log reads, and local source inspection. The absence of a voice occurrence does not prove voice spend is zero.

## Result

A1 remains open. Preserve the A1→A10 order. The next production evidence is a natural voice occurrence followed by readback of its Gemini/Telnyx cost rows and provider outcome; do not create a test call or infer actual spend from estimated zeros.
