# Mobile App Metrics Funnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make mobile app revenue and distribution metrics source-separated, daily, and conversion-ready without claiming unavailable data as zero.

**Architecture:** Extend the existing ASC acquisition snapshot with denominator-safe funnel rates, preserve RevenueCat as an observed subscription/revenue source, and expose ASC proceeds separately as settled store revenue. Keep campaign attribution unavailable until a campaign identity is actually attached.

**Tech Stack:** Node.js CommonJS, Python `skills/cfo/loop_pnl.py`, existing JSONL daily snapshots, `node:test`, Python unittest.

**Spec:** `docs/superpowers/specs/2026-10-03-mobile-app-metrics-funnel-design.md`

## Global Constraints

- Missing metrics and zero-denominator rates remain unavailable, never zero.
- RevenueCat charts are observations; only app-ID-matched ASC financial rows count as settled proceeds.
- Acquisition uses the official currently-published ASC app inventory. CFO/RevenueCat bindings are reconciled separately; never infer an app match from a similar name.
- Never sum RevenueCat estimates and ASC settled proceeds for the same product/window.
- Keep each source's actual observation time visible; a later report snapshot must not misclassify within-policy fresh mobile data as stale.
- Do not change app submission, paywall, pricing, or marketing publication in this plan.

## Review Focus

- A missing business-outcomes row for any canonical mobile product must fail closed.
- An ASC financial row with an unknown or mismatched app ID must remain unassigned.
- Apple fiscal report months must not be labeled as calendar months without translating the period dates.
- An available ASC financial report must supersede, not add to, RevenueCat chart revenue.
- ASC test/prelaunch records must not enter the live published-app acquisition denominator; preserve them separately for costs or future release tracking.
- The current RevenueCat project may not cover every published app; missing app/entitlement links stay unavailable, never inferred.
- Exercise the active `build_b7_projection` path; changes to the legacy `mobile_apps_entries()` helper alone do not change the CFO CLI output.
- Test both the adapter's freshness rule and the B0 projection's timestamp rule using distinct recent per-product observations.

## Execution Order Decision

Reason: the official ASC published audit falsified the old six-product CFO map as the live app set: only Anicca and Honne overlap, four old mapped IDs are unpublished, and four other seller-owned apps are public. The active user goal is distribution of existing apps, so Task 6 now targets the six official published IDs; the old prelaunch IDs remain separately tracked.

- Previous remaining order: Task 6 acquisition coverage → Task 7 B7 freshness/currency → Task 8 Finance Detail import → Task 9 paid cohort → Task 10 attribution.
- Updated remaining order: Task 6 six-published-app acquisition summary → Task 8 Finance Detail import with subscription/IAP identity crosswalk → Task 7 B7 live/prelaunch binding, currency, and freshness → Task 9 paid cohort → Task 10 attribution/activation/retention.
- Reorder reason: the official Finance Detail row previously thought unmatched is an exact approved Anicca Annual subscription ID + SKU match. Importing this settled row can deliver actual CFO revenue before resolving the separate RevenueCat currency/project gap.
- Scope ruling: the live acquisition denominator is the six official published ASC IDs; the four old CFO-bound unpublished apps remain separate. Risk if wrong: omit a live app or count a prelaunch app as active distribution; mitigated by official territory, bundle, seller, RevenueCat app, and subscription readbacks.
- Current cursor: Task 8, Step 1 — write the RED test for exact ASC subscription/IAP child-ID + SKU to parent-app mapping.

## Tasks

### Task 1: Denominator-safe ASC funnel rates

**Status:** rate contract complete (`56faf5cdaa` plus this branch); three store-total rates use aligned ASC dates. `install_to_paid` is explicitly unavailable until Task 9 connects a same-app, same-window cohort.

**Files:** `apps/life-manager/scripts/marketing-asc-acquisition.js`, `apps/life-manager/scripts/marketing-asc-acquisition.test.js`

