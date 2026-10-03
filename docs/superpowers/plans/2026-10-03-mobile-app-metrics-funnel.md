# Mobile App Metrics Funnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make mobile app revenue and distribution metrics source-separated, daily, and conversion-ready without claiming unavailable data as zero.

**Architecture:** Extend the existing ASC acquisition snapshot with denominator-safe funnel rates, preserve RevenueCat as an observed subscription/revenue source, and expose ASC proceeds separately as settled store revenue. Keep campaign attribution unavailable until a campaign identity is actually attached.

**Tech Stack:** Node.js CommonJS, Python `skills/cfo/loop_pnl.py`, existing JSONL daily snapshots, `node:test`, Python unittest.

**Spec:** `docs/superpowers/specs/2026-10-03-mobile-app-metrics-funnel-design.md`

## Global Constraints

- Missing metrics and zero-denominator rates remain unavailable, never zero.
- RevenueCat charts are observations; only app-ID-matched ASC financial rows count as settled proceeds.
- App and product IDs must match the canonical binding in `skills/cfo/adapters/capafy_mobile.py`.
- Never sum RevenueCat estimates and ASC settled proceeds for the same product/window.
- Keep each source's actual observation time visible; a later report snapshot must not misclassify within-policy fresh mobile data as stale.
- Do not change app submission, paywall, pricing, or marketing publication in this plan.

## Review Focus

- A missing business-outcomes row for any canonical mobile product must fail closed.
- An ASC financial row with an unknown or mismatched app ID must remain unassigned.
- Apple fiscal report months must not be labeled as calendar months without translating the period dates.
- An available ASC financial report must supersede, not add to, RevenueCat chart revenue.
- Apps outside the six CFO bindings, including ASC test records, must not enter mobile P&L implicitly.
- Exercise the active `build_b7_projection` path; changes to the legacy `mobile_apps_entries()` helper alone do not change the CFO CLI output.
- Test both the adapter's freshness rule and the B0 projection's timestamp rule using distinct recent per-product observations.

## Execution Order Decision

Reason: distribution of existing apps is the user's first priority, but live acquisition covers only two of the six CFO-bound products. Separately, the settled Apple row is not mapped to a current app, and the active B7 projection cannot verify mobile MRR or proceeds. RevenueCat observations and the unmatched Apple row are not settled app revenue.

- Previous remaining order: Task 6 acquisition coverage → Task 7 Finance Detail import → Task 8 paid conversion/campaign attribution.
- Updated remaining order: Task 6 six-app acquisition coverage → Task 7 active B7 freshness and explicit RevenueCat currency → Task 8 Finance Detail import and app-identity reconciliation → Task 9 same-window paid-customer cohort → Task 10 campaign/activation/retention sources.
- Reorder reason: distribution comes first; then fix the B7 projection mismatch and currency gap before claiming CFO revenue; import settled proceeds only with exact app identity; defer conversion/attribution until its data joins exist.
- Current cursor: Task 6, Step 1 (crosswalk the six canonical app IDs to current ASC inventory, RevenueCat IDs, and bundle IDs, then find official Analytics requests for the four uncovered products).

## Tasks

### Task 1: Denominator-safe ASC funnel rates

**Status:** rate contract complete (`56faf5cdaa` plus this branch); three store-total rates use aligned ASC dates. `install_to_paid` is explicitly unavailable until Task 9 connects a same-app, same-window cohort.

**Files:** `apps/life-manager/scripts/marketing-asc-acquisition.js`, `apps/life-manager/scripts/marketing-asc-acquisition.test.js`

- [x] Add failing tests for measured rates, zero denominators, missing metrics, and unavailable source.
- [x] Implement a pure rate helper returning measured/unavailable contracts with numerator/denominator.
- [x] Include all four rate fields in every product snapshot; keep `install_to_paid` unavailable with `paid_customer_cohort_unavailable` until its source exists.
- [x] Run focused tests and commit.

### Task 2: Separate ASC proceeds from RevenueCat observations

**Status:** adapter and fail-closed identity rules are implemented (`b61347e50a` plus this branch); the live Finance Detail producer is not connected. The only current report row is JPY 4,250 for Apple Identifier `6762049696`, which has no current/removed app record and is not attributable to a canonical product.

