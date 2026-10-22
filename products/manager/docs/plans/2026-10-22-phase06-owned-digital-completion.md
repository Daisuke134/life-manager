# Phase 06 Digital Public-Good v2 Implementation Plan


> **歴史的なPhase 06 v2スコープ移行と受け入れ方法の手順書（実装順ではない）**
>
> **唯一の現行実装順は E01 → E02 → E03 → E04 → E05 → E06 → E07 → E08 → E09 → E10 → E11 → E12 → E13 → E14 → E15 → E16。** 次はE01です。E01〜E16の[実装計画](2026-10-22-manager-core-execution-plan.md)を実行し、その証拠で **F005 → F006 → F008 → F009** を判定してください。
>
> 本書の「Task 1〜Task 3」はF004/F007の対象外化と台帳移行という**歴史的スコープ更新手順**です。現在の開発カーソルを上書きするものではありません。「Task 4〜Task 5」の証拠照合はE14〜E16の作業後のF受け入れ判定です。元の資金・屋内試験は未実施です。SSOTは `../roadmap/tasks.json` だけです。


> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Do not treat the plan as evidence that anything changed. Follow RED → GREEN for each code change.

**Goal:** Remove the obsolete third-party money and facility permissions from Manager's Phase06 critical path, and finish a verifiable first-party public-internet technical improvement loop without inventing human-benefit evidence.
**Architecture:** Version the original SSOT rows in place; waive old F004/F007 transparently; redefine F005/F006/F008/F009 as owned public goods with an existing kernel/publisher/readback path; verify two distinct public assets by independent reads; keep P3/P4 unmeasured.
**Tech Stack:** Python 3.11+ standard-library JSON/unittest, existing Manager core, GitHub Pages/API, already established GitHub Actions digital service verification and six HTML route manifests.
**Spec:** `../specs/2026-10-22-phase06-owned-public-good-scope-amendment.md`.

## Global Constraints

- One canonical Manager registry `docs/roadmap/tasks.json`; legacy history preserved in `original_*` and independent archive. No new SSOT, no retroactive claims.
- The product source remains `Daisuke134/life-manager:products/manager`. Current main + owner research branch must be checked before writes.
- P0 simulation/advice, P1 actual external effect, P2 independent observed artifact change; P3/P4 human benefit/causal effect NOT_MEASURED. Do not invent users, harm reductions or p-values.
- Do not touch third-party bank accounts, indoor facilities, private users, healthcare records or external accounts. Existing platform owner authentication and precise write scope remain mandatory for owned-site publishing.
- User explicitly retired mandatory outside finance/facility requirements. The external actor adapters remain disabled, but are not blockers to the first-party digital mission.
- No automatic blog article publishing in this Phase06 code PR. Anicca public-site content remains managed by its existing authorized publisher.

## Review Focus

1. A skipped obsolete finance/room task still accidentally blocking an owned digital task.
2. Historical tests silently rewritten to imply real finance/indoor experiments occurred.
3. Technical site bytes promoted to human-benefit causal proof.
4. Two topic pages in one release misrepresented as statistically independent human interventions.
5. Stale live source, misplaced manifest, wrong commit, or a successful CI job without independent served-asset GETs.

### Task 1 — Capture historical source and make a fresh failing migration test

**Files:** Create `tests/test_phase06_owned_scope.py`, `docs/verification/PHASE06_V1_RETIREMENT_20261022.json`. Source `docs/roadmap/tasks.json`.
**Interfaces:** `check_owned_phase06(tasks: list[dict]) -> None` (one checker lives only in tests); old acceptance is archived with original byte-hash and commit.
- [ ] Write tests asserting F004/F007 are `skipped` with original_status=`blocked`, original descriptors, nonempty waiver; F005/F006/F008/F009 have no dependency on skipped tasks; no phase6 task asks for room/sensor/budget provider; H005 waiver unchanged.
- [ ] Run `python -m unittest discover -s tests -p 'test_phase06_owned_scope.py' -v`; RED on original blocked status.
- [ ] Preserve exact v1 F004–F009 rows, registry SHA and user decision in the historical JSON; do not edit existing completed items.
- [ ] Verify archive byte matches original before any migration. Commit test+archive in isolation.

### Task 2 — Versioned in-place SSOT migration

