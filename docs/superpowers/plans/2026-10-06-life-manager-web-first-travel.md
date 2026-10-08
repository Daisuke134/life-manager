# Life Manager Cloud Web-First Travel Implementation Plan

> For agentic workers: Execute inline with superpowers:executing-plans. Work task-by-task in this dedicated worktree; do not modify production state from this branch.

**Goal:** Match the proven automatic Telegram travel engine in the Web entry: one Google Calendar connection, an immediate hard paywall with the existing seven-day card trial regardless of Travel-block count, and backend automatic Travel updates without a scan UI.

**Architecture:** Keep Google identity verification and Calendar consent behind one user action. After exact Calendar ACTIVE readback, show the connected/paywall screen immediately while the backend starts automatic processing through the existing exact-tenant travel owner and dedupe ledger. Travel-block/scan status never gates the offer. Stripe webhook remains authoritative: recurring Calendar work starts only after a card-backed trial or paid subscription is confirmed.

**Tech Stack:** CommonJS Node.js HTTP server, Supabase Auth/PostgREST/RPC, Composio Google Calendar, existing travel engine, Stripe Checkout/Billing, Node test runner, browser-based E2E with synthetic Calendar data.

**Spec:** docs/superpowers/specs/2026-10-06-life-manager-web-first-travel-design.md; ordered delivery cursor: docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md.

## Global Constraints

- Serve the Web product at LM_PANEL_BASE/lm; the Google Calendar is the customer's daily surface.
- The page has no dashboard, chat thread, home-address question, Life Manager password, Gmail access, or browser location request.
- The first CTA says Google Calendarに接続; Google account verification and Calendar permission remain required.
- Preserve the existing $29/month price. Show the seven-day, card-required trial offer immediately after Calendar is ACTIVE, regardless of scan status or Travel-block count; the trial starts only after explicit Checkout consent and Stripe webhook confirmation.
- Start the initial automatic Travel pass after Calendar is ACTIVE without exposing a scan control or waiting screen. Periodic scans start only after Stripe confirms the trial/subscription and payment method.
- The Stripe webhook remains the sole writer of lm_users.paid. Web cancel/payment failure pauses future Calendar reads/writes and preserves existing Travel blocks. Preserve existing Telegram billing behavior.
- Reuse the shared travel owner, exact ACTIVE Calendar account, event-level effect fences, route cache, and duplicate prevention. Never guess an unknown origin or destination.
- An event-specific question may use an already-linked Telegram or iMessage route. Show an optional one-time pairing control only when its provider is ready; bind the inbound sender to the exact Web tenant before sending questions or applying replies. Photon Find My reads are allowed only after a separate visible request and the user's acceptance; they never replace Calendar origin rules or become passive GPS. Do not ask during Web onboarding or use email fallback.
- A Web-only ask or Telegram/iMessage reply can read or write Calendar only while `webTravelEntitled` is true. After trial expiry, cancellation, or payment failure, a linked message cannot update Calendar.
- An iMessage outbound ask is confirmed only when Spectrum returns a provider message ID. If a send has an ambiguous outcome or no receipt, retain the atomic ask claim and do not retry that message automatically.
- The iMessage stream handler is one process-local sequential consumer per `life-call` replica. Current production Railway readback shows one active `life-call` replica. Do not scale this service above one replica until cross-replica stream ownership and reply-effect claims are implemented; the user-id/ask ledger handles sequential replay after completed replies.
- A location reply is written as an idempotent Calendar setter and then marked answered in `lm_ask_log`. A process stop between those steps may retry the same setter after a Calendar readback that still appears empty; this is not an exactly-once guarantee. Do not generalize this write pattern to non-idempotent external effects.
- Demos and published content use synthetic Calendar data. Never expose private event titles, addresses, or voice recordings.
- Do not change the public /lm landing or activate marketing publication from this branch; those remain later SSOT items after the app path and billing are verified.

### Execution order update — 2026-10-08

Old remaining order: find the staging Google test identity/callback → real OAuth/Calendar/Travel E2E → Stripe trial lifecycle → recover the missing `lm_ask_log` baseline → Photon message pilot.

New order: complete Task 8 and the 15 staging Web migrations → recover the production `lm_ask_log` catalog, add its source-owned baseline, validate locally, and apply it to staging → find a designated non-personal Google test identity and configure the exact staging callback → real OAuth/Calendar/Travel E2E → Stripe test lifecycle/funnel → Spectrum iMessage pairing/reply/location-consent pilot → production readback → measured Web acquisition → WB-16 verified $10K gross MRR.

Reason: after the 15 Web migrations, staging still lacked the ask ledger used by the existing clarification engine. Restoring that independent source prerequisite does not require Google login or Calendar data, so it can be completed while the separate test-identity search continues. Fresh provider readback confirms the staging Google provider is disabled and Auth has no users; the stored Google identities are not test-labeled, and the separate Railway installed-app client has the wrong redirect/client for Supabase Auth. No personal Google account or Calendar is used. Current cursor: find a designated non-personal Google test identity and configure a matching staging Supabase Auth client/callback; then run real Web OAuth/Calendar/Travel E2E.

### Execution order update — 2026-10-08 — Source-only iMessage work while Google identity search remains open

Old remaining order: find the dedicated Google identity/callback → real OAuth/Calendar/Travel → Stripe test lifecycle → Spectrum adapter and pairing.

New temporary order: finish Task 9's source-only Spectrum Cloud stream adapter, tenant pairing, and synthetic PostgreSQL/provider tests without live sends → continue the non-personal identity search and staging Auth setup → real OAuth/Calendar/Travel E2E → Stripe lifecycle → controlled Japanese iMessage pairing and consent → production readback → measured acquisition and $10K gross MRR.

Reason: fresh central credential/secret-safe Railway scans found two unmarked free-mail Google identities, no Google test identity variable across 18 Railway services, an empty Railway environment named `Google Calendar, `, no staging Google provider, and no staging Auth users. The separate API staging Supabase ref is not present in the Management API project inventory. No personal Google account or Calendar may be used. Source-only adapter work is independent and can be verified with synthetic senders while the live identity/provider gate stays closed. Photon Stable docs say app.webhook is request-scoped, acknowledges before handler completion, and delivers at-least-once; the managed Cloud iMessage provider instead uses a resumable ordered stream with catch-up. Use that stream so message side effects finish before the application advances its cursor. Cost if wrong: a stream recovery defect could delay a reply; link and ask operations remain idempotent and a live provider receipt stays required. Historical cursor at the time of this order update, superseded by the current cursor below: Task 9 Step 6 — location-consent integration and tests remain source-open. No real line or live iMessage send is configured.

### iMessage toolkit readback — 2026-10-08

Vercel Chat SDK is the OSS toolkit that most closely matches “one agent across Telegram and iMessage”: it has a maintained Telegram adapter, a vendor-official Photon iMessage adapter, and `create-chat-sdk` scaffolding. The dedicated Vercel Labs iMessage template uses Sendblue and Vercel Workflows; it is a starter, not the Life Manager backend. Keep this existing CommonJS/Railway service on direct `spectrum-ts` for Task 9: it already owns the Telegram webhook, Web sender registry, ask ledger, Calendar writes, and billing gates. Do not migrate its channel or business logic to Chat SDK in this source task. Revisit Chat SDK for new factory apps or a separately scoped adapter extraction.

