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

- [x] **Step 1: Write failing freshness tests.** Add fixtures for fresh complete transactions, stale credential status, empty transaction results without completeness proof, and a failed connector. Assert exact status/reason and that stale accounts have `verification.status="stale"`.
- [x] **Step 2: Run the focused tests to verify RED.** Run `node --test lib/moneytree-local-adapter.test.js lib/financial-manager-ingest.test.js lib/financial-manager-report.test.js scripts/personal-cfo-report.test.js`; expected failure is missing freshness classification and false zero output.
- [x] **Step 3: Implement source-status extraction.** Preserve only allowlisted freshness fields from Moneytree `structuredContent.data`; if the provider does not prove transaction completeness or source update time, return `partial`/`unknown`, never `fresh`.
- [x] **Step 4: Propagate status into ingestion and projection.** Do not attach a verified evidence receipt to stale/partial rows; retain last-known balances as stale records and exclude incomplete transaction totals.
- [x] **Step 5: Fix renderers and CLI exit semantics.** `personal-cfo-report.js` must print a source warning and exit nonzero for a stale/partial transaction source; it must still show last-known balance with its timestamp.
- [x] **Step 6: Run focused tests to verify GREEN.** Re-run the commands from Step 2 and assert no `収入 ¥0 / 支出 ¥0` appears for an incomplete source.
- [x] **Step 7: Commit.** `git add apps/life-manager/lib apps/life-manager/scripts && git commit -m "fix(cfo): fail closed on stale moneytree data"`.

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

- [x] **Step 1: Write the canonical-path failing test.** Inject Moneytree account/transaction records, one verified business receipt, one unavailable source, and a notify stub. Assert the daily result contains personal balance, business revenue, source status, and no false zero.
- [x] **Step 2: Run current local CFO tests to capture RED.** Run `node --test scripts/cfo-hourly-local.test.js scripts/cfo-result-local.test.js lib/financial-manager-runtime.test.js`; assert the current default still selects the legacy result path.
- [x] **Step 3: Route the default entrypoint through Financial Manager.** Preserve the existing durable snapshot/receipt/idempotency boundary; move source path wiring into the Financial Manager ingestion call. Keep the old collector behind an explicit compatibility option for one rollback window.
- [x] **Step 4: Set local default cadence to daily.** Keep hourly only when explicitly configured; do not create a second scheduler owner.
- [x] **Step 5: Run focused tests and replay the injected report.** Verify the same digest is quiet on exact replay and delivery without a provider receipt is a failed/unknown-effect result.
- [x] **Step 6: Commit.** `git add apps/life-manager/scripts apps/life-manager/lib/financial-manager-* && git commit -m "feat(cfo): use canonical financial manager locally"`.

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

- [x] **Step 1: Write source-coverage tests.** Cover configured verified source, missing artifact, stale artifact, and empty artifact. Assert missing revenue is `unavailable`/`unknown`, never verified zero.
- [x] **Step 2: Run the focused ingestion/report tests to verify RED.** Run `node --test lib/financial-manager-ingest.test.js lib/financial-manager-report.test.js`.
- [x] **Step 3: Implement `readBusinessReadback()`.** Spawn the existing Python collector with a bounded timeout, require matching `reporting_date`, retain its table digest and receipt refs, and return its coverage gaps without re-summing its monetary cells in JavaScript.
- [x] **Step 4: Wire the readback and normalized test readers.** Use existing artifact paths and adapter output; do not add a second arithmetic implementation. Join source coverage into the report projection.
- [x] **Step 5: Render source-by-source totals and coverage gaps.** Settled revenue, refunds, fees, pending revenue, and unknown gaps remain separate.
- [x] **Step 6: Run focused tests and inspect a JSON report snapshot.** Confirm every displayed total has a receipt or is visibly `未確認`.
- [x] **Step 7: Commit.** `git add apps/life-manager/lib apps/life-manager/scripts && git commit -m "feat(cfo): join settled business source coverage"`.

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

