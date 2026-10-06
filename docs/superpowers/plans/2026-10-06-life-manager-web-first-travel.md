# Life Manager Web-First Travel Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` to execute the tasks in order. Keep one owner per worktree and lease. Do not modify production state from a feature worktree.

**Goal:** Let a customer use Life Manager from a browser, connect Google Calendar, enter a home location, and see the shared travel engine add a correctly timed Travel block without Telegram.

**Architecture:** Add a Supabase SSR PKCE web session beside the existing Telegram session. Derive each Web uid from the server-verified Supabase subject, then reuse `lm_users`, the existing Composio Calendar transport, `travelUserOnce`/`fillTravel`, and `lm_travel_log`; add only the Web OAuth state and onboarding RPC contracts the Telegram-bound contracts cannot serve.

**Tech Stack:** CommonJS Node.js HTTP server, `@supabase/ssr`, Supabase PostgREST/service-role RPCs, Composio Google Calendar, existing travel engine, Node test runner, Railway.

**Spec:** `docs/superpowers/specs/2026-10-06-life-manager-web-first-travel-design.md`

## Global Constraints

- Serve the Web product at Railway `LM_PANEL_BASE/lm`; keep one Life Manager service and one travel engine.
- A Web uid is `lm_` plus the verified Supabase Auth user UUID. Client uid/chat IDs and email matching never establish or link identity.
- If that exact uid already has a Telegram chat binding, preserve the row and refuse Web onboarding until a separate explicit link flow exists.
- Existing Telegram sessions, chat IDs, call consent, and Telegram onboarding continue to use their current contracts.
- Reuse `lm_users`, `lm_panel_preferences`, Composio, `travelUserOnce`/`fillTravel`, route cache, departure calculation, and `lm_travel_log` idempotency.
- Calendar reads and writes require an ACTIVE Composio account whose owner is the verified uid; multiple or mismatched accounts fail closed.
- Web Calendar status reports connected only for the persisted exact ACTIVE account. A user-initiated start may recover one unique exact-uid ACTIVE account after an interrupted callback. Exact MISSING/EXPIRED bindings stay actionable for reauthorization without enabling the stale account; network/provider ownership/ID ambiguity remains fail-closed.
- Before scheduled Web Calendar event access, re-read the current NULL-Telegram row and exact selected ACTIVE account; keep the Telegram scheduler path unchanged.
- Carry the account ID returned by that guard through snapshot reads and `fillTravel`; the Calendar adapter rechecks the current NULL-Telegram selected marker before every Composio operation and refuses a changed account rather than re-resolving to another ID.
- Home address, ACTIVE Calendar, and a successful server-owned setup transition are required before enabling daily travel automation or starting the existing three-day trial.
- Web setup sets `call_enabled=false` and `notifications_enabled=false`; `paid` remains writable only by the existing Stripe webhook.
- Departure remains event start minus accepted route duration minus one five-minute buffer. Calendar's existing default reminders remain in effect and must be described truthfully.
- A created Travel event sets `send_updates` to `none`, `exclude_organizer` to `true`, and `create_meeting_room` to `false`.
- Release a Travel claim only when no provider write was dispatched or the Composio endpoint explicitly rejects the HTTP request with 4xx. After dispatch, network/5xx/unreadable responses and 2xx `successful:false` outcomes keep the claim fenced pending strict readback.
- Resolve an unknown Calendar write only when one read-back event matches exact summary and `startMs`/`endMs`, plus destination after whitespace removal and lowercasing. Readback alone is not a create receipt and cannot label a helper `travel_added`.
- Display the appointment and departure in one effective zone: explicit appointment IANA zone, otherwise browser-local. The Travel helper's persisted UTC is not its display zone.
- Web pause/resume/disconnect use verified uid, exact Origin, JSON, and CSRF. Resume needs saved home and exact ACTIVE Calendar binding; a DB disconnect-pending fence blocks concurrent resume until exact DISABLED provider readback or a retry resolves it.
- Do not add Telegram, phone, Gmail, live location, staff management, or Web App Factory features to this MVP.
- Do not publish a price until the official Stripe catalog and actual cost inputs have been read back. Keep the factory unimplemented until at least 10 paying Web customers and three consecutive profitable months after refunds, Stripe fees, route/provider, hosting, and attributed marketing cost.

## Review Focus

- Supabase callback with missing, expired, or replayed PKCE state must create no user row or session; pin in Task 1's callback tests.
- Any body/query uid, chat ID, or paid value must be ignored; pin in Task 1 and Task 3's cross-tenant tests.
- A pre-existing `lm_users` row must keep its Telegram binding and billing fields during Web sign-in; pin in Task 1's insert-only identity test.
- A foreign, ambiguous, inactive, unpersisted, or rebound Composio account must never enable event access; pin Task 2/3 and OAuth/scheduler recovery in Task 6.
- Missing home/location, overlap/repeated sync, ambiguous GO/RETURN creation, missing/invalid display timezone, or failed Web control must preserve safe travel state and show an actionable result; pin Tasks 3 and 7–9.
- A Web UUID with NULL Telegram binding must not enter the legacy organ tick or trigger upcoming/history Calendar reads; scheduled Travel remains enabled through its exact-bound owner; pin Task 10.
- A failed or interrupted Calendar-enable claim must remain single-owner, release only after known no-effect or exact readback, and recover only after its lease plus an exact provider status; pin Task 11.

---

### Task 1: Server-verified Web sign-in