## Review Focus

- Expired, missing, or replayed OAuth state never creates a tenant session.
- A stale, foreign, changed, or non-ACTIVE Calendar account never triggers a Calendar read or write.
- No saved base and no recent physical Calendar event means no guessed route or Travel block; the connected/paywall screen still appears after Calendar is ACTIVE.
- A zero-block scan does not suppress Checkout or the trial offer. It does not start recurring automation before Stripe confirmation; an uncertain provider write stays fenced until exact Calendar readback.
- Duplicate, stale, canceled, or failed Stripe events cannot re-enable Web automation or overwrite a newer billing state.
- Checkout abandonment, trial cancellation, and payment failure preserve existing Travel blocks.
- UTM attribution survives Google auth and is joined to Calendar activation, trial, invoice, refund, and retention measures.

---

### Task 1: One-time Web activation through the shared travel owner

**Files:**
- Modify: apps/life-manager/lib/web-travel.js
- Modify: apps/life-manager/scheduler.js
- Modify: apps/life-manager/lib/travel.js only if a focused origin test requires a behavior change
- Create: apps/life-manager/migrations/2026-10-08-lm-web-initial-scan.sql
- Test: apps/life-manager/lib/web-travel.test.js
- Test: apps/life-manager/lib/travel.test.js
- Test: apps/life-manager/test/scheduler.test.js

**Interfaces:**
- runInitialWebTravelScan(uid, opts) in apps/life-manager/lib/web-travel.js returns { inserted, verified, confirmedTravelBlockCount, scanState } and requires the exact Web-owned ACTIVE Calendar account.
- travelUserOnce(user, deps) in apps/life-manager/scheduler.js accepts deps.initialScan=true only for a verified Web uid with the exact ACTIVE account and no pending disconnect/enable fence. The initial scan does not turn on scheduled automation; normal scheduled calls keep the existing gate.
- The migration adds lm_users.web_initial_scan_completed_at and lm_users.web_first_travel_at plus service-role-only RPC record_lm_web_initial_scan(p_uid text, p_calendar_account_id text, p_completed_at timestamptz, p_first_travel_at timestamptz). It stores no event title or address.
- Replace complete_lm_web_travel_setup so it no longer starts a three-day trial or enables periodic automation; an already-saved home_address remains usable as an optional origin.

- [x] Step 1: Add failing test web-travel.test.js: initial Web setup accepts no home and does not start a trial or recurring automation. Assert empty JSON body, HTTP 200, null home_address, null trial_expires_at, daily_automation_enabled=false, one initial scan, and resume with no saved base after exact ACTIVE verification.
- [x] Step 2: Run node --test --test-name-pattern='initial Web setup accepts no home' lib/web-travel.test.js and confirm RED: HTTP 400 invalid_home_address and resume returns 409 home_required.
- [x] Step 3: Add failing scheduler tests for the exact ACTIVE one-shot scan boundary and the Web-only question route with no email fallback; normal scheduled calls and existing Telegram/email routes remain gated.
- [x] Step 4: Run the named scheduler tests and confirm RED at the missing one-shot branch and missing Web channel policy.
- [x] Step 5: Add failing Web travel tests for zero confirmed blocks and uncertain Calendar readback; assert neither sets web_first_travel_at or starts Checkout.
- [x] Step 6: Implemented the migration, record_lm_web_initial_scan RPC, exact Web-only one-shot scheduler path, no-home resume, and no-email routing for Web-only question loops. Unknown-origin events remain unchanged.
- [x] Step 7: Focused result: web-travel 40/40, scheduler 15/15, travel 21/21; the one-shot path retains exact ACTIVE binding, leaves periodic automation off, and confirms zero/uncertain/duplicate cases.

### Task 2: Single-action Calendar onboarding and immediate connected/paywall screen

**Files:**
- Modify: apps/life-manager/lib/web-auth.js
- Modify: apps/life-manager/lib/web-calendar.js
- Modify: apps/life-manager/lib/web-page.js
- Modify: apps/life-manager/server.js
- Test: apps/life-manager/lib/web-auth.test.js
- Test: apps/life-manager/lib/web-calendar.test.js
- Test: apps/life-manager/lib/web-page.test.js

**Interfaces:**
- The initial Google callback returns to a fixed /lm continuation that starts Calendar OAuth automatically; all redirects remain server-owned.
- A successful Calendar callback starts the backend Travel process automatically. The browser does not wait for scan completion or display scan/loading/zero-block results.
- renderWebPage(model) renders the signed-out CTA, immediate connected/trial offer, trial-active confirmation, or billing/error state; it never renders the old dashboard or a scan control.

- [x] Step 1: Add failing page/auth/calendar tests for the exact CTA, automatic Calendar OAuth continuation, automatic first scan, combined offer, zero-block state, Messages visibility, and absence of dashboard/home-address/chat UI. The prior zero-block/no-offer expectation is superseded by WB-15d.0 below.
- [x] Step 2: Run those focused tests and confirm the expected states are missing.
- [x] Step 3: Implement the single-action flow and server-rendered states. Keep the optional Messages link hidden until its recipient and response owner are verified.
- [x] Step 4: Run the focused auth/calendar/page tests at mobile and desktop viewport sizes in the browser harness.

### Task 3: Card-required seven-day Stripe trial and subscription lifecycle

**Files:**
- Create: apps/life-manager/lib/web-billing.js
- Create: apps/life-manager/lib/web-billing.test.js
- Modify: apps/life-manager/lib/billing.js
- Modify: apps/life-manager/lib/billing.test.js
- Modify: apps/life-manager/lib/web-travel.js
- Modify: apps/life-manager/lib/web-travel.test.js
- Modify: apps/life-manager/lib/travel.js
- Modify/Test: apps/life-manager/lib/travel.test.js
- Modify/Test: apps/life-manager/lib/transport/calendar-composio.js and apps/life-manager/lib/transport/calendar-composio.test.js
- Modify: apps/life-manager/scheduler.js
- Modify: apps/life-manager/test/scheduler.test.js
- Modify: apps/life-manager/server.js
- Modify: apps/life-manager/lib/web-page.js
- Modify/Test: apps/life-manager/lib/stripe-webhook-signature.js and apps/life-manager/lib/stripe-webhook-signature.test.js
- Test: apps/life-manager/lib/web-page.test.js

**Interfaces:**
- createWebCheckoutSession(uid, user, opts) returns { url, trialEnd, trialEligible }, uses only the configured existing $29/month price, collects a payment method, and uses a verified Web uid for Stripe correlation.
- Checkout becomes available after exact Calendar ACTIVE readback and first-time trial eligibility; it does not require web_initial_scan_completed_at or web_first_travel_at. A first-time eligible uid receives one seven-day card-required trial; a prior trial or canceled subscription can restart only on explicit no-trial $29/month Checkout, charged at start.
- The webhook grants Web automation only for a valid trialing subscription with a retained payment method or a verified paid invoice. Web past_due, cancellation, and failed payment pause future Calendar work; Telegram grace behavior remains unchanged.
- A customer-portal session lets a user cancel/manage billing without a Life Manager dashboard. No Life Manager trial-ending reminder email is sent.
- The scheduled travel path rejects unpaid, expired-trial, canceled, or failed-payment Web tenants before Calendar event reads; the one-time pre-trial scan and Telegram behavior remain unchanged.
- Web Travel events set a zero-minute Google Calendar popup reminder, and the initial scan only counts a confirmed Travel block after its reminder is read back. The official Composio `GOOGLECALENDAR_CREATE_EVENT` schema has no `reminders` field, so the Web-only event write uses Composio's authenticated proxy against the same exact connected account; it never extracts or stores Google's OAuth token. This makes the post-onboarding notification claim match the event we create.
- A live Stripe API key can never verify a webhook with the test-mode endpoint secret.

