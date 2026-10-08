# Revenue Admission Floor Implementation Plan

> **For agentic workers:** use the native single-session execution path; complete each task's check before moving to the next.

**Goal:** Let explicitly revenue-priority finite owners use the existing 1 GiB disk floor while preserving the 2 GiB floor for borrow/support owners.

**Architecture:** Reuse the existing registry metadata, disk-floor helper, `resource_admission` queue, and per-owner producer guards. Extend `runtime/loop/lm_loop_run.py::_disk_floor` from `critical_paid` to `admission_class=revenue` with `priority=revenue`; do not change global concurrency, SQLite schema, provider paths, or external effects.

**Tech Stack:** Python 3, JSON loop registry, stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` (R18 and the 2026-10-08 23:24 JST capacity section).

## Global Constraints

- `LIFE_MANAGER_HOST_MAX_FINITE_RUNS` remains 8 by default; no unbounded concurrency.
- Revenue/critical-paid disk floor defaults to 1 GiB and never falls below 512 MiB.
- Borrow/support owners retain the 2 GiB floor.
- `disk_headroom_unavailable` remains fail-closed for every class.
- Keep Connector/Job Hunter's inner 512 MiB guards and preserve Fundraiser effect fences; never replay `effect_unknown`.
- Do not change admission DB schema, provider/browser configuration, launchd state, or watchdog installation in this source PR.

## Review Focus

- `priority=revenue` on a non-revenue admission class must not receive the lower floor.
- Missing or unknown priority must retain the 2 GiB floor.
- Invalid configured floors must not silently fall below 512 MiB or above 2 GiB.
- Disk availability below 1 GiB must still defer revenue owners before provider dispatch.
- A post-claim disk drop below the class floor must release/requeue without running the provider child.

---

### Task 1: Extend the existing revenue floor safely

**Files:**

- Modify: `runtime/loop/lm_loop_run.py::_disk_floor`
- Test: `runtime/loop/tests/test_lm_loop_run_bounds.py`

**Interfaces:**

- Consumes: registry `admission_class`, `priority`; `RECOVERY_FLOOR_BYTES` and the existing critical-paid floor setting.
- Produces: the same integer floor consumed by both pre-enqueue and post-claim `_disk_headroom_deferred` checks.

- [ ] **Step 1: Write the failing regression tests**

Add `test_revenue_priority_uses_one_gib_disk_floor` to assert:

  - `admission_class=revenue`, `priority=revenue` gets 1 GiB.
  - `admission_class=revenue`, `priority=critical_paid` retains 1 GiB.
  - `admission_class=borrow`, even with `priority=revenue`, gets 2 GiB.
  - missing priority gets 2 GiB.
  - configured floor is clamped to `[512 MiB, 2 GiB]`.

Add `test_revenue_loop_dispatches_between_one_and_two_gib_free` to assert a revenue owner can enqueue/claim at 1.5 GiB while a borrow owner defers before enqueue. Add `test_revenue_loop_still_defers_below_one_gib` and assert no provider child runs.

- [ ] **Step 2: Run the new tests and confirm RED**

Run: `python3 -m unittest runtime.loop.tests.test_lm_loop_run_bounds.RevenueDiskFloorTest -v`

Expected: the revenue-priority cases fail because only `critical_paid` currently receives 1 GiB.

- [ ] **Step 3: Implement the minimal floor rule**

In `_disk_floor(entry)`, apply the existing configurable 1 GiB floor when both `admission_class == "revenue"` and `priority` is `revenue` or `critical_paid`; clamp the configured value to the 512 MiB producer minimum and 2 GiB shared maximum. All other entries continue to use `RECOVERY_FLOOR_BYTES`.

- [ ] **Step 4: Run focused checks**

Run: `python3 -m unittest runtime.loop.tests.test_lm_loop_run_bounds -v`

Expected: all admission-bound tests pass, including existing critical-paid, unavailable-disk, and post-claim requeue cases.

Run: `git diff --check && bash scripts/verify-source-boundary.sh`

Expected: both pass.

- [ ] **Step 5: Commit the focused source change**

Create a fresh latest-main architecture worktree after PR #7156 merges. Commit `runtime/loop/lm_loop_run.py` and `runtime/loop/tests/test_lm_loop_run_bounds.py`, push, then obtain exact-head CI and a fresh read-only `ship` review.
