# English eBook HeyGen CLI Runtime Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let only the English eBook owner resolve the installed HeyGen CLI and keep the CLI's anonymous telemetry from blocking its renderer.

**Architecture:** `runtime/loop/lm_loop_run.py::_child_environment_for_owner()` builds the child environment for eBook owners. The English owner gets `LIFE_MANAGER_HEYGEN=<home>/.local/bin/heygen` when it has no nonempty override, plus `HEYGEN_NO_ANALYTICS=1`. The HeyGen CLI documents that variable as its telemetry opt-out; it prevents an unrelated PostHog DNS error from failing CLI calls. Keep `.local/bin` out of the general `PATH` and leave Japanese and unrelated owners unchanged.

**Tech Stack:** Python 3, pytest, Life Manager immutable releases.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` — “eBook Monk current blocker cursor — 2026-10-08 09:05 JST”.

## Global Constraints

- `main` is the sole code source; production uses a main-derived immutable release.
- Reconcile external effects against exact provider evidence; never retry an ambiguous publish.
- Credentials stay in the private credentials SSOT and never enter source, plan, or logs.
- Apply only the `ebook-en-tiktok-daily` owner for this change.

## Review Focus

- Missing or empty `LIFE_MANAGER_HEYGEN` uses the English owner's home-scoped CLI path.
- An explicit `LIFE_MANAGER_HEYGEN` value keeps precedence.
- The English fix does not add `~/.local/bin` to shared `PATH`.
- HeyGen telemetry opt-out is present for the English owner only.
- Japanese eBook owners do not receive the English renderer path.
- Unrelated owners retain their original environment.

### Task 1: Scope HeyGen CLI resolution to the English owner

**Files:**
- Modify: `runtime/loop/lm_loop_run.py::_child_environment_for_owner`
- Test: `runtime/loop/tests/test_lm_loop_run_bounds.py`

**Interfaces:**
- Consumes: `loop_id`, `base` environment, and optional `home` path.
- Produces: `LIFE_MANAGER_HEYGEN` for `ebook-en-tiktok-daily` only when no nonempty override is supplied.
- Pre-flight: no shared interfaces.

- [x] **Step 1: Write the failing regression test**

Add `test_english_ebook_child_environment_sets_scoped_heygen_cli_path` asserting that the English owner receives the literal `<tmp_path>/.local/bin/heygen`, that its `PATH` does not gain `.local/bin`, that the Japanese owner has no `LIFE_MANAGER_HEYGEN`, and that an explicit English override remains unchanged.

- [x] **Step 2: Run the test to verify RED**

Run: `python3 -m pytest runtime/loop/tests/test_lm_loop_run_bounds.py::test_english_ebook_child_environment_sets_scoped_heygen_cli_path -q`

Expected: FAIL because `LIFE_MANAGER_HEYGEN` is absent for the English owner.

- [x] **Step 3: Implement the minimal environment binding**

Set `LIFE_MANAGER_HEYGEN` to `(home or Path.home()) / ".local/bin/heygen"` only for `ebook-en-tiktok-daily` and only when the inherited value is empty. Do not widen `PATH`.

- [x] **Step 4: Run focused verification**

Run: `python3 -m pytest runtime/loop/tests/test_lm_loop_run_bounds.py -q`

Expected: PASS.

- [x] **Step 5: Commit the source and regression test**

Commit the focused code/test diff on the existing main-derived eBook task branch and update PR #6990. Reuse this task worktree and PR because they already own the same eBook Monk goal; after CI passes, merge and follow the canonical owner-release path in the spec.

### Task 2: Keep HeyGen telemetry from failing the English renderer

**Files:**
- Modify: `runtime/loop/lm_loop_run.py::_child_environment_for_owner`
- Test: `runtime/loop/tests/test_lm_loop_run_bounds.py`

**Interfaces:**
- Consumes: the English eBook owner's child environment.
- Produces: `HEYGEN_NO_ANALYTICS=1` for `ebook-en-tiktok-daily` only.
- Pre-flight: no shared interfaces.

- [x] **Step 1: Write the failing regression test**

Add `test_english_ebook_child_environment_disables_heygen_telemetry_only_for_english_owner` asserting that the English owner receives `HEYGEN_NO_ANALYTICS=1`, while the Japanese eBook owner and `article-daily` do not receive that variable.

- [x] **Step 2: Run the test to verify RED**

Run: `python3 -m pytest runtime/loop/tests/test_lm_loop_run_bounds.py::test_english_ebook_child_environment_disables_heygen_telemetry_only_for_english_owner -q`

Expected: FAIL because `HEYGEN_NO_ANALYTICS` is absent for the English owner.

- [x] **Step 3: Implement the scoped telemetry opt-out**

Set `HEYGEN_NO_ANALYTICS` to the documented value `1` only for `ebook-en-tiktok-daily` in `_child_environment_for_owner()`.

- [x] **Step 4: Run focused verification**

Run: `python3 -m pytest runtime/loop/tests/test_lm_loop_run_bounds.py -q`

Expected: PASS.

- [x] **Step 5: Commit the source and regression test**

Push this main-derived branch and open a PR. The canonical spec owns promotion order and production readback.
