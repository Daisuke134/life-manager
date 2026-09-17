# Mobile Postiz Admission Fence Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task by task. Read each applicable current Superpowers skill before acting. Steps use checkbox syntax for tracking.

**Goal:** Clear only provider-verified mobile publish fences and resume one idempotent natural wake per owner without changing Postiz routing.

**Architecture:** Keep the existing host admission ledger and `resolve_unknown_occurrence()` as the only fence-clearing boundary. Add the smallest missing identity/readback bridge in the existing publication adapters, then run a serialized recovery pass and verify provider receipt plus replay-zero.

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
- [x] Run the focused Python tests and validate the event schema: 109 relevant tests pass.

### Task 3: Add provider-owned official readback proof

**Files:**
- Modify: `apps/life-manager/lib/marketing-video-publication-adapter.js`
- Modify: `apps/life-manager/lib/marketing-native-carousel-publication-adapter.js`
- Test: the corresponding adapter and publication-chain tests

- [x] Add pre-effect identity emission to the existing video and native-carousel adapters. Video account IDs resolve through the canonical destination contract; native carousel lanes use their exact account and integration IDs. PR #5423 merged as `c947b72dbc7f`.
- [ ] Write failing tests for exact account, integration, provider post ID, content hash and reconciled status; reject a same-platform different-account receipt.
- [ ] Reuse each adapter's existing `reconcile()`/receipt verifier. Do not add a second Postiz client or a local-only proof path.
- [ ] Return an explicit proof object containing `owner_id`, `occurrence_id`, `verified`, `provider_receipt_id` and the exact matched identity.
- [x] Run the focused adapter tests: 37 tests pass. The provider official-readback portion remains open; no new provider request was made.

### Task 4: Reconcile released rows only

**Files:**
- Create: `apps/life-manager/scripts/mobile-postiz-effect-reconcile.py`
- Test: `apps/life-manager/tests/test_mobile_postiz_effect_reconcile.py`
- Reuse: `runtime.host.resource_admission.resolve_unknown_occurrence`

- [ ] Write a failing test proving the script skips `claimed` rows and inconclusive/mismatched receipts.
- [ ] Write a failing test proving one exact official proof clears one `released` unknown occurrence and does not touch another owner.
- [ ] Implement owner-scoped, one-occurrence-at-a-time reconciliation with a redacted evidence output. Never issue direct SQL updates.
- [ ] Run the script in read-only/dry inventory mode first; execute clearing only for rows with official proof.

### Task 5: Resume and verify one natural wake

**Files:**
- Read: the exact target plist and immutable release `RELEASE.json`
- Read: provider distribution ledger and runtime `events.jsonl`
- Read: admission SQLite before and after the wake

- [ ] Re-read the shared apply lock, host owner list, loaded argv and target's last terminal event.
- [ ] Permit one natural scheduled wake for one verified owner through the existing owner path; do not post a synthetic test item.
- [ ] Verify separate process result, terminal runtime event, official provider receipt, exact content/account mapping and replay-zero.
- [ ] Repeat only after the prior owner has a terminal receipt; leave inconclusive/claimed rows fenced.

### Task 6: Decide release alignment after recovery

**Files:**
- Read: `~/loops/current/RELEASE.json`
- Read: loaded mobile plist `ProgramArguments` and `LIFE_MANAGER_RELEASE_SHA`
- Modify only through: `lm-loop apply` from a pushed immutable main-derived release, if evidence requires it

- [ ] Confirm the current release contains both canonical mobile trees and that the target's loaded argv is one exact immutable directory.
- [ ] If no runtime cutover is needed, record that decision and keep production unchanged.
- [ ] If a cutover is required, apply one label at a time, verify plist argv, loaded argv, release SHA, state path and rollback receipt, then wait for a natural terminal event.

### Task 7: Close out

- [ ] Run focused tests, `git diff --check`, source-boundary verification and the relevant `lm-loop` targeted status checks.
- [ ] Update the spec evidence with verified/inconclusive counts and the exact remaining fences.
- [ ] Commit and push the dedicated branch, merge after checks pass, and remove the exact worktree without force.
