# Life Manager CFO and Provider Cost Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local daily CFO report source-backed for personal balances, business revenue, expenses, and provider costs while failing closed on stale or incomplete data.

**Architecture:** Reuse the existing Moneytree MCP adapter, Financial Manager projection, B7 `loop_pnl.py` receipts, provider usage ledger, route cache, and durable report receipts. Add freshness/coverage metadata, a canonical local report path, settled-cost reconciliation, persistent geocoding, and a budget governor. Personal and Life Manager business owners remain separate; estimates never become settled amounts.

**Tech Stack:** Node.js CommonJS, Python `skills/cfo/loop_pnl.py`, `node:test`, JSONL/Postgres stores, Supabase migrations, Moneytree MCP read-only tools, existing Telegram/email delivery and launchd templates.

**Spec:** `docs/superpowers/specs/2026-10-02-life-manager-cfo-cost-observability-design.md`

## Global Constraints

- Unknown, stale, failed, and `effect_unknown` are explicit states; none may be rendered as zero.
- `dais_personal`, `life_manager`, `transfer`, and `unknown` ownership is preserved in every financial row.
- Moneytree accounts and transactions are read-only; no bank credential mutation, payment, or transfer is performed by this plan.
- `loop_pnl.py` remains the authoritative B7 settled/coverage source until a replacement has equivalent receipt proof.
- Google Cloud Cost table CSV is the settled Google billing source; Cloud Monitoring and API-price calculations remain estimates.
- Raw prompts, credentials, cookies, bank numbers, addresses, and provider payloads are never persisted in observability rows.
- Provider cost events are append-only and include provider, operation, SKU, quantity, estimate/actual status, pricing version, and source receipt.
- Cache hits remain available when a nonessential provider is degraded or stopped.
- No new scheduler owner is activated while an existing owner is still active; cutover requires owner/readback evidence.

## Review Focus

- **Empty Moneytree transactions:** an empty array without completeness/freshness proof must render `未確認`, not ¥0; covered by Task 1 freshness tests.
- **Stale MUFG balance:** a last-known balance must retain its observation time and never be labeled current; covered by Task 1 and Task 8 natural-run tests.
- **Missing business source:** an absent Stripe/affiliate/marketplace artifact must produce a coverage gap, not zero revenue; covered by Task 3 source-coverage tests.
- **Estimated versus settled cost:** API usage estimates must not be added to settled totals without a billing receipt; covered by Task 4 reconciliation tests.
- **Unknown delivery effect:** a provider send without a positive receipt must stop retry/replay and remain reconcilable; covered by Task 7 delivery tests.

---

### Task 1: Make Moneytree freshness and empty coverage truthful

**Files:**
- Modify: `apps/life-manager/lib/moneytree-local-adapter.js`
- Modify: `apps/life-manager/lib/moneytree-observation-store.js`
- Modify: `apps/life-manager/lib/financial-manager-ingest.js`
- Modify: `apps/life-manager/lib/financial-manager-runtime.js`
- Modify: `apps/life-manager/lib/financial-manager-report.js`
- Modify: `apps/life-manager/scripts/personal-cfo-report.js`
- Test: `apps/life-manager/lib/moneytree-local-adapter.test.js`
- Test: `apps/life-manager/lib/financial-manager-ingest.test.js`
- Test: `apps/life-manager/lib/financial-manager-runtime.test.js`
- Test: `apps/life-manager/lib/financial-manager-report.test.js`
- Create: `apps/life-manager/scripts/personal-cfo-report.test.js`

**Interfaces:**
- Produce `classifyMoneytreeObservation(data, { observedAt, now, startDate, endDate }) -> { status, reason, sourceUpdatedAt, transactionCoverage }` in `moneytree-local-adapter.js`.
- Extend the non-enumerable `MONEYTREE_OBSERVATION` payload with `source_status`, `source_updated_at`, `transaction_coverage`, `requested_start`, and `requested_end` without storing raw provider payloads.
- Make `ingestFinancialRecords()` return `sources.moneytree` as `observed_verified`, `stale`, `partial`, `observed_unverified`, or `unavailable`, plus a `sourceFreshness` object.
- Make `renderFinancialManagerTelegram()` display `未確認`/`stale` warnings and never format an incomplete empty transaction set as ¥0.