- [x] Add failing tests for measured rates, zero denominators, missing metrics, and unavailable source.
- [x] Implement a pure rate helper returning measured/unavailable contracts with numerator/denominator.
- [x] Include all four rate fields in every product snapshot; keep `install_to_paid` unavailable with `paid_customer_cohort_unavailable` until its source exists.
- [x] Run focused tests and commit.

### Task 2: Separate ASC proceeds from RevenueCat observations

**Status:** adapter and fail-closed identity rules are implemented (`b61347e50a` plus this branch); the live Finance Detail producer is not connected. The JPY 4,250 report row's `Apple Identifier` is not an app ID: ASC confirms ID `6762049696` is the approved `Anicca Annual` subscription under app `6755129214`, with exact SKU `ai.anicca.app.ios.yearly.b`.

**Files:** `skills/cfo/loop_pnl.py`, `skills/cfo/test_loop_pnl.py`, `apps/life-manager/lib/financial-record-mobile-apps.js`, `apps/life-manager/lib/financial-record-mobile-apps.test.js`

- [x] Add failing fixtures for ASC settled proceeds plus RevenueCat chart revenue and assert no double count.
- [x] Count ASC proceeds only as settled external revenue when the source is available and currency is explicit.
- [x] Keep RevenueCat chart revenue labeled as observed/estimated and exclude it from settled totals when ASC proceeds are present.
- [x] Run focused CFO/Node tests and commit.
- Remaining producer work is Task 8; map each raw `Apple Identifier` + SKU to an official subscription/IAP record and its parent app ID. Do not compare the raw child record ID directly to the app ID.

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

### Task 6: Reconcile the published app portfolio and acquire daily ASC metrics

**Status:** source/configuration and isolated summary validation are complete on this branch. ASC audited 24 records and reports six published apps in 175 territories; only Anicca and Honne overlap the previous CFO map. Four other published apps were omitted, four old CFO-bound IDs are unpublished, and the configured RevenueCat project has no app records for the four additional live apps. Their Ongoing requests are active, but their daily report instances are still pending.

**Files:** `apps/life-manager/scripts/marketing-asc-acquisition.js`, `apps/life-manager/scripts/marketing-asc-acquisition.test.js`, `apps/life-manager/scripts/marketing-revenuecat-subscriptions.js`, its tests, `apps/life-manager/scripts/marketing-product-summary.js`, its tests, `docs/evidence/cfo/`

- [x] Crosswalk the six published ASC apps to exact app IDs and bundle IDs; separate the four unpublished CFO-map records from the live denominator.
- [x] Create and read back active `ONGOING` Analytics requests for Dhamma Quotes (`25b5906d-025b-4b9d-8226-dc1ea25bd13f`), For Better Sleep (`f4f4e486-d5cd-4b16-9d06-a1850fc9a477`), STUDIO CHERIE (`b1c18c4e-77f3-4b63-bee4-259353531c3d`), and Thankful (`a1149f87-b22a-42cb-85a8-324eb54d2f1a`).
- [x] Verify `r3`/`r15` report definitions exist and query official report-instance links; at this read they return no daily instances, so the four metrics are `report_pending`, not zero.
- [x] Add regression coverage that acquisition and RevenueCat coverage lists exactly the six currently published product IDs.
- [x] Update the daily funnel summary to retain six published-app rows and leave missing RevenueCat observations unavailable.
- [x] Run all-six acquisition and daily attribution-summary code against fresh official ASC reads in an isolated data root; Anicca is measured, Honne is `report_window_mismatch`, the four new reports are `report_pending`, and no existing immutable pointer is rewritten.

### Task 7: Reconcile mobile freshness and RevenueCat currency in active B7

**Status:** partial. The coverage assessment timestamp no longer produces false `stale_readback`. B7 still uses the old six CFO-bound app IDs, while ASC's live published set is different; only two live apps are in the configured RevenueCat project. MRR currency remains absent and no published-app financial rows are joined.

**Files:** `skills/cfo/adapters/capafy_mobile.py`, `skills/cfo/economic_attribution.py` only if the existing contract requires it, `skills/cfo/test_capafy_mobile_attribution.py`, `skills/cfo/test_loop_pnl.py`, RevenueCat business-outcomes producer, evidence.