**Files:**
- Create: `apps/life-manager/lib/web-auth.js`
- Create: `apps/life-manager/lib/web-auth.test.js`
- Modify: `apps/life-manager/server.js`
- Modify: `apps/life-manager/package.json`
- Modify: `apps/life-manager/package-lock.json`

**Interfaces:**
- `createWebAuthClient(req, res, opts) -> SupabaseServerClient` uses `@supabase/ssr` with request-cookie `getAll` and response-cookie `setAll` adapters.
- `handleWebAuthRequest(req, res, opts) -> Promise<void>` owns `GET /auth/google` and `GET /auth/google/callback`; return paths are fixed to `/lm`.
- `resolveWebUser(req, res, opts) -> Promise<{ uid, subject, email, csrf } | null>` calls `auth.getUser()` on every protected request and derives `uid` only from `user.id`.
- `createWebCsrfToken(uid, secret) -> string` binds a CSRF token to the verified uid with HMAC-SHA256; mutating Web endpoints require exact `Origin`, JSON, and matching `x-lm-web-csrf`.
- `ensureWebUser(uid, opts) -> Promise<void>` inserts the uid into existing `lm_users` with conflict-ignore semantics and never overwrites a row; it rejects an existing Telegram-bound row and never links by email.

- [x] **Step 1: Add focused failing auth tests**

Create `web-auth.test.js` cases named `exchange requires PKCE verifier and verified Supabase subject`, `ignores client tenant fields and derives lm uid from subject`, and `refuses Web session for Telegram-bound uid without changing row`; assert existing `telegram_chat_id`, `paid`, and Stripe fields are byte-for-byte unchanged.

- [x] **Step 2: Run the auth tests and confirm the new handler contract is missing**

Run: `node --test lib/web-auth.test.js`
Expected: FAIL because the Web auth module and HTTP routes do not exist.

- [x] **Step 3: Add the SSR dependency and implement the Web auth handler**

Use the official `@supabase/ssr` server-cookie adapter and PKCE flow. Require `SUPABASE_URL` and the public `SUPABASE_ANON_KEY`; keep the service-role key server-only for the insert-only `lm_users` write. On callback, exchange the code, call `auth.getUser()`, derive `lm_<user.id>`, insert with `Prefer: resolution=ignore-duplicates`, and redirect only to `/lm`. Set no identity from query or body.

- [x] **Step 4: Wire the auth routes and rerun focused tests**

Route `/auth/google` and `/auth/google/callback` from `server.js` through `handleWebAuthRequest`. Re-run: `node --test lib/web-auth.test.js`.
Expected: PASS; no authenticated session or user row is issued before verified `getUser`, and existing Telegram/billing fields remain unchanged. The PKCE verifier cookie is expected before the callback.

- [x] **Step 5: Commit the auth boundary**

Commit the five listed files as `feat(life-manager): add verified web sign-in`.

### Task 2: Web-owned Google Calendar connection

**Files:**
- Create: `apps/life-manager/lib/web-calendar.js`
- Create: `apps/life-manager/lib/web-calendar.test.js`
- Create: `apps/life-manager/migrations/2026-10-06-lm-web-calendar-oauth.sql`
- Modify: `apps/life-manager/server.js`
- Reuse: `apps/life-manager/lib/user-command.js:startCalendarOAuth`
- Reuse: `apps/life-manager/lib/panel-api.js:composioCalendarStatus, composioCalendarAccountStatus, composioCalendarStart`

**Interfaces:**
- `handleWebCalendarRequest(req, res, opts) -> Promise<void>` owns `GET /api/lm-web/calendar/status`, `POST /api/lm-web/calendar/start`, and `GET /lm/oauth/calendar/callback`.
- Every request first calls `resolveWebUser`; the only provider scope is `{ uid: verifiedUid }`.
- Calendar status is read-only. Start accepts JSON plus exact origin/CSRF and returns `{ connected: false, state: "action_required", redirectUrl }`; the callback consumes OAuth state once and redirects to `/lm` after ACTIVE readback.
- Calendar start uses `startCalendarOAuth({ uid }, state, { calendarCallbackPath: "/lm/oauth/calendar/callback", ... })`; state values are hashed at rest.
- The migration allows `chat_id IS NULL` only for Web rows in existing `lm_panel_oauth_states`, adds a unique live Web state per uid, and adds service-role-only create/attach/claim RPCs. Existing Telegram RPC predicates and non-null Telegram state behavior remain unchanged.
- The callback claims the one-time state, verifies the exact Composio account is ACTIVE and owned by the claimed uid, then writes and reads back `calendar_provider` plus `calendar_connected_account_id` in `lm_users`.

- [x] **Step 1: Add provider/state failure tests**

Create `web-calendar.test.js` cases `calendar status requires one exact ACTIVE account for verified uid`, `web OAuth state is single-use and unique per uid`, and `callback rejects foreign or inactive connected account`; assert rejected states cause no Calendar event call or `lm_users` mutation.

- [x] **Step 2: Run the Calendar tests and confirm the contract is missing**

Run: `node --test lib/web-calendar.test.js`
Expected: FAIL because Web-scoped OAuth routes and state functions do not exist.

- [x] **Step 3: Add Web-only atomic OAuth state to the existing state store**

Create the nullable `chat_id` Web scope, unique live-state index, and three RPCs. Keep raw OAuth state out of the database. Preserve all existing Telegram state functions and add SQL contract coverage for both NULL Web scope and non-null Telegram scope.