- [ ] **Step 1: Write failing freshness tests.** Add fixtures for fresh complete transactions, stale credential status, empty transaction results without completeness proof, and a failed connector. Assert exact status/reason and that stale accounts have `verification.status="stale"`.
- [ ] **Step 2: Run the focused tests to verify RED.** Run `node --test lib/moneytree-local-adapter.test.js lib/financial-manager-ingest.test.js lib/financial-manager-report.test.js scripts/personal-cfo-report.test.js`; expected failure is missing freshness classification and false zero output.
- [ ] **Step 3: Implement source-status extraction.** Preserve only allowlisted freshness fields from Moneytree `structuredContent.data`; if the provider does not prove transaction completeness or source update time, return `partial`/`unknown`, never `fresh`.
- [ ] **Step 4: Propagate status into ingestion and projection.** Do not attach a verified evidence receipt to stale/partial rows; retain last-known balances as stale records and exclude incomplete transaction totals.
- [ ] **Step 5: Fix renderers and CLI exit semantics.** `personal-cfo-report.js` must print a source warning and exit nonzero for a stale/partial transaction source; it must still show last-known balance with its timestamp.
- [ ] **Step 6: Run focused tests to verify GREEN.** Re-run the commands from Step 2 and assert no `収入 ¥0 / 支出 ¥0` appears for an incomplete source.
- [ ] **Step 7: Commit.** `git add apps/life-manager/lib apps/life-manager/scripts && git commit -m "fix(cfo): fail closed on stale moneytree data"`.

### Task 2: Make Financial Manager the canonical local daily path

**Files:**
- Modify: `apps/life-manager/scripts/cfo-hourly-local.js`
- Modify: `apps/life-manager/scripts/cfo-result-local.js`
- Modify: `apps/life-manager/lib/financial-manager-report.js`
- Modify: `apps/life-manager/scripts/cfo-hourly-local.test.js`
- Modify: `apps/life-manager/scripts/cfo-result-local.test.js`
- Test: `apps/life-manager/lib/financial-manager-runtime.test.js`

**Interfaces:**
- `runHourlyCfo(options)` is the canonical local report entrypoint and accepts `ingest`, `notify`, `now`, `reportCadence`, `agentReceiptPaths`, `marketplaceReceiptPaths`, `affiliateReadbackPath`, `capafyAnalyticsPath`, and `mobileAppsBusinessOutcomesPath`.
- The legacy `loop_pnl.py` result summary remains callable only as an explicit compatibility collector; it is not the default local report engine.
- The canonical result contains `personal`, `business`, `sourceFreshness`, `economicSourceCoverage`, `digest`, and delivery receipt fields.

- [ ] **Step 1: Write the canonical-path failing test.** Inject Moneytree account/transaction records, one verified business receipt, one unavailable source, and a notify stub. Assert the daily result contains personal balance, business revenue, source status, and no false zero.
- [ ] **Step 2: Run current local CFO tests to capture RED.** Run `node --test scripts/cfo-hourly-local.test.js scripts/cfo-result-local.test.js lib/financial-manager-runtime.test.js`; assert the current default still selects the legacy result path.
- [ ] **Step 3: Route the default entrypoint through Financial Manager.** Preserve the existing durable snapshot/receipt/idempotency boundary; move source path wiring into the Financial Manager ingestion call. Keep the old collector behind an explicit compatibility option for one rollback window.
- [ ] **Step 4: Set local default cadence to daily.** Keep hourly only when explicitly configured; do not create a second scheduler owner.
- [ ] **Step 5: Run focused tests and replay the injected report.** Verify the same digest is quiet on exact replay and delivery without a provider receipt is a failed/unknown-effect result.
- [ ] **Step 6: Commit.** `git add apps/life-manager/scripts apps/life-manager/lib/financial-manager-* && git commit -m "feat(cfo): use canonical financial manager locally"`.

### Task 3: Join all configured settled business sources without inventing zeros

**Files:**
- Modify: `apps/life-manager/lib/financial-manager-ingest.js`
- Modify: `apps/life-manager/lib/financial-manager-report.js`
- Modify: `apps/life-manager/scripts/cfo-hourly-local.js`
- Modify: `apps/life-manager/scripts/cfo-result-local.js`
- Create: `apps/life-manager/lib/financial-business-readback.js`
- Test: `apps/life-manager/lib/financial-business-readback.test.js`
- Test: `apps/life-manager/lib/financial-manager-ingest.test.js`
- Test: `apps/life-manager/lib/financial-manager-report.test.js`
- Test: `apps/life-manager/scripts/cfo-hourly-local.test.js`