- [x] Step 1: Add failing Checkout tests for the existing price, first seven-day trial, required payment method, exact uid metadata, prior-trial/active-user guards, no-trial paid restart after trial/cancellation, and idempotent repeated requests. The prior zero-block offer gate is superseded by WB-15d.0 below.
- [x] Step 2: Add failing webhook tests for trial activation, paid invoice, payment failure, cancellation reservation, duplicate/out-of-order events, Web past-due pause, and unchanged Telegram grace.
- [x] Step 3: Run focused billing tests and confirm these Web-specific behaviors are missing.
- [x] Step 4: Implement Checkout, portal, webhook reconciliation, Web card/trial/cancel entitlement, pending-return UI, no-trial paid restart, both scheduled-travel entitlement gates, and proxy-written zero-minute Calendar popup reminders.
- [x] Step 5: Run focused billing/web tests, synthetic desktop/mobile browser E2E, real Stripe test-mode Checkout/card collection/Subscription readback/Portal UI, then cancel/expire the test artifacts. No live charge occurred.

### Task 4: Funnel, cost, and revenue evidence

**Files:**
- Reuse: apps/life-manager/lib/web-attribution.js
- Modify: apps/life-manager/lib/ask.js, apps/life-manager/lib/travel.js, apps/life-manager/lib/usage-event.js
- Create: apps/life-manager/lib/web-funnel-events.js
- Create: apps/life-manager/lib/web-funnel-events.test.js
- Create: apps/life-manager/lib/web-funnel-report.js
- Create: apps/life-manager/lib/web-funnel-report.test.js
- Create: apps/life-manager/scripts/lm-web-funnel-report.test.js
- Create: apps/life-manager/migrations/2026-10-08-zz-lm-web-funnel-events.sql
- Modify: apps/life-manager/server.js, apps/life-manager/lib/web-auth.js, apps/life-manager/lib/web-calendar.js, apps/life-manager/lib/web-travel.js, apps/life-manager/lib/web-billing.js for server-side funnel events
- Create: apps/life-manager/scripts/lm-web-funnel-report.js
- Test: apps/life-manager/lib/ask-usage.test.js, apps/life-manager/lib/usage-event.test.js, apps/life-manager/lib/travel.test.js, apps/life-manager/lib/web-auth.test.js, apps/life-manager/lib/web-calendar.test.js, apps/life-manager/lib/web-travel.test.js, apps/life-manager/lib/web-billing.test.js

**Interfaces:**
- Places lookup accepts tenant uid and an optional usage writer, records one privacy-safe provider-usage row per billable success, and makes at most three Places Text Search calls per Calendar event. It never records the query, event title, address, or response text.
- The funnel event writer accepts an allowlisted lifecycle event, bounded first-touch UTM values, an optional opaque Web uid, an optional provider-object/event id, and optional amount/currency; it writes append-only rows to `lm_web_funnel_events` with service-role access only.
- The report joins anonymous landing/connect counts to Web users, Stripe events/subscriptions/invoices/refunds, Stripe Balance Transactions/payout statuses, and per-user `lm_api_cost` estimates. MRR requires both a current active Stripe subscription and webhook-verified `lm_users.paid=true`, `plan_status=active`, and matching subscription id; a trial counts only while the row is trialing, unexpired, and card-backed. The first positive invoice uses retained all-time invoice history, so renewals from earlier cohorts stay renewals.
- It separates paid invoice amount, Stripe-balance available/pending net, Stripe-paid-payout net, refunds, attributable charge/refund fees, and provider estimates. Stripe payout status does not prove bank credit. Partial or missing provider estimates, hosting, and marketing spend stay visibly unknown.
- Group acquisition by signed first-touch UTM; count Google auth, Calendar ACTIVE, first Travel block, Checkout creation, trialing, positive first paid invoice, renewals, cancellations, refunds, and mature D7/D30 retention. Stripe is the billing source of truth; Checkout redirects and trial rows are not paid revenue.
- Report gross MRR separately from paid invoice receipts, Stripe-balance available/pending values, paid payout net, refunds, attributable Stripe fees, estimated route/provider cost, hosting, and attributed marketing spend.
- Do not infer a paid customer from a trial or a Stripe checkout redirect.

- [x] Step 1: Read the current records. `lm_users` holds first-touch UTM and current Calendar/billing state; `lm_api_cost` holds tenant provider estimates; `lm_stripe_events` has only Stripe event id/type/receive time. No persistent Web page-view/connect-start events or historical invoice/refund attribution exists.
- [x] Step 2: Verify Google Maps and Gemini list prices from official documentation. A successful Places Text Search (Legacy) request estimates $0.040 after free caps ($0.032 base + $0.003 Contact Data + $0.005 Atmosphere Data; Basic Data is unlimited). Keep estimates labeled estimated; do not claim provider-bill actuals from list price.
- [x] Step 3 (RED): Focused tests fail on the missing 3-call Places cap, tenant usage event, route-fallback uid propagation, funnel event writer, lifecycle hooks, Stripe event mapping, and read-only report.
- [x] Step 4 (GREEN): Add Places metering/cap and thread uid through the existing route fallback. Extend the Maps SKU allowlist and pricing version without changing Calendar or Stripe entitlement behavior.
- [x] Step 5 (RED/GREEN): Add the append-only funnel migration and instrument `landing_view`, `google_connect_start`, `google_authenticated`, `calendar_active`, `first_travel_block`, `checkout_created`, `trial_started`, `paid_invoice`, `cancellation_requested`, `subscription_canceled`, and successful `refund_recorded`. No IP, user-agent, event titles, addresses, Gmail, or raw URLs are recorded.
- [x] Step 6 (source): Implement a read-only report over Web users, funnel events, all-time paid-invoice history, usage rows, current Stripe subscriptions, and attributable balance transactions/payout status. D7/D30 are labeled current webhook-verified paid-subscription retention; provider totals with missing estimates and unallocated hosting/marketing remain null.
- [x] Step 7: Prior source acceptance passed 243/243 focused tests. Fresh reviews found three report defects: nonexistent `BalanceTransaction.payout`, available/pending zero on incomplete transaction reads, and incomplete/manual payouts counted as complete. Regression tests reproduced all three; implementation now uses the official payout filter only for `automatic=true` and `reconciliation_status=completed`, and returns unknown totals when attribution is incomplete. Current source acceptance passed 247/247 focused tests, PostgreSQL integration, synthetic browser E2E at 390x844/1440x900, syntax, and diff checks. PR #6981 merged as `9fb58c74`; Railway deploy is SUCCESS and `/health` is 200 at that SHA. The funnel migration is applied in the verified production Supabase project; SQL readback confirms RLS, service_role SELECT/INSERT, browser-role denial, and append-only guards; REST readback is 200. Stripe live price remains $29/month, Web subscription count/MRR is 0, and the live webhook preserves its original six events plus `refund.created`/`refund.updated`. The 30-day production report initially had zero events and `$0` Web MRR; provider actual, hosting, marketing and net contribution remain unknown. PR #424 merged the `/lm` Web-first CTA to `life-call /lm`; Netlify production deploy and post-deploy smoke passed. Live page shows Google Calendar connect, seven-day card-required trial, existing $29/month, and same-tab Web handoff. A tagged two-hop OAuth-start probe reaches Supabase and yields a Google authorization URL; no Google login or personal Calendar access occurred. TEST credentials have only legacy Netlify webhook endpoints, not a test endpoint for current Railway `life-call`; refund delivery has source-contract coverage and the live endpoint subscription, without a test-provider delivery receipt. The only recent funnel activity is tagged internal E2E (`landingViews=1`, `googleConnectStarts=2`), with no customer subscriptions; do not count it as acquisition. No live price or charge changed.

