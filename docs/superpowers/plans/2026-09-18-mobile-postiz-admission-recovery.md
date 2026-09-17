# Mobile Postiz Admission Fence Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task by task. Read each applicable current Superpowers skill before acting. Steps use checkbox syntax for tracking.

**Goal:** Prove which mobile publish fences are eligible for provider reconciliation and prepare a safe one-owner executor without changing Postiz routing.

**Architecture:** Keep the existing host admission ledger and `resolve_unknown_occurrence()` as the only eventual fence-clearing boundary. The checked-in reconciler is deliberately read-only: it validates a private identity sidecar and an explicit Postiz readback proof, then reports `ready`; a provider-owned executor must perform the live readback again immediately before any future resolve.

**Tech Stack:** Python 3.14, Node.js, SQLite admission ledger, existing Life Manager runtime events, Postiz publication adapters and launchd-owned `lm-loop` commands.

**Spec:** `docs/superpowers/specs/2026-09-18-mobile-postiz-admission-recovery-design.md`

## Global constraints

- Work from fresh `origin/main` in one dedicated worktree; never edit the dirty normal checkout.
- Read the current registry row, loaded plist, event, admission occurrence and provider receipt before acting on an owner.
- Use official provider readback for effect-bearing rows; local ledgers and browser state are supporting evidence only.
- Never clear claimed rows, retry an uncertain effect, change destination IDs/cadence, enable OBOU, or mutate a sibling owner.
- Apply or restart at most one exact owner through `lm-loop`; preserve the old immutable release and rollback receipt.

## Atomic TODO

### Task 1: Freeze the current mobile fence inventory

**Files:**
- Read: `config/loop-registry.json`
- Read: `config/marketing-destinations.json`
- Read: `runtime/host/resource_admission.py`
- Read: private `~/.local/state/life-manager/host-admission/resources/admission-v2.sqlite3` and `events.jsonl`
- Create: a secret-free evidence file under `docs/superpowers/evidence/mobile-postiz-admission/`

- [x] Enumerate the 17 affected mobile/Honne owners and their `released`/`claimed` unknown occurrences from SQLite: 14 released, 3 claimed.
- [x] Join each released occurrence to its exact run report and publication effect identity. The current event rows do not carry the required identity, so all 17 are explicitly `inconclusive`; no timestamp inference was used.
- [x] Record the active destination account and integration reference from the canonical destination contract. Confirm OBOU is held out.
- [x] Run the targeted status command for each owner and save the blocker, installed release SHA and loaded state in `docs/superpowers/evidence/mobile-postiz-admission/mobile-fence-inventory.json`.

### Task 2: Preserve exact identity at the runtime boundary

**Files:**
- Modify: `runtime/loop/lm_loop_run.py` at admission claim, summary and terminal event construction
- Modify: `runtime/loop/runtime_event.py` only if the existing schema needs the identity fields
- Test: `runtime/loop/tests/test_lm_loop_run_bounds.py` and the runtime-event tests

- [x] Write a failing test that a publish occurrence's summary/event contains the exact occurrence ID, `effect_key`, `job_id`, account/integration reference and media/caption hashes before an effect-bearing child exits.
- [x] Write a failing test that a missing or malformed identity produces a held `effect_unknown` result and never becomes retryable.
- [x] Implement the smallest repository-owned identity record using the existing runtime scratch and private state paths; keep credentials and provider tokens outside the release. Nonzero effect-bearing runs persist only a validated sidecar and add an `lm-effect://` evidence reference.
- [x] Run the focused Python tests and validate the event schema: 109 focused tests pass (110 when the isolated CEO light-pass check is included).

### Task 3: Add provider-owned official readback proof

**Files:**
- Modify: `apps/life-manager/lib/marketing-video-publication-adapter.js`
- Modify: `apps/life-manager/lib/marketing-native-carousel-publication-adapter.js`
- Test: the corresponding adapter and publication-chain tests

