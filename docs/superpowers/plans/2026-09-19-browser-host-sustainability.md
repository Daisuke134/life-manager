# Browser and Host Sustainability Implementation Plan

> **For agentic workers:** Follow `superpowers:executing-plans` task by task. Use a dedicated worktree from fresh `origin/main`. Each task has one owner and one verification gate; do not edit another Codex's active branch, browser profile, or state.

**Goal:** Stop the accumulation of visible empty Chromium windows, keep enough disk space for Life Manager's local loops, and prove the 14 product loops' supporting jobs can continue from main-derived releases.

**Architecture:** Reuse the existing CDP lease ledger, target ownership registry, disk governor, release reconciler, and loop registry. First prove which process creates and fails to close each browser context. Fix that producer or its shared lifecycle boundary, then reclaim only positively owned leftovers. Continue the existing disk-cleanup P0–P7 sequence rather than installing a second cleaner. Verify the fleet from loaded argv, state receipts, and natural wakes.

**Tech Stack:** Python 3, CDP over WebSocket, macOS launchd, Git worktrees, pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md` (A15), `docs/superpowers/specs/2026-08-20-life-manager-disk-cleanup-loop-design.md` (P0–P7), and `README.ja.md` (14 product loops).

## Global constraints

- A product loop is a capability, not one process; keep its browser, inbox, reporting, and reconciliation jobs when required by `config/loop-registry.json`.
- The host finite admission default is eight in `runtime/host/resource_admission.py`; installed per-job environment and live reservations determine the effective limit. Browser contexts have a separate default limit of 16 per lease ledger. Do not conflate these with Capafy's five review slots.
- Preserve profiles, credentials, sessions, state ledgers, dirty/unpushed worktrees, current/loaded/open releases, and rollback pins. An unowned `about:blank` URL alone is never deletion authority.
- Use the existing `launchctl-safe` preflight for targeted production changes. Coordinate an active owner before touching its browser/profile/state; never restart the whole host or app server as a cleanup test.
- Record every action as source SHA, loaded SHA, browser port/profile, owner, target/context ID, before/after count, and receipt. Do not call source tests or a successful command a production effect.

## Design choices

1. **Recommended — owner lifecycle repair.** Bind a created target to a durable owner before returning it; close it or preserve a recoverable tombstone on every failure edge. The current `cdp_context_lease.py` already retains `cleanup_pending` after failed disposal and `audit` intentionally reports unknown contexts. Extend only the proven missing boundary. This makes GC safe and keeps the existing 16-context bound meaningful.
2. **Rejected — periodic “close every blank page.”** It is short but may close another Codex's new page before navigation or an authenticated loop's working context. The prior incident showed 9222 blank pages returning after manual sweeps; URL is insufficient ownership evidence.
3. **Rejected — restart all Chromium and reduce to 14 processes.** Restart destroys in-flight forms and sessions. The 14 catalog entries are backed by many jobs; process count is not a zombie count.

## Ordered tasks

### Task 1: Recover host headroom and capture a read-only baseline

**Files:** Update only the existing disk spec's live evidence/cursor: `docs/superpowers/specs/2026-08-20-life-manager-disk-cleanup-loop-design.md`. No new cleaner.

**Interfaces:** Input is the installed `life-manager-disk-cleanup` plist, `host-inventory.json`, `last-receipt.json`, `df`, and the current release pins. Output is a timestamped byte ledger and the exact next P0–P7 item.

- [ ] Read `df -k /Users/anicca`, the current disk receipt, loaded/installed cleanup argv, and `docs/superpowers/plans/2026-09-02-disk-cleanup-diff-patches.md`. Mark stale receipts as stale; do not infer that a configured five-minute job is executing.
- [ ] Identify the owner of growth since the prior inventory, using the existing bounded host inventory. Record `free_before`, each candidate's path/bytes/owner/open-path result, and `free_after`. If the inventory probe times out, record the gap; do not promote an unknown path into a delete candidate.
- [ ] Run the existing allow-listed cleanup only under its own lock. Preserve every open, pinned, dirty, or unclassified path. If it reclaims zero bytes, fix the specific writer's retention/finalizer or complete the current P0–P7 item; do not rerun the same zero-yield sweep as a substitute.
- [ ] Verify free space rises above the spec's 11 GiB recovery floor and no protected deletion occurred. The normal 30 GiB target and 24-hour/7-day observation remain P7 gates; report actual values if they cannot yet be achieved.
- [ ] Commit and push the updated canonical cursor and evidence summary on a dedicated branch. Integrate only after the spec's own acceptance gates pass.

### Task 2: Attribute every new blank context to a creator

**Files:** Modify `skills/browser/scripts/cdp_context_lease.py`, `skills/browser/scripts/cdp_default_tab.py`, or `target_ownership.py` only if Task 2 evidence proves a missing creation/cleanup boundary. Add a focused test alongside the affected script.

**Interfaces:** `context_inventory()` and `Target.getTargets` provide context/target IDs; the lease and target-owner ledgers provide task/owner/PID. The diagnostic receipt contains port, profile, loaded release SHA, parent PID, operation, context/target ID, and outcome, without URLs, cookies, or credentials.

- [ ] Capture two CDP inventories on ports 9222 and 9223 and all **configured** lease/target-owner file paths from the loaded job environments. Compare context IDs with ledgers and the list of active owner PIDs; do not assume only the default `leases.json` exists.
- [ ] Trace `Target.createBrowserContext` and `Target.createTarget` callers in the **loaded** releases, including `cdp_default_tab.py`, `cdp_context_lease.py`, Playwright callers, and startup scripts. Correlate a newly observed ID with the creator's own log/receipt and terminal outcome. A sample with no attributable creator is a diagnostic gap, not a cleanup candidate.
- [ ] Reproduce one failing edge in an isolated browser profile: creator dies after CDP creation and before owner claim; CDP disposal times out; owner release loses its response. Write the smallest test that fails on the demonstrated edge. Use `test_cdp_context_lease_orphan_census.py` and the existing owner/GC tests as fixtures.
- [ ] Add the focused regression to the test file for the failing boundary. Its essential assertion is that a created context remains attributable and can be reclaimed after the creator exits:

  ```python
  assert created_context_id in {row["context_id"] for row in lease_rows.values()}
  assert gc_result["reaped"] == [owner]
  assert foreign_context_id in browser_context_ids_after_gc
  ```

  Run `python3 -m pytest -q skills/browser/scripts/test_cdp_context_lease_orphan_census.py` (or the matching `test_cdp_default_tab*.py` for a target-claim failure) before the fix and require the new case to fail for the expected reason.
- [ ] Select the proven repair: reuse the existing seed target when the caller needs one page, or durably reserve/claim the new target before exposing it; on failed creation/claim/close, retain an owner-backed cleanup record. Keep `audit` read-only for unknown contexts.
- [ ] Re-run the same focused test and the existing `test_cdp_context_lease_gc_lock.py`, `test_cdp_context_lease_hangs.py`, and target-owner tests. Require the new target's owner to be recoverable after a forced child exit and require GC to leave foreign contexts untouched. Commit/push this one fix before starting another producer.

### Task 3: Cut over the browser owners and remove old leftovers

**Files:** No source edit unless Task 2's acceptance fails. Use `bin/lm-loop`/`launchctl-safe` through the repository's documented release path and the browser owner commands; preserve owner-specific state.

**Interfaces:** Pushed main SHA → immutable release → targeted installed and loaded argv → natural owner wake → CDP inventory/lease receipt.

- [ ] Merge the Task 2 fix after focused acceptance, cut one main-derived immutable release, and update only affected browser-owning jobs when their current work is idle. Check the user/GUI launchd preflight before any apply; if unavailable, leave the planned cutover pending with the exact preflight result.
- [ ] For each owner, verify the installed and loaded release SHA match the intended release. Exercise one natural wake that opens, navigates, closes, and releases a page. Read back the owner's terminal receipt and its CDP target count.
- [ ] Reclaim only contexts with a surviving owner-backed tombstone or a confirmed dead owner plus matching context ID, after re-reading CDP and lease state immediately before disposal. Separately report older unknown contexts; investigate or coordinate them instead of sweeping them by URL.
- [ ] Observe two complete natural wake cycles with no net blank-window growth on 9222/9223, zero surplus visible blank windows after owner idle, and no loss of nonblank authenticated pages. Repeat after the normal idle interval. If counts rise, return to Task 2 with the new IDs and loaded SHA.

### Task 4: Prove host and 14-loop sustainability

**Files:** Update the existing A15 foundation cursor and disk P0–P7 cursor; do not create a competing task list. Source fixes belong to the specific failed owner only.

**Interfaces:** `README.ja.md` maps 14 product capabilities to `config/loop-registry.json` jobs. Loaded argv, event SHA, state/ledger, and provider receipts establish each job's real status.

- [ ] Build a 14-row matrix from the README: required supporting job IDs, installed SHA, loaded SHA, most recent natural terminal, effect status, and exact blocker. Include the eight-slot host admission readback and per-class occupancy; keep Capafy review-slot readback separate.
- [ ] Run the existing release reconciler and `lm-loop doctor` read-only first. For each mismatch, repair only that owner through the normal main → immutable release → targeted apply path. A loaded/running process is not proof that its business effect succeeded.
- [ ] Confirm the disk-cleanup owner produces a fresh receipt on its five-minute cadence and that free bytes remain at or above 11 GiB for 24 hours. Continue the canonical P0–P7 plan to its 30 GiB normal target and seven-day state-write gate.
- [ ] Confirm every required job has at least one post-cutover natural terminal at the intended release; no browser contexts accumulate beyond owner limits, no ENOSPC or protected deletion occurs, and no effect-unknown action is retried without provider readback. Record exceptions by owner; do not mark all 14 healthy from a single `doctor` result.
- [ ] Push the evidence/cursor updates. Make one final integration only after the complete acceptance matrix passes; report any remaining external gate explicitly.

## Immediate stop conditions

- A live owner is writing the same browser profile/state or an application form is in flight: perform read-only attribution and wait for that owner's idle boundary before cutover.
- `df` falls below 512 MiB or a state write fails: cease new discretionary build/release allocation, preserve existing sessions and ledgers, and run the existing fail-closed disk recovery path. Do not delete unknown paths.
- CDP gives an unknown owner, conflicting lease rows, or a failed disposal response: retain the context, emit a receipt, and investigate its creator. Never treat `about:blank` as ownership proof.

## Plan self-review

The browser task has a source test, isolated failure reproduction, production cutover, and natural readback. Disk recovery delegates to the already ordered P0–P7 spec. Fleet proof uses the 14 product catalog and measured supporting jobs. No task authorizes broad process killing, profile deletion, or unowned tab disposal.
