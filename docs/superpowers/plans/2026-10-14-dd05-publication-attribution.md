# DD05 Publication Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to execute this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make the existing scheduled truth pipeline preserve and attribute instrumented publications using exact publication and native receipts, while reporting unsupported attribution, cost, and intervention evidence as unknown.

**Architecture:** Keep `marketing-owner-events` as the sole scheduled measurement owner. Preserve immutable publisher-intent fields in the canonical publication identity ledger, sweep only exact resolved publication identities into the existing experiment-attribution builder, and write daily idempotent snapshots from the existing native metrics and business ledgers. Do not backfill legacy posts by fuzzy matching; do not add publisher or scheduler routes.

**Tech Stack:** Python 3.14, stdlib SQLite/JSONL, existing Marketing Engine modules and unit tests.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` — DD05.

## Global Constraints

- Only the existing `marketing-owner-events` owner writes its state and attribution ledger.
- Exact `publish_key`, Postiz ID, experiment/product/account identity, and native receipt are required; missing or conflicting identity stays unknown/unattributed.
- Capafy account or agent aggregates never become per-publication orders or revenue.
- `actual_cost_usd` and `human_interventions` are separate metrics; missing exact publication-scoped evidence stays unknown, never zero.
- No publisher route, account, cadence, provider state, or external post changes in DD05.
- No new package or scheduler.

## Review Focus

- Legacy provider refresh omits intent fields: retain the previous exact intent binding for the same Postiz ID.
- Conflicting publish key, experiment, creative, product, account, integration/platform, token, or native receipt on a Postiz ID: fail closed rather than overwrite.
- Unresolved or duplicate native receipt: do not emit a deterministic attribution snapshot.
- Missing click, sales/order, cost, or intervention evidence: preserve explicit unavailable/unknown reasons.
- Repeated hourly sweep: append at most one snapshot per `publish_key` per UTC date.
- The business metrics become mature at 24 hours in the existing builder; do not create a publication's first daily snapshot before that age. Later daily snapshots can capture the existing 72-hour and 168-hour native checkpoints.
- The owner-state pipeline has no publication-scoped actual-cost or complete human-intervention evidence source today. Emit those two metrics as `unknown` with separate reasons until exact evidence exists; do not infer zero from missing data or count the required visual approval as the full intervention total.

## Sweep Contract

`run_sweep(identity_path, post_metrics_path, business_path, attribution_path, report_path, observed_at)` reads the owner's canonical publication identity ledger, native post-metrics ledger, existing read-only business-outcomes ledger, and attribution ledger. It writes only the attribution ledger and the sanitized report under the existing owner's state root. It does not open the publisher intent database, call a publisher, or make a post.

An eligible row must be `PUBLISHED`, have `identity_status=resolved`, contain the complete immutable intent fields (`publish_key`, experiment, creative and asset hash, product, account, hook, renderer, attribution token, scheduled time), and have one unique Postiz/native receipt. Any conflicting duplicate or identity field fails closed. Rows without exact metadata remain in coverage counts and do not produce snapshots. Exact rows younger than 24 hours are counted as `not_mature_yet`, not eligible.

The sweep waits until a publication is at least 24 hours old, then appends no more than one snapshot for that `publish_key` on each UTC date. It checks the attribution ledger before building a same-day snapshot, so a later hourly invocation skips it instead of trying to replay a different `observed_at`. Native metrics must match the exact native post and experiment and be observed no later than the snapshot. Click queries use the exact product/token; business snapshots use the exact product/date. Missing inputs retain the builder's explicit unavailable/unknown reason.

The report is `evidence/metrics/attribution-sweep-latest.json` with `schema_version`, `observed_at`, `status`, `eligible_publications` (mature exact rows), `snapshots_written`, `snapshots_already_present`, `excluded` counts by reason (including `not_mature_yet`), and unknown metric counts. The command exits 0 when at least one mature exact publication is eligible (including an idempotent no-op), 3 when none is eligible (attention), and 1 on an execution or data-integrity error. The truth pipeline classifies exit 3 as attention, not failure.

Gate 13 `gate_pass` means the snapshot is structurally complete, contains no fabricated zero, and agrees with the exact click query. It does not mean revenue, cost, or human-intervention evidence is known or that the publication was profitable; unknown metrics and their reasons remain visible.

---

### Task 1: Preserve the intent-bound identity row

**Files:**
- Modify: `skills/earn/marketing-engine/identity/publication_ledger.py`
- Modify: `skills/earn/marketing-engine/publish/reconcile.py`
- Test: `skills/earn/marketing-engine/identity/test_publication_ledger.py`
- Test: `skills/earn/marketing-engine/publish/test_reconcile.py`

**Interface:** `reconcile.identity_row()` emits `publish_key`, `experiment_id`, `creative_id`, `product_id`, `account_id`, `integration_id`, `platform`, `hook_id`, `renderer_id`, `attribution_token`, `scheduled_at`, Postiz identity, and native receipt. `merge_rows()` retains these fields when a later provider-list row for the same Postiz ID omits them, and rejects conflicting non-null values, including a changed native receipt.

- [x] Add a regression test proving a provider refresh preserves intent-bound metadata and the exact native receipt.
- [x] Add a regression test proving conflicting identity metadata fails closed.
- [x] Run the two test files against the old implementation and confirm the intended RED failures.
- [x] Implement the minimal metadata-preserving merge and complete identity row.
- [x] Run both focused test files and `git diff --check` (28 passed, 9 subtests passed).

### Task 2: Make attribution snapshots complete and truthful

**Files:**
- Modify: `skills/earn/marketing-engine/measure/experiment_attribution.py`
- Modify: `skills/earn/marketing-engine/measure/verify_gate13.py`
- Test: `skills/earn/marketing-engine/measure/test_experiment_attribution.py`
- Test: `skills/earn/marketing-engine/measure/test_verify_gate13.py`
- Test: `skills/earn/marketing-engine/report/test_owner_report.py`

**Interface:** `build_snapshot()` accepts only an exact identity whose `publish_key`, experiment, creative/hash, product, account, integration/platform, token, scheduled time, Postiz ID, native ID, and native URL agree with the enriched intent context. The result schema advances to v2 and includes separate `actual_cost_usd` and `human_interventions` metric rows. Because no publication-scoped source exists today, DD05 always emits these metrics as null/unknown with distinct reasons and adds no cost/intervention input source. Existing Capafy aggregate sales remain unknown for per-publication revenue.

- [x] Add failing tests for a mismatched publish key/native receipt and for separate `unknown` cost/intervention metrics with explicit reasons. No publication-scoped source exists today, so DD05 does not invent one or claim measured values.
- [x] Verify those tests fail for the expected missing contract behavior.
- [x] Implement v2 snapshot validation and exact identity checks.
- [x] Update Gate 13 and owner-report fixtures for the expanded result set.
- [x] Run the focused attribution, Gate 13, and owner-report tests (17 passed, 22 subtests; owner report 3 passed).

### Task 3: Sweep exact publications from the canonical ledger

**Files:**
- Create: `skills/earn/marketing-engine/measure/attribution_sweep.py`
- Test: `skills/earn/marketing-engine/measure/test_attribution_sweep.py`

**Interface:** `run_sweep(...)` follows the Sweep Contract above. It reads source JSONL without modifying it, reports legacy/unresolved/ambiguous/mismatched coverage separately, and returns `attention` when no exact publication is eligible.

- [x] Add local JSONL fixtures for exact, legacy, unresolved, duplicate, and mismatched identity rows.
- [x] Add RED tests for exact selection, no snapshot before 24 hours, daily deduplication, and explicit attention on no eligible rows.
- [x] Implement the bounded sweep by calling the existing `build_snapshot()` and click-receipt reader.
- [x] Run the focused sweep tests and verify no test contacts a real provider (6 passed; all click queries use test callbacks).

### Task 4: Wire the sweep into the existing truth owner

**Files:**
- Modify: `skills/earn/marketing-engine/report/truth_pipeline.py`
- Test: `skills/earn/marketing-engine/report/test_truth_pipeline.py`

- [x] Add the attribution sweep after publication identity reconciliation and native metric collection, using only `marketing-owner-events` state plus the existing read-only business-outcomes source.
- [x] Treat sweep return code 3 as `attention`, like a publication-identity coverage gap; hard errors remain pipeline failures.
- [x] Add tests for command order, owner state paths, attention handling, and continued owner reporting.
- [x] Run focused truth-pipeline tests, source-boundary verification, and `git diff --check` (58 tests, 31 subtests; owner-report 3 tests).

### Task 5: Integrate and read the natural owner result

- [x] Commit and push the initial SSOT, plan, and implementation (`84714bf8cb9454deda7aa2fdb427aa77b2a0fa93`); PR #8009 is open.
- [x] Merge latest `origin/main` (`c900bf0aa3b0d5f00ceff32d01f9d108df4c7dea`) into the DD05 branch locally (`143ff3ea743e9137f1d5de3b2397e4bc2a5d292d`); the merge adds seven upstream SSOT lines without conflicts.
- [x] Push the latest-main merge plus the refreshed SSOT cursor and Task 5 list (`82d877ed42ec325732b50739f8c11a0db26c9b4c`); verify the remote branch and PR point to that head.
- [ ] Require exact-head CI to pass, then merge to main under the repository's merge policy.
- [ ] Allow the existing release reconciler to ship the immutable main release and apply only when the truth owner is idle and its owner lock is clear.
- [ ] Let the registered cleanup owner produce a fresh cleanup receipt and restore eligible release capacity; do not stop active processes or delete protected paths.
- [ ] Let the existing fence reconciler resolve `capafy-distribute-daily:18de4680b4bcfe18-18857` from exact provider evidence; do not manually wake the publisher, clear the fence, or replay the occurrence.
- [ ] Reconcile the four owner-report `sending` / `delivery_unknown` message keys from exact Telegram MTProto history through `OwnerReportStore.reconcile_delivery()`; do not resend or edit the delivery ledger manually.
- [ ] Verify the first natural `marketing-owner-events` pass from the new SHA and its attribution-sweep evidence; if the live ledger still has no intent-bound rows, report that exact coverage gap without claiming attribution completion.
- [ ] Keep DD05 open while attribution is absent or unverified; advance the SSOT cursor to DD06 only after natural owner readback and exact sweep evidence are verified.