### Task 5: Immediate connected/paywall after Calendar ACTIVE (WB-15d.0)

**Files:**
- Tests: `apps/life-manager/lib/billing.test.js`, `web-billing.test.js`, `web-travel.test.js`, `web-page.test.js`
- Source: `apps/life-manager/lib/billing.js`, `web-billing.js`, `web-travel.js`, `web-page.js`

**Interfaces:**
- Calendar ACTIVE plus first-trial eligibility determines the connected/paywall offer; initial scan completion and `web_first_travel_at` do not.
- The page immediately renders the seven-day card-required trial at the existing $29/month price. Background initial processing uses the existing exact-account travel owner and effect fence; no scan spinner, result/zero-block state, or rescan action is rendered.
- Stripe webhook product/tenant checks, card-backed entitlement, recurring-automation gate, cancellation/failure pause, exact Calendar binding, and duplicate prevention remain intact.

- [x] Step 1 (RED): Add failing cases for Checkout before any scan/block, ACTIVE Calendar with no events, zero-block and pending initial processing, invisible background setup dispatch, and rejection of unrelated Stripe products. The focused run confirms the offer is gated on a first Travel block and the page exposes scan UI. It also found a local install gap (`@noble/hashes/sha3.js` missing), which remains to fix before GREEN.
- [x] Step 2 (GREEN): Remove only the first-block/scan prerequisites from offer eligibility, Checkout, and Web billing event classification. Return the offer immediately after ACTIVE Calendar verification; keep backend processing and strict Travel readback separate from page state. Web-only billing events still require the Web product marker; prior cancellation/failure and Stripe invoice protections remain.
- [x] Step 3: Focused billing, Web Checkout, Calendar snapshot, Web page, and attribution suites pass 157/157. Scheduler suite passes 20/20. Syntax and `git diff --check` pass.
- [x] Step 4: Synthetic onboarding browser E2E passes at 390x844 and 1440x900. It delays the background zero-block setup response while confirming the connected paywall and Stripe CTA are already visible; no spinner, results screen, or rescan action appears. The run uses mocked Google and Stripe providers and causes no real login or payment.

### Task 6: Isolated staging schema and identity readiness (WB-15d.1c)

**Files:**
- Read/apply only the missing prerequisites, in order: `2026-06-24-hard3-stripe-billing.sql`, `2026-07-21-lm-panel-control-center.sql`, `2026-08-27-lm-panel-oauth-atomic.sql`, `2026-08-28-lm-trial-first.sql`, `2026-09-11-lm-calendar-account-binding.sql`, `2026-10-06-lm-api-cost-append-only.sql`, `2026-10-06-lm-web-attribution.sql`, `2026-10-06-lm-web-calendar-oauth.sql`, `2026-10-06-lm-web-travel-setup.sql`, `2026-10-06-z-lm-web-travel-controls.sql`, `2026-10-07-lm-usage-cost-period-summary.sql`, `2026-10-08-lm-web-initial-scan.sql`, `2026-10-08-z-lm-web-billing-ordering.sql`, `2026-10-08-zz-lm-web-funnel-events.sql`, and `2026-10-08-zzz-lm-message-channels.sql`
- External target: Anicca Railway `life-call-staging` and the Supabase project named by its `SUPABASE_URL`; never production `life-call`

**Interfaces:**
- Use only existing staging variables from Railway at runtime; never print values. Read/modify schema only through Supabase's official migration endpoint using an existing centrally stored token with `database_migrations_write`. Do not run DDL through service-role PostgREST or experimental `/database/query`.
- A successful fixture has the main-derived schema, Google provider enabled with a verified callback URI, and one dedicated non-personal Google test identity/Calendar. A client ID or OAuth service config is not a user identity. The central Supabase credential SSOT has a token whose permission metadata includes `database_migrations_write`; use the official Management API migration endpoint, never service-role DDL or experimental `/database/query` for changes.

- [x] Step 1: Read back exact Anicca project/service/environment, staging Supabase host, Auth Google-provider status, Auth-user count, and schema without reading Calendar rows. Fresh readback: Google provider `false`, Auth users `0`, one `lm_users` row, zero Telegram-bound users and duplicate senders; `calendar_connected_account_id`, panel preferences/OAuth state, Stripe event ledger, Web funnel table, and Web RPCs are absent. The current public `API` service holds an `installed` Google OAuth client whose client ID differs from the Supabase Auth client and whose redirect list does not include the staging Supabase callback; it is not a Web test identity.
- [x] Step 2: Compare the staged OpenAPI schema with production and source migrations. Supabase Management API read-only migration listing returns 0 rows for staging and 10 for production; `to_regclass('supabase_migrations.schema_migrations')` confirms staging has no migration-history relation, while PostgREST does not expose that schema. The source dependency order is the 15-file list above: panel/Stripe/trial base tables first, then account binding, Web OAuth/travel/billing controls, cost/funnel, and message-channel migrations. Production/staging schema comparison confirms the Web tables, columns, and RPCs in this list are absent from staging; `lm_users`, `lm_api_cost`, and `lm_travel_log` already exist.
- [x] Step 3: Applied all 15 main-derived migrations to only `life-manager-staging` through the official Supabase Management API. Every POST returned HTTP 200; immediately afterward the migration history increased by one and contained the exact migration name, from 0 to 15. Production schema and Stripe were untouched; no Calendar/event rows were read or written.
- [x] Step 4: Read back the required Web columns/tables/RPCs, RLS, grants, and Google status. The 7 required panel/Stripe/funnel/message tables, Calendar/trial/billing/scan columns, and expected OAuth/Web/travel/message RPCs exist. RLS is enabled on the service tables and `pg_policies` returns no anon/authenticated policies; service-only RPC EXECUTE grants are limited to `service_role`. Supabase default table grants exist on some panel/Stripe tables, but RLS has no policies; `lm_web_funnel_events` explicitly revokes anon/authenticated access. The staging Google provider remains disabled and Auth users are 0. `lm_ask_log` is still absent and needs its own verified baseline before ask/reply E2E.
- [ ] Step 5: Find a designated non-personal Google test identity and isolated Calendar. Fresh credential/railway inventory found two Google user records with no test/sandbox/E2E label, no staging Auth users, a production-only Supabase Google client, and no matching staging callback. Do not use the API service's `installed` client, sign in to a personal account, or read Dais's Calendar.

