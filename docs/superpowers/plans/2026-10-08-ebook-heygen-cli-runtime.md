# English eBook HeyGen CLI Runtime Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let only the English eBook owner resolve the installed HeyGen CLI and keep the CLI's anonymous telemetry from blocking its renderer, across the actual JavaScript-to-Python subprocess boundary.

**Architecture:** `runtime/loop/lm_loop_run.py::_child_environment_for_owner()` builds the English owner's environment with `LIFE_MANAGER_HEYGEN=<home>/.local/bin/heygen` when it has no nonempty override and `HEYGEN_NO_ANALYTICS=1`. `ebook-distribute-daily.js::renderInput()` then creates a minimal Python environment; it must explicitly forward those two values only for `ebook-en`. The HeyGen CLI documents the telemetry variable as its opt-out. Keep `.local/bin` out of shared `PATH` and leave Japanese/unrelated renderer environments unchanged.

**Tech Stack:** Node.js, Python 3, node:test, pytest, Life Manager immutable releases.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` — “eBook Monk current blocker cursor — 2026-10-08 10:05 JST”.

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
- The English JavaScript wrapper forwards both HeyGen values to the real Python renderer subprocess.
- Japanese eBook owners do not receive the English renderer path.
- Japanese renderer subprocesses do not receive the HeyGen values, even if present in their input environment.
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

Push this main-derived branch and open PR #6999. The canonical spec owns promotion order and production readback.

### Task 3: Preserve the scoped HeyGen environment through the renderer boundary

**Files:**
- Modify: `apps/life-manager/scripts/ebook-distribute-daily.js::renderInput`
- Test: `apps/life-manager/scripts/ebook-distribute-daily.test.js`

**Interfaces:**
- Consumes: the owner environment passed to `run()`.
- Produces: `LIFE_MANAGER_HEYGEN` and `HEYGEN_NO_ANALYTICS` in the English Python renderer subprocess only.
- Pre-flight: no shared interfaces; the test uses an isolated fake renderer process and never calls Postiz or HeyGen.

- [x] **Step 1: Add a failing subprocess-boundary regression test**

Run `run()` with the active English registry fixture and a fake Python executable that records its inherited environment. Assert that the English child receives both HeyGen values, while a Japanese child receives neither and unrelated secrets are not forwarded. Update the stale English route assertions to match the approved-active registry.

- [x] **Step 2: Verify RED**

Run: `node --test --test-name-pattern='renderer receives scoped HeyGen environment' apps/life-manager/scripts/ebook-distribute-daily.test.js`

Observed: FAIL because the renderer child received `null` for `LIFE_MANAGER_HEYGEN`, as expected from the current allowlist.

- [x] **Step 3: Forward only the two English values**

Pass `run()`'s environment into `renderInput()`. Add the two keys to its subprocess allowlist only when `product === "ebook-en"`; do not pass the rest of the owner environment.

- [x] **Step 4: Verify GREEN and related behavior**

Observed: focused Node selection 3/3 PASS; complete `ebook-distribute-daily.test.js` 11/11 PASS; `python3 -m pytest runtime/loop/tests/test_lm_loop_run_bounds.py -q` 133 passed; `bash scripts/verify-source-boundary.sh` and `git diff --check` PASS.

- [x] **Step 5: Update PR #6999, review, and merge**

PR #6999 merged as `46ec94bdea884fd7afa61e603a79fdd1b3048ef7` after a fresh independent review with no findings and all required Security Scan checks passing. Production release and owner readback remain in the canonical spec.

### Task 4: Promote the merged renderer fix and verify English Monk delivery

**Files:**
- Production owner: `ebook-en-tiktok-daily`
- Evidence: canonical eBook cursor in `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

**Interfaces:**
- Consumes: the immutable release built from main commit `46ec94b` and current owner effect fence.
- Produces: one verified English HeyGen video and one Postiz `PUBLISHED` receipt per due slot.
- Pre-flight: same-time host free space at or above 2 GiB, cleanup receipt with zero errors/protected deletions, reconciler terminal, and safe launchd preflight.

- [ ] **Step 1: Recover and verify host capacity**

Use the disk-cleanup owner and its allow-listed inventory. PR #7003 adds Xcode DerivedData as a candidate; keep the existing open-file guard. Keep leased/unknown/open paths protected. Do not enable the disabled disk sentinel/guard because they send Telegram alerts and apply writer backpressure. Require fresh cleanup `free_after >= 2,147,483,648` bytes and same-time `df -Pk /` above 2 GiB.

- [ ] **Step 2: Verify/apply the main-derived release**

The current symlink points to `20261008T094938-c65449ef`; latest main is `4056d35903` from PR #7003. After release reconciler terminal and apply-lock readback, verify the owner's loaded SHA/argv. If it is behind, apply only `ebook-en-tiktok-daily` through the safe control path. Read back its English-only child environment.

- [ ] **Step 3: Start one due owner occurrence and read back provider receipts**

Only after the exact old effect fence is reconciled, start the registered owner once. Join HeyGen video ID/SHA, wallet delta, Postiz integration/post ID, `PUBLISHED` state, public URL, and the exact occurrence.

- [ ] **Step 4: Verify recurring daily cadence**

Use official Postiz reads to confirm each of the three eBook accounts reaches its configured three slots/day without cross-account compensation or duplicate effects.
