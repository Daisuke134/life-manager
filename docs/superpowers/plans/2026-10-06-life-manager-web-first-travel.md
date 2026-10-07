# Life Manager Cloud Web-First Travel Implementation Plan

> For agentic workers: Execute inline with superpowers:executing-plans. Work task-by-task in this dedicated worktree; do not modify production state from this branch.

**Goal:** Replace the current address/dashboard/three-day flow with a one-button Google Calendar connection, one automatic initial Travel scan, a single connected/trial-offer screen, and a verified seven-day Stripe trial on the existing $29/month price.

**Architecture:** Keep Google identity verification and Calendar consent as separate provider steps behind one user action. Use the existing exact-tenant Web auth, Calendar binding, travel owner, dedupe ledger, Stripe webhook, and attribution contracts. The initial Calendar scan is one-shot; scheduled Calendar work starts only after Stripe confirms a card-backed trial or paid subscription.

**Tech Stack:** CommonJS Node.js HTTP server, Supabase Auth/PostgREST/RPC, Composio Google Calendar, existing travel engine, Stripe Checkout/Billing, Node test runner, browser-based E2E with synthetic Calendar data.

**Spec:** docs/superpowers/specs/2026-10-06-life-manager-web-first-travel-design.md; ordered delivery cursor: docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md.

## Global Constraints

- Serve the Web product at LM_PANEL_BASE/lm; the Google Calendar is the customer's daily surface.
- The page has no dashboard, chat thread, home-address question, Life Manager password, Gmail access, or browser location request.
- The first CTA says Google Calendarに接続; Google account verification and Calendar permission remain required.
- Preserve the existing $29/month Stripe price. Use a seven-day, card-required subscription trial; do not activate a trial before at least one Travel block is confirmed.
- A one-time initial scan may write Travel blocks before Checkout. Periodic scans start only after Stripe confirms the trial/subscription and payment method.
- The Stripe webhook remains the sole writer of lm_users.paid. Web cancel/payment failure pauses future Calendar reads/writes and preserves existing Travel blocks. Preserve existing Telegram billing behavior.
- Reuse the shared travel owner, exact ACTIVE Calendar account, event-level effect fences, route cache, and duplicate prevention. Never guess an unknown origin or destination.
- A location question may use an already-linked Telegram route. Do not send a Web location question or trial-ending reminder by email. Show a Messages link only when its business recipient and monitored response owner are verified.
- Demos and published content use synthetic Calendar data. Never expose private event titles, addresses, or voice recordings.
- Do not change the public /lm landing or activate marketing publication from this branch; those remain later SSOT items after the app path and billing are verified.

## Review Focus

- Expired, missing, or replayed OAuth state never creates a tenant session.
- A stale, foreign, changed, or non-ACTIVE Calendar account never triggers a Calendar read or write.
- No saved base and no recent physical Calendar event means no guessed route, no Travel block, and no trial offer.
- A zero-block scan never starts Checkout or scheduled automation; an uncertain provider write stays fenced until exact Calendar readback.
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

### Task 2: Single-action Calendar onboarding and one combined result/offer screen

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
- A successful Calendar callback starts the one-time scan automatically. The client may show only an in-place loading state while that request runs.
- renderWebPage(model) renders the signed-out CTA, scan/loading, compact zero-block state, combined connected/trial offer, or trial-active confirmation; it never renders the old dashboard.

