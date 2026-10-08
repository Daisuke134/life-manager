# Life Manager Cloud On-Time Core Implementation Plan

> **Required subskill:** Execute this plan with `superpowers:subagent-driven-development`, one task at a time. Production changes use test-driven development; every task receives a fresh read-only review before the next task.

**Goal:** Make cloud Life Manager call consenting users at T-10/T-5, send a safe event-and-transit Telegram reminder at T-5, preserve travel-block autofill, and onboard each QR-scanned Telegram user without Google/Supabase browser sign-in.

**Architecture:** Google Calendar remains the schedule source. `travel.js` requests an event-anchored Transit itinerary and persists the existing travel block/ledger. The scheduler runs calling and Telegram reminder organs independently. Telegram `initData` establishes tenant identity for a server-owned onboarding state machine; Composio remains the Google Calendar consent boundary and Stripe remains the only payment authority.

**Tech stack:** Node.js 22, built-in `node:test`, Express, Telegram Bot API, Transit API `/plan`, Google Directions fallback, Composio, Stripe, existing PostgreSQL/Supabase adapters.

**Design spec:** `docs/superpowers/specs/2026-08-26-life-manager-cloud-on-time-core-design.md`

**Product UX:** `docs/superpowers/specs/2026-08-28-life-manager-cloud-telegram-product-ux-design.md`

## Global invariants

- Do not alter `deploy/local`, add a database, service, package, or authentication provider.
- Calls require `call_enabled === true`. Dais receives all-event calls; other tenants explicitly opt in.
- Physical-event reminder time is computed departure T-5; non-travel reminder time is event-start T-5.
- Transit requests include the event date, clock time, correct `arrival`/`departure` anchor, and `numItineraries=3`.
- A valid Transit result causes zero Google calls. An unusable/error result causes at most one sequential Google fallback.
- Platform, exit, carriage, congestion and accessibility facts are nullable. Never infer or fabricate them.
- Telegram reminder dedupe reuses `lm_travel_log` with leg `telegram-t5`; failed sends release the claim.
- Escape event/provider text before Telegram HTML. Never put tokens, phone numbers, home addresses, OAuth URLs, or live coordinates in ordinary logs.
- Telegram session identity is authoritative. Ignore client-supplied `uid`, `tg`, `telegram_id`, localStorage identity, and query-string identity.
- Phone collection never enables calling. Only explicit call consent does.
- The only paid-state writer is the verified Stripe webhook.
- The server grants one three-day trial after Calendar, home, and notifications are ready. Reopening onboarding never extends it.
- Do not add OpenClawMU, Hermes, a conversational runtime, or local-product parity before this on-time core has provider receipts and replay-zero.
- Baseline before implementation: focused suite 175/175 passing.

## File map

| Area | Production | Tests |
|---|---|---|
| Structured itinerary | `apps/life-manager/lib/transit.js` | `apps/life-manager/lib/transit.test.js` |
| Provider wiring/cache | `apps/life-manager/lib/travel.js`, `route-cache.js` | `travel-transit-wire.test.js`, `route-cache.test.js` |
| T-5 reminder | `apps/life-manager/lib/travel-reminder.js`, `travel.js` | `travel-reminder.test.js` |
| Scheduler isolation | `apps/life-manager/lib/scheduler.js` | `test/wake-loop-isolation.test.js` |
| Telegram onboarding entry | `apps/life-manager/lib/telegram.js` | `telegram-onboard.test.js`, `panel-auth.test.js` |
| Calendar consent | `apps/life-manager/lib/calendar-onboard.js`, `server.js` | `calendar-onboard.test.js` |
| Onboarding state/UI | `apps/life-manager/lib/panel-api.js`, panel assets | `panel-api.test.js`, `panel-ui.test.js` |
| Legacy authority retirement | `apps/landing/src/app/lm/LmClient.tsx`, server routes | existing contract/billing tests |

---

## Task 1: Parse a truthful structured Transit itinerary

**Files:** Modify `lib/transit.js`, `lib/transit.test.js`.