### Task 7: Real OAuth, Calendar write, and existing Telegram readback (WB-15d.2–3)

**Files:**
- Read: `apps/life-manager/lib/web-auth.js`, `web-calendar.js`, `web-travel.js`, `scheduler.js`, and `lib/transport/calendar-composio.js`
- Read-only external target: the isolated test identity and Calendar from Task 6

**Interfaces:**
- The first CTA begins Google identity confirmation and the separate Calendar consent; no Life Manager password is introduced.
- Use the exact ACTIVE account ID read back by the Web tenant. Automatic initial processing starts on Calendar ACTIVE; the page does not wait for it. Recurring processing remains gated on Stripe trial/paid entitlement.

- [ ] Step 1: From a mobile Safari-compatible browser session already authenticated as the dedicated test identity, open `/lm`, start the OAuth chain, grant only Calendar permission, and read back the same tenant through callback and later session resolution. Expected: no Gmail scope, no production identity, no cross-tenant binding.
- [ ] Step 2: Use the isolated Calendar to test a resolvable in-person event, an online event, and a missing/ambiguous location. Expected: one accurate Travel block with the event reminder, no block for online/unknown events, and replay-zero.
- [ ] Step 3: Trigger the existing ask loop for an already-linked Telegram test tenant. Expected: one question in the existing Telegram chat, no email fallback for Web-only tenants, and no duplicate send.

### Task 8: Tenant-safe message linking and Telegram reply path (WB-15d.3b)

**Files:**
- Create: `apps/life-manager/lib/message-links.js` and `message-links.test.js`
- Create: `apps/life-manager/migrations/2026-10-08-zzz-lm-message-channels.sql`
- Modify/Test: `apps/life-manager/server.js`, `apps/life-manager/lib/web-page.js`, `apps/life-manager/lib/scheduler.js`, `apps/life-manager/lib/telegram-reply.js`
- Test: existing Telegram HTTP and scheduler contracts plus new message-link/PostgREST integration coverage

**Interfaces:**
- `createWebMessageLink(uid, channel, opts)` returns a channel URL plus expiry only for an authenticated Web tenant and CSRF-valid request.
- `consumeWebMessageLink(token, channel, senderId, opts)` atomically binds one verified sender to one tenant and returns `{ uid, channel }`; tokens are one-use, expire, and are stored only as hashes. `lm_message_channels` is the global owner registry; it preserves all existing Telegram owners and rejects a sender already owned by another tenant.
- Existing Telegram `/start` remains the bot entry. A valid signed deep-link payload binds the existing Web tenant and skips Telegram-specific name/home/phone/call onboarding; email matching is forbidden.

- [x] Step 1: Add failing tests for issued token expiry/replay, cross-tenant binding denial, one-sender/one-tenant uniqueness, no phone form, and hidden/visible message controls. RED observed for parser, token issue, CSRF/API, canonical sender mapping, Scheduler/Inngest routing, and the mounted Telegram flow.
- [x] Step 2: Run the new tests and confirm they fail on the missing link store/route. Each first failure named the missing behavior; the migration integration initially failed because the message-channel migration did not exist.
- [x] Step 3: Add `2026-10-08-zzz-lm-message-channels.sql`: hashed short-lived tokens, global owner-unique channel registry, legacy Telegram backfill/trigger, per-sender transaction lock, append-only guards, RLS and service-role ACL. Add the authenticated Web link endpoint and atomic create/consume RPCs.
- [x] Step 4: Add the optional Web link button behind `LM_TELEGRAM_WEB_LINKS_ENABLED`. A valid private Telegram deep link is handled before legacy onboarding; the Web UID and `lm_users.telegram_chat_id` remain separate. Linked replies use the existing ask/Calendar flow with no phone form or Gmail fallback.
- [x] Step 5: `npm run test:web-first-travel` passes 224/224 tests plus `test:lm-message-channels:postgres`; Scheduler, Inngest, legacy Telegram, Web-page, auth, webhook and retry contracts are included. Source boundary, `lm-loop-contract`, and `git diff --check` pass.

### Task 9: Inbound-first managed iMessage transport and reply handling (WB-15d.3b)

**Files:**
- Read-only schema source: production `information_schema.columns`, `pg_constraint`, and `pg_indexes` for `public.lm_ask_log`; read no ask rows or message contents.
- Create: `apps/life-manager/migrations/2026-06-23-lm-ask-log-baseline.sql` from that verified schema. The staging catalog lacked `lm_ask_log`; repository migrations only altered it and did not create it.
- Create: `apps/life-manager/lib/imessage-cloud.js` and `imessage-cloud.test.js`
- Modify: `apps/life-manager/server.js`, `scheduler.js`, `lib/ask.js`, and Task 8's message-link schema/API as required
- Test: Web-only ask routing, config-gated resumable stream receiver, inbound pairing, sender-to-tenant binding, message dedup, reply resolution, provider delivery receipt

**Interfaces:**
- Use Photon Spectrum Cloud as the primary technical candidate, keeping Telegram's existing webhook path intact. Stable [Photon iMessage docs](https://photon.codes/docs/spectrum-ts/providers/imessage), [routing/quota docs](https://photon.codes/docs/spectrum-ts/providers/imessage/connection-and-routing), and the [Chat SDK Photon adapter](https://chat-sdk.dev/adapters/vendor-official/photon) show managed cloud iMessage on Node/Bun without a Messages Mac. The selected ingress is the resumable `app.messages` stream. The [Advanced iMessage Locations API](https://photon.codes/docs/advanced-kits/imessage/locations.md) can send a visible Find My request; a request alone grants no access. [Photon pricing](https://photon.codes/pricing) lists Free up to 10 users, Pro $25/month up to 100 shared-pool users, and Business $250 per dedicated line/month; Business unlimited users require Auto Scale. Published limits include 5,000 messages/server/day and 50 new outbound conversations/line/day. The actual Auto Scale price, Japanese line routing, shared-pool first-contact path, and location API availability on each plan still require a controlled readback. [Sendblue](https://sendblue.com/pricing) is the fallback at $100/month for a dedicated inbound-first line, up to 1,000 inbound contacts/day; its free sandbox has no webhooks, and its [FAQ](https://docs.sendblue.com/faq#is-it-possible-to-request-or-receive-location-data-via-the-imessage-api) says the API does not expose location sharing. Do not buy a paid line or expose the button before provider terms and a controlled receipt are verified.
- Apple's [documented SMS URL scheme](https://developer.apple.com/library/archive/featuredarticles/iPhoneURLScheme_Reference/SMSLinks/SMSLinks.html) can specify a recipient but must not include message text. Open Messages with the provider number, show a short-lived one-time pairing code on the Web page with a copy control, and require the user to paste/send that code. The inbound stream supplies the sender address; bind it atomically to the exact Web tenant. No phone-number form, email matching, or unregistered-sender inference.
- After pairing, the manager may send a visible Photon Find My request only for an event whose route origin remains unresolved. The user must accept or begin sharing. Use only a currently visible share with coordinates, a fresh timestamp, and a future expiry; location watch updates are non-durable and missed updates cannot be replayed. If sharing is absent, stale, or declined, retain Calendar-based origin logic, ask one event-specific question through the linked channel, or leave that event unchanged. No passive GPS or location prompt during Calendar onboarding.
- Production and `lib/ask.js` use `lm_ask_log` for pending-question/dedup state. The production catalog was read without selecting ask rows: 15 columns, primary key, canonical `(uid,event_id)` unique claim, reply-token index, partial unique semantic-key index, RLS enabled/no policies, and service-role API access. The new baseline is source-owned and applied only to staging; no production ask row or message content was read.
- Do not adopt `@emotion-machine/claw-messenger` for this flow: its official docs say unregistered numbers are ignored and self-serve plans cap registered contacts, which conflicts with the no-phone-field pairing. Its OpenClaw channel package is `UNLICENSED`; the MIT Vercel Chat SDK is a separate cross-channel framework, not a provider credential or a drop-in replacement for this CommonJS service.
- Route existing `ask.js` clarification decisions through exactly one linked channel. The model resolves free-text replies; code performs sender/tenant checks, pending-ask matching, atomic consumption and dedup. No Web email fallback, passive GPS, duplicate question, or phone-number form.
- Web-only asks and Telegram/iMessage replies are gated by `webTravelEntitled`; an expired/canceled/past-due account cannot read or write Calendar through a late message reply. The scheduler's user projection and sender lookup must include the exact billing fields used by this check.
- Count an iMessage ask as sent only when Spectrum returns a message ID. A missing receipt, timeout, or thrown send error is effect-unknown: keep the atomic ask claim and do not retry automatically. Release the claim only on an explicitly known pre-effect failure.
- Forward the provider's message ID into the reply resolver and persist it on the online/offline follow-up transition. Reject the same offline-message ID before Calendar/LLM work; use an atomic compare-and-set against the prior message ID.
- Toolkit decision: Vercel Chat SDK has Telegram and Photon iMessage adapters plus a scaffold CLI, but it is a channel framework rather than Calendar/billing logic. Keep the current service on direct `spectrum-ts` to preserve its working Telegram owner and existing tenant/ask contracts; do not migrate the service in Task 9.