**Interfaces:**
- `readBusinessReadback({ reportingDate, trailingStart, pythonBin, env }) -> { table, observedAt, sourceReceiptRefs, coverageGaps }` runs the existing `skills/cfo/loop_pnl.py --json` artifact collector and never converts an `unknown` cell to zero.
- `financial-manager-ingest.js` accepts `readBusinessReadback` and includes its receipt-backed business summary in `economicSourceCoverage`; test doubles supply normalized FinancialRecords only for source-specific projection tests.
- Add `businessSourceCoverage` entries with `source`, `state`, `observedAt`, `receiptCount`, and `gapReason`.
- Continue using `skills/cfo/loop_pnl.py` for B7 sources that do not yet have a Node FinancialRecord adapter; preserve its receipt-backed `economic_attribution` as a separate business snapshot.

- [ ] **Step 1: Write source-coverage tests.** Cover configured verified source, missing artifact, stale artifact, and empty artifact. Assert missing revenue is `unavailable`/`unknown`, never verified zero.
- [ ] **Step 2: Run the focused ingestion/report tests to verify RED.** Run `node --test lib/financial-manager-ingest.test.js lib/financial-manager-report.test.js`.
- [ ] **Step 3: Implement `readBusinessReadback()`.** Spawn the existing Python collector with a bounded timeout, require matching `reporting_date`, retain its table digest and receipt refs, and return its coverage gaps without re-summing its monetary cells in JavaScript.
- [ ] **Step 4: Wire the readback and normalized test readers.** Use existing artifact paths and adapter output; do not add a second arithmetic implementation. Join source coverage into the report projection.
- [ ] **Step 5: Render source-by-source totals and coverage gaps.** Settled revenue, refunds, fees, pending revenue, and unknown gaps remain separate.
- [ ] **Step 6: Run focused tests and inspect a JSON report snapshot.** Confirm every displayed total has a receipt or is visibly `未確認`.
- [ ] **Step 7: Commit.** `git add apps/life-manager/lib apps/life-manager/scripts && git commit -m "feat(cfo): join settled business source coverage"`.

### Task 4: Add actual-versus-estimated provider cost and Google settlement import

**Files:**
- Create: `apps/life-manager/lib/google-billing-readback.js`
- Create: `apps/life-manager/lib/google-billing-readback.test.js`
- Modify: `apps/life-manager/lib/ledger.js`
- Modify: `apps/life-manager/lib/usage-event.js`
- Modify: `apps/life-manager/lib/financial-manager-ingest.js`
- Modify: `apps/life-manager/lib/financial-manager-report.js`
- Create: `apps/life-manager/migrations/2026-10-02-lm-provider-cost-settlement.sql`
- Modify: `apps/life-manager/lib/financial-report-migration.test.js`

**Interfaces:**
- `recordProviderCost({ uid, provider, product, sku, operation, quantity, unit, estimatedUsd, actualUsd, billingStatus, pricingVersion, sourceReceiptRef, meta }, deps) -> Promise<boolean>`.
- `readGoogleBillingCsv(filePath, { invoiceMonth, observedAt }) -> { rows, receiptRef, totals, status }`.
- `billingStatus` is `estimated`, `settled`, `unknown`, or `not_applicable`; missing actual billing remains `null`.

- [ ] **Step 1: Write ledger contract tests.** Assert actual nullable amounts, status enum validation, provider/SKU dimensions, secret-shaped metadata rejection, and failed write visibility.
- [ ] **Step 2: Write CSV readback tests.** Assert strict header parsing, JPY amounts, invoice-month filtering, tax separation, SHA-256 receipt reference, malformed rows rejected, and absent file returns `unknown` rather than empty settled totals.
- [ ] **Step 3: Run tests to verify RED.** Run `node --test lib/ledger.test.js lib/usage-event.test.js lib/google-billing-readback.test.js lib/financial-report-migration.test.js`.
- [ ] **Step 4: Add additive migration and ledger writer.** Preserve compatibility for existing `lm_api_cost` rows; map legacy rows to `estimated`/`unknown`, never zero.
- [ ] **Step 5: Integrate the Google billing readback path.** Use `LM_CFO_GOOGLE_BILLING_CSV` for a read-only settlement artifact and include estimate-versus-settled variance in the report.
- [ ] **Step 6: Run focused tests and a fixture reconciliation.** Assert the September invoice fixture totals by service/SKU and that estimated API usage is not included as settled without the CSV.
- [ ] **Step 7: Commit.** `git add apps/life-manager/lib apps/life-manager/migrations && git commit -m "feat(cfo): reconcile provider estimates with billing receipts"`.