- [x] Stamp current coverage assessment at `snapshot_at` after the adapter applies its freshness rule; a fresh live B7 projection no longer labels coverage stale.
- [ ] Reconcile B7/RevenueCat product bindings against the six published apps and four explicit prelaunch records without dropping historical receipts or costs.
- [ ] Add an active-path regression with distinct recent per-product observations and explicit currency; verify subscription snapshots pass B0 freshness and a stale-over-one-day case remains unavailable.
- [ ] Trace the RevenueCat source/project for the four newly published apps and explicit currency; emit only verified mappings, otherwise retain the precise unavailable reason.
- [ ] Re-run active B7 and verify MRR appears only with explicit currency, missing settled proceeds remain unknown, and source status/window is visible.

### Task 8: Import ASC Financial Detail into CFO business outcomes

**Status:** in progress. No `app_store_financial` source rows have been imported yet. The Financial Manager adapter accepts the normalized parent app ID plus exact child subscription ID/SKU/catalog evidence (10/10 focused Node tests); the B7 adapter and active B7 integration pass (49/49 and 43/43 Python tests). The active B7 source path emits one verified JPY 4,250 receipt, but the 30-day B0 projection remains `unknown` because the final finance period ends 2026-09-26 while the current complete-data cutoff is 2026-09-30. This is a coverage gap, not a zero. The production business-outcomes producer is still unmodified.

**Implementation ruling:** extend `skills/earn/marketing-engine/measure/business_outcomes.py`, which is already the scheduled producer that writes the JSONL consumed by both Financial Manager and B7. A separate `marketing-asc-financial.js` would have no scheduled invocation and would require extra cross-runtime wiring. Keep the live report/catalog reads and normalization in the existing producer, then let both existing consumers project the same immutable source rows.

**Integrity contract:** `report_sha256` is the raw downloaded Finance Detail artifact hash; `content_sha256` is the canonical normalized-row hash checked by B7. Do not reuse one for the other.

**Completed in this task:** RED→GREEN tests prove exact child ID + SKU maps through Financial Manager and the active B7 reader, and RevenueCat chart revenue is not emitted as a second settled receipt.

**Files:** `skills/earn/marketing-engine/measure/business_outcomes.py`, `skills/earn/marketing-engine/measure/test_business_outcomes.py`, `skills/cfo/adapters/capafy_mobile.py`, `skills/cfo/test_capafy_mobile_attribution.py`, `skills/cfo/loop_pnl.py`, `skills/cfo/test_loop_pnl.py`, `apps/life-manager/lib/financial-record-mobile-apps.js`, its tests, `docs/evidence/cfo/`

- [ ] Parse official `FINANCE_DETAIL` `Z1` fiscal period, row identity, Apple Identifier, SKU, currency, transaction/settlement dates, and raw downloaded-report SHA-256; keep a separate normalized-content SHA-256 for adapter integrity checks.
- [ ] Resolve raw `Apple Identifier` + SKU to an official ASC subscription/IAP record, then its parent app ID; preserve rows without an exact catalog match as unassigned coverage.
- [ ] Normalize the parent app ID separately from the raw child Apple Identifier and SKU in `app_store_financial`; retain the ASC catalog record type/ID, parent binding, and evidence reference.
- [ ] Add stable report/row identity and replay-zero handling to the business-outcomes producer.
- [ ] Preserve the mapped receipt in active B7 inputs while keeping the full trailing total unavailable until the settlement source covers the full reported window; do not add RevenueCat chart revenue as settled proceeds.
- [ ] Import the confirmed `6762049696` Anicca Annual row as JPY 4,250 once with stable report/row identity and no RevenueCat double count.
- [ ] After import, correlate the next natural CFO report occurrence to an official provider receipt/readback and verify the delivered report contains the settled row; process pass and uncorrelated `last-result.json` are not delivery proof.

**Current cursor:** write RED tests for Finance Detail TSV parsing, exact ASC subscription/IAP catalog mapping, source upsert/replay-zero, and attaching the final report to the existing business-outcomes rows; then implement the producer.

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