- [x] **Step 4: Implement Web Calendar start, status, and callback**

Require exact `Origin`, JSON, and a Web CSRF token for `POST`. Reuse the existing Composio account/status functions and `startCalendarOAuth`; do not trust a client-selected uid/account. Save the selected account only after ACTIVE owner readback. On callback, consume state exactly once before provider readback.

- [x] **Step 5: Rerun focused Calendar tests and commit**

Run: `node --test lib/web-calendar.test.js`.
Expected: PASS, including Telegram/Web state separation. Commit the module, tests, migration, and server route as `feat(life-manager): connect web calendar accounts`.

### Task 3: Minimal setup and first shared travel sync

**Files:**
- Create: `apps/life-manager/lib/web-travel.js`
- Create: `apps/life-manager/lib/web-travel.test.js`
- Create: `apps/life-manager/migrations/2026-10-06-lm-web-travel-setup.sql`
- Modify: `apps/life-manager/lib/travel.js`
- Modify: `apps/life-manager/lib/travel.test.js`
- Modify: `apps/life-manager/server.js`

**Interfaces:**
- `handleWebTravelRequest(req, res, opts) -> Promise<void>` owns `POST /api/lm-web/setup` and `GET /api/lm-web/today`.
- `completeWebTravelSetup(uid, homeAddress, opts) -> Promise<{ trialExpiresAt }>` calls one service-role RPC that validates and stores the address, requires a Telegram-unbound row plus stored ACTIVE-connection markers, sets `trial_expires_at = coalesce(existing, now() + interval '3 days')`, and writes only Web preference values (`call_enabled=false`, `notifications_enabled=false`, `daily_automation_enabled=true`). It never accepts or updates `paid`.
- `buildTodaySnapshot(uid, opts) -> Promise<TodaySnapshot>` returns `{ setupState, calendarState, nextEvent, travelBlock, departureAt, trialExpiresAt, paid }`, where `setupState` is one of `needs_calendar | needs_home | sync_pending | ready`; event values are null until an ACTIVE account has been read.
- After setup commits and Calendar status is read back ACTIVE, call existing `travelUserOnce(user)` for the immediate sync. The same `lm_travel_log` unique `(uid,event_key,leg)` claim remains the only helper dedupe.
- Export `listEvents7d` from `travel.js` for the Web dashboard to read the same normalized Calendar event shape; do not duplicate its query or event interpretation.

- [x] **Step 1: Add failing setup/sync tests**

Create `web-travel.test.js` cases `setup stores home and starts one trial only for active unbound web user`, `ignores client uid and paid fields`, and `calendar readback must be ACTIVE before setup writes`; also pin missing-home/locationless-event state and repeat setup/scheduler execution to one trial and one helper. Keep existing overlapping/back-to-back decisions in `travel.test.js` and add only the missing replay assertion.

- [x] **Step 2: Run the setup tests and confirm the contract is missing**

Run: `node --test lib/web-travel.test.js`
Expected: FAIL because the Web setup/snapshot routes and RPC do not exist.

- [x] **Step 3: Add the atomic setup RPC and verified server handler**

Validate a trimmed home address of 1–240 characters. Require a fresh exact Calendar ACTIVE readback before the RPC. The RPC locks the `lm_users` row, requires `telegram_chat_id IS NULL`, `calendar_provider='composio_gcal'`, and a selected account ID; it writes `home_address`, starts the existing trial only once, and upserts Web preferences. Do not mutate Telegram stage, phone, chat ID, Stripe billing fields, or `paid`.

- [x] **Step 4: Connect the first sync to the existing travel owner**

Call `travelUserOnce` once after the committed setup transition. Return a truthful sync state; only report “Travel time added” after a fresh Calendar read contains the matching helper. A thrown, missing, or ambiguous provider read remains pending/error and never causes a second ad-hoc travel implementation.

- [x] **Step 5: Pin safe Calendar event defaults and export the existing event reader**

In `createTravelBlock`, pass `send_updates: "none"`, `exclude_organizer: true`, and `create_meeting_room: false`. Export `listEvents7d` and add focused assertions in `travel.test.js` that event creation keeps the existing single five-minute buffer while applying all three safe defaults.

- [x] **Step 6: Rerun focused tests and commit**

Run: `node --test lib/web-travel.test.js lib/travel.test.js`.
Expected: PASS; no Calendar effect is attempted before ACTIVE, and replay uses the existing unique travel claim. Commit the files as `feat(life-manager): onboard web travel users`.

### Task 4: Responsive `/lm` product screen

**Files:**
- Create: `apps/life-manager/lib/web-page.js`
- Create: `apps/life-manager/lib/web-page.test.js`
- Modify: `apps/life-manager/server.js`

**Interfaces:**
- `renderWebPage(model) -> string` renders only escaped server-owned data and includes a mobile-first Today view, Google sign-in, Calendar status, one home-location form, next physical event, Travel block/departure time, missing-location/setup states, and a plain explanation that Calendar default reminders apply.
- `GET /lm` uses `resolveWebUser`; anonymous users see Google sign-in, setup users see only the missing next step, and completed users see `GET /api/lm-web/today` data.
- The page's small inline script links to `/auth/google`; reads Calendar status; POSTs Calendar start and follows only the server-returned `redirectUrl`; POSTs the home address to `/api/lm-web/setup`; and refreshes `/api/lm-web/today`. It sends `x-lm-web-csrf` and never sends uid/chat ID/paid.
- The payment CTA uses existing `lib/payment-link.js:paymentLink(opts, { uid })`; display the current official Stripe terms only after catalog readback in the later launch task.

