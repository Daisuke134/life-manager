# Life Manager Web-First Travel Product

## Goal

Let a new Life Manager customer use the hosted product from a browser without installing Telegram. Life Manager connects Google Calendar, inserts a travel block before a physical appointment, and makes the actual departure time visible before the user's usual event reminder would be too late.

The Web App Factory is a later phase. It starts only after this product has paid users and verified positive contribution; the first app's acquisition and cost evidence then becomes the factory's first reusable lesson.

## Superseded Contract

The approved 2026-08-26 Cloud On-Time Core contract made a verified Telegram actor the only tenant identity and retired the standalone browser onboarding flow. Dais's current explicit Web-first instruction supersedes that interface and identity choice for new Web users. It does not remove existing Telegram users, change their identity/session, enable phone calls, or weaken the existing Stripe-only paid-state writer.

The new Web identity is a verified Supabase Auth Google user. The Railway server uses Supabase SSR PKCE cookies and calls auth.getUser before accepting a user-scoped request. It derives uid as lm_ plus the verified Supabase user UUID. Client query/body identity, localStorage uid/sig, and Telegram chat IDs never establish Web tenant identity.

## Product Flow

1. The visitor opens the hosted Railway /lm route and chooses Continue with Google.
2. Supabase Auth verifies the Google identity and returns to the server-owned callback. The server resumes or creates the corresponding existing lm_users row.
3. The user explicitly grants Google Calendar access through the existing Composio-managed Calendar connection. The page shows connected only after the selected account is read back as ACTIVE and bound to the same uid.
4. The user enters one usual starting location. Calendar, home location, and first sync are the only required setup steps. Phone, calls, Telegram, Gmail, live location, and staff are not required.
5. The existing travel owner runs for this uid. It uses the shared route calculation and durable lm_travel_log claim; the page shows the next appointment, route duration, travel block, and computed departure time.
6. Web users have calls disabled and no Telegram delivery. A Calendar Travel event uses the user's Google Calendar default reminder settings. The UI states this dependency and never claims that Life Manager has changed the user's device-notification settings.

## Shared Implementation and Tenant State

- Keep one Life Manager product and the existing Railway service. Serve the Web app at LM_PANEL_BASE/lm; do not create a second scheduler or a copy of travel logic.
- Reuse lm_users, lm_panel_preferences, the Composio calendar transport, travelUserOnce/fillTravel, route caching, departure calculation, and lm_travel_log idempotency.
- Web-created lm_users rows may have telegram_chat_id null. The existing travel loop already skips Telegram reports when no chat ID exists. Web onboarding explicitly stores call_enabled=false and notifications_enabled=false; Calendar's own event reminder is independent of the Telegram notification switch.
- Set daily_automation_enabled=true only after Calendar is ACTIVE and a valid home address is stored. Start the existing 3-day trial once at that server-owned transition; the browser cannot set trial or paid. Stripe webhook remains the only writer of lm_users.paid.
- Do not auto-link a Google account to a Telegram tenant by matching an unverified email. Existing Telegram accounts keep their current session and records; a future explicit link flow can be added from measured user need.
- Calendar account writes remain user-scoped by uid and selected connected_account_id. OAuth status must be ACTIVE before Calendar reads or writes begin.
- Web status reports connected only when the exact selected account is ACTIVE and its provider/account markers are persisted and read back on the Telegram-unbound `lm_users` row. If a callback consumed OAuth state before marker persistence, a user-initiated Calendar start may recover only one exact-uid ACTIVE account and must persist/read it back before reporting connected.
- Before scheduled Calendar event access for a Web uid, re-read the current user row, require `telegram_chat_id IS NULL`, and verify that the exact selected account is still ACTIVE. Preserve the existing Telegram scheduler path.
- Carry that verified account ID through the Web travel run. Each Calendar transport call must reject if the current NULL-Telegram row no longer selects that exact ID; it must never silently switch to another account mid-run.

## Travel Calendar Effect

- The departure calculation remains event start minus accepted route duration minus the existing single 5-minute buffer.
- The Travel helper starts at the calculated departure instant and uses the user's default Calendar reminders. Google Calendar's API inherits the calendar's default reminders when an event does not override them. If readback shows that no reminder applies, the UI does not claim an alert is configured.
- Every created Travel event explicitly sets send_updates=none, exclude_organizer=true, and create_meeting_room=false. The event has no attendees, no Meet link, and no invitation emails.
- Repeated onboarding or scheduler evaluation relies on the existing unique (uid,event_key,leg) claim. Release it only when no provider write was dispatched or the Composio endpoint explicitly rejects the HTTP request with 4xx; after dispatch, a network/5xx/unreadable response or a 2xx `successful:false` result is effect-unknown. Retain that claim and reconcile through strict Calendar readback. Resolve it only when exactly one event matches the expected summary exactly, `startMs`/`endMs` exactly, and destination after whitespace removal plus lowercasing; if the readback is missing, failed, or ambiguous, keep the claim fenced and do not replay. A readback proves the helper exists but is not a create receipt, so do not report `travel_added` without a confirmed create response.
- Missing event location or missing home location leaves that event unchanged and explains the missing input in the Web view. Web-only users receive no Telegram location question.

## Web Interface