**Files:** `skills/cfo/loop_pnl.py`, `skills/cfo/test_loop_pnl.py`, `apps/life-manager/lib/financial-record-mobile-apps.js`, `apps/life-manager/lib/financial-record-mobile-apps.test.js`

- [x] Add failing fixtures for ASC settled proceeds plus RevenueCat chart revenue and assert no double count.
- [x] Count ASC proceeds only as settled external revenue when the source is available and currency is explicit.
- [x] Keep RevenueCat chart revenue labeled as observed/estimated and exclude it from settled totals when ASC proceeds are present.
- [x] Run focused CFO/Node tests and commit.
- Remaining live producer and report-identity work is Task 8; keep unmatched `6762049696` unassigned until an official identity mapping exists.

### Task 3: Surface mobile funnel status in the owner/CFO summary

**Status:** presentation implementation is complete (`b61347e50a`); the current aligned read is measured for Anicca iOS and unavailable for Honne, with explicit reasons. This does not mean six-app coverage or settled proceeds are complete.

**Files:** `apps/life-manager/scripts/marketing-product-summary.js`, related tests, `docs/evidence/cfo/`

- [x] Add failing tests for source status, rates, attribution unavailable, and per-product separation.
- [x] Render the funnel with explicit `取得不可`/`UNKNOWN` states and source refs.
- [x] Record current ASC Agreement state, live acquisition totals, and unresolved financial identity as evidence.
- [x] Run full mobile/CFO suites and commit.

### Task 4: ASC CLI and distribution handoff

**Status:** complete. Account Holder Agreement is active (`pending=false`), ASC API access works, and acquisition reads work; no additional Apple approval is required.

- [x] Use Rork `asc` 5.9.2 after checksum verification.
- [x] Run read-only auth/analytics preflight; do not submit builds or alter pricing.
- [x] Complete the Account Holder agreement approval and verify official status is `pending=false`; no approval action remains.
- [x] Run acquisition reads after ASC access returned; keep app distribution/publication effects out of scope.

### Task 5: Wire all six canonical products into the active B7 reader

**Status:** source-path changes are present in this branch, but live B7 acceptance is not complete. The active CLI is the B7 projection path, not the legacy `mobile_apps_entries()` helper. A fresh projection is `unknown` with no settled receipts or verified subscription snapshots; gaps are `app-store-connect-financial: missing_coverage` and `revenuecat-mrr: unsupported_currency`.

**Files:** `skills/cfo/loop_pnl.py`, `skills/cfo/test_loop_pnl.py`, `skills/cfo/fixtures/loop_pnl/business_outcomes_fresh.jsonl`, `skills/cfo/fixtures/loop_pnl/business_outcomes_stale.jsonl`

- [x] Filter mixed business-outcomes JSONL to the six canonical mobile product IDs before the active B7 adapter reads it.
- [x] Match the real RevenueCat evidence hash and numeric chart-period shape; keep unknown currency unavailable and exclude RevenueCat estimates from verified Financial Manager totals.
- [x] Enforce app identity, settlement period, refund sign, freshness, and no-double-count behavior in source adapters.
- [x] Run focused CFO/mobile suites and `npm test --prefix apps/life-manager` after the fix pass (all commands exit 0).
- [x] Read the active B7 path against the current six product rows: no settled receipts or verified MRR snapshots; gaps remain explicit (`missing_coverage`, `unsupported_currency`).

### Task 6: Reconcile ASC inventory and acquisition coverage

**Status:** not started. ASC lists 24 records, while the CFO binding lists six products and the live acquisition producer reads only Anicca iOS and Honne. A fresh read measured Anicca for 2026-10-01; Honne returned `report_window_mismatch`.

**Files:** `apps/life-manager/scripts/marketing-asc-acquisition.js`, `apps/life-manager/scripts/marketing-asc-acquisition.test.js`, `skills/cfo/adapters/capafy_mobile.py`, `docs/evidence/cfo/`

- [ ] Crosswalk each canonical product's ASC app ID, RevenueCat app ID, bundle ID, and active/test/removed state against the 24-record official ASC inventory.
- [ ] Discover official Analytics request/report IDs and available windows for Breath Reset, Sleep Ritual, Desk Stretch Timer, and Micro Mood.
- [ ] Extend the producer only to confirmed products; aggregate counts on intersecting dates and keep no-overlap reports unavailable with an exact reason.
- [ ] Read the daily summary back for all six products and record source refs, aligned windows, metrics, and gaps.