- [x] **Step 1: Add page rendering tests**

Create `web-page.test.js` cases `renders sign-in and each missing setup step`, `renders next event and verified Travel block`, `escapes event and address text`, and `payment link uses only verified uid`; assert the responsive layout includes a small-screen viewport and no Telegram setup prompt.

- [x] **Step 2: Run page tests and confirm the route does not exist**

Run: `node --test lib/web-page.test.js`
Expected: FAIL because no Web page renderer or `/lm` handler exists in the Railway server.

- [x] **Step 3: Implement the page and mount `/lm`**

Use existing Node server and minimal inline CSS/JS; no front-end framework or second site build. Keep static public marketing source and Telegram `/panel` separate. Map only normalized data from the server API into the page.

- [x] **Step 4: Rerun page tests and commit**

Run: `node --test lib/web-page.test.js`.
Expected: PASS with no client-supplied tenant identity and no false success copy. Commit as `feat(life-manager): serve web travel dashboard`.

### Task 5: First-touch attribution through Stripe checkout

**Files:**
- Create: `apps/life-manager/lib/web-attribution.js`
- Create: `apps/life-manager/lib/web-attribution.test.js`
- Create: `apps/life-manager/migrations/2026-10-06-lm-web-attribution.sql`
- Modify: `apps/life-manager/lib/web-auth.js`
- Modify: `apps/life-manager/lib/web-page.js`
- Reuse: `apps/life-manager/lib/payment-link.js` and `apps/life-manager/lib/billing.js`

**Interfaces:**
- `captureWebAttribution(query, secret, nowMs) -> signed first-touch cookie` accepts only bounded `utm_source`, `utm_medium`, `utm_campaign`, `utm_content`, and `utm_term` values.
- `consumeWebAttribution(cookie, secret, nowMs) -> attribution | null` verifies signature/expiry and stores first touch only once in a new nullable `lm_users.web_first_touch` JSONB field.
- Checkout uses `paymentLink({ stripePaymentLink }, { uid: verifiedUid })`, preserving the existing `client_reference_id` to `checkout.session.completed` → Stripe-only paid writer mapping.

- [x] **Step 1: Add attribution tests**

Create `web-attribution.test.js` cases `preserves signed first-touch through Google OAuth`, `rejects tampered or expired attribution`, `keeps first touch immutable`, and `checkout carries verified uid only`; assert unknown UTM keys and oversized values are discarded.

- [x] **Step 2: Run attribution tests and confirm the contract is missing**

Run: `node --test lib/web-attribution.test.js`
Expected: FAIL because Web signup currently drops source data.

- [x] **Step 3: Implement signed first-touch persistence and checkout linkage**

Add only a nullable `web_first_touch` field to the existing `lm_users` row. Sign attribution state with the server-only `LM_UID_SECRET`, set a secure same-site cookie, consume it after verified Google callback, and use existing Payment Link/webhook behavior. Do not create a second billing table or paid writer.

- [x] **Step 4: Rerun focused tests and commit**

Run: `node --test lib/web-attribution.test.js lib/payment-link.test.js lib/billing.test.js`.
Expected: PASS; Stripe remains the only paid-state authority. Commit as `feat(life-manager): retain web acquisition source`.

### Task 6: Recover Web Calendar binding and gate scheduled reads

**Files:**
- Modify: `apps/life-manager/lib/web-calendar.js` and `apps/life-manager/lib/web-calendar.test.js`
- Modify: `apps/life-manager/lib/web-travel.js` and `apps/life-manager/lib/web-travel.test.js`
- Modify: `apps/life-manager/scheduler.js` and `apps/life-manager/test/scheduler.test.js`
- Modify: `apps/life-manager/lib/travel.js` and `apps/life-manager/lib/travel.test.js`
- Modify: `apps/life-manager/lib/transport/index.js` and `apps/life-manager/lib/transport/calendar-composio.js`
- Modify: `apps/life-manager/lib/events-history.test.js` and `apps/life-manager/lib/calendar-cache.test.js`

**Interface:**
- `resolveActiveWebCalendar(uid, opts) -> Promise<{ accountId } | null>` re-reads the NULL-Telegram row, verifies its selected provider/account against exact-owner ACTIVE provider readback, then re-reads the unchanged marker before returning it.
- GET status reports connected only for that persisted exact ACTIVE binding. Exact MISSING/EXPIRED status reports action-required rather than stranding the user. POST start may recover one unique exact-uid ACTIVE account or begin OAuth for a stale binding, then reports connected only after provider verification plus marker persistence/readback. It never enables an expired, missing, or unknown selected account.
- `travelUserOnce` uses the Web-only guard before `fillTravel` for an `lm_<uuid>` row whose current Telegram binding is NULL; Telegram users retain their existing path.
- The `accountId` returned by the Web guard is passed as `expectedCalendarAccountId` to both `buildTodaySnapshot` event listing and `fillTravel`. `getCalendar` includes that expected ID in its cache identity, and each Composio event operation verifies the current row is still NULL-Telegram and selects the expected ID; mismatch fails before provider event access.

- [x] **Step 1: Add failing recovery and scheduler-boundary cases**