### Task 5: Persist geocodes and enforce the free-provider lane

**Files:**
- Create: `apps/life-manager/lib/geocode-cache.js`
- Create: `apps/life-manager/lib/geocode-cache.test.js`
- Create: `apps/life-manager/lib/place-search-openpoi.js`
- Create: `apps/life-manager/lib/place-search-openpoi.test.js`
- Modify: `apps/life-manager/lib/travel.js`
- Modify: `apps/life-manager/lib/ask.js`
- Create: `apps/life-manager/migrations/2026-10-02-lm-geocode-cache.sql`
- Modify: `apps/life-manager/lib/travel-transit-wire.test.js`

**Interfaces:**
- `normalizeGeocodeAddress(value) -> string`.
- `createSupabaseGeocodeStore({ supaUrl, supaKey, fetchImpl }) -> { get(key), put(key, value) }`.
- `searchOpenPoi(query, { center, radius, limit, fetchImpl }) -> { candidates, attributions, observedAt }`.
- `ask.js` uses OpenPOI first for Japan facility resolution; Google is an explicit budget-authorized fallback.

- [ ] **Step 1: Write cache and OpenPOI tests.** Assert normalized address identity, cross-process persistence, TTL, attribution preservation, empty result behavior, and OpenPOI candidate mapping.
- [ ] **Step 2: Run tests to verify RED.** Run `node --test lib/geocode-cache.test.js lib/place-search-openpoi.test.js lib/travel-transit-wire.test.js`.
- [ ] **Step 3: Add the additive geocode migration/store.** Keep process memory as read-through only; persist successful and bounded negative results with provider/status metadata.
- [ ] **Step 4: Wire `travel.js` to persistent geocode cache.** Preserve existing event-scoped route cache and usage events; prove cached route can be served before a paid geocode.
- [ ] **Step 5: Wire OpenPOI into `ask.js`.** Store `licenses` and `attributions`; only fall back to Google when no trustworthy candidate exists.
- [ ] **Step 6: Run route/ask tests and a read-only OpenPOI probe.** Assert accepted Japan transit calls produce zero Google fallback calls.
- [ ] **Step 7: Commit.** `git add apps/life-manager/lib apps/life-manager/migrations && git commit -m "feat(life-manager): persist geocodes and prefer free Japan POI"`.

### Task 6: Enforce provider budgets and observability summaries

**Files:**
- Create: `apps/life-manager/lib/provider-budget.js`
- Create: `apps/life-manager/lib/provider-budget.test.js`
- Modify: `apps/life-manager/lib/composio-budget.js`
- Modify: `apps/life-manager/lib/usage-event.js`
- Modify: `apps/life-manager/migrations/2026-09-06-lm-usage-cost-summary.sql`
- Modify: `apps/life-manager/lib/travel.js`
- Modify: `apps/life-manager/lib/ask.js`
- Modify: `apps/life-manager/lib/financial-manager-report.js`

**Interfaces:**
- `evaluateProviderBudget({ measuredUsd, estimatedUsd, unknownCount, thresholds }) -> { state, totalUsd, reasons }`.
- `authorizeProviderOperation({ tenantId, provider, operation, essential, cacheHit }, deps) -> { allowed, state, reason }`.
- Budget summary includes event count, provider units, cache hits, estimates, settled amounts, unknown count, and last observation.

- [ ] **Step 1: Write pure budget tests.** Pin `normal`, `warning`, `degraded`, `stopped`, unknown-cost behavior, essential cache reads, and per-tenant isolation.
- [ ] **Step 2: Run tests to verify RED.** Run `node --test lib/provider-budget.test.js lib/composio-budget.test.js`.
- [ ] **Step 3: Implement budget policy and SQL summary fields.** Keep old Composio thresholds compatible while adding generic provider states.
- [ ] **Step 4: Gate Google fallback, nonessential Gemini work, and new paid operations.** Record every deny and cache hit.
- [ ] **Step 5: Render budget state in the daily report and run focused tests.**
- [ ] **Step 6: Commit.** `git add apps/life-manager/lib apps/life-manager/migrations && git commit -m "feat(cfo): enforce provider budget states"`.

