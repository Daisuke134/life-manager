# Mercor Human Gate Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make a completed Mercor person-bound step produce an append-only, exact account/listing/step resolution receipt so the next wake can resume the same application without stale human-gate state.

**Architecture:** The browser model reports a resolution candidate only after fresh official step readback. The parent pass validates the candidate's exact identity, completion status, and current evidence path, then calls the existing `HumanGateStore.resolve` API and records the returned receipt in the pass result. Existing notification and submission behavior remains unchanged.

**Tech Stack:** Python 3.14, JSON Schema, pytest/unittest, existing Mercor `HumanGateStore` and pass runner.

**Spec:** `docs/superpowers/specs/2026-09-17-mercor-first-income-design.md`

## Global Constraints

- Resolve only the same account, listing, and provider step after official `Completed` or `reused` readback.
- Never resolve from a card count, a title-only match, a different account, or a guessed listing/step identifier.
- Evidence references must be regular files under the current wake evidence directory.
- Gate resolution is append-only and idempotent; a missing or already-resolved gate is a no-op.
- The loop must not enter or impersonate interviews, assessments, recordings, camera, microphone, or screen-sharing steps.

## Review Focus

- A completed step on the wrong account must remain pending — covered by exact identity and same-account tests.
- A `reused` provider step must resume safely — covered by the action decision test.
- A stale/out-of-tree evidence path must block resolution — covered by evidence validation tests.
- A duplicate resolution must produce no second row — covered by store idempotence tests.
- An old result without the optional field must retain existing behavior — covered by pass contract compatibility tests.

### Task 1: Define the result contract and failing tests

**Files:**
- Modify: `apps/job-search-loop/schemas/mercor-pass-result.v1.schema.json`
- Modify: `apps/job-search-loop/tests/test_mercor_human_gate.py`
- Modify: `apps/job-search-loop/tests/test_mercor_pass_contract.py`

**Interfaces:**
- Add optional `resolved_human_gates` result rows with `account_id`, `listing_id`, `step_id`, `official_step`, `same_account`, `same_application`, and `evidence_ref`.

- [x] **Step 1: Write failing tests** for `reused` action, resolution row shape, prompt requirement, and legacy result compatibility.
- [x] **Step 2: Run focused tests** and confirm they fail because the schema/prompt/action do not yet support the contract.

### Task 2: Implement exact resolution and evidence validation

**Files:**
- Modify: `apps/job-search-loop/job_search_loop/mercor_human_gate.py`
- Modify: `apps/job-search-loop/job_search_loop/mercor_pass.py`

**Interfaces:**
- Extend `next_action` to accept official `reused` state.
- Add `reconcile_human_gate_resolutions(state_root, result, run_id, evidence_root) -> list[dict[str, Any]]`.
- Validate each resolution evidence path beneath the current pass root before resolving.
- Store receipts under `human_gate_resolutions` while leaving the model's requested rows intact.

- [x] **Step 1: Implement the smallest code needed for the failing tests.**
- [x] **Step 2: Run focused tests and confirm the new behavior passes.**

### Task 3: Wire the model contract and production pass

**Files:**
- Modify: `apps/job-search-loop/prompts/mercor-pass.md`
- Modify: `apps/job-search-loop/job_search_loop/mercor_pass.py`

**Interfaces:**
- Tell the model to read pending exact gates and emit a resolution row only after official same-application `Completed`/`reused` readback.
- Invoke reconciliation after model validation and before recording the pass summary.

- [x] **Step 1: Run the full job-search-loop test suite with the repository's required `PYTHONPATH`.**
- [x] **Step 2: Run `./bin/lm-loop-contract`.**
- [ ] **Step 3: Commit the plan and implementation on the dedicated branch.**

### Task 4: Promote and verify

- [ ] **Step 1:** Push the branch and open the focused PR.
- [ ] **Step 2:** Wait for all required CI checks.
- [ ] **Step 3:** Merge to `main`, cut an immutable release, and apply only `mercor-revenue-application`.
- [ ] **Step 4:** Verify loaded release SHA, one natural wake, exact gate-resolution evidence, and replay-zero.
