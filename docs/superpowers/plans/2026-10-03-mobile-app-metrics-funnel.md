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
- Do not change app submission, paywall, pricing, or marketing publication in this plan.

## Review Focus

- A missing business-outcomes row for any canonical mobile product must fail closed.
- An ASC financial row with an unknown or mismatched app ID must remain unassigned.
- Apple fiscal report months must not be labeled as calendar months without translating the period dates.
- An available ASC financial report must supersede, not add to, RevenueCat chart revenue.
- Apps outside the six CFO bindings, including ASC test records, must not enter mobile P&L implicitly.

## Execution Order Decision

Reason: the fresh 2026-10-02 RevenueCat snapshot has six mapped products, but the CFO default includes only two. Expanding P&L coverage uses already-read data immediately; the JPY 4,250 ASC row has no current app mapping and cannot safely be assigned first.

- Old remaining order: Task 1 `install_to_paid` → Task 2 live finance import → Task 5 app inventory reconciliation → Task 6 paid/campaign attribution.
- Reordered prefix complete: Task 5 six-product CFO coverage. Remaining order: Task 6 acquisition coverage reconciliation → Task 7 live finance import and unmapped-row reconciliation → Task 8 paid/campaign attribution.
- Current cursor: Task 6, Step 1 (reconcile the six CFO app bindings against ASC and RevenueCat, including acquisition request coverage).

## Tasks

### Task 1: Denominator-safe ASC funnel rates

**Status:** partial (`56faf5cdaa`); the three ASC-to-store rates are implemented and live. The fourth rate is tracked in Task 8 because its paid-customer cohort is not connected.

**Files:** `apps/life-manager/scripts/marketing-asc-acquisition.js`, `apps/life-manager/scripts/marketing-asc-acquisition.test.js`

- [x] Add failing tests for measured rates, zero denominators, missing metrics, and unavailable source.
- [x] Implement a pure rate helper returning measured/unavailable contracts with numerator/denominator.
- [x] Include `impression_to_page_view`, `page_view_to_install`, and `impression_to_install` in every product snapshot.
- [x] Run focused tests and commit.

### Task 2: Separate ASC proceeds from RevenueCat observations

**Status:** local adapters complete (`b61347e50a`); current Apple Financial Detail was read successfully, but its only JPY 4,250 row belongs to Apple Identifier `6762049696`, which has no current app resource and does not map to either tracked product.

**Files:** `skills/cfo/loop_pnl.py`, `skills/cfo/test_loop_pnl.py`, `apps/life-manager/lib/financial-record-mobile-apps.js`, `apps/life-manager/lib/financial-record-mobile-apps.test.js`

- [x] Add failing fixtures for ASC settled proceeds plus RevenueCat chart revenue and assert no double count.
- [x] Count ASC proceeds only as settled external revenue when the source is available and currency is explicit.
- [x] Keep RevenueCat chart revenue labeled as observed/estimated and exclude it from settled totals when ASC proceeds are present.
- [x] Run focused CFO/Node tests and commit.
- Remaining live producer and report-identity work is Task 7; keep unmatched `6762049696` unassigned until an official identity mapping exists.

### Task 3: Surface mobile funnel status in the owner/CFO summary

**Status:** complete for daily summary output (`b61347e50a`); latest ASC totals now read successfully for Anicca iOS and Honne.

**Files:** `apps/life-manager/scripts/marketing-product-summary.js`, related tests, `docs/evidence/cfo/`

- [x] Add failing tests for source status, rates, attribution unavailable, and per-product separation.
- [x] Render the funnel with explicit `取得不可`/`UNKNOWN` states and source refs.
- [x] Record current ASC Agreement state, live acquisition totals, and unresolved financial identity as evidence.
- [x] Run full mobile/CFO suites and commit.

### Task 4: ASC CLI and distribution handoff

**Status:** complete. Account Holder Agreement is active (`pending=false`), ASC API access works, and a daily acquisition snapshot is persisted.

- [x] Use Rork `asc` 5.9.2 after checksum verification.
- [x] Run read-only auth/analytics preflight; do not submit builds or alter pricing.
- [x] Hand off the required production credential/permission fix to the registered release owner.
- [x] Re-run one daily snapshot after ASC readback becomes available.

### Task 5: Include all six CFO-bound mobile products in the daily P&L

