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
- A location question may use an already-linked Telegram route. Do not send a Web location question or trial-ending reminder by email. Show a Messages link only when its business recipient and monitored response owner are verified.
- Demos and published content use synthetic Calendar data. Never expose private event titles, addresses, or voice recordings.
- Do not change the public /lm landing or activate marketing publication from this branch; those remain later SSOT items after the app path and billing are verified.

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

### After this source plan

The public `/lm` page and production retry path are live. PR #6995 deployed the OAuth tenant-isolation fix and Safari callback-download fix. The no-code callback readback proves failure recovery only; a successful Google callback and Calendar consent through a dedicated test identity are still unverified.

**Telegram baseline read from source:** `/start` offers a Calendar connection link; the automatic scheduler's travel tick invokes the shared Travel owner every 30 minutes; the ask engine can ask Telegram-linked users whether an event is online/in-person or ask for a missing location. There is no user-operated scan step in that flow. The Telegram-specific home-address and optional phone/call prompts are not copied into the one-action Web entry. Telegram's `/subscribe` command opens its configured Stripe Payment Link; the Web keeps the owner-specified seven-day card-required trial and existing $29/month offer.

**Scope update:** Per Dais's latest direction, Life Manager marketing work is complete for this phase. No new marketing account, campaign, post, article, or posting-cadence task belongs in this app-completion queue. This records scope; it does not assert that a post was published or revenue generated. The latest recorded 30-day Web/Stripe report remains at zero authenticated users, Calendar connections, Travel blocks, trials, and paid invoices, with gross Web MRR `$0`. The `$10K MRR` target remains unmet.

**Current priority:** Match the Telegram backend flow and the corrected Web paywall contract. After exact Calendar ACTIVE readback, the Web page immediately shows “Calendar connected” plus the card-required seven-day trial offer. The backend starts automatic Travel processing independently. The offer is visible even when the initial pass is pending, returns zero blocks, or the user has no upcoming eligible event. The page never shows a scan spinner, result screen, zero-block screen, or rescan button, and it never claims a block was added before readback. Stripe confirmation, not a Travel block, starts recurring automation.

- [x] **WB-15d.0 — Correct the Web paywall/auto-fill contract.** Calendar ACTIVE plus first-trial eligibility now shows the connected/trial offer regardless of scan status or Travel-block count. Initial setup starts automatically in the background with no scan UI; recurring automation remains gated on Stripe webhook confirmation. Acceptance: focused suites 157/157, scheduler 20/20, synthetic onboarding browser E2E PASS at 390x844 and 1440x900; no Google sign-in, personal Calendar access, or real payment. Source promotion is tracked by the current cursor below.
- [ ] **WB-15d.1 — Prepare isolated staging E2E.** A fresh Railway readback found an existing Anicca `staging` environment with `life-call-staging`, active on the old `docs/lm-mental-life-plan-20260916` branch and using a Supabase project distinct from production. Composio Calendar config is present, but staging has no Stripe secret, price, or webhook secret. The central credential SSOT has an active Stripe test key; Stripe test readback found one active USD $29/month price and four test endpoints, none for `life-call-staging`. Staging Supabase currently has zero auth users and one Web tenant row. No dedicated test Google identity was found in the central SSOT, staging auth inventory, or targeted local/GitHub search; existing Google credentials are not test-labeled. After source merge, repoint staging to main and configure the existing test price plus a staging-only test webhook. Do not use Dais's personal Google account or Calendar, and do not touch live Stripe configuration.
- [ ] **WB-15d.2 — Complete real OAuth on mobile Safari.** From aniccaai.com/lm, press Google Calendarに接続; verify Google identity callback, Calendar consent, stable Web-only tenant binding, and return to the connected/paywall screen. The first automatic pass must not be a user action.
- [ ] **WB-15d.3 — Verify automatic Calendar value and Telegram ask behavior.** Use an isolated calendar with an eligible in-person event, an online event, and a missing/ambiguous location. Confirm the backend adds one correct Travel block/reminder when possible, does not guess, and handles existing Telegram-linked online/offline/location questions through ask.js. Replays create no duplicates. Zero blocks do not hide the paywall or display a scan result.
- [ ] **WB-15d.4 — Verify the immediate connected/paywall UI.** The same screen appears as soon as Calendar is ACTIVE, before scan results, whether there are zero, pending, or confirmed Travel blocks. It says the manager will add eligible travel time automatically; it does not claim an existing block. No separate value screen, dashboard, chat, home-address question, or scan UI.
- [ ] **WB-15d.5 — Finish Checkout through an isolated Stripe test route.** Verify the existing $29/month price, required payment method, seven-day trial, webhook-confirmed entitlement, customer portal, cancellation, expiry, and payment-failure pause. Keep test/live Stripe credentials separate; make no live charge; clean up test subscriptions.
- [ ] **WB-15d.6 — Verify automatic lifecycle and metrics.** The initial Travel pass starts after Calendar ACTIVE; recurring Travel ticks start only after Stripe confirms trial/paid entitlement, stop after cancellation/failure, and preserve existing blocks. Read back auth, Calendar, first Travel block (if eligible), Checkout, trial, invoice, cancellation, and refund without counting internal E2E as customers.
- [ ] **WB-15d.7 — Re-read deployed experience.** Verify the main-derived life-call release and public /lm CTA on mobile and desktop after the provider flow succeeds. Record app build, isolated provider IDs, and test cleanup receipt.

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

Current cursor: source commit/push and PR/CI/merge for WB-15d.0; then provision an isolated Google Calendar and Railway Stripe-test route for WB-15d.1. Synthetic browser acceptance is not live Google or payment proof.