- [x] Step 1: Read the production `lm_ask_log` catalog and confirm columns, defaults, constraints, indexes, and RLS/grants without selecting any ask row. Fresh catalog readback confirms the exact 15-column shape, `lm_ask_log_uid_event_id_key`, `lm_ask_log_reply_token_idx`, partial `lm_ask_log_uid_semantic_key_key`, RLS enabled/no policies, and service-role access.
- [x] Step 2a: Add a PostgreSQL integration test for the missing baseline table. RED reproduced the absent source migration; after the source migration, GREEN confirms idempotent rerun, 15 columns, unique claim, semantic index, RLS/browser denial, and service-role CRUD.
- [x] Step 2b: Add `2026-06-23-lm-ask-log-baseline.sql` with the verified production columns/defaults and least-privilege staging ACL. PostgreSQL collapses the two redundant production `(uid,event_id)` constraints to the canonical named unique constraint on fresh creation; this is sufficient for `lib/ask.js` atomic claims.
- [x] Step 2c: Apply the baseline to staging Supabase only through the official Management API. POST returned HTTP 200; history readback advanced 15→16 and recorded the exact migration name. Readback confirms the 15 columns, canonical unique constraint, reply/semantic indexes, RLS enabled/no policies, anon/authenticated denied, and service-role CRUD. Production was not changed. `npm run test:web-first-travel` passes 224/224 with both PostgreSQL integrations; full `npm test` exits 0, with Life Manager 1045/1045 and all surrounding suites at 0 failures.
- [~] Step 3: Provider tests cover missing Spectrum credentials, malformed/absent sender handling, invalid/expired/replayed pairing, foreign tenant isolation, duplicate pairing delivery, linked-channel routing, Web billing entitlement, provider message-ID handoff/replay, and ambiguous sends. New send/entitlement/reply-message regressions were added before their source fixes. Find My consent/freshness tests remain open with the source flow.
- [x] Step 4: The four new entitlement/receipt tests were run RED before implementation; existing provider, tenant, message-link and ask tests also cover the no-credential and pairing boundaries. The ask-log baseline PostgreSQL regression remains green.
- [x] Step 5: Add the MIT `photon-hq/spectrum-ts` Cloud iMessage provider (`@spectrum-ts/imessage`) behind the iMessage-only adapter in the existing Node service. The ESM package is lazily imported from CommonJS; startup is disabled without credentials; the persistent `app.messages` stream is used; Telegram retains its existing webhook owner. No credentials or live line are enabled.
- [~] Step 6: Copy-code pairing, tenant-bound replies and billing-entitlement checks for both Telegram and iMessage are implemented. An iMessage offline reply records its provider message ID on the follow-up transition so a replay cannot be reinterpreted as a location. The opt-in Find My request/read flow still needs separate linked-channel consent, freshness/expiry enforcement, and provider-backed tests; preserve Calendar history as the default origin source.
- [~] Step 7: Focused Web/provider/scheduler acceptance passes 257/257 plus message-channel and ask-ledger PostgreSQL RLS/ACL integrations; the full `npm test` exits 0 and `git diff --check` passes. A controlled Japanese sender pairing, one live reply, and any Find My read remain unverified because Spectrum credentials and a Japanese line are not configured. If Photon fails the verified first-contact/cost contract, evaluate Sendblue using the same pairing API.

### Task 10: Stripe trial lifecycle and funnel readback (WB-15d.5–6)

**Files:**
- Read/Modify only if a focused failure requires: `apps/life-manager/lib/web-billing.js`, `lib/billing.js`, `lib/web-funnel-events.js`, `lib/web-funnel-report.js`, `server.js`, and their existing tests
- External target: staging Stripe TEST endpoint and the isolated staging user; no live charge

**Interfaces:**
- Existing price is USD $29/month. First eligible user gets one seven-day card-required trial; Stripe webhook is the only paid/trial entitlement writer.
- The funnel must join landing/UTM, Calendar ACTIVE, first Travel block, Checkout, card-backed trial, paid invoice, renewal, cancellation, refund, cost and D7/D30 retention without counting internal E2E as customers.

- [ ] Step 1: Verify existing test price/webhook and the staging identity. Expected: test mode only, seven-day trial and payment-method collection, with no live Stripe resource mutation.
- [ ] Step 2: Complete one staging Checkout and verify the trial webhook, first invoice, portal, cancellation, expiry and payment-failure pause. Expected: recurring Travel stays off until verified trial/paid state and stops on cancel/failure.
- [ ] Step 3: Read back the Web funnel report and source attribution. Expected: synthetic/test activity is labeled and excluded from customer MRR/CAC.

### Task 11: Production signed-out readback and task close (WB-15d.7)

**Files:**
- Read-only: public `aniccaai.com/lm`, Railway `life-call /lm`, production `/health`, latest immutable deployment SHA, and the canonical Web funnel report

- [ ] Step 1: Verify desktop/mobile signed-out entry, Google Calendar CTA, $29/seven-day offer copy, and same-tab handoff. Expected: the live route matches the accepted copy and remains Web-first.
- [ ] Step 2: Verify the deployed SHA and report authenticated OAuth, Calendar write, Stripe test/live evidence, provider cost, subscription count and MRR separately. Expected: no claim of authenticated production E2E from signed-out reads or synthetic tests.
- [ ] Step 3: Update the canonical SSOT cursor and plan evidence; leave `WB-16` active until Stripe-verified $10K MRR is actually reached.