**Status:** complete (`39/39` CFO loop_pnl tests). `loop_pnl.py` now uses the six canonical products and ASC app IDs from `capafy_mobile`; live 2026-10-02 RevenueCat rows read back for all six.

**Files:** `skills/cfo/loop_pnl.py`, `skills/cfo/test_loop_pnl.py`, `skills/cfo/fixtures/loop_pnl/business_outcomes_fresh.jsonl`, `skills/cfo/fixtures/loop_pnl/business_outcomes_stale.jsonl`

- [x] Add a test using all six daily rows and assert the default P&L notes contain six MRR observations.
- [x] Add four zero-revenue rows for the remaining mapped products to the fresh/stale fixtures; preserve ASC identity checks.
- [x] Derive `MOBILE_APPS_PRODUCTS` and app-ID validation from `capafy_mobile.MOBILE_PRODUCTS` / `MOBILE_PRODUCT_BINDINGS` rather than a second two-product list.
- [x] Keep missing-product fail-closed behavior and ASC-over-RevenueCat precedence unchanged; the precedence test scopes its fixture to Anicca/Honne.
- [x] Run focused `MobileAppsTest` (6/6) and the complete `skills.cfo.test_loop_pnl` suite (39/39).

### Task 6: Reconcile ASC inventory and acquisition coverage

**Status:** not started. ASC lists 24 records, while the CFO binding lists six products and acquisition currently reads two.

**Files:** `apps/life-manager/scripts/marketing-asc-acquisition.js`, `apps/life-manager/scripts/marketing-asc-acquisition.test.js`, `skills/cfo/adapters/capafy_mobile.py`, `docs/evidence/cfo/`

- [ ] Reconcile the six CFO bindings to ASC app IDs, RevenueCat app IDs, and bundle IDs; explicitly identify inactive/test apps.
- [ ] Discover complete ASC Analytics request/report IDs for the four mapped products not currently in the acquisition producer.
- [ ] Extend daily acquisition collection only to confirmed mapped products and keep missing report instances unavailable.
- [ ] Record the 24-record inventory, six-product mapping, and acquisition coverage in evidence.

### Task 7: Import ASC Financial Detail into CFO business outcomes

**Status:** not started. The latest report has a JPY 4,250 row for `6762049696`, which is not a current app resource.

**Files:** new `apps/life-manager/scripts/marketing-asc-financial.js`, its `node:test` file, `skills/cfo/loop_pnl.py`, `skills/cfo/test_loop_pnl.py`, `docs/evidence/cfo/`

- [ ] Parse the Apple fiscal period, report rows, currency, transaction/settlement dates, and SHA-256 from `FINANCE_DETAIL` `Z1` output.
- [ ] Persist rows only when `Apple Identifier` exactly matches a mapped app; otherwise preserve a source gap and do not assign revenue.
- [ ] Store the report in `business_outcomes` with stable report identity and idempotent replay; leave RevenueCat observations intact.
- [ ] Verify the mapped settled proceeds replace RevenueCat chart revenue in CFO totals without double counting.
- [ ] Keep the `6762049696` row unassigned until an official app/IAP identity mapping exists.

### Task 8: Complete paid conversion and campaign attribution

**Status:** not started; no same-window paid-customer cohort or campaign identity is connected.

**Files:** `apps/life-manager/scripts/marketing-asc-acquisition.js`, `apps/life-manager/scripts/marketing-revenuecat-subscriptions.js`, `apps/life-manager/scripts/marketing-product-summary.js`, related tests

- [ ] Add `install_to_paid` to every product snapshot and daily summary; compute only from same-app, same-window paid customers and first-time downloads, otherwise return `unavailable` with a specific reason.
- [ ] Connect only a source that provides a verifiable paid-customer cohort; do not infer paid customers from MRR or RevenueCat chart revenue.
- [ ] Keep campaign-level install attribution unavailable until a campaign token joins the same ASC report window.
- [ ] Record activation/retention as unavailable until a product analytics cohort source is connected.

## Verification

```bash
node --test apps/life-manager/scripts/marketing-asc-acquisition.test.js
python3 -m unittest skills/cfo/test_loop_pnl.py
npm test --prefix apps/life-manager
```

Current live readbacks and their limits: `docs/evidence/cfo/2026-10-03-mobile-metrics-readback.md`.