1. Add failing fixtures for overnight `arrival` selection, `departure` selection, rail/bus/walk leg fields, fare, and absent platform/exit facts.
2. Run `node --test lib/transit.test.js`; confirm the new assertions fail for missing behavior.
3. Add `parseTransitPlan(plan, { anchorType, anchorSecs })` while keeping the existing duration adapter compatible.
4. Select the latest viable departure for arrival-anchored requests and earliest viable arrival for departure-anchored requests. Normalize times beyond 24:00.
5. Return only provider-backed fields: departure/arrival, duration, transfers, fare, route/headsign, stop names, platform when present, and walking legs. Unknowns remain `null`/absent.
6. Run the test, mutate one expected platform/route value to prove the assertion fails, restore it, rerun green.
7. Commit: `feat(life-manager): parse structured transit itineraries`.

## Task 2: Anchor provider queries to the calendar event and scope cache keys

**Files:** Modify `lib/travel.js`, `lib/travel-transit-wire.test.js`, `lib/route-cache.js`, `lib/route-cache.test.js`.

1. Write failing tests that inspect the Transit URL for `date=YYYYMMDD`, `time=HH:MM`, `type=arrival|departure`, `numItineraries=3`, and timezone-correct values.
2. Add tests proving accepted Transit makes zero Google calls, failure/unusable output makes exactly one Google call, and cache keys differ by provider, endpoints, mode, anchor type, and time bucket.
3. Run the two tests and record RED.
4. Introduce a structured `directionsRoute(...)`; retain `directionsMinutes(...)` as a thin compatibility adapter.
5. Thread the calendar event anchor through the Transit request and sequential fallback. Remove the shared unscoped cache key.
6. Run both tests, then Task 1 tests; mutation-check the request type and fallback count.
7. Commit: `feat(life-manager): anchor transit routes to events`.

## Task 3: Build the claimed T-5 Telegram reminder organ

**Files:** Create `lib/travel-reminder.js`, `lib/travel-reminder.test.js`; modify `lib/travel.js` exports only as required.

1. Write failing tests for physical-event computed-departure T-5, non-travel start T-5, due-window/catch-up boundaries, and no early send.
2. Test origin precedence: a user-shared Telegram live fix observed within 120 seconds and not expired, previous event location, configured home. Stale, future-dated, expired, or out-of-range fixes fall back and their exact stored row is conditionally cleared. Future Travel blocks never use today's live fix. If no origin exists, format an event-only reminder without inventing a route.
3. Test the exact Japanese message structure: next event, leave/start time, ordered legs, transfers, fare, and optional facts only when provider-supplied.
4. Test HTML escaping, `telegram-t5` claim-before-send, duplicate suppression, and claim release after send failure.
5. Run `node --test lib/travel-reminder.test.js`; confirm module/behavior RED.
6. Implement the smallest pure due/format helpers and one claimed send function using existing `claimTravel`/`unclaimTravel`.
7. Run green and mutation-check escaping and failed-send release.
8. Commit: `feat(life-manager): send claimed t5 travel reminders`.

## Task 4: Isolate calls and Telegram reminders in the scheduler

**Files:** Modify `lib/scheduler.js`, `test/wake-loop-isolation.test.js`.

1. Add failing tests proving a reminder failure does not suppress a due call and a call failure does not suppress a due reminder.
2. Prove `call_enabled !== true` produces no call but can still produce a notification; disabled Telegram notifications produce neither Telegram send nor leaked event data.
3. Wire the reminder organ after event/travel calculation with its own error boundary. Keep T-10/T-5 call levels unchanged.
4. Run scheduler, wake-level, catch-up, claim-token, and reminder tests; mutation-check each isolation boundary.
5. Commit: `feat(life-manager): isolate call and reminder organs`.

## Task 5: Make `/start` open a Telegram-authenticated onboarding page

**Files:** Modify `lib/telegram.js`, `lib/telegram-onboard.test.js`, `lib/panel-auth.test.js`.

1. Add failing tests that `/start` returns a `web_app` button to configured HTTPS `/panel/onboarding`, contains no user ID/token, and preserves the existing authorized panel session flow.
2. Implement the button using the configured public Railway origin. Keep the QR deep link unchanged.
3. Reject non-HTTPS production origins and invalid Telegram `initData`; never fall back to query identity.
4. Run both tests and mutation-check removal of `initData` verification.
5. Commit: `feat(life-manager): open authenticated telegram onboarding`.

## Task 6: Add session-scoped Calendar consent

**Files:** Create `lib/calendar-onboard.js`, `lib/calendar-onboard.test.js`; modify `lib/server.js`.