### After this source plan

The public `/lm` page and production retry path are live. PR #6995 deployed the OAuth tenant-isolation fix and Safari callback-download fix. The no-code callback readback proves failure recovery only; a successful Google callback and Calendar consent through a dedicated test identity are still unverified.

**Telegram baseline read from source:** `/start` offers a Calendar connection link; the automatic scheduler's travel tick invokes the shared Travel owner every 30 minutes; the ask engine can ask Telegram-linked users whether an event is online/in-person or ask for a missing location. There is no user-operated scan step in that flow. The Telegram-specific home-address and optional phone/call prompts are not copied into the one-action Web entry. Telegram's `/subscribe` command opens its configured Stripe Payment Link; the Web keeps the owner-specified seven-day card-required trial and existing $29/month offer.

**Marketing readiness re-audit (current owner readback):** Marketing is not verified complete. The product registry for `life-manager-cloud` names `/lm`, the existing $29/month price after a seven-day card-required trial, approved travel-only claims, and the Web funnel events. `ai.anicca.life-manager-daily` is installed-idle on SHA `36881e43` and its latest run is blocked by `resource_effect_unknown`, inherited from the unresolved publish occurrence `life-manager-daily:tiktok-retry-20260918-3`; `lm-loop status --explain` has no provider receipt or official readback, and `lm-loop pre-effect-reconcile life-manager-daily --dry-run` returns `unprovable: claimed_by_other_run`. Do not retry or publish through this fence. The earlier `sqlite3.OperationalError: database is locked` remains an uncorrelated historical stack; it is not the blocker reported by the latest owner receipt. The separate `tiktok-browser` owner is live under PID `2594`; its browser profile remains untouched. The previous 10:15 JST loop still does not implement the requested X/Instagram/Japanese-article cadence, and the last verified Web/Stripe report remains 0 paid subscriptions / `$0` Web MRR. The old `anicca-products/docs/launch/content-reels-life-manager.md` promotes Telegram, phone calls and `$20/month`. The current Remotion asset `skills/video/lm-assets/src/LifeManagerCalendar.tsx` shows English consent copy, a schedule view, and no connected/trial offer. Use only synthetic Calendar data; exclude private event titles, addresses, and calls.

### Task 12: Web-first Japanese Remotion demo

This asset correction proceeds independently from the blocked publication fence. It does not publish or replace any existing video.