### Task 7: Reconcile mobile freshness and RevenueCat currency in active B7

**Status:** partial. This branch now timestamps the coverage assessment at the B7 projection time, and a fresh run no longer reports false `stale_readback`. No MRR snapshots are emitted because all six RevenueCat payloads omit currency; the end-to-end snapshot freshness case still needs a fixture with explicit currency.

**Files:** `skills/cfo/adapters/capafy_mobile.py`, `skills/cfo/economic_attribution.py` only if the existing contract requires it, `skills/cfo/test_capafy_mobile_attribution.py`, `skills/cfo/test_loop_pnl.py`, RevenueCat business-outcomes producer, evidence.

- [x] Stamp current coverage assessment at `snapshot_at` after the adapter applies its freshness rule; a fresh live B7 projection no longer labels coverage stale.
- [ ] Add an active-path regression with distinct recent per-product observations and explicit currency; verify subscription snapshots also pass B0 freshness, and a stale-over-one-day negative case remains unavailable.
- [ ] Trace the RevenueCat response/producer for explicit currency; emit and validate only the provider's actual currency, otherwise retain `unsupported_currency` (never default to USD).
- [ ] Re-run active B7 and verify MRR appears only with explicit currency, missing settled proceeds remain unknown, and source status/window are visible.

### Task 8: Import ASC Financial Detail into CFO business outcomes

**Status:** not started. No `app_store_financial` source rows exist in the six latest product snapshots. The latest official report has one JPY 4,250 row for unmapped Apple Identifier `6762049696`.

**Files:** new `apps/life-manager/scripts/marketing-asc-financial.js`, its `node:test` file, `skills/cfo/loop_pnl.py`, `skills/cfo/test_loop_pnl.py`, `docs/evidence/cfo/`

- [ ] Parse official `FINANCE_DETAIL` `Z1` fiscal period, row identity, Apple Identifier, SKU, currency, transaction/settlement dates, and report SHA-256.
- [ ] Persist only rows whose Apple Identifier exactly matches a canonical app; preserve unmatched rows as unassigned coverage.
- [ ] Add stable report/row identity and replay-zero handling to the business-outcomes producer.
- [ ] Verify matched settled proceeds replace, rather than add to, RevenueCat revenue in the active B7 total.
- [ ] Keep `6762049696` unassigned unless an authoritative historical app identity is found; owner recognition is optional evidence, not required for current implementation.

### Task 9: Connect the paid-customer cohort for install-to-paid

**Status:** not started; `install_to_paid` is explicitly unavailable because a same-app, same-window paid-customer cohort is not connected.

**Files:** RevenueCat subscription producer, `apps/life-manager/scripts/marketing-asc-acquisition.js`, `apps/life-manager/scripts/marketing-product-summary.js`, related tests.

- [ ] Find a provider report that identifies paid customers by product and purchase/cohort date.
- [ ] Join it to ASC first-time downloads by product and intersecting cohort window; do not infer paid counts from MRR, active subscriptions, or chart revenue.
- [ ] Calculate `install_to_paid` with numerator, denominator, and source refs; otherwise retain `paid_customer_cohort_unavailable`.

### Task 10: Add campaign attribution and product activation/retention sources

**Status:** not started; no campaign identity or product analytics cohort source is connected.

**Files:** `apps/life-manager/scripts/marketing-asc-acquisition.js`, product analytics source/adapter, related tests.

- [ ] Join campaign IDs/tokens only when the same report window and app identity match.
- [ ] Connect activation/retention cohorts with their definitions, observation windows, and evidence refs.
- [ ] Keep unsupported metrics unavailable with a specific reason and show source status in the daily summary.

## Verification

```bash
node --test apps/life-manager/scripts/marketing-asc-acquisition.test.js
python3 -m unittest skills.cfo.test_capafy_mobile_attribution
python3 -m unittest skills.cfo.test_loop_pnl
node --test apps/life-manager/lib/financial-record-mobile-apps.test.js apps/life-manager/lib/financial-manager-report.test.js apps/life-manager/lib/financial-manager-ingest.test.js apps/life-manager/scripts/marketing-product-summary.test.js
npm test --prefix apps/life-manager
```

Current live readbacks and their limits: `docs/evidence/cfo/2026-10-03-mobile-metrics-readback.md`.