- The route is server-rendered HTML/CSS using the existing raw Node service and the visual direction of the approved UX mock: departure time first, travel block and appointment beneath it, responsive at phone width.
- Display appointment and departure in the appointment's explicit IANA timezone; when it is absent, use the browser's local timezone. The helper's UTC storage timezone must not become the display timezone.
- Logged-out view has one Google sign-in action. Onboarding exposes Calendar connection and one home-location input. The signed-in view shows today's next departure, the associated appointment, travel duration, Calendar connection status, the count of locationless non-Travel events in the upcoming seven-day Calendar window, and pause/resume/disconnect actions.
- When the locationless count is nonzero, show an existing same-origin Today refresh action with the count notice, including when the next appointment itself already has a location.
- Pause changes only Web daily automation. Resume requires a saved home and the exact selected Calendar account to be ACTIVE. Disconnect atomically pauses automation and sets a Web-only disconnect-pending fence before provider I/O. Resume is rejected while that fence is set. Clear the exact local binding and fence only after exact-account DISABLED readback; failed/unknown outcomes keep automation paused, the binding intact, and expose a retry action.
- Do not add a chat interface, app-store client, employee/staff feature, background GPS, generic calendar replacement, or factory dashboard to the first version.
- Keep the old aniccaai.com marketing surface separate from the Railway product route. The production handoff must point to the exact verified Railway /lm origin; do not edit the archived anicca-products checkout to change this feature.

## Price, Marketing, and Profit

- Do not alter existing Stripe products or subscribers in the Web identity implementation. The current /lm page advertises $29/month and the repository billing design uses a 3-day trial. The direct category competitor Add Travel Time currently advertises $5/month, $36/year, and a 14-day no-card trial. Read back the actual Stripe catalog, active subscribers, and same-period provider costs before changing current terms.
- The competitor's $5/month and $36/year are a candidate price test for a narrower Travel-only plan, not a current Life Manager price. A new price may launch only after route, hosting, payment, refund, and marketing cost are bounded so a paid order cannot lose money.
- Refresh the offer and CTA for a direct Web signup. Use two Instagram demo Reels per week, three founder-led X posts per week, and two high-intent SEO articles per month for the first month. Every link carries source attribution into the Web signup and Stripe checkout.
- Reuse existing product marketing copy and the shared marketing engine's content-manifest idea. Do not activate its private Instagram automation route; actual account operation must use the registered CloakBrowser direct-CDP route.
- Profit is not MRR alone. It is settled subscription revenue less refunds, Stripe fees, route/provider cost, hosting, and attributed marketing spend over the same period. The repo's founder-attested historical revenue is not accepted as this product's profit proof.

## Factory Gate

Do not implement app-generation automation yet. Start a separate Web App Factory design only after Life Manager has at least 10 paying Web customers and three consecutive months of positive contribution with actual costs. Then reuse the mobile loop's product lifecycle, shared marketing evidence, and Life Manager's reviewed Self-Build promotion boundary. The factory must take customer and cost evidence as inputs and emit one independently measurable Web product at a time.

## Acceptance Criteria

1. A fresh browser opens the hosted Railway /lm route, signs in with Google, and resumes without Telegram.
2. The server verifies the Supabase user, derives uid from the verified subject, and refuses cross-tenant requests and client-supplied uid/chat_id/paid values.
3. Calendar connection is bound to that uid; persisted exact ACTIVE account readback precedes any event access, including scheduler runs. Interrupted callback completion can recover through a user-initiated start only when the exact-uid ACTIVE account is unique.
4. Home location is validated and saved. No phone, Telegram, Gmail, or call opt-in is required; Web user calls are off.
5. First setup runs the shared travel owner and creates at most one Travel helper for each eligible event. Departure time matches the shared calculation and one 5-minute buffer.
6. New Travel events send no attendee emails, add no organizer attendee, and request no Meet link. Calendar's default reminder behavior is read back and described truthfully.
7. The dashboard renders the departure first, then its appointment and Travel helper at mobile and desktop widths, using one correct display timezone; missing location and Calendar authorization are actionable, and locationless upcoming events are counted.
8. Pause/resume/disconnect controls use the verified Web identity and CSRF fence. Resume requires saved home plus exact ACTIVE Calendar binding; disconnect pauses, disables/read-backs that exact account, and clears its binding.
9. Repeat onboarding, OAuth callback, and scheduler replay produce no duplicate Calendar helper. Unknown create outcomes retain the claim and require strict readback before any resolution. Existing Telegram auth, call consent, and existing-user behavior pass their current contracts.
10. Stripe subscription changes are accepted only through the existing webhook. The public price and terms match the official Stripe catalog before launch.
11. Railway deploy SHA, fresh browser signup, Calendar ACTIVE account, created Travel event, replay-zero, Stripe invoice/renewal, and actual cost readback are reported separately.
12. The Web App Factory remains unimplemented until its paid-user and positive-contribution gate is met.

## Current External Documentation

- Supabase SSR PKCE, server cookies, and verified getUser: https://github.com/supabase/ssr/blob/main/README.md
- Composio Google Calendar account and event input contract: https://docs.composio.dev/toolkits/googlecalendar
- Composio tool execution response and error-code contract: https://docs.composio.dev/reference/errors and https://docs.composio.dev/reference/api-reference/tools/postToolsExecuteByToolSlug
- Google Calendar default reminders and overrides: https://developers.google.com/workspace/calendar/api/concepts/reminders
- Direct category pricing reference: https://www.addtraveltime.com/