**Files:**
- Modify: `skills/video/lm-assets/src/LifeManagerCalendar.tsx`
- Modify: `skills/video/lm-assets/package.json` to render to a new, unique output filename
- Read/Update: this plan and the canonical Life Manager Cloud cursor in `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

**Design:** Render one 15-second 9:16 Japanese demo with synthetic Calendar data. Show the existing `/lm` CTA `Google Calendarに接続`, Google account selection and Calendar permission (including that Gmail is not read), the same-page connected state with the existing seven-day card trial and `$29/month` terms, then a Google Calendar Travel block for a resolvable 15:00 in-person event (40-minute route + five-minute buffer, 14:15 departure). The connected/trial offer appears before the background pass finishes. Do not depict a dashboard, scan screen, rescan action, passive GPS, or unconfigured iMessage capability. Keep the old render intact and write this version to a new filename.

- [x] Step 1: Update the existing composition and render target. Japanese copy matches the current Web flow and all Calendar data is synthetic.
- [x] Step 2: Install only the locked package dependencies if missing; render the new MP4. Readback: 1080×1920, 30 fps, 15 seconds; `renders/life-manager-cloud-web-first-v2.mp4`, 1,194,699 bytes, SHA-256 `e2b0a059384a2e4e58870f8a2fd81dd40d764d32268e0cf0e35f7beb2068e81e`. The unique filename does not overwrite the legacy render path.
- [x] Step 3: Inspect rendered frames at 1.5s, 4.2s, 6.6s, 10.4s, and 13.8s. The CTA, Google permission, connected/trial terms, Travel block, and outro are legible; no dashboard or scan UI appears.
- [~] Step 4: Record render hash and acceptance in the ledger; commit/push the source and plan. No post is sent and the existing TikTok effect fence remains open.

**Marketing TODO and order update:** Old assumption=`fix the reported SQLite lock → update creatives → publish cadence`. New order=`keep the exact TikTok publish fence closed until official provider readback → refresh and render the Web-first creative in parallel → correlate/repair the historical SQLite lock only if a current owner receipt reproduces it → after the customer path and effect fence are clear, resume the authorized cadence experiment → attribute paid invoices, refunds, retention, provider costs, and marketing spend`. Reason: the current daily owner reports `resource_effect_unknown`, not `database_busy`; changing SQLite first would not clear the actual publication fence. The user-directed experiment remains 24 distinct X posts/day, two distinct video masters/day, one distinct Instagram carousel/day, and three original Japanese articles/day, each with a unique angle and `/lm` UTM. This cadence is not a proven conversion forecast; keep every piece useful and distinct, and count only Stripe-confirmed subscriptions toward 345 active `$29` customers (`$10,005` gross MRR).

**Current priority:** Match the Telegram backend flow and the corrected Web paywall contract. After exact Calendar ACTIVE readback, the Web page immediately shows “Calendar connected” plus the card-required seven-day trial offer. The backend starts automatic Travel processing independently. The offer is visible even when the initial pass is pending, returns zero blocks, or the user has no upcoming eligible event. The page never shows a scan spinner, result screen, zero-block screen, or rescan button, and it never claims a block was added before readback. Stripe confirmation, not a Travel block, starts recurring automation.

- [x] **WB-15d.0 — Correct the Web paywall/auto-fill contract.** Calendar ACTIVE plus first-trial eligibility now shows the connected/trial offer regardless of scan status or Travel-block count. Initial setup starts automatically in the background with no scan UI; recurring automation remains gated on Stripe webhook confirmation. Acceptance: focused suites 157/157, scheduler 20/20, synthetic onboarding browser E2E PASS at 390x844 and 1440x900; no Google sign-in, personal Calendar access, or real payment. Source promotion is tracked by the current cursor below.
- [x] **WB-15d.1a — Deploy the existing isolated staging service from main.** `life-call-staging` now tracks `Daisuke134/life-manager:main`; deployment SHA `5de5319c` is SUCCESS, `/health` returns 200, and signed-out `/lm` shows the Calendar connect CTA. Staging Supabase is separate from production.
- [x] **WB-15d.1b — Configure Stripe test mode on staging.** Reuse the active Stripe test key and existing active USD $29/month test price. Create one test webhook for Checkout, Subscription, Invoice, and Refund events; save its signing secret only in the local credential SSOT. Readback confirms test mode, matching price/webhook values, and an enabled endpoint with eight events. No live price, endpoint, or payment changed.
- [~] **WB-15d.1c — Make isolated Google/Calendar E2E ready.** The source-derived Web, message-channel and `lm_ask_log` migrations are applied to staging with RLS/ACL readback. Staging Google Auth remains disabled with zero users; no dedicated non-personal test identity or matching callback is identified. Configure that isolated identity/callback before real OAuth/Calendar E2E. Do not use Dais's personal Google account or Calendar.
- [ ] **WB-15d.2 — Complete real OAuth on mobile Safari.** From aniccaai.com/lm, press Google Calendarに接続; verify Google identity callback, Calendar consent, stable Web-only tenant binding, and return to the connected/paywall screen. The first automatic pass must not be a user action.
- [ ] **WB-15d.3 — Verify automatic Calendar value and existing Telegram ask behavior.** Use an isolated calendar with an eligible in-person event, an online event, and a missing/ambiguous location. Confirm the backend adds one correct Travel block/reminder when possible, does not guess, handles online/offline/location questions for existing Telegram-linked users through ask.js, and creates no duplicates on replay. Zero blocks do not hide the paywall or display a scan result.
- [~] **WB-15d.3b — Add tenant-safe Telegram and iMessage replies for Web-only users.** Task 8/9 source now supports one-use pairing, sender-to-tenant binding, billing-entitled Telegram/iMessage replies and the optional Spectrum Cloud transport; focused Web/provider tests and PostgreSQL channel/ask RLS/ACL integration pass. No Spectrum credentials or Japanese line are configured, so the iMessage button stays hidden until provider readiness and a controlled reply receipt. Keep the Vercel Chat SDK as an OSS reference for new factory apps; do not migrate the proven Telegram webhook in this task. If no route is linked, unresolved events stay unchanged; no email fallback or passive GPS.
- [x] **WB-15d.4 — Verify the immediate connected/paywall UI in source E2E.** At mocked Calendar ACTIVE, the same screen appears before scan results, including while a zero-block response is delayed. It says the manager will add eligible travel time automatically and does not claim a block already exists. No separate value screen, dashboard, chat, home-address question, scan UI, or rescan action. The live provider path remains WB-15d.1c–WB-15d.3.
- [ ] **WB-15d.5 — Finish Checkout through an isolated Stripe test route.** Verify the existing $29/month price, required payment method, seven-day trial, webhook-confirmed entitlement, customer portal, cancellation, expiry, and payment-failure pause. Keep test/live Stripe credentials separate; make no live charge; clean up test subscriptions.
- [ ] **WB-15d.6 — Verify automatic lifecycle and metrics.** The initial Travel pass starts after Calendar ACTIVE; recurring Travel ticks start only after Stripe confirms trial/paid entitlement, stop after cancellation/failure, and preserve existing blocks. Read back auth, Calendar, first Travel block (if eligible), Checkout, trial, invoice, cancellation, and refund without counting internal E2E as customers.
- [~] **WB-15d.7 — Re-read deployed experience.** Production `life-call` deployment SHA `5de5319c` reports `/health` 200 with the same SHA; public `aniccaai.com/lm` and Railway `/lm` show the Google Calendar connect entry. Staging `life-call-staging` is healthy on main SHA `5de5319c` and shows the same signed-out entry. Authenticated connected/paywall/trial states remain unverified live until WB-15d.1c–WB-15d.6 complete.

### Web OAuth callback screenshot regression

- [x] Preserve existing non-Web `lm_users` rows and route the verified Google subject to a stable, separate Web-only UID whenever the canonical UID has a non-null `telegram_chat_id`. Callback and later session resolution both choose the same UID; the old row is read-only.
- [x] Return OAuth failures to `/lm?auth_error=connection` and show a retry message in the existing signed-out page; Safari no longer receives a plain-text body to download as `callback.txt`.
- [x] Verify callback tenant selection and retry state with focused tests and the synthetic browser flow: Web/auth/Calendar/billing suites pass 127/127; browser flow passes at 390x844 and 1440x900. Production proof still requires a dedicated test identity; do not sign into or read a personal Google Calendar.
- [x] Deploy and read back the public failure path: PR #6995 merged as `3f1bd81a77b9001284678888b641aaedb1e3e497`; Railway `life-call` deployment `a973d8c1-3930-4e07-a0a5-6b0c25e72a62` and `/health` both report that SHA. `/lm?auth_error=connection` displays the retry copy, OAuth start returns 302 to Supabase, and a no-code callback returns 302 to the retry page without a text response.
- [ ] WB-15d.2: Verify the successful OAuth callback and Calendar consent with the dedicated E2E identity found or provisioned in WB-15d.1; no personal Google account or Calendar.

### Task 3 corrective gate after fresh read-only review

The review reopened Task 3 because prior tests did not exercise the real initial-scan transport or all Stripe event orders. The source correction and acceptance gate were completed before the production WB-12 readback recorded above; remaining live user-path checks are in the current WB-15d cursor under “After this source plan”.

- [x] Add failing tests for the pre-trial initial Travel write reaching the exact active Google Calendar only while the persisted one-shot scan is still eligible and disconnect/enable fences are clear; confirm they fail before the fix.
- [x] Add failing tests for $0 `invoice.paid`, invoice/subscription reordering, cancellation and late invoice, same-second recovery, competing webhook writes, automation-RPC retry, unlinked new-subscription invoices, zero-block rescan, fresh billing entitlement gates, and claim/read/unclaim retry; confirm they fail before the fix.
- [x] Implement exact-account rescan only while no first Travel/subscription exists; keep subscription status independent from invoice evidence; link subscription IDs only from current checkout/subscription events; retry a new invoice until its subscription is linked; retain cancellation intent; resolve same-second recovery from the exact latest-invoice identity; use atomic revision CAS; recheck persisted billing entitlement before the scheduler enters Travel and immediately before each Calendar write; replay duplicate Web events after transient claim/read/unclaim failures.
- [~] Focused onboarding/billing/scheduler and webhook HTTP integration suites pass (181 tests). Synthetic browser E2E passes at 390x844/1440x900 through zero-block → explicit rescan → Travel offer → Checkout. Stripe TEST API readback now confirms the existing $29/month price, a saved-card seven-day `trialing` subscription, a paid $0 trial invoice, portal-session creation, scheduled cancellation, and final cancellation cleanup. The hosted Checkout page displays the 7-day/$29 terms but headless and direct-CDP submit attempts remain in Stripe's CAPTCHA/Processing state; all test sessions/subscriptions were expired or canceled. No live charge occurred.
- [x] Obtain a fresh read-only review and CI before reopening WB-12. PR #6981 merged as `9fb58c74`; source review and required contract check passed.

Current cursor: PR #7144 merged as `d52c5150` after all same-head required CI passed. Railway production deployment `c34cdedb-e4bb-4468-9c24-68d2636cd77e` is `SUCCESS` and `/health` reports build SHA `d52c5150`; the signed-out `/lm` readback shows `Google Calendarに接続` and states Google identity/Calendar consent is required and Gmail is not read. Source tests pass (ask-iMessage 5/5, Web-first 262/262, full `npm test`, both PostgreSQL integrations, PII scanner, declared Python security tests, source-boundary, and diff-check). Remaining product work: designate a non-personal Google E2E identity, verify real OAuth/Calendar writes and the card-backed Stripe trial lifecycle, verify a controlled Japanese iMessage reply, and read back authenticated states in production. In parallel repair the `life-manager-daily` SQLite admission lock and update stale Cloud creatives; do not replay an uncertain publication or use Dais's personal Google account/Calendar.