- [x] **Step 1: Write ledger contract tests.** Assert actual nullable amounts, status enum validation, provider/SKU dimensions, secret-shaped metadata rejection, and failed write visibility.
- [x] **Step 2: Write CSV readback tests.** Assert strict header parsing, JPY amounts, invoice-month filtering, tax separation, SHA-256 receipt reference, malformed rows rejected, and absent file returns `unknown` rather than empty settled totals.
- [x] **Step 3: Run tests to verify RED.** Run `node --test lib/ledger.test.js lib/usage-event.test.js lib/google-billing-readback.test.js lib/financial-report-migration.test.js`.
- [x] **Step 4: Add additive migration and ledger writer.** Preserve compatibility for existing `lm_api_cost` rows; map legacy rows to `estimated`/`unknown`, never zero.
- [x] **Step 5: Integrate the Google billing readback path.** Use `LM_CFO_GOOGLE_BILLING_CSV` for a read-only settlement artifact and include estimate-versus-settled variance in the report.
- [x] **Step 6: Run focused tests and a fixture reconciliation.** Assert the September invoice fixture totals by service/SKU and that estimated API usage is not included as settled without the CSV.
- [x] **Step 7: Commit.** `git add apps/life-manager/lib apps/life-manager/migrations && git commit -m "feat(cfo): reconcile provider estimates with billing receipts"`.

### Task 4 follow-up: Include cross-month rows in the selected invoice — NOT DONE

The private September invoice contains a Cloud Storage usage row starting 2026-08-31 and ending 2026-09-30 (JPY 0.000300). `readJapaneseCostTable()` currently filters only on the month of `使用開始日`, omitting the row and making the candidate service subtotal short by JPY 0.000300 even though the header invoice total is correct.

**Files:**
- Modify: `apps/life-manager/lib/google-billing-readback.js`
- Test: `apps/life-manager/lib/google-billing-readback.test.js`

- [ ] **Step 1: Add a failing Japanese Cost Table case.** Add test `Japanese Cost Table includes cross-month rows within the invoice month` using `japaneseCells()`: cross-month Cloud Storage / Archive storage usage 2026-08-31..2026-09-30 costs `0.000300`; September-only usage costs `1.000000`; August-only usage ending 2026-08-31 costs `0.500000`. Set tax and rounding rows to `0` and invoice total to `1.000300`. Assert only the first two usage rows are selected and `totals.costJpy`/`totalJpy` are `1.000300`.
- [ ] **Step 2: Run the focused test and verify RED.** Run `cd apps/life-manager && node --test lib/google-billing-readback.test.js`; the new cross-month assertion must fail because selection currently uses only `使用開始日`'s month.
- [ ] **Step 3: Fix the minimal date selection.** In `readJapaneseCostTable()`, select usage rows whose usage interval overlaps the invoice month, preserving separate tax, rounding, and total handling.
- [ ] **Step 4: Verify GREEN and reconcile the private invoice read-only.** Re-run `cd apps/life-manager && node --test lib/google-billing-readback.test.js`. With the existing private CSV, assert all billed usage rows reconcile to JPY 25,354.451251 and invoice total JPY 27,889; do not store the raw CSV or claim cash payment from the invoice.
- [ ] **Step 5: Commit the parser correction.** Keep this source correction separate from production env/config changes.

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

- [x] **Step 1: Write cache and OpenPOI tests.** Assert normalized address identity, cross-process persistence, TTL, attribution preservation, empty result behavior, and OpenPOI candidate mapping.
- [x] **Step 2: Run tests to verify RED.** Run `node --test lib/geocode-cache.test.js lib/place-search-openpoi.test.js lib/travel-transit-wire.test.js`.
- [x] **Step 3: Add the additive geocode migration/store.** Keep process memory as read-through only; persist successful and bounded negative results with provider/status metadata.
- [x] **Step 4: Wire `travel.js` to persistent geocode cache.** Preserve existing event-scoped route cache and usage events; prove cached route can be served before a paid geocode.
- [x] **Step 5: Wire OpenPOI into `ask.js`.** Store `licenses` and `attributions`; only fall back to Google when no trustworthy candidate exists.
- [x] **Step 6: Run route/ask tests and a read-only OpenPOI probe.** Assert accepted Japan transit calls produce zero Google fallback calls.
- [x] **Step 7: Commit.** `git add apps/life-manager/lib apps/life-manager/migrations && git commit -m "feat(life-manager): persist geocodes and prefer free Japan POI"`.

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

