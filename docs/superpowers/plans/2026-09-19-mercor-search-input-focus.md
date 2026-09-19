# Mercor Search Input Focus Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Mercor's visible search input recover once from a provider SPA rerender that removes focus before typing, while preserving real keyboard input and fail-closed behavior.

**Architecture:** Keep the existing `DirectCDPPage.type_target` input path and its real `Input.dispatchKeyEvent`/`Input.insertText` events. If the first post-click focus/selection observation fails before any text is inserted, reacquire the same exact target once and re-check focus; a second failure remains an explicit action error. No provider selector, synthetic value assignment, or external retry is added.

**Tech Stack:** Python 3, asyncio, CDP, unittest/pytest.

**Spec:** `docs/superpowers/specs/2026-08-22-mercor-life-manager-consolidation.md` and `apps/job-search-loop/prompts/mercor-pass.md`.

## Global Constraints

- Use only the leased Mercor CDP page and the repository-owned browser helper.
- Never assign `.value` or dispatch synthetic `input`/`change` events as the search action.
- Retry only before text insertion and at most once; preserve fail-closed error reporting.
- Validate with focused tests, the Life Manager loop contract, an immutable release, and loaded-owner readback before claiming production repair.

### Task 1: Prove the focus-loss recovery behavior

**Files:**
- Modify: `apps/job-search-loop/tests/test_direct_cdp.py`
- Test: `apps/job-search-loop/tests/test_direct_cdp.py`

**Interfaces:**
- Consumes: `DirectCDPPage.type_target`.
- Produces: a regression test that fails when the first focus observation is false and passes only when one bounded re-focus attempt succeeds.

- [ ] **Step 1: Add the failing test**

  Add an async test with `resolve_target` returning the same coordinates, `evaluate` returning `False` then `True`, and `call` recording two mouse click sequences plus one text insertion. Assert that typing completes and only one `Input.insertText` call occurs.

- [ ] **Step 2: Run the focused test and verify RED**

  Run `python3 -m pytest apps/job-search-loop/tests/test_direct_cdp.py -q -k focus_loss_recovery`.
  Expected: failure because the current implementation raises `visible text target did not accept whole-value selection` after the first observation.

### Task 2: Implement the minimal bounded recovery

**Files:**
- Modify: `apps/job-search-loop/job_search_loop/browser_agent/direct_cdp.py`
- Test: `apps/job-search-loop/tests/test_direct_cdp.py`

**Interfaces:**
- Consumes: the exact target and coordinates returned by `resolve_target`.
- Produces: `type_target` that reacquires the same target once before raising the existing error.

- [ ] **Step 1: Re-run the RED test**

  Confirm the failure is the expected focus-loss error, not a fixture or import error.

- [ ] **Step 2: Add one bounded re-focus attempt**

  Extract the existing mouse-focus and selection observation into a local helper. If selection is false, call `resolve_target` again, repeat one mouse click, and re-check selection. Do not send keyboard events until selection succeeds; keep the existing error on a second failure.

- [ ] **Step 3: Run the focused test and verify GREEN**

  Run `python3 -m pytest apps/job-search-loop/tests/test_direct_cdp.py -q -k 'focus_loss_recovery or type_selects_the_existing_whole_value'`.
  Expected: PASS.

- [ ] **Step 4: Run the full direct-CDP suite**

  Run `python3 -m pytest apps/job-search-loop/tests/test_direct_cdp.py -q`.
  Expected: all tests pass with no new warnings.

### Task 3: Promote and verify the Mercor owner

**Files:**
- No additional source files; use the canonical release and loop registry.

**Interfaces:**
- Consumes: merged `origin/main`, `bin/cut-loop-release.sh`, and the existing `mercor-revenue-application` owner.
- Produces: one immutable release, loaded argv/SHA readback, a natural terminal receipt, and no new uncertain submission.

- [ ] **Step 1: Run `./bin/lm-loop-contract` and push the branch**

- [ ] **Step 2: Merge the focused PR into `main` and cut an immutable release**

- [ ] **Step 3: Apply only `mercor-revenue-application` through `lm-loop` after the current wake is idle**

- [ ] **Step 4: Read back loaded release SHA, profile/auth state, terminal result, Telegram receipt, and `effect_unknown`**

- [ ] **Step 5: Confirm the next natural wake records search query values/cards and either a verified submission or an exact fit/human-gate reason without duplicate submission**