### Task 7: Make daily delivery source-backed and idempotent

**Files:**
- Modify: `apps/life-manager/scripts/cfo-hourly-local.js`
- Modify: `apps/life-manager/scripts/cfo-result-local.js`
- Modify: `apps/life-manager/lib/cfo-report-delivery.js`
- Modify: `apps/life-manager/lib/report-job-adapter.js`
- Modify: `apps/life-manager/scripts/cfo-hourly-local.test.js`
- Modify: `apps/life-manager/scripts/cfo-result-local.test.js`
- Modify: `apps/life-manager/lib/report-job-adapter.test.js`
- Modify: `apps/life-manager/launchd/ai.anicca.life-manager-financial-report.plist.template`
- Modify: `apps/life-manager/scripts/install-financial-report-launchd.sh`

**Interfaces:**
- Canonical local entrypoint: `runHourlyCfo(options) -> { status, reason, reportingDate, report, sourceFreshness, providerMessageId }`.
- Delivery accepts only a positive provider receipt and records one period-keyed durable receipt.
- Partial source reports are delivered with explicit warnings; unavailable sources produce an owner-visible failure receipt and no false financial totals.

- [ ] **Step 1: Write delivery tests.** Assert daily cadence, exact replay quiet, partial warning delivery, missing provider receipt as unknown effect, and no blind resend.
- [ ] **Step 2: Run tests to verify RED.** Run `node --test scripts/cfo-hourly-local.test.js scripts/cfo-result-local.test.js lib/report-job-adapter.test.js`.
- [ ] **Step 3: Route the local default to the canonical Financial Manager path.** Keep compatibility mode explicit and preserve one scheduler owner.
- [ ] **Step 4: Wire freshness, business coverage, cost settlement, and budget state into the message/panel payload.**
- [ ] **Step 5: Update the launchd template/installer contract for daily local execution.** Do not load or unload launchd in this task.
- [ ] **Step 6: Run focused delivery tests and commit.** `git add apps/life-manager && git commit -m "feat(cfo): deliver source-backed daily report"`.

### Task 8: End-to-end acceptance and owner readback

**Files:**
- Create: `apps/life-manager/scripts/cfo-natural-run.test.js`
- Create: `docs/evidence/cfo/2026-10-02-cfo-cost-observability-acceptance.md`
- Modify: `docs/superpowers/specs/2026-10-02-life-manager-cfo-cost-observability-design.md`

**Interfaces:**
- Acceptance bundle contains run ID, release SHA, source statuses, Moneytree observation ref, revenue receipts, Google billing receipt ref, provider cost summary, delivery provider ID, and final digest.

- [ ] **Step 1: Add deterministic natural-run harness.** Use real Moneytree MCP read-only calls only when the environment is authenticated; use fixture receipts for disconnected business sources and retain their gaps.
- [ ] **Step 2: Run all focused suites.** Run the Task 1–7 commands, then the Life Manager finance/report suites and `npm test` from a clean installed worktree.
- [ ] **Step 3: Execute one local daily close with delivery injected.** Verify actual balance observation, nonzero/unknown transaction semantics, source coverage, cost state, and digest replay.
- [ ] **Step 4: Execute one cloud report canary.** Verify the runtime job, database receipt, provider message ID, and no duplicate on replay.
- [ ] **Step 5: Observe seven expected daily periods.** Record cache hit rate, paid calls, budget transitions, source freshness, settled/estimated variance, and report delivery.
- [ ] **Step 6: Read back official provider state and finalize evidence.** Mark each spec requirement `proved`, `partial`, or `blocked`; do not claim full CFO completion while any required source remains unknown/stale without an owner-visible reason.
- [ ] **Step 7: Commit and push evidence/spec cursor.** `git add apps/life-manager docs/evidence docs/superpowers/specs && git commit -m "docs(cfo): record natural-run acceptance"`.

## Verification Commands

```bash
cd apps/life-manager
node --test lib/moneytree-local-adapter.test.js lib/financial-manager-ingest.test.js lib/financial-manager-report.test.js
node --test lib/financial-manager-runtime.test.js lib/financial-report-snapshot.test.js
node --test lib/ledger.test.js lib/usage-event.test.js lib/route-cache.test.js lib/travel-transit-wire.test.js
node --test scripts/cfo-hourly-local.test.js scripts/cfo-result-local.test.js lib/report-job-adapter.test.js
npm test
git diff --check
```