**Files:** Modify `docs/roadmap/tasks.json`, `docs/roadmap/ATOMIC_BACKLOG.md`; update legacy status assertions in `tests/test_backlog.py`, `test_phase06_unblocking.py`, `test_phase06_f001_u001.py`, `test_crossfield_research_20261021.py`, `test_phase06_internet_public_good.py`, `test_eba_landscape_sources.py`, `test_phase06_environment_atomic_plan.py`.
**Interfaces:** F004/F007 `skipped`, F005/F006/F008/F009 `todo` pending actual proof. For each changed row, `scope_version=2` and `original_*` fields preserve prior wording/status/depends.
- [ ] Verify RED from Task 1 and record the expected failure; restore baseline before editing if test does not fail.
- [ ] Change only F004–F009. Retire old finance/facility obligations; F005 first-party release; F006 honest technical outcome evaluation; F008 second independently observed public-resource topic; F009 common-gate two-target report. F005 depends K009; F008 depends F005/K010; F009 depends F006/F008. All other task statuses retained.
- [ ] Replace historical tests' *registry-status assertions* with skipped+waiver+unchanged safety checks, not their unrelated finance/indoor validation logic.
- [ ] Run `python scripts/make_roadmap.py`; `python scripts/make_roadmap.py --check`; test newly migrated contract and all existing tests. Verify no active task depends on retired F004/F007.
- [ ] Commit manifest+generated view+tests, collect actual test command/outcome.

### Task 3 — Reconcile the active product spec and legacy documentation

**Files:** Modify `docs/MANAGER_PRODUCT_SPEC.md`, `docs/verification/PHASE06_TO_12_ACCEPTANCE_20261022.md`; prepend a dated superseded-scope notice in `docs/roadmap/PHASE06_TO_COMPLETION_RESEARCH_JA.md` and `docs/roadmap/EBA_FROM_PHASE06_TO_END_TO_END_20261022.md`; add `docs/roadmap/PHASE06_V2_ACTIVE_PLAN.md`.
- [ ] RED test `test_active_spec_has_no_mandatory_external_blockers` asserts the current section and active plan have two archived waivers, no external prerequisite and no claim of measured welfare.
- [ ] Run the failing test, update the active text and historical headers without deleting old trial notes.
- [ ] GREEN: no confusion over v1/v2 scope; Phase06 v2 is labeled owner-operated, technical P2 first, P3/P4 unknown; no stale `F004/F007 blocked` inside the active executive summary.
- [ ] Commit only spec/notes/tests.

### Task 4 — Independently verify current owned-site public effect

**Files:** Add `scripts/phase06_owned_scope_proof.py`, `tests/test_phase06_owned_scope_proof.py`, and new read-only `.github/workflows/manager-phase06-v2-proof.yml`.
**Interfaces:** `collect_owned_result(commit_sha: str, fetcher) -> dict`; returns distinct `finance.html` and `mental.html`/ `physical.html` records: immutable provider commit+parent, public URL, observed sha256, independent HTTP GET timestamps, result=P2_ARTIFACT_ONLY, human_outcome=NOT_MEASURED, causal_effect_verified=False.
- [ ] RED tests wrong provider commit, forged manifest, missing source, changed external path, missing independently fetched page, duplicate content counted as same intervention, stale connection, unrelated site, URL redirect, unexpected auth header.
- [ ] Reuse `manager_core.digital_handoff`, `phase06_kernel_release.prove` and existing `public_goods` source audit. Do not reimplement its platform authority or treat a cached local fixture as live proof.
- [ ] GREEN synthetic test; run read-only public GET on networked GitHub Actions against the actual published provider commit. Save evidence artifact including full SHA/time and don't call historical P2 fresh if present bytes no longer match.
- [ ] Commit proof code/tests. Repeated runs must produce ZERO writes.

### Task 5 — Report and honestly decide completion state

**Files:** Write `docs/verification/PHASE06_DIGITAL_V2_RESULT_20261022.json`; add `tests/test_phase06_v2_result.py` and `docs/verification/PHASE06_DIGITAL_V2_RESULT_20261022.md`.
**Interfaces:** `validate_v2_result(report: dict, live_evidence: dict) -> dict` ensures F005 first scope, F006 outcome report, F008 distinct public asset and F009 shared guard have authentic receipts; preserves human_outcome=NOT_MEASURED.
- [ ] RED on forged readback, missing provider link, repeated same target called two assets, result proving welfare from bytes, irrelevant parent commit and unsupported assertion of two separate human field trials.
- [ ] GREEN with actual confirmed public provider/served bytes from Task4, measurable before/after technical checks, control/no-change reference, accessible page text and explicit unknowns.
- [ ] Set revised F005/F006/F008/F009 to `done` **only if all 4 revised acceptance contracts have independent, replayable proof**. Otherwise keep each `todo` with exact evidence required.
- [ ] Regenerate backlog, re-run all tests, inspect full Git diff, use normal PR/CI process. Verify no article publication, no unrelated files changed, exact branch state. Public benefit/causal proof remains unmeasured.

## Completion boundaries

**Success = technically complete v2** when canonical task IDs F001–F003 and revised F005/F006/F008/F009 are done and F004/F007 are explicitly **waived**, with actual external P2 proof. **Original third-party finance/indoor studies are NOT completed.** **Manager's larger mission is NOT yet proven.** If provider proof is unavailable/altered or tests fail, report a partial milestone and remaining atomic blockers instead of rewriting statuses.
