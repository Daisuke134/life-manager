# English eBook HeyGen CLI Runtime Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let only the English eBook owner resolve the installed HeyGen CLI and keep the CLI's anonymous telemetry from blocking its renderer, across the actual JavaScript-to-Python subprocess boundary.

**Architecture:** `runtime/loop/lm_loop_run.py::_child_environment_for_owner()` builds the English owner's environment with `LIFE_MANAGER_HEYGEN=<home>/.local/bin/heygen` when it has no nonempty override and `HEYGEN_NO_ANALYTICS=1`. `ebook-distribute-daily.js::renderInput()` then creates a minimal Python environment; it must explicitly forward those two values only for `ebook-en`. The HeyGen CLI documents the telemetry variable as its opt-out. Keep `.local/bin` out of shared `PATH` and leave Japanese/unrelated renderer environments unchanged.

**Tech Stack:** Node.js, Python 3, node:test, pytest, Life Manager immutable releases.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` — “eBook Monk current blocker cursor — 2026-10-08 10:44 JST”.

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

### Task 4: Reconcile the 08:00 English render without replay

**Files:**
- Read: protected local HeyGen effect sidecar `ebook-run.571924dc4e4867349fc6fd13.heygen-effect.json` (private state path is not committed).
- Production owner: `ebook-en-tiktok-daily`
- Evidence: canonical eBook cursor in `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

**Interfaces:**
- Consumes: the exact 08:00 occurrence, official HeyGen video/wallet reads, and official Postiz post list.
- Produces: a matched provider receipt or a retained unresolved fence with its exact missing evidence.
- Boundary: never calls `video create`, Postiz publish, or manually edits the sidecar.

- [x] **Step 1: Read the exact Postiz targets and today's posts**

Observed 10:22 JST: the English Monk, Japanese TikTok, and Japanese Instagram integrations all return `disabled=false`. Today's Postiz list has two eBook `PUBLISHED` posts (one per Japanese target) and zero English Monk posts.

- [x] **Step 2: Read HeyGen video pages and wallet**

Observed 10:22 JST: the full two-page title `Anicca` search returns zero videos. Wallet is USD 11.78; the sidecar recorded USD 12.30 before create. The USD 0.52 movement is not attributable to this create from the available evidence.

- [x] **Step 3: Preserve the old effect fence**

The sidecar remains `delivery_uncertain` without `video_id` or `provider_status`; `lm-loop status` remains `effect_status=unknown` and `next_action=official_readback_required`. Do not replay the same occurrence or clear the sidecar.

- [ ] **Step 4: Obtain exact provider-side create or billing evidence**

Use HeyGen's official video/billing readback to match a video ID or prove the wallet change is unrelated. If those records cannot identify the create, keep the effect fenced and record the exact missing provider artifact; a zero-result title search alone does not explain the wallet delta.

### Task 5: Preserve HeyGen provider IDs and safe renderer diagnostics

**Files:**
- Modify: `skills/earn/marketing-engine/render_eval/heygen_candidate.py`
- Test: `skills/earn/marketing-engine/render_eval/test_heygen_candidate.py`
- Modify: `apps/life-manager/scripts/ebook-distribute-daily.js::renderInput`
- Test: `apps/life-manager/scripts/ebook-distribute-daily.test.js`

**Interfaces:**
- Consumes: HeyGen `video create` result and renderer child-process result.
- Produces: a durable video ID/status before completion checks, and a sanitized parent error class/exit result.
- Boundary: a valid provider ID is recovered with `heygen video get <video-id>`; no retry path may issue a second `video create` for that request hash.

- [ ] **Step 1: Add a failing non-completed-create regression test**

Add `test_noncompleted_create_persists_video_id_and_replay_never_creates_again`. Mock `video create` returning a valid `video_id` with status `processing`; assert the intent stores both fields before returning reconciliation-required, and a second run uses `video get <video-id>` with exactly one total create call.

- [ ] **Step 2: Run the regression to verify RED**

Run: `python3 -m pytest skills/earn/marketing-engine/render_eval/test_heygen_candidate.py::test_noncompleted_create_persists_video_id_and_replay_never_creates_again -q`

Expected: FAIL because the current exception handler writes `delivery_uncertain` without the parsed video ID or status.

- [ ] **Step 3: Persist the provider ID/status before validating completion**

After parsing a valid ID, durably write `state=provider_created`, `video_id`, `provider_status`, and wallet-before data. For a non-completed status, return reconciliation-required and query that same ID on the next run; never call create again. Keep `delivery_uncertain` only when the provider ID itself cannot be proved.

- [ ] **Step 4: Add a sanitized subprocess failure regression**

Use the existing fake-renderer test to assert a nonzero result retains safe `error_class`/exit metadata while omitting arbitrary stderr text, credential-shaped strings, and request bodies.

- [ ] **Step 5: Implement minimal error propagation and run focused checks**

Make the Python renderer emit a stable failure class and let `renderInput()` propagate only that class and exit metadata. Run the two focused test files plus `git diff --check`.

- [ ] **Step 6: Commit and integrate the source repair**

Use a latest-main-derived owner branch, fresh read-only review, required CI, and the main merge path. Production release/apply stays in Task 6.

### Task 6: Promote the repair and verify one new English slot

**Files:**
- Production owner: `ebook-en-tiktok-daily`
- Evidence: canonical eBook cursor in `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

**Interfaces:**
- Consumes: merged main source, exact prior-effect disposition, and release-reconciler terminal state.
- Produces: one HeyGen render receipt and one exact Postiz `PUBLISHED` receipt for a distinct due slot.
- Pre-flight: free space remains above 2 GiB; current release and apply lock are read back; target owner is confirmed idle.

- [ ] **Step 1: Wait for the running release reconciler and read back terminal state**

Do not overlap its apply lock. Confirm the resulting immutable release SHA and current symlink.

- [ ] **Step 2: Verify the English owner's loaded SHA, argv, and scoped renderer environment**

If the owner is behind, run `launchctl-safe preflight` and apply only `ebook-en-tiktok-daily`. Confirm `LIFE_MANAGER_HEYGEN` and `HEYGEN_NO_ANALYTICS=1` are scoped to the English child; do not expose credential values in logs.

- [ ] **Step 3: Run one distinct natural slot after the 08:00 effect is safely resolved**

Use the registered owner once for the next distinct slot. Do not retry the old 08:00 occurrence. Join exact occurrence, HeyGen video ID/output SHA/wallet cost, Postiz post ID/state/public URL, and provider integration.

- [ ] **Step 4: Continue the daily receipt check from the canonical SSOT**

The target is three unique published posts per account/day (nine total), with one Japanese render shared across Japanese TikTok and Instagram. A single successful slot is not proof of recurring cadence.