1. Write failing tests for session-derived uid, signed one-time nonce, Composio connect start, callback/status polling, ACTIVE-only success, replay/expiry rejection, and body/query uid being ignored.
2. Implement start/status routes as adapters around the existing Composio integration; do not add a second OAuth system.
3. Ensure redirect URLs and provider errors are returned only to the authenticated session and sanitized in logs.
4. Run new tests plus calendar signature/resume contract tests; mutation-check nonce replay and ACTIVE-only handling.
5. Commit: `feat(life-manager): add session scoped calendar consent`.

## Task 7: Implement server-owned onboarding state and mobile UI

**Files:** Modify `lib/panel-api.js`, `lib/panel-api.test.js`, panel UI assets, `lib/panel-ui.test.js`.

1. Add failing API tests for this fixed progression: Calendar → home → Telegram notifications → phone → explicit call consent → dashboard. Checkout remains reachable but is not an onboarding gate.
2. Test that server state resumes on another browser session for the same Telegram user, out-of-order writes are rejected, body uid is ignored, phone save leaves calls off, and unverified clients cannot set paid.
3. Add UI contract tests at 375px for one primary action, skippable optional phone/call, escaped copy, and no Google/Supabase login control. The ready screen shows the next event and server-owned trial deadline.
4. Implement the minimal state adapters using existing tenant/profile fields and existing panel auth; no new table or framework.
5. Run API/UI tests plus billing/auth tests; mutation-check phone→call and client→paid prohibitions.
6. Commit: `feat(life-manager): add telegram native onboarding state`.

## Task 8: Retire legacy browser identity and payment authority

**Files:** Modify the legacy LM server routes and `apps/landing/src/app/lm/LmClient.tsx`; update `test/onboarding-resume-contract.test.js`, `test/calendar-connect-signature-contract.test.js`, `lib/billing.test.js`.

1. Add failing contracts requiring legacy Google/Supabase exchange and raw Telegram-link endpoints to return `410 Gone` with no side effect.
2. Require the landing client to hand off to the Telegram WebApp route and contain no raw `tg`, localStorage identity, or client paid-state write.
3. Implement the retirement response and minimal handoff; preserve unrelated landing behavior.
4. Run all onboarding, panel, auth, and billing contracts; mutation-check one retired endpoint and the Stripe-only paid writer.
5. Commit: `refactor(life-manager): retire legacy onboarding authority`.

## Task 9: Full verification, deployment, and production acceptance

1. Run the focused regression set from the design spec and `npm test` in `apps/life-manager`. Any failure returns to the owning task.
2. Inspect `git diff --check`, secret scan of the branch diff, dependency/lockfile diff, and `git status`. No unintended package or local-runtime changes.
3. Run a fresh whole-branch read-only adversarial review against all 38 acceptance criteria; resolve every critical/high finding and rerun affected tests.
4. Fetch/rebase safely, push the branch, merge/deploy through the repository's existing production path, and read back the Railway deployment commit hash and health endpoint.
5. On a controlled Dais calendar event, verify official effects: travel block created/updated, T-10 call, T-5 call, one T-5 Telegram message, correct event-anchored itinerary, and no duplicate on replay.
6. On a separate test Telegram identity from the QR, verify session separation and complete onboarding without Google/Supabase browser login. Optional call remains off until consent; Stripe webhook alone changes paid state.
7. Re-run the scheduler after the event and verify replay-zero from durable ledgers/provider readback.
8. Mark every acceptance criterion and atomic task in the design spec complete only from observed evidence; leave any unavailable external observation explicitly open.

## Operational Task 0: Restore calling credit

This runs alongside code tasks but closes before production call acceptance:

1. Authenticate to Telnyx using the private credential SSOT and existing session. Never use recovery/reset.
2. Read the official portal balance and minimum permitted top-up. Do not infer balance from a low-credit error.
3. Before the irreversible charge, show the exact amount/currency/payment source and obtain the required approval if not already explicit for that exact charge.
4. Add only the minimum amount, save the official receipt privately, read back the new balance, and place one controlled call through the real runtime.

## Remaining execution

Tasks 1–11 above are the implemented baseline. The sole active checklist is:

→ `docs/superpowers/plans/2026-08-28-life-manager-cloud-on-time-core-finish.md`