- [x] Step 1: Add failing page/auth/calendar tests for the exact CTA, automatic Calendar OAuth continuation, automatic first scan, combined offer, zero-block state without Checkout, Messages visibility, and absence of dashboard/home-address/chat UI.
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
- Checkout is unavailable until the initial Calendar scan has confirmed a Travel block. A first-time eligible uid receives one seven-day card-required trial; a prior trial or canceled subscription can restart only on an explicit no-trial $29/month Checkout, charged at start.
- The webhook grants Web automation only for a valid trialing subscription with a retained payment method or a verified paid invoice. Web past_due, cancellation, and failed payment pause future Calendar work; Telegram grace behavior remains unchanged.
- A customer-portal session lets a user cancel/manage billing without a Life Manager dashboard. No Life Manager trial-ending reminder email is sent.
- The scheduled travel path rejects unpaid, expired-trial, canceled, or failed-payment Web tenants before Calendar event reads; the one-time pre-trial scan and Telegram behavior remain unchanged.
- Web Travel events set a zero-minute Google Calendar popup reminder, and the initial scan only counts a confirmed Travel block after its reminder is read back. The official Composio `GOOGLECALENDAR_CREATE_EVENT` schema has no `reminders` field, so the Web-only event write uses Composio's authenticated proxy against the same exact connected account; it never extracts or stores Google's OAuth token. This makes the post-onboarding notification claim match the event we create.
- A live Stripe API key can never verify a webhook with the test-mode endpoint secret.

- [x] Step 1: Add failing Checkout tests for the existing price, first seven-day trial, required payment method, exact uid metadata, blocked zero-block/active users, no-trial paid restart after trial/cancellation, and idempotent repeated requests.
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
- Create: apps/life-manager/migrations/2026-10-08-zz-lm-web-funnel-events.sql
- Modify: apps/life-manager/server.js, apps/life-manager/lib/web-auth.js, apps/life-manager/lib/web-calendar.js, apps/life-manager/lib/web-travel.js, apps/life-manager/lib/web-billing.js for server-side funnel events
- Create: apps/life-manager/scripts/lm-web-funnel-report.js
- Test: apps/life-manager/lib/ask-usage.test.js, apps/life-manager/lib/usage-event.test.js, apps/life-manager/lib/travel.test.js, apps/life-manager/lib/web-auth.test.js, apps/life-manager/lib/web-calendar.test.js, apps/life-manager/lib/web-travel.test.js, apps/life-manager/lib/web-billing.test.js

**Interfaces:**
- Places lookup accepts tenant uid and an optional usage writer, records one privacy-safe provider-usage row per billable success, and makes at most three Places Text Search calls per Calendar event. It never records the query, event title, address, or response text.
- The funnel event writer accepts an allowlisted lifecycle event, bounded first-touch UTM values, an optional opaque Web uid, an optional provider-object/event id, and optional amount/currency; it writes append-only rows to `lm_web_funnel_events` with service-role access only.
- The report joins anonymous landing/connect counts to Web users, Stripe events/subscriptions/invoices/refunds, and per-user `lm_api_cost` estimates. It separates estimated provider cost from verified Stripe fees/refunds and labels unavailable marketing/hosting allocations as unavailable.
- Group acquisition by signed first-touch UTM; count Google auth, Calendar ACTIVE, first Travel block, Checkout creation, trialing, positive first paid invoice, renewals, cancellations, refunds, and mature D7/D30 retention. Stripe is the billing source of truth; Checkout redirects and trial rows are not paid revenue.
- Report gross MRR separately from settled receipts, refunds, Stripe fees, estimated route/provider cost, hosting, and attributed marketing spend.
- Do not infer a paid customer from a trial or a Stripe checkout redirect.