Cover `status is connected only for the persisted exact ACTIVE account`, `start recovers one ACTIVE account after callback binding was interrupted`, `expired or missing selected binding is actionable for reauthorization without enabling it`, `unknown/network provider status stays fail-closed`, `ambiguous ACTIVE accounts are not bound`, `Web scheduler pins fillTravel to the checked account ID`, `transport issues no Calendar event call after the selected marker changes`, `account-scoped calendar adapters do not share cache entries`, and `Telegram travel keeps its existing path`.

- [x] **Step 2: Run focused tests and confirm the new cases fail**

Run: `node --test lib/web-calendar.test.js lib/web-travel.test.js test/scheduler.test.js lib/travel.test.js lib/events-history.test.js lib/calendar-cache.test.js`.
Expected: the new recovery/gate assertions fail before implementation.

- [x] **Step 3: Reuse one exact-binding guard for status, recovery, and scheduled Web travel**

Keep GET status read-only. On explicit POST start, recover only a unique owner-verified ACTIVE account when the local marker is missing/stale; persist and read back the exact binding. Gate `fillTravel` immediately before Calendar access and carry the checked ID into the adapter; each event operation fails closed if the current row no longer selects it. Do not re-resolve to a different account mid-run or change Telegram selection/consent.

- [x] **Step 4: Rerun focused tests and commit**

Run: `node --test lib/web-calendar.test.js lib/web-travel.test.js test/scheduler.test.js lib/travel.test.js lib/events-history.test.js lib/calendar-cache.test.js`.
Expected: recovered exact accounts work; inactive, ambiguous, mismatched, Telegram-bound, or rebound rows issue no Web Calendar event call. Commit the scoped fix as `fix(life-manager): pin web calendar calls to checked account`.

### Task 7: Fence ambiguous Calendar create outcomes

**Files:**
- Modify: `apps/life-manager/lib/transport/calendar-composio.js`
- Modify: `apps/life-manager/lib/calendar-cache.js` and `apps/life-manager/lib/calendar-cache.test.js`
- Modify: `apps/life-manager/lib/travel.js` and `apps/life-manager/lib/travel.test.js`
- Modify: `apps/life-manager/lib/travel-return.test.js`
- Modify: `apps/life-manager/lib/events-history.test.js`
- Verify: `apps/life-manager/lib/travel-usage.test.js` preserves Composio outcome recording.

**Interface:**
- The travel caller can distinguish confirmed creation, definite no-effect rejection, and unknown effect. Only a rejection before provider dispatch (for example, missing credentials or account-marker mismatch) or an explicit Composio HTTP 4xx is definite no-effect. Network/5xx/unreadable responses and a 2xx `successful:false` action body remain unknown because the docs do not guarantee no side effect.
- `fillTravel` releases a GO/RETURN claim only on a definite no-effect rejection. For unknown outcomes it performs strict Calendar readback through Task 6's same expected account ID. Resolve only one event matching exact expected summary and `startMs`/`endMs`, plus destination after whitespace removal and lowercasing; no match, ambiguity, or failed readback keeps the claim fenced and prevents replay. Readback-only matches remain verified, never newly added.
- Preserve the existing `createEvent` call path through `makeCachedCalendar`; effect classification must not add an unwrapped second create method. Unknown attempts still invalidate that uid's cached event windows before strict reconciliation.
- Operation-level `expectedCalendarAccountId` must pass through the cache wrapper to Composio list/create/patch calls even when the adapter was built without a constructor pin; cache keys separate account IDs.

- [x] **Step 1: Add failing GO and RETURN claim-fence regressions**

Cover `keeps GO claim after an unknown create result`, `keeps RETURN claim after an unknown create result`, `2xx successful:false remains unknown`, `no-dispatch and Composio HTTP 4xx release only the unperformed claim`, `one exact readback match resolves to verified but not travel_added`, `summary/startMs/endMs/destination mismatch is not a match`, `unknown create invalidates cached events before strict readback`, `cached adapter forwards operation account pin to list/create`, `cache keys separate account IDs`, and `failed/empty/ambiguous readback never releases an unknown claim`.

- [x] **Step 2: Run focused travel tests and confirm the new cases fail**

Run: `node --test lib/travel.test.js lib/travel-return.test.js lib/events-history.test.js lib/travel-usage.test.js lib/calendar-cache.test.js`.
Expected: unknown create outcomes currently become `successful:false` and unclaim; new assertions fail.

- [x] **Step 3: Preserve effect uncertainty from Composio through both travel legs**

Keep confirmed success and definite-rejection behavior. Preserve uncertainty through the existing `createEvent` adapter and cache invalidation path, use the existing strict event reader for exact readback, and never delete the unique claim while the result remains unresolved. Preserve route-cost/allowance settlement semantics.

- [x] **Step 4: Rerun focused tests and commit**

Run: `node --test lib/travel.test.js lib/travel-return.test.js lib/events-history.test.js lib/travel-usage.test.js lib/calendar-cache.test.js`.
Expected: both legs remain fenced on unresolved effect, one exact readback stays verified rather than newly added, and no duplicate create is attempted. Commit as `fix(life-manager): retain claims for unknown calendar writes`.

### Task 8: Complete truthful Today display

**Files:**
- Modify: `apps/life-manager/lib/web-travel.js` and `apps/life-manager/lib/web-travel.test.js`
- Modify: `apps/life-manager/lib/web-page.js` and `apps/life-manager/lib/web-page.test.js`