- [x] Add pre-effect identity emission to the existing video and native-carousel adapters. Video account IDs resolve through the canonical destination contract; native carousel lanes use their exact account and integration IDs. PR #5423 merged as `c947b72dbc7f`.
- [x] Write failing tests for exact account, integration, provider post ID, content hash and reconciled status; reject a same-platform different-account receipt. The provider executor suite has 9 tests.
- [x] Reuse the existing `postiz_video.py` official post parser and canonical ledger contracts; the executor has no create or second Postiz client path. Provider-observed content and local media-hash evidence remain separate.
- [x] Return an explicit proof object containing `owner_id`, `occurrence_id`, `verified`, `provider_receipt_id` and the exact matched identity. PR #5453 merged as `23afec79cd640f343e5ac152a4950f90faac4b4d`.
- [x] Run the focused adapter/provider tests: 37 mobile publication tests, 9 provider-executor tests and 24 Postiz adapter tests pass. No live provider request was made during verification.

### Task 4: Gate released rows for a provider executor

**Files:**
- Create: `apps/life-manager/scripts/mobile-postiz-effect-reconcile.py`
- Test: `apps/life-manager/tests/test_mobile_postiz_effect_reconcile.py`
- Create: `apps/life-manager/scripts/mobile-postiz-provider-reconcile.py`
- Test: `apps/life-manager/tests/test_mobile_postiz_provider_reconcile.py`
- Modify: `runtime/host/resource_admission.py` to support an atomic expected-state predicate

- [x] Write tests proving the script skips `claimed` rows and inconclusive/mismatched receipts.
- [x] Implement owner-scoped, read-only proof gating with a redacted output. The script never issues SQL updates or calls `resolve_unknown_occurrence`.
- [x] Run the script in read-only mode for a historical occurrence; it returned `identity_missing_or_invalid` and left the ledger unchanged. PR #5431 merged as `b325a34d5b8e3ca9eaecc396311026d58d0ce399`.
- [x] Implement a provider-owned executor that performs official Postiz API/account readback in the same call and invokes `resolve_unknown_occurrence` only after a fresh proof. `--resolve` requires the authoritative admission DB and passes an atomic `expected_state='released'` predicate; PR #5453 merged as `23afec79cd640f343e5ac152a4950f90faac4b4d`. Historical rows whose exact identity is missing remain blocked.

### Task 5: Resume and verify one natural wake

**Files:**
- Read: the exact target plist and immutable release `RELEASE.json`
- Read: provider distribution ledger and runtime `events.jsonl`
- Read: admission SQLite before and after the wake

- [x] Re-read the admission ledger, loaded argv and target's last terminal event. The ledger still has 17 mobile/Honne `effect_unknown=1` rows (14 released, 3 claimed); `life-manager-honne-ja` is `loaded-idle` but terminal `blocked`, exit 75, blocker `host_admission_deferred:resource_effect_unknown`.
- [ ] Permit one natural scheduled wake for one verified owner through the existing owner path; do not post a synthetic test item. No owner is currently eligible because no historical row has an exact identity proof.
- [ ] Verify separate process result, terminal runtime event, official provider receipt, exact content/account mapping and replay-zero.
- [ ] Repeat only after the prior owner has a terminal receipt; leave inconclusive/claimed rows fenced.

### Task 6: Decide release alignment after recovery

**Files:**
- Read: `~/loops/current/RELEASE.json`
- Read: loaded mobile plist `ProgramArguments` and `LIFE_MANAGER_RELEASE_SHA`
- Modify only through: `lm-loop apply` from a pushed immutable main-derived release, if evidence requires it

- [x] Confirm the current release contains both canonical mobile trees and each inspected target plist points to one exact immutable release directory. The observed current release is main-derived; the loaded Honne releases remain older immutable directories.
- [x] No runtime cutover is needed while all mobile publish fences remain unresolved; keep production unchanged and do not mutate loaded jobs during the posting window.
- [ ] If a cutover is required, apply one label at a time, verify plist argv, loaded argv, release SHA, state path and rollback receipt, then wait for a natural terminal event.

### Task 7: Close out

- [x] Run focused tests, `git diff --check`, source-boundary verification and the relevant `lm-loop` targeted status checks for the read-only reconciler; seven reconciler tests pass and no ledger row changed.
- [x] Update the spec evidence with verified/inconclusive counts and the exact remaining fences; the 17 historical mobile/Honne rows remain inconclusive or claimed-held.
- [x] Commit and push the dedicated branch, merge after checks pass, and remove the exact worktree without force. PR #5438 merged as `e3e44eb76d8e12d6476c9c3d74662ab4bb7f0a41`; the worktree path and Git registration were then removed without force.
