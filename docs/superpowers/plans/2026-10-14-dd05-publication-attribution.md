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

**Cursor reorder, 2026-10-14T10:43Z:** Old: DD05 production adoption, then DD06 Writer. New: finish Writer fence integration; add CTA-lineage-to-paid measurement; resume DD05 after current-main capacity recovery; then run a controlled Writer experiment and DD07–DD12. The local capacity check fails because the checkout is shallow; GitHub compare verifies donor 9c71a1a is a 49d9858 ancestor. The verified read-only requirement is 252653568 bytes, with 141164 KiB free at 10:43Z. The cleanup owner passed at 10:39Z but no fresh receipt is persisted; release reconciliation failed at 10:41Z.

**Current cursor readback, 2026-10-14T11:08Z (supersedes prior capacity numbers):** Current remote/local `origin/main` is `dfb8213c4a51dcbc74d925d4ee8ee136a1978e64`; the task worktree is at `7e8e37f39a886801ac2e4bddb76026c5e64d5b33`, based on `13f59bca114e48e284b3b55fee1c1f450c66b2c0` (current main is 15 commits ahead, 0 behind that base). `df` reports 168508 KiB available at 11:08Z; a 2-byte scratch-file write now succeeds, but the volume still reports 100% full. The cleanup owner failed at 11:08:06Z (`life-manager-disk-cleanup:18de60c1a2f71ed8-55795`, `storage_write_failed_pre_effect` / `scratch_enospc`, no evidence refs); its last successful terminal was 10:58:44Z and there is no fresh receipt. The capacity requirement for `dfb8213` is unmeasured; do not reuse the 252653568-byte figure measured for `49d9858`. The dirty worktree still has four tracked edits; preserve its untracked `.DS_Store`.

**Cursor/order change, 2026-10-14T11:08Z:** Old cursor: integrate the Writer fence patch, then build CTA-to-paid measurement. New order: (1) restore scratch writes through the registered cleanup owner and synchronize the task branch to current main; (2) rerun fence tests and complete review/CI/integration; (3) implement CTA lineage and destination identity using the existing Web funnel/Writer join; (4) resume DD05 release adoption after a fresh capacity gate; (5) establish a mature outcome baseline, then run a controlled experiment; (6) continue DD07–DD12. Reason: current main advanced beyond the branch base and the cleanup receipt remains stale. Do not manually clear the active cleanup owner or any effect fence.

**Writer cursor**

1. [x] Add resumed-run RED case; expected inconclusive/run_reached_publication was observed.
2. [x] Pair publication rows with attempt starts from valid run directories; validate IDs and refuse symlink paths. AST and diff checks pass.
3. [x] Real read-only reconcile returns effected with 4 HTTP 200 URLs and closed=false; resolver test double passes without production mutation.
4. [x] Run the focused fence suite (24 passed); real read-only reconcile returns four HTTP 200 URLs, effected/closed=false; injected resolver test did not mutate the fence.
5. [ ] Push a dedicated latest-main branch and open a focused PR; pass exact-head CI/review and merge. Production release/apply is a separate DD05 gate; only the registered reconciler may close receipt-backed proof. Never resolve manually or replay.
6. [x] Classify all 8 retained runs; 14/439 ledger rows join. Dispatch, prepublication ambiguity, identity-gate block, pending run state, and outcome-coverage gap are distinct.

**Writer CTA outcome measurement — required before experimentation**

1. [ ] Preserve product_id, run_id, artifact_id, variant_id, and click_id from the /lm landing request through authenticated first-touch and Stripe paid/refund events. The current UTM-only sanitizer and sign-in forwarding drop these fields.
2. [ ] Reuse lm_web_funnel_events, lm_users.web_first_touch, lm-web-funnel-report, and the Writer artifact join; keep request counts separate from unique people.
3. [ ] Bind each publication destination to a distinct attribution identity. A single article-ja click_id is reused across published copies, so it cannot compare destinations.
4. [ ] Verify per-artifact views/landing requests, activation, paid invoices, refunds/net, production cost, and intervention from exact receipts. Keep missing values unknown and do not run an experiment before the join works.

**DD05 remains open**

1. [x] Merge Writer DD06 source fix PR #8037 as `e0a53f101a5da13d9cb6d09d16bc80b67c7b19b2` after current-main sync; all 11 automated checks passed on head `8e7df3ce7b52d52b3eb64eb20e8ef3bc9954ef3a`. CodeRabbit skipped manual review. This source merge does not prove production release/adoption or revenue.
2. [ ] Obtain a fresh exact release-capacity measurement for then-current `origin/main`. The requirement for `dfb8213` is unmeasured; the 252653568-byte result is historical for `49d9858` only.
3. [ ] Recover only the newly measured shortfall through the registered cleanup owner; preserve protected and unknown paths. Do not treat a passing process terminal without a fresh receipt as capacity recovery.
4. [ ] Cut/apply a main-derived immutable release only after the exact gate; verify installed SHA and natural owner terminal.
5. [ ] Inspect the persisted attribution sweep. The 08:36Z artifact has 0 eligible rows, 0 snapshots, 1323 legacy-uninstrumented and 31 unpublished rows.
6. [ ] Verify a unique exact-identity publication after 24h maturity or keep DD05 open. Revenue/cost/intervention remain unknown without exact sources.

