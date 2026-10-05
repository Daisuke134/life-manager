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
- Home address, ACTIVE Calendar, and a successful server-owned setup transition are required before enabling daily travel automation or starting the existing three-day trial.
- Web setup sets `call_enabled=false` and `notifications_enabled=false`; `paid` remains writable only by the existing Stripe webhook.
- Departure remains event start minus accepted route duration minus one five-minute buffer. Calendar's existing default reminders remain in effect and must be described truthfully.
- A created Travel event sets `send_updates` to `none`, `exclude_organizer` to `true`, and `create_meeting_room` to `false`.
- Do not add Telegram, phone, Gmail, live location, staff management, or Web App Factory features to this MVP.
- Do not publish a price until the official Stripe catalog and actual cost inputs have been read back. Keep the factory unimplemented until at least 10 paying Web customers and three consecutive profitable months after refunds, Stripe fees, route/provider, hosting, and attributed marketing cost.

## Review Focus

- Supabase callback with missing, expired, or replayed PKCE state must create no user row or session; pin in Task 1's callback tests.
- Any body/query uid, chat ID, or paid value must be ignored; pin in Task 1 and Task 3's cross-tenant tests.
- A pre-existing `lm_users` row must keep its Telegram binding and billing fields during Web sign-in; pin in Task 1's insert-only identity test.
- A Composio account owned by another uid, an ambiguous account list, or an inactive account must cause no Calendar event read/write, trial, or automation enablement; pin in Task 2's provider tests and Task 3's setup test.
- Missing home, an event without a physical location, an overlapping event, and repeated sync must preserve the current travel decision and create at most one helper; pin in Task 3 using the existing travel fixtures and claim contract.

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

- [ ] **Step 1: Add focused failing auth tests**

Create `web-auth.test.js` cases named `exchange requires PKCE verifier and verified Supabase subject`, `ignores client tenant fields and derives lm uid from subject`, and `refuses Web session for Telegram-bound uid without changing row`; assert existing `telegram_chat_id`, `paid`, and Stripe fields are byte-for-byte unchanged.

- [ ] **Step 2: Run the auth tests and confirm the new handler contract is missing**

Run: `node --test lib/web-auth.test.js`
Expected: FAIL because the Web auth module and HTTP routes do not exist.

- [ ] **Step 3: Add the SSR dependency and implement the Web auth handler**

Use the official `@supabase/ssr` server-cookie adapter and PKCE flow. Require `SUPABASE_URL` and the public `SUPABASE_ANON_KEY`; keep the service-role key server-only for the insert-only `lm_users` write. On callback, exchange the code, call `auth.getUser()`, derive `lm_<user.id>`, insert with `Prefer: resolution=ignore-duplicates`, and redirect only to `/lm`. Set no identity from query or body.

- [ ] **Step 4: Wire the auth routes and rerun focused tests**

Route `/auth/google` and `/auth/google/callback` from `server.js` through `handleWebAuthRequest`. Re-run: `node --test lib/web-auth.test.js`.
Expected: PASS; no authenticated session or user row is issued before verified `getUser`, and existing Telegram/billing fields remain unchanged. The PKCE verifier cookie is expected before the callback.

- [ ] **Step 5: Commit the auth boundary**

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

- [ ] **Step 1: Add provider/state failure tests**

Create `web-calendar.test.js` cases `calendar status requires one exact ACTIVE account for verified uid`, `web OAuth state is single-use and unique per uid`, and `callback rejects foreign or inactive connected account`; assert rejected states cause no Calendar event call or `lm_users` mutation.

- [ ] **Step 2: Run the Calendar tests and confirm the contract is missing**

Run: `node --test lib/web-calendar.test.js`
Expected: FAIL because Web-scoped OAuth routes and state functions do not exist.

- [ ] **Step 3: Add Web-only atomic OAuth state to the existing state store**

Create the nullable `chat_id` Web scope, unique live-state index, and three RPCs. Keep raw OAuth state out of the database. Preserve all existing Telegram state functions and add SQL contract coverage for both NULL Web scope and non-null Telegram scope.

- [ ] **Step 4: Implement Web Calendar start, status, and callback**

Require exact `Origin`, JSON, and a Web CSRF token for `POST`. Reuse the existing Composio account/status functions and `startCalendarOAuth`; do not trust a client-selected uid/account. Save the selected account only after ACTIVE owner readback. On callback, consume state exactly once before provider readback.

- [ ] **Step 5: Rerun focused Calendar tests and commit**

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

- [ ] **Step 1: Add failing setup/sync tests**

Create `web-travel.test.js` cases `setup stores home and starts one trial only for active unbound web user`, `ignores client uid and paid fields`, and `calendar readback must be ACTIVE before setup writes`; also pin missing-home/locationless-event state and repeat setup/scheduler execution to one trial and one helper. Keep existing overlapping/back-to-back decisions in `travel.test.js` and add only the missing replay assertion.

