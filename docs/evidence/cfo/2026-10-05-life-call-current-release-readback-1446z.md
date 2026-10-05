# A1: `life-call` cumulative production readback (14:46 UTC)

Scope: Railway production `life-call`, the latest successful release, and read-only GETs against existing production cost/wake/cache tables. No UID, tenant ID, run/occurrence ID, route/cache key, phone number, calendar event content, or raw log message was selected or retained.

## Release

- Railway deployment list readback at `2026-10-05T14:46:22Z`: latest successful deployment remains `38b34ef2-4900-4ccc-83b8-f874bf88fac8`, source SHA `9e3fb448b6799e6f5183f087773fa245c8409778`, created `2026-10-05T12:34:01.656Z`. The latest main deployment for merge SHA `26f872118a1eba956a17d16af884bd330b2ac68b` was `SKIPPED` at `2026-10-05T14:45:47.428Z` (`No changes to watched files`).

## Cost ledger

- Read-only GET at `2026-10-05T14:46:22Z`, exact release SHA, half-open window `2026-10-05T12:34:01.656Z <= ts < 2026-10-05T14:46:22Z`: 143 rows, timestamp range `2026-10-05T12:36:13.084567Z`–`2026-10-05T14:45:21.611104Z`.
- All 143 rows contain owner, run, occurrence, and release SHA; all 143 lack `loop_id` and remain partial.

| Kind / provider / feature | Outcome | Rows | Row `est_usd` sum |
|---|---|---:|---:|
| `composio_call` / `GOOGLECALENDAR_EVENTS_LIST` | success | 88 | USD 0.000 |
| `provider_usage` / `route_cache` / `travel_route` | cache hit | 14 | USD 0.000 |
| `provider_usage` / `google_maps` / `directions` | failure | 36 | USD 0.180 |
| `provider_usage` / `google_maps` / `geocoding` | success | 5 | USD 0.025 |
| **Total** |  | **143** | **USD 0.205** |

- Compared with the previous fixed snapshot ending at `2026-10-05T14:29:44Z`, 25 rows were added: 13 Calendar list calls and 12 failed Directions calls, increasing the row-estimate total by USD 0.060. All 36 cumulative Directions failures have `failure_class=no_route`; this is an estimate, not actual spend, an invoice, or proof of free usage. Production actual/billing columns remain absent per the earlier schema probe.

## Cache evidence

- Read-only `lm_route_cache` GET for `2026-10-05T14:29:44Z <= computed_at < 14:46:22Z` returned 14 entries: 12 negative `no_route` entries with TTL 1,800 seconds and 2 successful entries with TTL 600 seconds. The count matches the 12 new Directions failure rows, but the returned aggregates do not join each failure to a specific route key.
- Focused local tests passed 39/39: `route-cache.test.js`, `travel-transit-wire.test.js`, and `travel-usage.test.js`. They verify repeated same-event ticks use the cache and deterministic failures suppress paid replay until negative TTL. This fixture/source evidence does not prove production event-level replay-zero.

## Wake and voice occurrence

- GETs bounded to the same release window returned 0 `lm_wake_log.called_at` rows and 0 `lm_wake_miss.occurred_at` rows. The cumulative cost ledger has 0 `gemini_live`, `telnyx_call`, or `feature=live_api` rows.
- Railway logs classified locally for `2026-10-05T14:29:44Z`–`14:46:22Z`: 732 lines; `voice reconciliation checked` matched 3. Wake placement, dial failure, missed wake, carrier connection, Gemini, and Telnyx categories each matched 0. Raw messages were not saved.
- Source inspection confirms wake evaluation schedules the next tick 60 seconds after the prior tick completes, and the call path has paid/opt-in/valid-phone plus timed-event T-10/T-5 gates. Candidate event counts are not logged and fetch exceptions return silently, so no call/miss record cannot distinguish no candidate from a filtered/empty result or fetch failure.
- The verifier did not query calendar content, initiate a voice call, or write to the database. It used read-only cost/wake/cache GETs, Railway deployment/log reads, local source inspection, and local tests. Absence of a voice occurrence does not prove voice spend is zero.

## Result

A1 remains open and A1→A10 order remains unchanged. Natural voice occurrence plus Gemini/Telnyx cost/provider readback is still unobserved. A3 remains open: focused tests and cache rows show functioning cache paths, but the aggregate production records do not establish event-level replay-zero, and geocode persistence is still incomplete.