- [x] **Step 1: Write pure budget tests.** Pin `normal`, `warning`, `degraded`, `stopped`, unknown-cost behavior, essential cache reads, and per-tenant isolation.
- [x] **Step 2: Run tests to verify RED.** Run `node --test lib/provider-budget.test.js lib/composio-budget.test.js`.
- [x] **Step 3: Implement budget policy and SQL summary fields.** Keep old Composio thresholds compatible while adding generic provider states.
- [x] **Step 4: Gate Google fallback, nonessential Gemini work, and new paid operations.** Record every deny and cache hit.
- [x] **Step 5: Render budget state in the daily report and run focused tests.**
- [x] **Step 6: Commit.** `git add apps/life-manager/lib apps/life-manager/migrations && git commit -m "feat(cfo): enforce provider budget states"`.

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

- [x] **Step 1: Write delivery tests.** Assert daily cadence, exact replay quiet, partial warning delivery, missing provider receipt as unknown effect, and no blind resend.
- [x] **Step 2: Run tests to verify RED.** Run `node --test scripts/cfo-hourly-local.test.js scripts/cfo-result-local.test.js lib/report-job-adapter.test.js`.
- [x] **Step 3: Route the local default to the canonical Financial Manager path.** Keep compatibility mode explicit and preserve one scheduler owner.
- [x] **Step 4: Wire freshness, business coverage, cost settlement, and budget state into the message/panel payload.**
- [x] **Step 5: Update the launchd template/installer contract for daily local execution.** Do not load or unload launchd in this task.
- [x] **Step 6: Run focused delivery tests and commit.** `git add apps/life-manager && git commit -m "feat(cfo): deliver source-backed daily report"`.

### Task 8: End-to-end acceptance and owner readback

**Latest Moneytree readback (2026-10-04):** the connected plugin returns one MUFG account, but the newest transaction is dated 2026-08-25 and no source update timestamp/completeness cursor is exposed; September/October coverage is missing. Personal balances and flows remain `stale/partial`, not current or zero; the tracked plan intentionally omits exact personal amounts. See `docs/evidence/cfo/2026-10-04-moneytree-mcp-readback.md`.

