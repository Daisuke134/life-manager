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

### Task 5: Integrate and verify production adoption

**Merged source and documentation**

- [x] DD05 source tasks 1–4 are merged in PR #8009 (`ec0ff40b44b6b453132d36388615277158bc5dc6`); exact-head CI and CodeRabbit passed.
- [x] Post-merge cursor PR #8016 is merged (`b76d6df9a49fce8c1c09a618feb6902b4678d48b`).
- [x] Capafy fence reconciliation and fail-closed Postiz readbacks are merged in PR #8022 (`8b2f8686d71b288dd8a5ea0cbe8bc132283c244a`).
- [x] DD05 cursor cleanup is merged in PR #8020 (`6c569277bf52d25db39f36fbc1c1d5467be26688`); latest main also contains the Capafy runtime checkpoint PR #8023 (`0ecf503a7ea21913652db85d86279c76ffabc09d`).
- [x] `lm-loop doctor` reports 191 registry entries, with no missing, unmanaged, or installed-retired labels.

**Live evidence, read-only capture `2026-10-14T06:55Z`**

- Current main is `0ecf503a7ea21913652db85d86279c76ffabc09d`; `/Users/anicca/loops/current` remains release `20261014T150809-87f2425e`, SHA `87f2425ed209f00a3a0174b1b798e580917752b1`, cut 06:08:45Z. PR #8022 is source-only until a newer release is cut and applied.
- `life-manager-release-reconciler` terminal `18de52ad97952188-52792` ended 06:51:24Z with exit 1. The bounded log for the same interval shows the 87f fleet pass was partial (11 changed, 11 skipped, 0 errors), followed by `cut-loop-release` failing with `release_capacity_measurement_failed`.
- **Root-cause evidence:** the release-capacity calculator in `runtime/host/disk_admission.py::release_capacity_bytes` runs `git merge-base --is-ancestor <current-release-sha> origin/main` to validate its immutable dependency-bundle donor. The source checkout is shallow (`git rev-parse --is-shallow-repository=true`); this local ancestry check returns 1 for donor `87f2425e`. GitHub's compare of `87f2425e...0ecf503a` returns `status=ahead`, `ahead_by=17`, `behind_by=0`, with merge base `87f2425e`. Calling the measurement function directly reproduces `CalledProcessError` at that local ancestry check. **Inference:** the shallow local graph prevents proof of a valid remote ancestor; it is not evidence that the release is actually outside main.
- Host storage was `558219264` bytes free at 06:52Z and `capacity_recovered=false`. The last exact release requirement (`2394329088` bytes, 15:30 JST) predates PR #8022; it is historical only. A fresh requirement for current main is not yet measured. The RRC log also records `scratch_enospc` while writing terminal events.
- `marketing-owner-events` remains on old SHA `52f33c67c3da765af516209e35c394b47e2e6f13`; its latest terminal `18de51a57c57e5a8-26311` ended 06:36:49Z, exit 1 in `report` (`reconcile=attention/3`, `collect=pass`, `report:action=fail`, `report:checkpoint=fail`; remaining report stages passed). The output includes two `delivery_unknown` keys; this run is not DD05-source evidence.
- `capafy-distribute-daily` remains safely fenced on `a299acc04573ab916fb261ad7ff94b1d3f79a119`. Latest occurrence `18de52a169f44300-51572` ended 06:49:16Z with `effect_status=unknown`, no provider receipt, and no official readback. The main fix is not deployed.

**Remaining DD05 acceptance, in order**

1. [ ] Add a failing regression in `runtime/loop/tests/test_cut_loop_release_pressure.py` for a shallow source checkout whose immutable donor is verified as an ancestor by the remote. Fix `runtime/host/disk_admission.py::release_capacity_bytes` so it can establish valid ancestry without weakening the non-ancestor rejection; the direct measurement for current main must return required bytes instead of `CalledProcessError`.
2. [ ] Re-run the read-only capacity measurement for exact main SHA `0ecf503a7ea21913652db85d86279c76ffabc09d`; record its exact required bytes and the free-space readback.
3. [ ] Recover the measured shortfall through the registered cleanup owner. Preserve open/protected/unknown paths; do not bypass the capacity gate or delete protected data.
4. [ ] After the exact preflight passes, cut a new immutable release from current main through `bin/cut-loop-release.sh origin/main` and verify its descriptor.
5. [ ] Let the registered release reconciler apply the new release to `marketing-owner-events`; verify the exact fleet row, loaded argv, and installed SHA. Do not manually wake, stop, restart, or apply the owner.
6. [ ] Read the first natural terminal from the new SHA and inspect the persisted attribution-sweep stage output. A separate Telegram report-stage failure does not invalidate a persisted successful sweep artifact.
7. [ ] Verify at least one unique exact-identity `PUBLISHED` publication has passed the 24-hour maturity window and is represented in the persisted sweep. If none is eligible, record the exact coverage gap and keep DD05 open.
8. [ ] Keep publication-level orders/revenue, actual cost, and human interventions `unknown` without exact sources; Capafy account/agent aggregates do not prove post-level revenue or profit uplift. Close DD05 only when terminal and sweep output share the same exact identity; then advance to DD06.

**Separate operational cursors**

- [ ] Adopt the merged PR #8022 source only after the standard release gate passes, then reconcile `capafy-distribute-daily:18de4680b4bcfe18-18857` with occurrence-bound official evidence; do not clear or replay it.
- [ ] Reconcile the two `delivery_unknown` rows only from exact history/receipt evidence; never resend or edit the ledger manually.
- [ ] Continue capacity diagnosis through the registered cleanup owner; preserve protected and unknown paths.

DD05 is shared publication-measurement infrastructure. The first agent-level EDD vertical slice remains Writer as recorded in the SSOT; Capafy distribution reuses this evidence path when exact per-publication outcomes exist.
