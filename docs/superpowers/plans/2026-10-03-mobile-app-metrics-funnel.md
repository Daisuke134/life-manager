# Mobile App Metrics Funnel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make mobile app revenue and distribution metrics source-separated, daily, and conversion-ready without claiming unavailable data as zero.

**Architecture:** Extend the existing ASC acquisition snapshot with denominator-safe funnel rates, preserve RevenueCat as an observed subscription/revenue source, and expose ASC proceeds separately as settled store revenue. Treat Apple D7 Download-to-Paid as experimental because its current Rork read path is a private ASC web endpoint; keep attribution/activation/retention unavailable until their source identities and definitions are verified.

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
- The ASC D7 web-cohort path is experimental/private, not a supported public API; label every value and fail closed on endpoint, identity, cohort, denominator, maturity, redownload, or precision mismatch.

## Execution Order Decision

The official ASC published audit establishes six live apps; only Anicca and Honne overlap the old CFO map, while four old mapped app IDs are unpublished and four other seller-owned apps are public. Keep the six published IDs as the acquisition denominator and the four old unpublished apps as a separate historical/prelaunch set.

- Previous remaining order: Task 6 acquisition coverage → Task 7 B7 freshness/currency → Task 8 Finance Detail import → Task 9 paid cohort → Task 10 attribution.
- Previous updated order: Task 6 six-published-app acquisition summary → Task 8 Finance Detail import → Task 7 B7 live/prelaunch binding, currency, and freshness → Task 9 paid cohort → Task 10 attribution/activation/retention.
- Previous remaining order: Task 7 B7 live/prelaunch binding, currency, and freshness → Task 9 paid cohort/source disposition → Task 10 attribution/activation/retention source disposition → Task 8 production Finance Detail import and same-occurrence CFO delivery readback.
- Previous remaining order: Task 9 paid-cohort source disposition → Task 10 campaign/activation/retention source disposition → Task 8 production Finance Detail import and same-occurrence CFO delivery readback.
- Previous remaining order: Task 7/8 source-correctness remediation (no production writes) → Task 9 paid-cohort source disposition → Task 10 campaign/activation/retention source disposition → Task 8 production Finance Detail import and same-occurrence CFO delivery readback.
- Previous remaining order: Task 9 experimental ASC D7 read-only integration and acceptance → Task 10 campaign/activation/retention source disposition → Task 8 full-acceptance promotion, natural Finance Detail import, and same-occurrence CFO delivery readback.
- Previous remaining order: Task 10 campaign/activation/retention source disposition → Task 8 full-acceptance promotion, natural Finance Detail import, and same-occurrence CFO delivery readback.
- Previous remaining order: Task 8 full-acceptance promotion, natural Finance Detail import, and same-occurrence CFO delivery readback.
- New remaining order: close the two Important Task 8 findings from the latest-main whole-branch review (stable cross-provider FinancialRecord replay and visible past-period ASC settlement) → rerun full source acceptance → fresh whole-branch review → satisfy the repository issue/maintainer approval gate for this already-implemented branch → open the single PR and merge → immutable main release and targeted apply → natural Finance Detail import → B7/Financial Manager readback → same-occurrence CFO receipt/readback.
- Historical reorder reason: `origin/main` advanced twice while source review was running, so both current-main commits had to be merged without rewriting the feature branch. Syncs `655b2cf2` → `a1b6dadb3a` and `3e1e30a6` → `e46284c351` both completed without conflicts. The latest natural Marketing Metrics run still uses production release `9c03543e`, not the feature branch.
- Reorder reason: Task 10's source audit and per-source summary reasons are complete; no configured matching campaign or verified activation/retention cohort source exists in the current account/readbacks. Preserve those gaps and do not modify app repositories; continue to Task 8's production Finance Detail acceptance and readback.
- Reorder reason: Task 9 now has a fail-closed read-only collector, mature cohort readback, and passing source/app/CFO verification. Its data remains branch-only; Task 10 is the next incomplete source task, with production Finance Detail import last.
- Reorder reason: the Task 7/8 review findings now have RED→GREEN source fixes and the full CFO, producer, and Life Manager suites pass. Source corrections are no longer the cursor; finish cohort/source disposition before the final production import.
- Reorder reason: the fresh review of base `ede6efa47d` to head `9be7a8a368` found two Important gaps: timestamp-only replay collisions in the shared FinancialRecord store (also used by Capafy/RevenueCat) and a settled ASC row outside the report's date windows being omitted from the CFO message. Both now have RED→GREEN regressions and implementation fixes; promotion stays after a fresh review. Old order: issue/maintainer gate → full acceptance/review → PR. New order: code/data-integrity fixes → full acceptance → fresh review → issue/maintainer gate → PR. Current cursor: post-fix fresh review.
- Previous cursor (readback 2026-10-04 05:41 JST, before review-status commit): the initial whole-branch review found no Critical, one Important (`d7Unavailable()` undefined), and one Minor (stale branch cursor). The Important was fixed test-first in `1dca1b36e9`; the same reviewer rechecked base `3e1e30a6` to head `d4da1cd4a6` and returned `SHIP`, with all findings closed. Latest main `3e1e30a6` is merged as `e46284c351` without conflict; the branch is pushed and current. After latest main sync: runtime loop tests 755/755, `lm-loop-contract` 14 loops/178 jobs with no errors, source-boundary PASS, focused mobile/Financial Manager tests 53/53, CFO unittest discovery 275/275, producer 36/36, full Life Manager `npm test` exit 0. Historical production read at 2026-10-04 05:39 JST showed Marketing Metrics on `9c03543e` and CFO on `655b2cf2`; newer readback below supersedes those runtime hashes. Do not manually trigger either owner.
- Previous cursor (2026-10-04 06:07 JST): latest main `ede6efa47d` was merged as `bb9ae35844`, with the focused upstream runtime regression 22/22. Newer production reread below supersedes the runtime status.
- Current cursor (2026-10-04 07:00 JST): review of base `ede6efa47d` to head `9be7a8a368` returned HOLD with two Important findings. Both have test-first fixes: the common FinancialRecord store now treats only `recorded_at`/`verification.observed_at` changes as replays while preserving original stored metadata and failing on economic/evidence differences; the ASC adapter deduplicates repeated report rows across business dates and fails closed on missing time/conflicting identity; the Financial Manager surfaces newly recorded prior-period ASC rows with settlement date, product ID, amount, source reference, and evidence, without altering today/week/month totals. The combined source tests are 41/41; ASC acquisition 15/15; CFO adapter suites 52/52 and 44/44; CFO discovery 275/275; producer 36/36; full Life Manager `npm test` exit 0; loop contract 14/178 PASS; source-boundary PASS; diff check clean. Runtime tests 758/758 were run on the same latest-main runtime code before these app/report-only changes.
- Latest production remains outside this branch: Marketing Metrics release `9c03543e` hit `host_admission_deferred:resource_capacity_busy` at 07:00 JST; production JSONL remains at business date `2026-10-03` with six `provider_query_failed` legacy sales rows, missing RevenueCat currency, and no Finance Detail rows. CFO is installed on main `ede6efa47d` but its 06:57 JST occurrence is also capacity-blocked/exit 75 with no provider receipt/readback. The local 19:02Z result still claims message `102459`; the durable snapshot remains `2026-09-26` / `94946`; delivery is unverified.
- Promotion gate (verified 2026-10-04): `CONTRIBUTING.md` requires an issue and maintainer 👍 before writing code; `.github/PULL_REQUEST_TEMPLATE.md` requires the related issue and 👍 before PR. This already-implemented branch still needs maintainer acceptance as the intended route before PR. `gh` read-only searches found no matching issue or PR. No issue/PR was created. Current remaining order: fresh post-fix whole-branch review → associate the work with an issue and obtain maintainer 👍 → single PR/main promotion → immutable main release and targeted apply → natural Marketing Metrics Finance Detail import → B7/Financial Manager verification with 30-day `unknown` preserved → same-occurrence CFO official receipt/readback.
- Canonical TODO boundary: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` remains the global source of order/state; this plan is task-level execution detail only. Its latest committed mobile pointer is still `a47b4db`, and its separate worktree has an active lease, so reconcile the global cursor through that owner rather than editing the same file in this lane.
- Current RevenueCat readback: the configured account exposes one project (`anicca`) and eight app records. Its product endpoint returns 21 products across six app IDs (Anicca, Honne, SleepRitual, Desk Stretch Timer, Micro Mood, Test Store); BreathReset and Anicca Web Billing have app records but no listed products. The four additional published ASC apps have no RevenueCat app binding. Direct MRR chart reads for the six legacy CFO app IDs expose `yaxis_currency=USD` for period `2026-10-02`: Anicca is `20.34`; Honne, BreathReset, SleepRitual, Desk Stretch Timer, and Micro Mood are `0`. These are RevenueCat-observed MRR values, not settled proceeds. Test Store is excluded from the mobile portfolio.

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

**Status:** the four `fix-first` source findings are implemented and source suites pass; production owners are loaded on `marketing-metrics-daily=9c03543e` and `life-manager-cfo-hourly=ede6efa47d`, neither containing this branch's full Finance Detail integration. B0's one-day tolerance now applies only to mobile subscriptions, and B7 emits a separate coverage row for each product-level RevenueCat gap even if another app is stale. Direct API readback confirms USD for the current legacy charts, but persisted production RevenueCat rows still omit currency.

**Files:** `skills/cfo/adapters/capafy_mobile.py`, `skills/cfo/economic_attribution.py`, `skills/cfo/test_capafy_mobile_attribution.py`, `skills/cfo/test_economic_attribution.py`, `skills/cfo/test_loop_pnl.py`, `skills/earn/marketing-engine/measure/business_outcomes.py` and its tests, `skills/earn/marketing-engine/report/runners.json`, `apps/life-manager/lib/financial-record-mobile-apps.js` and its tests, evidence.

- [x] Stamp current coverage assessment at `snapshot_at` after the adapter applies its freshness rule; a fresh live B7 projection no longer labels coverage stale.
- [x] Reconcile B7/RevenueCat product bindings against the six published apps and four explicit prelaunch records without dropping historical receipts or costs.
- [x] Add an active-path regression with distinct recent per-product observations and explicit currency; verify subscription snapshots pass B0 freshness and a stale-over-one-day case remains unavailable.
- [x] Trace the RevenueCat source/project for the four newly published apps and explicit currency; persist only observed chart currency, and mark missing app bindings `app_not_in_project`/`source_unconnected`.
- [x] Re-run active B7 and verify six mapped MRR snapshots remain USD observations, total MRR is unknown while four public-app bindings are missing, missing settled proceeds remain unknown, and source status/window is visible.
- [x] Limit the one-day `observed_at` tolerance to mobile RevenueCat subscription rows; add a regression proving non-mobile B0 loops retain their prior freshness behavior.
- [x] Emit distinct unavailable coverage entries for Dhamma Quotes (`6757726663`), Sleep Reset (`6762143790`), STUDIO CHERIE (`6766485903`), and Thankful (`6759514159`); verify aggregate/stale coverage cannot hide any app's missing binding.

### Task 8: Import ASC Financial Detail into CFO business outcomes

**Status:** source implementation is present. The latest whole-branch review returned HOLD with two Important defects; both are fixed test-first and pushed in `5a141f8cc5`. The shared store makes timestamp-only re-observation idempotent but retains collisions for changed economics/evidence, and the CFO report displays newly recorded historical ASC settlements outside period totals. Fresh verification: Financial Manager/store/mobile/ingest 41/41; ASC acquisition 15/15; CFO unittest discovery 275/275; business-outcomes producer 36/36; full `npm test --prefix apps/life-manager` exit 0; loop contract PASS (14 loops/178 jobs, no errors); source-boundary PASS via `bash`; `git diff --check` clean; full runtime suite 759/759 after push. No `app_store_financial` row has been imported into production; the active B7 fixture emits one mapped JPY 4,250 row without a duplicate RevenueCat receipt; the full 30-day B0 projection remains `unknown` because the report period ends 2026-09-26 before the 2026-09-30 cutoff.

**Implementation ruling:** extend `skills/earn/marketing-engine/measure/business_outcomes.py`, which is already the scheduled producer that writes the JSONL consumed by both Financial Manager and B7. A separate `marketing-asc-financial.js` would have no scheduled invocation and would require extra cross-runtime wiring. Keep the live report/catalog reads and normalization in the existing producer, then let both existing consumers project the same immutable source rows.

**Integrity contract:** `report_sha256` is the raw downloaded Finance Detail artifact hash; `content_sha256` is the canonical normalized-row hash checked by B7. Do not reuse one for the other.

**Completed in this task:** RED→GREEN tests prove exact child ID + SKU maps through Financial Manager and the active B7 reader, and RevenueCat chart revenue is not emitted as a second settled receipt.

**Source-integrity corrections (complete before Task 9/10):**

- [x] Financial Manager recomputes/validates the canonical hash and evidence identity for the complete normalized report before any row is marked `verified`; missing hash/evidence or a modified/arbitrary row must fail closed. RED→GREEN: 15/15 Financial Manager mobile tests; `npm test --prefix apps/life-manager` exit 0.
- [x] A transient `provider_query_failed` refresh cannot overwrite a previous successful `app_store_financial` row with unavailable data. Preserve the last-good row and its actual `observed_at`, and report the latest failed attempt separately without making old evidence appear fresh. RED→GREEN: same-date and next-date producer upsert regressions; Financial Manager consumes the source observation timestamp.

**Files:** `skills/earn/marketing-engine/measure/business_outcomes.py`, `skills/earn/marketing-engine/measure/test_business_outcomes.py`, `skills/cfo/adapters/capafy_mobile.py`, `skills/cfo/test_capafy_mobile_attribution.py`, `skills/cfo/loop_pnl.py`, `skills/cfo/test_loop_pnl.py`, `apps/life-manager/lib/financial-record-mobile-apps.js`, its tests, `docs/evidence/cfo/`

- [x] Parse official `FINANCE_DETAIL` `Z1` fiscal period, row identity, Apple Identifier, SKU, currency, transaction/settlement dates, and raw downloaded-report SHA-256; keep a separate normalized-content SHA-256 for adapter integrity checks.
- [x] Resolve raw `Apple Identifier` + SKU to an official ASC subscription/IAP record, then its parent app ID; preserve rows without an exact catalog match as unassigned coverage.
- [x] Normalize the parent app ID separately from the raw child Apple Identifier and SKU in `app_store_financial`; retain the ASC catalog record type/ID, parent binding, and evidence reference.
- [x] Add stable report/row identity and replay-zero handling to the business-outcomes producer.
- [x] Preserve the mapped receipt in active B7 inputs while keeping the full trailing total unavailable until the settlement source covers the full reported window; do not add RevenueCat chart revenue as settled proceeds.
- [x] Merge freshly fetched `origin/main` into the already-pushed feature branch without rewriting it; syncs `655b2cf2` and later `3e1e30a6` merged as `a1b6dadb3a` and `e46284c351`, no conflicts.
- [x] Rerun after latest main sync: runtime loop tests 755/755, `lm-loop-contract` 14 loops/178 jobs with no errors, source-boundary PASS, focused mobile/Financial Manager Node 53/53, CFO unittest discovery 275/275, `business_outcomes` producer 36/36, and full Life Manager `npm test` exit 0.
- [x] Complete a fresh read-only whole-branch review; the first review returned `fix-first` with no Critical, one Important, and one Minor finding.
- [x] Fix the Important D7 collector failure-path bug test-first; after latest main sync, runtime tests 755/755, mobile 53/53, CFO 275/275, producer 36/36, and full Life Manager `npm test` exit 0.
- [x] Have the assigned reviewer verify the fix against base `3e1e30a6`; the same reviewer returned `SHIP` with no Critical/Important/Minor findings.
- [x] Fix same-row replay collisions in JSONL/Postgres stores while preserving the first record; timestamp-only changes are duplicates, while amount/evidence changes still collide. RED→GREEN: store and ingest regressions cover JSONL, Postgres, ASC daily snapshots, Capafy, and RevenueCat.
- [x] Deduplicate ASC rows by stable product/report/row identity across business-date snapshots, preserve source observation time, and fail closed when source time is missing or identity/evidence conflicts.
- [x] Render newly recorded prior-period ASC settlements with original settlement date, product ID, amount, provider, row ref, and evidence, separately from today/last-7/current-month totals.
- [ ] After Tasks 9/10 and all source acceptance checks pass, complete the single full-acceptance main/release promotion; do not load feature-worktree code directly into production.
- [ ] Import the confirmed `6762049696` Anicca Annual row as JPY 4,250 once with stable report/row identity and no RevenueCat double count.
- [ ] After import, correlate the next natural CFO report occurrence to an official provider receipt/readback and verify the delivered report contains the settled row; process pass and uncorrelated `last-result.json` are not delivery proof.

**Current cursor:** both Important findings are fixed and pushed in `5a141f8cc5`; fresh app/CFO/source verification passes, including runtime 759/759 on the pushed HEAD. The two release-cut guard failures from the earlier unpushed run are resolved. Next: fresh post-fix whole-branch review. No matching issue/PR exists; after technical acceptance, associate the branch with an issue and obtain maintainer 👍 before PR/main promotion → immutable release → natural Finance Detail import → B7/Financial Manager readback with 30-day `unknown` preserved → same-occurrence CFO receipt and provider readback. Do not manually trigger either owner or treat local `last-result-report.json` state as official delivery proof.

### Task 9: Connect the paid-customer cohort for install-to-paid

**Status:** complete on the feature branch; not loaded in production. Focused acquisition/summary tests pass 19/19; the full Life Manager suite exits 0; CFO 275/275 and producer 36/36 pass; `git diff --check` is clean. Read-only probes at `2026-10-03T19:04Z` returned mature `2026-09-25` D7 0/1 for Anicca and Honne; the younger Anicca `2026-09-26` cohort (n=3) remains unavailable until UTC `cohort_date + 8 days`. These are experimental samples, not a trend; the private endpoint is not a supported public ASC API.

**Files:** RevenueCat subscription producer, `apps/life-manager/scripts/marketing-asc-acquisition.js`, `apps/life-manager/scripts/marketing-product-summary.js`, related tests.

- [x] Add RED tests for exact app/date/`d7` matching, mature cohorts, nonzero official `r3` denominators, zero redownloads, privacy/null/error responses, and unambiguous integer payer reconstruction at provider precision; mismatches remain unavailable.
- [x] Add a read-only `asc --read-only web analytics cohorts --app APP_ID --start COHORT_DATE --end COHORT_DATE --frequency day --measures cohort-download-to-paid-rate --periods d1,d7,d35 --output json` collection path and join only the matching app/date to official `r3` first-time downloads. Preserve the provider's experimental/private source status; do not infer paid counts from RevenueCat, MRR, active subscriptions, or summed purchase rows.
- [x] Show `Install→Paid D7`, cohort date, numerator/denominator/sample size, and experimental/unavailable status in the daily summary; preserve `paid_customer_cohort_unavailable` when the guard fails.
- [x] Run focused tests and the relevant app/CFO suites; verify no production owner/data was changed by the source-only implementation.

### Task 10: Close campaign and product-analytics source disposition

**Status:** source disposition complete for this CFO-only slice; campaign attribution and activation/retention metrics remain unavailable. Honne has token `honne_en_base_20260823`, but the latest collector reports `report_window_mismatch` and the checked 2026-10-02 report had no matching row; Anicca has no campaign token. Anicca's 2026-10-03 Mixpanel data contains raw event counts (`app_opened=3`, `onboarding_started=1`, `paywall_primer_viewed=2`) but no purchase event or user-level cohort denominator. Honne has `no_verified_readable_funnel`; PostHog lacks a project-read credential; the product-analytics pack directory is empty. ASC report-instance reads show no App Sessions/Retention instance, and the private Retention query lacked a threshold-verified flag before the ASC web session expired. The daily summary now surfaces campaign IDs/status/reasons and product-pack missing reasons. No app repositories were changed.

**Files:** `apps/life-manager/scripts/marketing-asc-acquisition.js`, product analytics source/adapter, related tests.

- [x] Verify campaign identity and the exact app/date report window; show `campaign_identity_unavailable` for Anicca and `report_window_mismatch` / no matching rows for Honne, never zero attribution.
- [x] Audit available analytics sources and their cohort definitions; raw Mixpanel counts lack purchase/user-cohort denominators, Honne/PostHog sources are unavailable, and ASC retention lacks threshold proof. Preserve these source-specific gaps rather than inventing rates.
- [x] Show campaign and product-analytics reasons in the daily summary and run focused/full tests; leave app-repository instrumentation to its owner.

**Deferred mobile-team dependency:** activation, purchase, and retention cohorts need stable in-app events/user identity and campaign-tagged acquisition links. This CFO-only plan does not modify app repositories or reauthenticate the expired ASC web session.

## Verification

```bash
node --test apps/life-manager/scripts/marketing-asc-acquisition.test.js
python3 -m unittest skills.cfo.test_capafy_mobile_attribution
python3 -m unittest skills.cfo.test_loop_pnl
node --test apps/life-manager/lib/financial-record-mobile-apps.test.js apps/life-manager/lib/financial-manager-report.test.js apps/life-manager/lib/financial-manager-ingest.test.js apps/life-manager/scripts/marketing-product-summary.test.js
npm test --prefix apps/life-manager
```

Current live readbacks and their limits, including the 2026-10-04 production delta: `docs/evidence/cfo/2026-10-03-mobile-metrics-readback.md`.