**Repository cursor (2026-10-05 00:21 JST):** issue [#6549](https://github.com/Daisuke134/life-manager/issues/6549) remains OPEN, updated 2026-10-03T22:53:18Z, with one 👍; the source-change gate is cleared. Candidate branch `docs/lm-cfo-cost-observability-spec-20261002` includes current `origin/main` `82d31995e68a5220b7a288318a893866a24c7ea6`; immediately before this documentation refresh it was clean at `641e0f1120a8cfa59dd05ee36f2b2209d98afa9c`. The unrelated marketing commit `cab8cce811` remains on the branch and must be excluded from any final CFO PR. Task 8A, Task 8B, and the B7 mobile default-path classification fix are complete as candidate source/tests; none is production-loaded. At 00:21 JST the latest local CFO and cloud wakes both defer before effect for resource capacity, with no provider receipt; no production config, enqueue, stop, or send was performed. A separate `codex-money-printer` lease still owns `lm-mobile-metrics-20261003` through 2026-10-04T21:29:23Z; do not edit that worktree or its overlapping mobile implementation while its lease is active.

**Current execution cursor:** unified SSOT §87-J item 5 / §87-AD. The candidate B7 collector defaults to the existing Marketing Metrics file when its environment override is absent; focused module 44/44 and source-boundary checks pass, and independent review found no Critical/Important issue. Correct the fiscal-month interpretation: `--date 2026-09` produced two JPY 592 rows with May/June transaction dates, while fiscal `2026-12` contains a 2026-09-12 JPY 4,250 proceeds row. Its Apple Identifier is not mapped to a current app, so neither report is attributed to current Anicca revenue/B7. RevenueCat's latest complete six-app MRR is JPY 3,196.91 (as of 2026-10-03), but local rows still lack currency/definition; its JPY 3,363.77 calendar-September proceeds metric is not settlement. Next resolve authoritative app/source attribution and remaining business coverage, then fresh Moneytree, before item 6's Google Cost Table reconciliation and OpenPOI UX/cost measurement. The formal promotion sequence remains item 7 because global and project rules currently have no shared path. Do not create a CLI, enqueue endpoint, or use Railway credentials; do not edit the leased mobile-metrics worktree, manually restart, or resend a capacity-deferred occurrence.

**Google billing read correction (2026-10-04 evidence):** the private September invoice CSV exists and its invoice header total matches the provided ¥27,889 invoice, so CSV acquisition is not the current blocker. The live-file parser drops an Aug 31/September overlap row of ¥0.000300; the new Task 4 follow-up above is required before treating its line-item subtotals as reconciled. The CSV is an invoice, not proof of payment. B6 production actual-cost linkage remains unverified/unavailable in the last recorded read; October is only an estimate in §87-Y, not an invoice.

**Files:**
- Create: `apps/life-manager/scripts/cfo-natural-run.test.js`
- Create: `docs/evidence/cfo/2026-10-02-cfo-cost-observability-acceptance.md`
- Modify: `docs/superpowers/specs/2026-10-02-life-manager-cfo-cost-observability-design.md`

**Interfaces:**
- Acceptance bundle contains run ID, release SHA, source statuses, Moneytree observation ref, revenue receipts, Google billing receipt ref, provider cost summary, delivery provider ID, and final digest.

- [x] **Step 1: Add deterministic natural-run harness.** Use real Moneytree MCP read-only calls only when the environment is authenticated; use fixture receipts for disconnected business sources and retain their gaps.
- [x] **Step 2: Run all focused suites.** Run the Task 1–7 commands, then the Life Manager finance/report suites and `npm test` from a clean installed worktree. (CFO suites pass; the full suite has two unrelated marketing caption-guard failures.)
- [x] **Step 3: Execute one local daily close with delivery injected.** Verify actual balance observation, nonzero/unknown transaction semantics, source coverage, cost state, and digest replay.
- [ ] **Step 4: Verify one natural local daily report after source/Google acceptance and Task 8A/8B promotion.** Follow unified SSOT §87-J items 5–7: first reconcile attributable business/mobile/Moneytree source coverage and Google actual cost; then use the formally permitted main-derived release path, confirm source freshness/coverage warnings and a durable Telegram provider receipt, and replay the same JST daily period to prove no second send. Only after this gate, retire the cloud wallet-only sender.
- [ ] **Step 5: Observe seven expected daily periods.** Record cache hit rate, paid calls, budget transitions, source freshness, settled/estimated variance, and report delivery.
- [x] **Step 6: Read back official provider state and finalize evidence.** Mark each spec requirement `proved`, `partial`, or `blocked`; do not claim full CFO completion while any required source remains unknown/stale without an owner-visible reason.
- [x] **Step 7: Commit and push evidence/spec cursor.** `git add apps/life-manager docs/evidence docs/superpowers/specs && git commit -m "docs(cfo): record natural-run acceptance"`.

### Task 8A: Skip repeated local source reads after a verified daily delivery — DONE

This was the prerequisite for Task 8 Step 4. At task start, the local owner woke hourly for capacity recovery and had a stable daily period/destination in `runHourlyCfo`, but invoked ingestion before `deliveryStore.lookup`, allowing a same-day replay to reread Moneytree/B7 after a verified report.

**Files:**
- Modify: `apps/life-manager/scripts/cfo-hourly-local.js`
- Test: `apps/life-manager/scripts/cfo-hourly-local.test.js`

**Contract:**
- For `reportCadence=daily`, if the persisted snapshot is `delivered`, the JST `reportingDate`/period matches, destination channel/hash matches, and a provider receipt is present, return `quiet` before `ingest()` and `notify()`.
- A pending snapshot, missing provider receipt, changed destination, or next JST date must not take the early-return path; pending delivery continues through the existing reconciliation behavior.
- Do not change hourly mode semantics or claim that this source-only task changes production state.

- [x] **Step 1: Add the failing same-day replay test.** RED confirmed the second same-day wake ingested twice instead of once.
- [x] **Step 2: Run the focused test and verify RED.** `node --test apps/life-manager/scripts/cfo-hourly-local.test.js` failed only at the expected duplicate-ingestion assertion (14/15 pass).
- [x] **Step 3: Add the minimal receipt-aware pre-ingest guard.** Pending reconciliation stays first; the guard requires daily cadence, matching JST date/period, matching channel/hash, delivered state, and non-empty provider receipt.
- [x] **Step 4: Verify GREEN and commit.** Focused suite 15/15, `cd apps/life-manager && npm test`, and `git diff --check` PASS. Commit `d6cb0d4070cd9c96d32c0cd25696c88c1d074fe7` pushed; fresh read-only task review Approved. Production state unchanged.

The cloud-report enqueue/UID/DB path is no longer the chosen user-facing sender. Preserve its code/evidence for now; registry/catalog retirement is a later, ordered action after Task 8 Step 4 proves the local replacement in production.

### Task 8B: Give the CFO borrower a revenue-ranked place in the existing queue

The 2026-10-04 21:55/21:57 JST natural wakes were pre-effect `resource_capacity_busy`. At 22:02 JST all eight finite host slots were live. The read-only admission DB showed the CFO waiter retained as `borrow/support` with no unknown effect; 29 eligible deterministic `borrow/support` waiters were ahead of the report. `critical_paid` cannot be assigned to a borrower. Do not change the total cap or preempt owners.

**Files:**
- Modify: `runtime/host/resource_admission.py`
- Test: `runtime/host/tests/test_resource_admission.py`
- Modify: `config/loop-registry.json`
- Test: `runtime/loop/tests/test_macos_loop_registry.py`

**Contract:**
- Set only `life-manager-cfo-hourly` to existing `priority=revenue`, retaining `admission_class=borrow`; do not add a priority enum or schema.
- In queue ranking, preserve the existing effective/age behavior for `admission_class=revenue`; map `borrow/revenue` to a fixed report band after actual revenue and `borrow/support` to a fixed support band after the report.
- Age is only a tie-break inside a borrower band. A borrower must not age into `critical_paid`, and aged support must not jump ahead of revenue or the CFO report.
- Preserve one coalesced CFO queue entry, queue sequence/occurrence identity, total host cap, active claims, and effect-unknown fences. Do not delete or rewrite unrelated waiters.
- The change is source/test only. It does not change the loaded CFO owner or claim that production has run.

- [x] **Step 1: Add failing queue-order and registry tests.** RED was observed for queue ordering and the old CFO registry expectation; tests cover actual-revenue precedence, borrower bands, and preservation of queue identity/sequence.
- [x] **Step 2: Run focused tests to verify RED.** RED confirmed before implementation.
- [x] **Step 3: Implement the minimal class-specific queue bands and set only life-manager-cfo-hourly to borrow/revenue.** Existing schema/priority enum, host caps, owner count, queue sequence, and effect fences are preserved.
- [x] **Step 4: Verify GREEN and contract.** `python3 -m pytest runtime/host/tests/test_resource_admission.py runtime/loop/tests/test_macos_loop_registry.py` passed 269/269; `./bin/lm-loop-contract`, `git diff --check`, and `scripts/verify-source-boundary.sh` passed. Commit `7a8209744693390b251c0e54ba12e26ad08a2457` is pushed to the candidate branch.
- [x] **Step 5: Fresh read-only task review.** Approved; actual paid/revenue precedence is preserved, with no preemption, capacity increase, queue deletion, or effect-fence weakening.

Task 8B completion is candidate-source/test proof only. No production apply, launchd change, admission DB mutation, provider call, or send occurred. The earlier sandboxed CLI test attempt stopped when `/bin/ps` was denied; the same focused suite was rerun successfully in the parent environment. No new CLI was created.

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