- [x] Step 1: Read the current records. `lm_users` holds first-touch UTM and current Calendar/billing state; `lm_api_cost` holds tenant provider estimates; `lm_stripe_events` has only Stripe event id/type/receive time. No persistent Web page-view/connect-start events or historical invoice/refund attribution exists.
- [x] Step 2: Verify Google Maps and Gemini list prices from official documentation. A successful Places Text Search (Legacy) request estimates $0.040 after free caps ($0.032 base + $0.003 Contact Data + $0.005 Atmosphere Data; Basic Data is unlimited). Keep estimates labeled estimated; do not claim provider-bill actuals from list price.
- [x] Step 3 (RED): Focused tests fail on the missing 3-call Places cap, tenant usage event, route-fallback uid propagation, funnel event writer, lifecycle hooks, Stripe event mapping, and read-only report.
- [x] Step 4 (GREEN): Add Places metering/cap and thread uid through the existing route fallback. Extend the Maps SKU allowlist and pricing version without changing Calendar or Stripe entitlement behavior.
- [x] Step 5 (RED/GREEN): Add the append-only funnel migration and instrument `landing_view`, `google_connect_start`, `google_authenticated`, `calendar_active`, `first_travel_block`, `checkout_created`, `trial_started`, `paid_invoice`, `cancellation_requested`, `subscription_canceled`, and successful `refund_recorded`. No IP, user-agent, event titles, addresses, Gmail, or raw URLs are recorded.
- [x] Step 6 (source): Implement a read-only report over Web users, funnel events, usage rows, current Stripe subscriptions, and attributable Stripe balance transactions. D7/D30 are labeled current paid-subscription retention; provider actuals and unallocated hosting/marketing remain null.
- [~] Step 7: Source acceptance passes 238/238 focused tests, synthetic browser onboarding E2E at 390x844/1440x900, `node --check` on changed JavaScript, and `git diff --check`. Remaining: test migration/ACL on the target project after merge, run the report against read-only production data, refresh live Stripe/Composio readbacks, and exercise TEST-mode refund/trial lifecycle. No live price or live charge changed in WB-12 source work.

## After this source plan

Continue the canonical SSOT cursor: complete safe Google signup/Calendar E2E with a dedicated test identity; pass source acceptance/review/CI and merge; apply only a main-derived immutable Railway release; verify /lm, Stripe test/live settings, and official readbacks; update the separate anicca-products landing; create/warm the dedicated Life Manager Cloud social accounts; then activate the existing marketing assets through one measured owner. Keep public posting disabled until the end-to-end onboarding and billing path is verified.

### Task 3 corrective gate after fresh read-only review

The review reopened Task 3; previous test results did not exercise the real initial-scan transport or all Stripe event orders. Current order:

- [x] Add failing tests for the pre-trial initial Travel write reaching the exact active Google Calendar only while the persisted one-shot scan is still eligible and disconnect/enable fences are clear; confirm they fail before the fix.
- [x] Add failing tests for $0 `invoice.paid`, invoice/subscription reordering, cancellation and late invoice, same-second recovery, competing webhook writes, automation-RPC retry, unlinked new-subscription invoices, zero-block rescan, fresh billing entitlement gates, and claim/read/unclaim retry; confirm they fail before the fix.
- [x] Implement exact-account rescan only while no first Travel/subscription exists; keep subscription status independent from invoice evidence; link subscription IDs only from current checkout/subscription events; retry a new invoice until its subscription is linked; retain cancellation intent; resolve same-second recovery from the exact latest-invoice identity; use atomic revision CAS; recheck persisted billing entitlement before the scheduler enters Travel and immediately before each Calendar write; replay duplicate Web events after transient claim/read/unclaim failures.
- [~] Focused onboarding/billing/scheduler and webhook HTTP integration suites pass (181 tests). Synthetic browser E2E passes at 390x844/1440x900 through zero-block → explicit rescan → Travel offer → Checkout. Stripe TEST API readback now confirms the existing $29/month price, a saved-card seven-day `trialing` subscription, a paid $0 trial invoice, portal-session creation, scheduled cancellation, and final cancellation cleanup. The hosted Checkout page displays the 7-day/$29 terms but headless and direct-CDP submit attempts remain in Stripe's CAPTCHA/Processing state; all test sessions/subscriptions were expired or canceled. No live charge occurred.
- [ ] Obtain a fresh read-only review and CI before reopening WB-12.

Current cursor: repeat Stripe TEST-mode verification → fresh read-only review → CI; WB-12 remains next after those source gates.
