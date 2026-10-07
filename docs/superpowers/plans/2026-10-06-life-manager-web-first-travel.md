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

- [ ] Step 1: Add failing page/auth/calendar tests for the exact CTA, automatic Calendar OAuth continuation, automatic first scan, combined offer, zero-block state without Checkout, and absence of dashboard/home-address/chat UI.
- [ ] Step 2: Run those focused tests and confirm the expected states are missing.
- [ ] Step 3: Implement the single-action flow and server-rendered states. Keep the optional Messages link hidden until its recipient and response owner are verified.
- [ ] Step 4: Run the focused auth/calendar/page tests at mobile and desktop viewport sizes in the browser harness.

### Task 3: Card-required seven-day Stripe trial and subscription lifecycle

**Files:**
- Create: apps/life-manager/lib/web-billing.js
- Create: apps/life-manager/lib/web-billing.test.js
- Modify: apps/life-manager/lib/billing.js
- Modify: apps/life-manager/lib/billing.test.js
- Modify: apps/life-manager/server.js
- Modify: apps/life-manager/lib/web-page.js
- Test: apps/life-manager/lib/stripe-webhook-signature.test.js

**Interfaces:**
- createWebTrialCheckout(uid, user, opts) returns { url, trialEnd }, uses only the configured existing $29/month price, collects a payment method, starts a seven-day subscription trial, and uses a verified Web uid for Stripe correlation.
- Checkout is unavailable until the initial Calendar scan has confirmed a Travel block; a uid with a prior or canceled trial cannot receive another trial.
- The webhook grants Web automation only for a valid trialing subscription with a retained payment method or a verified paid invoice. Web past_due, cancellation, and failed payment pause future Calendar work; Telegram grace behavior remains unchanged.
- A customer-portal session lets a user cancel/manage billing without a Life Manager dashboard. No Life Manager trial-ending reminder email is sent.

- [ ] Step 1: Add failing Checkout tests for the existing price, seven-day trial, required payment method, exact uid metadata, blocked zero-block users, and idempotent repeated requests.
- [ ] Step 2: Add failing webhook tests for trial activation, paid invoice, payment failure, cancellation, duplicate/out-of-order events, Web past-due pause, and unchanged Telegram grace.
- [ ] Step 3: Run focused billing tests and confirm these Web-specific behaviors are missing.
- [ ] Step 4: Implement Checkout, portal, webhook reconciliation, and the scheduled-travel entitlement gate.
- [ ] Step 5: Run focused billing/web tests with Stripe test-mode fixtures and a browser Checkout flow; verify no live charge.

### Task 4: Funnel, cost, and revenue evidence

**Files:**
- Reuse: apps/life-manager/lib/web-attribution.js
- Modify only if needed: apps/life-manager/lib/usage-event.js and apps/life-manager/lib/ledger.js
- Create only if no existing read-only reporter provides the same measures: apps/life-manager/scripts/lm-web-funnel-report.js
- Test: focused existing Web attribution/cost tests plus one new report test if a new reporter is required

**Interfaces:**
- Group acquisition by the signed first-touch UTM, then count Google auth, Calendar ACTIVE, first Travel block, Checkout, trialing, first paid invoice, renewal, cancellation, refund, and D7/D30 retention.
- Report gross MRR separately from Stripe-net receipts and contribution after refunds, Stripe fees, route/provider, hosting, and attributed marketing spend.
- Do not infer a paid customer from a trial or a Stripe checkout redirect.

- [ ] Step 1: Read the existing attribution and cost rows and identify any missing funnel event before adding schema.
- [ ] Step 2: Add the smallest failing focused test only if the current records cannot produce the required metric.
- [ ] Step 3: Implement a read-only report using existing ledgers first; add no second scheduler or user-facing dashboard.
- [ ] Step 4: Run the focused reporter tests and compare the output with Stripe test-mode and synthetic Calendar receipts.

## After this source plan

Continue the canonical SSOT cursor: complete safe Google signup/Calendar E2E with a dedicated test identity; pass source acceptance/review/CI and merge; apply only a main-derived immutable Railway release; verify /lm, Stripe test/live settings, and official readbacks; update the separate anicca-products landing; create/warm the dedicated Life Manager Cloud social accounts; then activate the existing marketing assets through one measured owner. Keep public posting disabled until the end-to-end onboarding and billing path is verified.
