# Ryu Manual Fence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep Coconala talkroom `18211957` permanently outside the Paid loop while leaving every other eligible room runnable.

**Architecture:** Apply one immutable manual-room set at both queue observation and active-item admission. The existing targeted/manual workflow remains available outside the loop; no provider message is sent by this change.

**Tech Stack:** Python 3.14, pytest, existing Coconala Paid owner.

**Spec:** `docs/superpowers/specs/2026-09-22-paid-fulfillment-all-platforms-design.md` and `docs/superpowers/plans/2026-09-22-coconala-paid-manual-exception-and-live-fulfillment.md`.

## Global Constraints

- Ryu `18211957` stays manual-only permanently.
- The loop must continue processing an eligible non-Ryu room in the same wake.
- No provider mutation is part of this code change.
- Production uses only a pushed immutable release after focused tests and `lm-loop-contract` pass.

## Review Focus

- Orders-only observation containing Ryu: Ryu is absent while another room remains.
- A caller bypassing orders filtering and passing Ryu directly to active admission: Ryu is still absent.
- Empty/manual-only input: no unrelated queue or admission behavior changes.

### Task 1: Enforce the permanent Ryu fence

**Files:**
- Modify: `skills/earn/gig/scripts/paid_direct.py:194,6768`
- Test: `skills/earn/gig/tests/test_paid_remote_wait.py:5068`
- Modify: `docs/superpowers/specs/2026-09-22-paid-fulfillment-all-platforms-design.md`

**Interfaces:**
- `MANUAL_ONLY_TALKROOM_IDS: frozenset[str]` remains the single manual-room source.
- `_paid_active_items(args, items)` returns only non-manual items.

- [x] **Step 1: Write the failing test**

  Change the existing observation test to expect Ryu to be filtered and add a direct active-item assertion for a mixed Ryu/non-Ryu list.

- [x] **Step 2: Run the focused test and verify RED**

  Run `pytest -q skills/earn/gig/tests/test_paid_remote_wait.py -k 'observation_does_not_exclude_ryu or manual_ryu_room'`.
  Expected: fail because the manual set is currently empty.

- [x] **Step 3: Implement the minimal fence**

  Set `MANUAL_ONLY_TALKROOM_IDS = frozenset({"18211957"})` and add the same membership guard to `_paid_active_items`.

- [x] **Step 4: Run the focused test and verify GREEN**

  Run the same pytest command; expect all selected tests to pass.

- [x] **Step 5: Run the relevant suite and contract check**

  Run `pytest -q skills/earn/gig/tests/test_paid_remote_wait.py` and `./bin/lm-loop-contract`.

- [x] **Step 6: Update the runtime checkpoint and commit**

  Record the code/test evidence in the all-platforms spec, then commit and push the dedicated branch.