- [ ] **Step 2: Run the setup tests and confirm the contract is missing**

Run: `node --test lib/web-travel.test.js`
Expected: FAIL because the Web setup/snapshot routes and RPC do not exist.

- [ ] **Step 3: Add the atomic setup RPC and verified server handler**

Validate a trimmed home address of 1–240 characters. Require a fresh exact Calendar ACTIVE readback before the RPC. The RPC locks the `lm_users` row, requires `telegram_chat_id IS NULL`, `calendar_provider='composio_gcal'`, and a selected account ID; it writes `home_address`, starts the existing trial only once, and upserts Web preferences. Do not mutate Telegram stage, phone, chat ID, Stripe billing fields, or `paid`.

- [ ] **Step 4: Connect the first sync to the existing travel owner**

Call `travelUserOnce` once after the committed setup transition. Return a truthful sync state; only report “Travel time added” after a fresh Calendar read contains the matching helper. A thrown, missing, or ambiguous provider read remains pending/error and never causes a second ad-hoc travel implementation.

- [ ] **Step 5: Pin safe Calendar event defaults and export the existing event reader**

In `createTravelBlock`, pass `send_updates: "none"`, `exclude_organizer: true`, and `create_meeting_room: false`. Export `listEvents7d` and add focused assertions in `travel.test.js` that event creation keeps the existing single five-minute buffer while applying all three safe defaults.

- [ ] **Step 6: Rerun focused tests and commit**

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

- [ ] **Step 1: Add page rendering tests**

Create `web-page.test.js` cases `renders sign-in and each missing setup step`, `renders next event and verified Travel block`, `escapes event and address text`, and `payment link uses only verified uid`; assert the responsive layout includes a small-screen viewport and no Telegram setup prompt.

- [ ] **Step 2: Run page tests and confirm the route does not exist**

Run: `node --test lib/web-page.test.js`
Expected: FAIL because no Web page renderer or `/lm` handler exists in the Railway server.

- [ ] **Step 3: Implement the page and mount `/lm`**

Use existing Node server and minimal inline CSS/JS; no front-end framework or second site build. Keep static public marketing source and Telegram `/panel` separate. Map only normalized data from the server API into the page.

- [ ] **Step 4: Rerun page tests and commit**

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

- [ ] **Step 1: Add attribution tests**

Create `web-attribution.test.js` cases `preserves signed first-touch through Google OAuth`, `rejects tampered or expired attribution`, `keeps first touch immutable`, and `checkout carries verified uid only`; assert unknown UTM keys and oversized values are discarded.

- [ ] **Step 2: Run attribution tests and confirm the contract is missing**

Run: `node --test lib/web-attribution.test.js`
Expected: FAIL because Web signup currently drops source data.

- [ ] **Step 3: Implement signed first-touch persistence and checkout linkage**

Add only a nullable `web_first_touch` field to the existing `lm_users` row. Sign attribution state with the server-only `LM_UID_SECRET`, set a secure same-site cookie, consume it after verified Google callback, and use existing Payment Link/webhook behavior. Do not create a second billing table or paid writer.

- [ ] **Step 4: Rerun focused tests and commit**

Run: `node --test lib/web-attribution.test.js lib/payment-link.test.js lib/billing.test.js`.
Expected: PASS; Stripe remains the only paid-state authority. Commit as `feat(life-manager): retain web acquisition source`.

## Required continuation after the source implementation

The main goal remains active after this source plan. Continue the existing SSOT cursor through these real-world steps; none is proven by source tests or merge alone:

1. Pass current source acceptance and review, merge to latest `main`, cut the immutable Railway release, and read back the deployed SHA and `LM_PANEL_BASE/lm` response.
2. Read back Supabase Google provider/callback configuration, Composio Calendar ACTIVE account, home setup, first Travel event ID, Calendar readback, and duplicate-zero for one natural Web signup. Keep each provider receipt separate.
3. Inspect the authoritative public `aniccaai.com/lm` owner and route; point its CTA and all campaign links to the verified Railway `/lm` origin without changing the archived test copy as if it were production.
4. Read back the live Stripe catalog/subscribers and same-period route, provider, hosting, refund, fee, and marketing costs. Research current successful travel/calendar apps and profitable narrow SaaS offers from primary/current sources before selecting or publishing a price.
5. Restart acquisition on Instagram and X and publish high-intent SEO articles. Carry UTM attribution into the verified signup, Stripe checkout, subscription receipt, and contribution report. Publish only product claims supported by the live UX.
6. Prove at least 10 paying Web customers and three consecutive months of positive contribution after refunds, Stripe fees, route/provider, hosting, and attributed marketing spend.
7. Only after that exact gate, write a separate Web App Factory design and implementation plan that reuses the mobile loop, shared marketing evidence, and reviewed Self-Build boundary; build and measure one Web product at a time.
8. After the factory gate is complete, resume the prior §84-A cursor at PromptBase P5c.