**Interface:**
- `TodaySnapshot` adds `displayTimeZone` (the next event's validated IANA zone, otherwise null for browser-local formatting) and `missingLocationCount` (upcoming seven-day non-Travel events without a location).
- Appointment and departure use `displayTimeZone`; the helper's stored `timezone: "UTC"` is never used as the display zone. The departure card renders before the appointment card.
- A nonzero locationless count renders an actionable same-origin Today refresh button even if the next event itself already has a location.

- [x] **Step 1: Add failing display-zone, order, and location-count tests**

Cover an event with an explicit non-UTC timezone, an event without a timezone, a helper stored in UTC, departure-first markup, the exact upcoming seven-day count excluding past and Travel events, and a refresh button when a later event lacks a location but the next event has one.

- [x] **Step 2: Run focused page and snapshot tests and confirm the new cases fail**

Run: `node --test lib/web-travel.test.js lib/web-page.test.js`.
Expected: current rendering formats the helper in UTC, places appointment first, and exposes no count.

- [x] **Step 3: Add snapshot facts and use one effective display zone**

Use the normalized seven-day event list already fetched by the snapshot. Do not add another Calendar query or timezone field/table. When no valid event zone exists, leave formatting to the browser's local zone. Keep the count notice's refresh control visible when the next event is located.

- [x] **Step 4: Rerun focused tests and commit**

Run: `node --test lib/web-travel.test.js lib/web-page.test.js`.
Expected: event and departure times share the correct zone and the UI count/order match the spec. Commit as `fix(life-manager): render travel times in event timezone`.

### Task 9: Add Web travel pause, resume, and disconnect controls

**Files:**
- Create/rename: `apps/life-manager/migrations/2026-10-06-z-lm-web-travel-controls.sql` so its control and setup-fence functions apply after the initial Web setup migration.
- Modify: `apps/life-manager/lib/web-travel.js` and `apps/life-manager/lib/web-travel.test.js`
- Modify: `apps/life-manager/lib/web-page.js` and `apps/life-manager/lib/web-page.test.js`
- Modify: `apps/life-manager/lib/panel-api.js` and `apps/life-manager/lib/panel-api.test.js`
- Modify: `apps/life-manager/lib/web-calendar.js` and `apps/life-manager/lib/web-calendar.test.js`
- Modify: `apps/life-manager/scheduler.js` and `apps/life-manager/test/scheduler.test.js`
- Modify: `apps/life-manager/lib/runtime-preferences.js`
- Modify: `apps/life-manager/lib/transport/calendar-composio.js`; create `apps/life-manager/lib/transport/calendar-composio.test.js`
- Modify: `apps/life-manager/server.js`
- Reuse: `apps/life-manager/lib/panel-api.js:composioCalendarDisconnect`

**Interface:**
- `POST /api/lm-web/travel/control` accepts only `{ action: "pause" | "resume" | "disconnect" }`; uid and account ID come only from the verified Web user and current server row.
- Pause atomically sets `daily_automation_enabled=false` for a NULL-Telegram row. If setup has not created the preference row yet, seed safe defaults with `call_enabled=false`, `notifications_enabled=false`, `daily_automation_enabled=false`, and `web_calendar_disconnect_pending=false`, then apply the action-specific pending state in the same RPC; preserve all other fields on existing rows. Resume requires saved home plus exact selected ACTIVE account readback, then conditionally sets only `daily_automation_enabled=true` for that same account and reads back the preference.
- `TodaySnapshot` returns persisted `dailyAutomationEnabled` and `disconnectPending` even when Calendar event read fails, so controls do not vanish with an event-read error.
- Disconnect atomically sets automation false plus `calendar_disconnect_pending=true` before provider I/O; resume and setup refuse while pending. Setup preserves an existing pause, and the immediate travel run checks persisted automation/pending state before dispatch.
- Provider account mutations and readback must verify the exact selected account ID, Web owner, and Google Calendar toolkit before PATCH. `composioCalendarStart` rejects a GET whose returned ID differs from the requested ID before mutation. Web Calendar enable additionally requires the exact explicit disabled predicate (`sameDisabledCalendarAccount`) before enable PATCH; expired, missing, initiated, mismatched, or contradictory states remain uncertain and cause zero Web PATCH. `DISABLED` is returned only for explicit disabled readback. A Web disable with uncertain readback must not PATCH `enabled:true` as rollback; retain the pause, binding, and pending fence for retry. Telegram retains its existing status/rollback behavior.
- Calendar re-enable takes a durable `calendar_enable_pending` claim under the same NULL-Telegram user row lock used by disconnect. Disconnect begin refuses while enable is claimed; enable finish releases the claim only after exact ACTIVE readback. Calendar start and OAuth callback/recovery binding writes use SQL RPCs that lock the same row and refuse an in-progress disconnect.
- `travelUserOnce` re-reads exact Web automation and pending flags after the provider ACTIVE await; the Calendar transport repeats the check before Web create/patch dispatch. The control-state reader uses the same Supabase config resolution as account binding on the production `getCalendar` path. Paused dashboard event reads continue to work.
- The page displays Pause or Resume from persisted preference state, blocks Resume while either Calendar operation is pending, and offers Disconnect/retry for the currently bound Calendar.

- [x] **Step 1: Add failing endpoint, migration-contract, and UI control tests**

Cover missing/wrong Origin and CSRF, forged uid/account fields, Telegram-bound uid, pause/disconnect/calendar-enable before a preference row exists, preservation of existing call/notification settings, resume without home/inactive account, concurrent resume during disconnect, provider enable claim excluding concurrent disconnect and second start, start/callback/binding blocked during disconnect pending, setup during pending disconnect, setup preserving an existing pause and not dispatching Travel after pause, scheduler owner recheck after ACTIVE await, transport create/patch fence after a pause through normal `getCalendar` config resolution, Calendar start returned-ID mismatch and EXPIRED/missing/contradictory status with zero PATCH, Web disconnect unknown readback with zero rollback-enable (including a delayed concurrent retry), exact disabled state/readback, persisted pause state after Calendar event-read failure, and button state/copy.

- [x] **Step 2: Run focused Web control tests and confirm the new cases fail**

Run: `node --test lib/panel-api.test.js lib/web-calendar.test.js lib/web-travel.test.js lib/web-page.test.js test/scheduler.test.js lib/transport/calendar-composio.test.js`.
Expected: the control route, atomic preference contract, and controls are absent.

- [x] **Step 3: Add the smallest Web-only preference RPC and route**

The SQL functions lock and recheck the NULL-Telegram user row and expected account marker before preference writes. `begin_lm_web_calendar_enable` and disconnect-begin are mutually exclusive durable claims; enable-finish clears only after exact ACTIVE provider readback. The binding RPC refuses both pending flags. The setup RPC shares the same lock order, rejects pending operations, and preserves an existing automation choice. Reuse `composioCalendarDisconnect`, adding exact provider-ID/status checks and a Web-only no-rollback option at its boundary; do not add a settings framework or change Telegram preference RPCs.

- [x] **Step 4: Wire controls into the existing page and rerun focused tests**

Run: `node --test lib/panel-api.test.js lib/web-calendar.test.js lib/web-travel.test.js lib/web-page.test.js test/scheduler.test.js lib/transport/calendar-composio.test.js`.
Expected: pause/resume/disconnect report only verified persisted state and all failures remain fail-closed. Commit as `feat(life-manager): add web travel controls`.

### Task 9 review follow-up: recover stale Calendar bindings

**Files:**
- Modify: `apps/life-manager/lib/panel-api.js` and `apps/life-manager/lib/panel-api.test.js`
- Modify: `apps/life-manager/lib/web-calendar.js` and `apps/life-manager/lib/web-calendar.test.js`
- Modify: `apps/life-manager/lib/web-travel.js`, `apps/life-manager/lib/web-travel.test.js`, `apps/life-manager/lib/web-page.js`, and `apps/life-manager/lib/web-page.test.js`

**Interface:**
- An exact selected account readback of `MISSING` or `EXPIRED` reports an actionable Calendar state. The user-initiated start may bind one unique exact-uid ACTIVE account or begin fresh OAuth; it never enables the stale account.
- Network/5xx failures, ownership or ID mismatch, and contradictory/unknown status remain unavailable and fail closed. Those outcomes never initiate OAuth, bind an account, or PATCH the provider.

- [x] **Step 5: Add failing expired/missing binding recovery cases**

Cover exact MISSING and EXPIRED status with actionable Today/Calendar UI, one exact ACTIVE account recovery, fresh OAuth when no ACTIVE account exists, zero stale-account enable PATCH, and unchanged fail-closed behavior for network/5xx/owner/ID/unknown-status failures. Exercise the real Composio status helper.

- [x] **Step 6: Run the focused suite and confirm the new cases fail**

Run: `node --test lib/panel-api.test.js lib/web-calendar.test.js lib/web-travel.test.js lib/web-page.test.js test/scheduler.test.js lib/transport/calendar-composio.test.js`.
Expected: current EXPIRED/404 readback aborts before the actionable recovery and status path.

- [x] **Step 7: Keep safe status resolution separate from enable permission**

Map only exact selected-account 404 to MISSING and exact EXPIRED provider state to EXPIRED. Allow those states to enter user-initiated recovery/OAuth without enabling the old account. Preserve no-effect behavior for unknown, ownership, account-ID, and network failures.

- [x] **Step 8: Rerun focused tests and commit**

Run the same focused suite. Expected: stale accounts offer a usable reauthorization path, unknown outcomes remain fenced, and no stale account is re-enabled.

### Task 10: Keep Web-only tenants out of legacy organ Calendar reads

**Files:**
- Modify: `apps/life-manager/scheduler.js`
- Modify: `apps/life-manager/test/scheduler.test.js`

**Interface:**
- `organsUserOnce` returns before cache/provider reads and non-Travel organ work when `uid` matches the Web UUID form and `telegram_chat_id === null`. `travelTick` remains the sole scheduled Calendar consumer for those Web-only rows; Telegram-bound users keep current organ behavior.

- [x] **Step 1: Add the failing Web-only scheduler regression**

Cover a Web UUID with NULL Telegram binding and enabled daily automation: `organsUserOnce` must make zero `fetchUpcomingEvents` calls and zero care-organ calls. Also cover a Telegram-bound user to prove its legacy organ path still runs.

- [x] **Step 2: Run the scheduler test and confirm it fails**

Run: `node --test test/scheduler.test.js`.
Expected: the Web-only fixture reaches the upcoming-event reader and non-Travel organ path.

- [x] **Step 3: Skip Web-only rows at the organ owner boundary**

Add the exact Web UUID plus NULL-Telegram guard at the start of `organsUserOnce`. Do not disable `travelTick` or add another Calendar adapter.

- [x] **Step 4: Rerun the scheduler test and commit**

Run: `node --test test/scheduler.test.js`.
Expected: Web-only Calendar/organ calls are zero, and Telegram-bound behavior passes. Commit as `fix(life-manager): keep web tenants in travel scheduler only`.

### Task 11: Recover Web Calendar-enable claims safely

**Files:**
- Modify: `apps/life-manager/migrations/2026-10-06-z-lm-web-travel-controls.sql`
- Modify: `apps/life-manager/lib/runtime-preferences.js` and `apps/life-manager/lib/runtime-preferences.test.js`
- Modify: `apps/life-manager/lib/panel-api.js` and `apps/life-manager/lib/panel-api.test.js`
- Modify: `apps/life-manager/lib/web-calendar.js` and `apps/life-manager/lib/web-calendar.test.js`

**Interface:**
- Store a server-generated `calendar_enable_claim_id` UUID and database `calendar_enable_claimed_at` on the exact Web `lm_users` row. `begin_lm_web_calendar_enable(p_uid text, p_calendar_account_id text, p_claim_id uuid) -> boolean`, `recover_lm_web_calendar_enable(p_uid text, p_calendar_account_id text, p_expected_claim_id uuid, p_new_claim_id uuid) -> boolean`, and `finish_lm_web_calendar_enable(p_uid text, p_calendar_account_id text, p_claim_id uuid) -> boolean` set/rotate/clear only the matching owner claim. `readWebTravelControlState` returns the internal `enableClaimId` and `enableClaimedAt`; neither value is sent to the browser.
- A claim is recoverable after 120 seconds. Each Composio enable GET/PATCH/status read is bounded to 20 seconds. Before the lease expires, an exact DISABLED read remains pending and sends no PATCH. After expiry, exact ACTIVE finishes the old claim, exact DISABLED rotates the UUID atomically before one retry, and exact MISSING/EXPIRED clears only the stale claim before existing active-account recovery/new OAuth. Unknown states remain fenced.
- A failure before provider enable PATCH is known no-effect and releases only the current matching claim without changing the saved daily-automation preference. Pending transports are fenced, and the still-DISABLED account remains blocked by the scheduled owner's exact ACTIVE gate. A PATCH timeout, network/5xx, or post-dispatch readback failure remains unknown and retains the claim. A previous owner cannot finish or clear a rotated claim.

- [ ] **Step 1: Add failing claim-ownership and recovery tests**

Cover token-scoped begin/finish, pre-PATCH no-effect release without changing saved daily automation, post-PATCH unknown retention, non-expired DISABLED refusal, expired DISABLED one-winner rotation, exact ACTIVE finish, expired MISSING/EXPIRED reauthorization, old-token rejection, and two concurrent recovery requests with only one provider enable. Pin the 20-second provider timeout and 120-second SQL lease in focused contracts.

- [ ] **Step 2: Run the focused Calendar and state tests and confirm they fail**

Run: `node --test lib/runtime-preferences.test.js lib/panel-api.test.js lib/web-calendar.test.js`.
Expected: current boolean-only claim cannot identify an owner or reclaim a crashed operation.

- [ ] **Step 3: Add the smallest token-owned claim lease**

Extend the existing claim columns/RPCs, read internal claim metadata, bound the exact Composio enable requests, and change `startCalendar` to recover only from exact provider readback and token-checked SQL transitions. Keep Calendar operations fenced and leave the saved daily-automation preference unchanged.

- [ ] **Step 4: Rerun the focused Calendar and state tests and commit**

Run: `node --test lib/runtime-preferences.test.js lib/panel-api.test.js lib/web-calendar.test.js`.
Expected: confirmed ACTIVE completes, exact DISABLED has one leased owner, definite no-effect is retryable, and uncertain provider outcomes stay fenced. Commit as `fix(life-manager): recover stale calendar enable claims`.

## Required continuation after the source implementation

The main goal remains active after this source plan. Continue the existing SSOT cursor through these real-world steps; none is proven by source tests or merge alone:

1. Complete Task 10 then Task 11, and run their focused tests plus the full Web travel focused suite.
2. Open the PR, pass CI, merge to latest `main`, cut the immutable Railway release, and read back the deployed SHA and `LM_PANEL_BASE/lm` response.
3. Read back Supabase Google provider/callback configuration, Composio Calendar ACTIVE account, home setup, first Travel event ID, Calendar readback, and duplicate-zero for one natural Web signup. Keep each provider receipt separate.
4. Inspect the authoritative public `aniccaai.com/lm` owner and route; point its CTA and all campaign links to the verified Railway `/lm` origin without changing the archived test copy as if it were production.
5. Read back the live Stripe catalog/subscribers and same-period route, provider, hosting, refund, fee, and marketing costs. Research current successful travel/calendar apps and profitable narrow SaaS offers from primary/current sources before selecting or publishing a price.
6. Restart acquisition on Instagram and X and publish high-intent SEO articles. Carry UTM attribution into the verified signup, Stripe checkout, subscription receipt, and contribution report. Publish only product claims supported by the live UX.
7. Prove at least 10 paying Web customers and three consecutive months of positive contribution after refunds, Stripe fees, route/provider, hosting, and attributed marketing spend.
8. Only after that exact gate, write a separate Web App Factory design and implementation plan that reuses the mobile loop, shared marketing evidence, and reviewed Self-Build boundary; build and measure one Web product at a time.
9. After the factory gate is complete, resume the prior §84-A cursor at PromptBase P5c.
