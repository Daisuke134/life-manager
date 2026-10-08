# English Monk Instagram Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a release-reconciler self-handoff safe when Launchd explicitly reports `not running` with no PID, so the eBook publishing owner can converge without stopping or restarting a live service.

**Architecture:** Keep the existing per-label apply lock and two-read idle proof. Accept `not running` only when PID is absent; keep inconsistent PID and all other unknown states fail-closed. Then promote through the existing main/immutable-release path and continue the English Monk Instagram publication cursor in the SSOT.

**Tech Stack:** Bash, Python `unittest`, `launchctl-safe` fixture, GitHub PR checks.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

## Global Constraints

- `main` is the only source of truth; production uses immutable releases.
- Do not stop or restart the release reconciler; let its owner path reach a natural terminal.
- Preserve the per-label lock through repeated state reads, bootout, target bootstrap, and readback.
- Do not clear or replay an unknown eBook publishing effect without exact provider readback.
- The requested English Monk destination is Instagram; do not silently fall back to TikTok.

## Review Focus

- `state = not running` with no PID: require two consecutive observations before handoff.
- A transition from `waiting`/`idle` to `not running`: do not combine observations across states; require two consecutive `not running` observations.
- `state = not running` with a PID: fail closed and do not boot out the old service.
- Any other unsupported Launchd state: keep failing closed and do not boot out the old service.
- Verify target loaded SHA and argv after bootstrap using the existing receipt contract.

---

### Task 1: Reconcile explicit Launchd not-running state

**Files:**
- Modify: `runtime/loop/tests/test_reconcile_agent_self_handoff.py`
- Modify: `bin/reconcile-agent-self-handoff.sh`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

**Interfaces:**
- Consumes: the existing `launchctl-safe print` output, per-label run lock, and handoff receipt schema.
- Produces: a handoff only after two `not running` observations with no PID, followed by the existing old-service absence and target SHA/argv readbacks.

- [x] **Step 1: Add the failing fixture tests** `test_handoff_accepts_not_running_old_service_without_pid` and `test_handoff_fails_closed_when_not_running_has_pid`; keep `test_handoff_fails_closed_on_unknown_old_service_state` as the unknown-state guard.
- [x] **Step 2: Run the focused valid-state test** `python3 -m unittest runtime.loop.tests.test_reconcile_agent_self_handoff.ReconcilerSelfHandoffTest.test_handoff_accepts_not_running_old_service_without_pid`; observed exit 1 because the helper reported `old_service_state_unknown`.
- [x] **Step 3: Implement the minimal `not running` branch** in `bin/reconcile-agent-self-handoff.sh`; require an empty PID and reuse the existing two-observation counter under the lock.
- [x] **Step 4: Run focused acceptance** with `python3 -m unittest discover -s runtime/loop/tests -p 'test_reconcile_agent_self_handoff.py'`, `bash -n bin/reconcile-agent-self-handoff.sh`, and `git diff --check`.
- [x] **Step 5: Commit the tested source, fixture, and SSOT cursor update on the task branch.** Commit `fe9c4dc4` pushed; a later review added Task 2.

### Task 2: Keep not-running observations consecutive

**Files:**
- Modify: `runtime/loop/tests/test_reconcile_agent_self_handoff.py`
- Modify: `bin/reconcile-agent-self-handoff.sh`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

**Interfaces:**
- Consumes: Task 1's explicit `not running` branch and the same fake Launchd/receipt contract.
- Produces: handoff eligibility only after two consecutive `not running` observations, even if preceding states were `waiting` or `idle`.

- [x] **Step 1: Add fixture sequence** `waiting` then `not running`, and test `test_handoff_requires_two_consecutive_not_running_observations_after_waiting`.
- [x] **Step 2: Run that test first**; observed failure because the shared idle counter allowed bootout after only one `not running` observation (2 reads, expected at least 3).
- [x] **Step 3: Add a `not_running_observations` counter**; reset it on `waiting`, `idle`, or `running`; use it only for the exact `not running` branch while preserving the PID guard.
- [x] **Step 4: Run the full handoff test file, shell syntax check, and `git diff --check`; all 12 tests and both static checks pass.**
- [x] **Step 5: Commit and push the regression fix to PR #7115.**