HTTP 200 proves publication only; resolver test double left fence open.

**Separate operational cursors**

- [ ] Adopt the merged PR #8022 source only after the standard release gate passes, then reconcile `capafy-distribute-daily:18de4680b4bcfe18-18857` with occurrence-bound official evidence; do not clear or replay it.
- [ ] Reconcile the two `delivery_unknown` rows only from exact history/receipt evidence; never resend or edit the ledger manually.
- [ ] Continue capacity diagnosis through the registered cleanup owner; preserve protected and unknown paths.

DD05 is shared publication-measurement infrastructure. The first agent-level EDD vertical slice remains Writer as recorded in the SSOT; Capafy distribution reuses this evidence path when exact per-publication outcomes exist.


**Verification attempt, 2026-10-14T11:11Z:** The focused Writer command `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider skills/writer-agent/tests/test_article_fence_reconcile.py` exited 1 before collection: pytest reported no usable temporary directory while creating capture files. This is not a test failure or pass. The 11:08 two-byte scratch probe did not restore pytest temp-file capability; DD06 verification remains open, and no current-main test result is claimed.


**Verification update, 2026-10-14T11:15Z:** `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider skills/writer-agent/tests/test_article_fence_reconcile.py` passed 24/24 on worktree HEAD `7e8e37f`; AST and `git diff --check` also pass. This is source-only; latest-main sync, CI/review, integration, release, and natural readback remain open. Git-reported orphan packs totaling 15990784 bytes were reclaimed after confirming no open handles. The cleanup owner still has no receipt after its 11:08Z `scratch_enospc` failure; exact capacity for `dfb8213` remains unmeasured. The current pytest temp `pytest-505` was removed; older temp dirs were preserved.

**Current branch state, 2026-10-14T11:56Z:** GitHub `main=72ff5f9` is integrated locally by merge `6418770`; branch `fix/writer-resumed-publication-fence-20261014` has a four-file diff. The focused Writer suite passes 24/24 on the merged 72ff tree. PR #8037 is open with remote head `1c9c553` and base `72ff5f9`; its merge conflict is resolved locally, but the updated head is not pushed yet. CodeRabbit passed on the previous head and skipped manual review; exact-head checks remain pending. At 11:56Z, `df` showed 184236 KiB free; cleanup last passed at 11:45Z but `last-receipt.json` remains dated 2026-10-10. Exact release capacity is unmeasured. Production release, owner adoption, and natural readback remain open. Preserve `.DS_Store` as untracked.


**PR readback, 2026-10-14T12:12Z:** PR #8037 is OPEN and CLEAN on `main=72ff5f9`, head `553e882`; all automated checks pass. CodeRabbit skipped manual review, and self-review found no Critical or Important issue. The merged-main Writer suite is 24/24. This doc update creates a new head and requires fresh exact-head checks. After checks pass, merge using the authorized no-human-loop path; CTA lineage, DD05 production adoption, baseline/experiment, and DD07–DD12 remain open. Exact release capacity and natural business outcome remain unverified.

**Latest-main synchronization, 2026-10-14T21:32Z:** main `70a9ead` is integrated with a non-force merge commit whose parents are the prior PR head `10301b7` and current main. The local fetch failed with ENOSPC; this server-side Git Data merge preserves the latest main tree and the four intended PR files. The new head reruns CI. Exact release capacity remains unmeasured; no production apply or provider effect is claimed.


**EDD integration checkpoint, 2026-10-14T12:52Z:** Current main is `3de213777ef82996ada82ea6bbc4d898afcee7a9`. Before synchronization PR #8037 was head `04a0b1c4145e4f73d6ca6314bdb7699c2e831c0f`, based on `70a9ead`; its prior-head checks all passed, but main advanced and the branch conflicted. This update creates a non-force merge commit with the current main parent and preserves the PR four intended files. Exact-head checks rerun on the new commit. Writer source/test are unchanged by this sync. No current-main local pytest, capacity measurement, release adoption, natural outcome, or revenue is claimed. After integration, CTA lineage and destination identity are the next EDD implementation atom.


**DD06 merge readback, 2026-10-14T13:03Z:** PR #8037 is MERGED as `e0a53f101a5da13d9cb6d09d16bc80b67c7b19b2`; its tree exactly matches tested PR head `8e7df3ce7b52d52b3eb64eb20e8ef3bc9954ef3a`. The 11 automated checks passed. Local worktree remains preserved because its lease is active and it contains user-generated `.DS_Store`; no worktree removal is claimed. Next EDD atom: CTA lineage and destination identity. Production adoption, current release capacity, natural publication outcomes, and publication-level revenue remain unverified.
