# Coconala Paid Manual Exception and Live Fulfillment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task by task.

**Goal:** Keep Ryu permanently manual while restoring `hf-gig-paid-direct` so every other eligible Coconala paid room receives correct work, one buyer-visible send, official readback, and replay-zero.

**Architecture:** Add a durable room-local manual-owner record that is independent of prior send receipts and has no time-based expiry. Enforce it during parent admission and again at every child/effect boundary. Reuse the existing paid decision, work, verifier, provider-effect, and official-readback pipeline for non-manual rooms; do not create a second fulfillment implementation.

**Tech Stack:** Python 3, pytest, Coconala CDP collector/effect adapters, Life Manager loop registry/release tooling, JSON owner records.

**Spec:** `docs/superpowers/specs/2026-09-22-paid-fulfillment-all-platforms-design.md`

## Global Constraints

- Coconala talkroom `18211957` (`Ryu0820119`) is permanently manual until Dais explicitly releases it. A buyer reply, process restart, successful readback, or elapsed time cannot release it.
- There is no Risa client or work item; every earlier `Risa` reference means Ryu.
- Never use the formal-delivery checkbox for Ryu. This plan performs no additional Ryu send unless a new buyer request arrives.
- Keep `hf-gig-paid-direct` stopped until its exact `admission_effect_unknown` occurrence is reconciled from official provider readback.
- Do not clear an effect fence by inference, timestamp alone, or owner-wide reset.
- Non-Ryu work must pass the existing complete-context, current-buyer-event, artifact/remote-result, verifier, presend, official-readback, and replay protections. Do not replace semantic verification with keywords.
- Runtime changes use `lm-loop`/`launchctl-safe` only after the required GUI-owner preflight; never invoke raw `launchctl`.
- Production proceeds one non-Ryu room at a time. A room failure remains isolated and cannot block another eligible room.
- Keep credentials, buyer materials, screenshots, and live evidence outside Git.

## Current State Update (2026-09-23)

- Chii is not self-actionable: the latest authenticated buyer request was already answered with the reply/reaction count and sending method. Until a newer buyer message appears, the correct state is `awaiting_buyer`; no additional DM or delivery is permitted.
- Ryu remains a permanent manual-only exception. The paid loop must report `reserved_for_owner` with zero effect and never press formal delivery for that room.
- The paid state-machine fix is implemented and reviewed: seller-answer detection is gated to the `revision` stage, and report-only observations persist through `queue_observed` without creating an admission/actionable cycle. PR #5787 (`84dd3c124d...`) merged successfully as `37e1d582f15fd642669eb699c09c467903bc08bb`.
- Next cursor is operational proof: resolve the bounded host storage/write-capacity issue, then verify a natural terminal event and replay-zero for Chii before processing any genuinely actionable Coconala room. CloudWorks, Lancers, and Upwork remain later platform-proof work.

### Deployment readback

- PR #5787 is merged as `37e1d582f15fd642669eb699c09c467903bc08bb`; immutable release `/Users/anicca/loops/releases/20260923T073120-37e1d582` is installed for `hf-gig-paid-direct` only.
- The stale admission occurrence was reconciled against the official Chii snapshot and is now `released` with `effect_unknown=0`.
- The first natural kickstart produced no external effect, but could not write its terminal evidence because the host paid-loop writer hit `No space left on device`; the target loop was stopped safely. A live terminal/replay-zero canary is still required after bounded storage remediation.
- Ryu manual completion is already verified: v696's production correction and authenticated audit passed, then the final answer was sent through talkroom `18211957` with `formal_delivery_checkbox=false`. The official evidence is `/Users/anicca/gig/projects/18211957/evidence/manual-v696-send/paid-queue-evidence.json`; no formal-delivery button was pressed and the durable owner fence remains permanent.

## Review Focus

1. A new Ryu buyer reply still cannot enter decision, preparation, reply, attachment, cancellation, remote mutation, or formal-delivery paths.
2. A forged, malformed, mismatched-room, symlinked, or silently edited manual-owner record fails closed without granting automation authority.
3. Excluding Ryu does not exclude or stall another eligible paid room in the same wake.
4. A buyer event that changes after work preparation is rejected before any provider mutation.
5. A prior uncertain effect is reconciled by exact room/event official readback and cannot be resent.

## Task 1: Specify the durable manual-owner record with failing tests

**Files:**
- Modify: `skills/earn/gig/tests/test_paid_remote_wait.py`
- Reference: `skills/earn/gig/scripts/paid_direct.py` (`_paid_project_root`, `_paid_project_is_delegated`, `_account_owner_observe_only`, `_paid_active_items`)

- [ ] **Step 1: Add a fixture helper that writes `context/paid-owner.json`**

  The valid record is exact and minimal:

  ```json
  {
    "version": 1,
    "provider": "coconala",
    "contract_id": "18211957",
    "mode": "manual",
    "owner_id": "dais",
    "authority": "account_owner_instruction",
    "reason": "permanent_manual_exception",
    "release_required": true
  }
  ```

- [ ] **Step 2: Add a regression proving a valid record reserves Ryu even when `buyer_reply_after_artifact_observed` is true**

  Assert the durable owner predicate returns the record path, `_paid_active_items` omits Ryu, and the parent result reports `reserved_for_owner` with zero effect.

- [ ] **Step 3: Add table-driven rejection tests**

  Cover wrong provider, contract mismatch, wrong authority, non-manual mode, missing `release_required: true`, symlinked file, and an extra/unknown field. Assert every invalid record does not suppress a normal paid item.

- [ ] **Step 4: Add a multi-room test**

  Provide Ryu plus one eligible room and assert only Ryu is reserved while the other room reaches admission.

- [ ] **Step 5: Run the new tests and confirm RED**

  Run:

  ```bash
  pytest -q skills/earn/gig/tests/test_paid_remote_wait.py -k 'manual_owner or permanent_manual or manual_exception'
  ```

  Expected: failure because no durable manual-owner predicate exists.

## Task 2: Implement the smallest fail-closed owner fence

**Files:**
- Modify: `skills/earn/gig/scripts/paid_direct.py`
- Test: `skills/earn/gig/tests/test_paid_remote_wait.py`

- [ ] **Step 1: Add the exact owner-record schema and `_manual_owner_record(args, item)`**

  Resolve the project with `_paid_project_root`; require a regular non-symlink `context/paid-owner.json`; require the exact key set and values from Task 1; require `contract_id == talkroom_id`. Return the resolved record path only for a valid manual record. Treat read/parse/schema failure as no valid exclusion so malformed policy cannot silently seize an ordinary room.

- [ ] **Step 2: Separate permanent ownership from historical effect dedupe**

  Keep `_account_owner_observe_only` unchanged for receipt-backed prior-send dedupe. Add `_paid_project_is_manual` and make `_paid_active_items` omit both fresh runtime delegations and durable manual items.

- [ ] **Step 3: Report manual items explicitly in `run_once`**

  Before targeted readback scheduling, add one `reserved_for_owner` row per valid manual item with `send_performed=false`, `formal_delivery_checkbox=false`, and the owner-record path as evidence. Do not count it as actionable, failed, or pending.

- [ ] **Step 4: Recheck the owner fence at every child boundary**

  Add the same early return to `_decision_only`, `_prepare_one`, and `_write_one`. In `_write_one`, evaluate it after resolving the prepared room and immediately before `_write_file_effect`, `_run_coconala_cancellation`, or the remote/formal branch can mutate the provider.

- [ ] **Step 5: Run focused tests**

  Run:

  ```bash
  pytest -q skills/earn/gig/tests/test_paid_remote_wait.py -k 'manual_owner or permanent_manual or manual_exception or delegated or observe_only'
  ```

- [ ] **Step 6: Commit the source regression and implementation**

  ```bash
  git add skills/earn/gig/scripts/paid_direct.py skills/earn/gig/tests/test_paid_remote_wait.py
  git commit -m "fix(gig): fence permanent manual paid rooms"
  git push
  ```

## Task 3: Install and verify the Ryu owner record outside Git

**Files:**
- Create outside Git: `$HOME/gig/projects/18211957/context/paid-owner.json`
- Create outside Git: `$HOME/gig/projects/18211957/evidence/manual-owner-install.json`

- [ ] **Step 1: Confirm live identity before writing**

  Use the targeted Coconala collector for talkroom `18211957`; require buyer `Ryu0820119`, transaction state `取引中`, and the exact project root. Record the current buyer-event identity and collector evidence path.

- [ ] **Step 2: Write the record atomically with mode `600`**

  Use the exact Task 1 schema. Record its SHA-256 and project/talkroom binding in `manual-owner-install.json`; do not copy buyer messages into the record.

- [ ] **Step 3: Exercise read-only child and parent paths**

  Run the decision-only path against the current queue item and a parent dry/natural observation with the operator brake held. Require `reserved_for_owner`, `effect=0`, and no new seller message or formal-delivery observation.

- [ ] **Step 4: Simulate a newer buyer event in the focused fixture**

  Re-run the permanent-manual regression with a changed buyer hash and require the same exclusion. This proves the rule is ownership-based, not receipt-based.

## Task 4: Preserve the current buyer-event and uncertain-effect safety gates

**Files:**
- Modify only if a regression fails: `skills/earn/gig/scripts/paid_direct.py`
- Modify: `skills/earn/gig/tests/test_paid_remote_wait.py`

- [ ] **Step 1: Add or identify the existing stale-event regression**

  The test prepares work for buyer event A, changes targeted official readback to buyer event B, invokes `_write_one`, and asserts zero browser/effect calls plus a stale-input failure.

- [ ] **Step 2: Add or identify the existing effect-unknown regression**

  The test starts with an exact room/event effect fence, proves no send occurs before official reconciliation, then proves a matching official seller receipt deduplicates instead of resending.

- [ ] **Step 3: Run both regressions**

  ```bash
  pytest -q skills/earn/gig/tests/test_paid_remote_wait.py -k 'stale and (presend or buyer or feedback) or effect_unknown or reconcile'
  ```

- [ ] **Step 4: Make only the minimal implementation change needed for GREEN**

  Reuse existing targeted readback, snapshot, effect-key, and reconciliation code. Do not introduce a parallel receipt format.

## Task 5: Run the Coconala source acceptance gate

**Files:**
- Verify: `skills/earn/gig/scripts/paid_direct.py`
- Verify: `skills/earn/gig/scripts/paid_admission.py`
- Verify: `skills/earn/gig/scripts/paid_thread_state.py`
- Verify: `skills/earn/gig/tests/test_paid_remote_wait.py`
- Verify: `config/loop-registry.json`

- [ ] **Step 1: Run the complete paid-loop focused suite**

  ```bash
  pytest -q skills/earn/gig/tests/test_paid_remote_wait.py skills/earn/gig/tests/test_coconala_cancel_browser.py
  ```

- [ ] **Step 2: Run release and cadence contract tests**

  ```bash
  pytest -q skills/earn/gig/tests/test_gig_release.py skills/earn/gig/tests/test_gig_disk_guard.py skills/earn/gig/tests/test_apply_cadence_is_polite.py
  ```

- [ ] **Step 3: Run repository loop contracts**

  ```bash
  ./bin/lm-loop-contract
  ./bin/lm-loop doctor
  git diff --check
  ```

- [ ] **Step 4: Review the diff against all five Review Focus cases**

  Confirm each case has a named automated test and that no client material, credentials, runtime evidence, or mutable state entered Git.

- [ ] **Step 5: Commit any remaining test-only changes and push**

  ```bash
  git add skills/earn/gig/tests/test_paid_remote_wait.py
  git commit -m "test(gig): prove paid room ownership boundaries"
  git push
  ```

## Task 6: Reconcile the stopped production occurrence exactly

**Files:**
- Read outside Git: the current `hf-gig-paid-direct` state/occurrence record
- Write outside Git: exact occurrence reconciliation evidence

- [ ] **Step 1: Verify runtime-owner preconditions without mutation**

  Check `id`, Directory Services user identity, Aqua console manager, manager UID/PID, `lm-loop status hf-gig-paid-direct`, and the immutable release SHA currently referenced by the job. If any GUI premise fails, do not issue a GUI-domain mutation.

- [ ] **Step 2: Resolve the exact `admission_effect_unknown` occurrence**

  Read its `run_id`, `occurrence_id`, room ID, buyer-event identity, command/effect phase, and evidence references. Query only that talkroom's official Coconala history. Classify it as observed send, verified no-send, or still unknown.

- [ ] **Step 3: Close only a proven occurrence**

  If official readback proves a send, write the matching receipt/dedupe transition. If it proves no send, write the verified no-effect reconciliation. If official evidence remains ambiguous, keep the fence and collect a stronger provider readback; do not retry or clear it.

- [ ] **Step 4: Verify Ryu remains separately reserved**

  Re-read `paid-owner.json` and run the read-only owner predicate from the release candidate. The occurrence reconciliation cannot modify or release the Ryu record.

## Task 7: Merge and promote one immutable Coconala release

**Files:**
- Merge: the dedicated outcome branch
- Deploy: immutable release from merged `main`

- [ ] **Step 1: Obtain a fresh read-only review**

  Review the final diff and Task 5 evidence specifically for the five Review Focus cases. Resolve every correctness or safety finding and repeat affected tests.

- [ ] **Step 2: Create one PR after all source acceptance checks pass**

  Push the final branch, create the PR, wait for required checks, and merge with `--admin`; if the server rejects it, record the exact server blocker rather than substituting an unmerged deployment.

- [ ] **Step 3: Build/promote the immutable release from merged `main`**

  Use the repository release procedure. Verify the release SHA equals merged `main`, `current` resolves to that immutable release, and the Ryu owner record remains in the mutable project state outside the release tree.

- [ ] **Step 4: Apply only `hf-gig-paid-direct`**

  After the runtime-owner preflight passes, use the repository's safe loop apply path for this one product. Verify loaded configuration, argv/env, release SHA, operator-brake state, and one registered owner.

## Task 8: Prove one non-Ryu natural canary end to end

**Files:**
- Modify: `skills/browser/scripts/tiktok_message_transport.py`
- Modify: `skills/browser/scripts/test_tiktok_message_transport.py`
- Read/write outside Git: selected non-Ryu project state and evidence

- [ ] **Step 0: Close the recipient-idempotency production incident before re-entry**

  Add a RED regression where a prior `sent`, `attempting`, or `unknown` row uses a
  different effect key for the same canonical TikTok handle. Under the existing
  project transport lock, reject it before `new_target`, insertion, or keypress. Keep
  verified `not_sent` retryable. Run the focused transport suite, the Paid/Coconala
  source gate, fresh review, PR/merge, immutable release, and targeted apply before a
  new canary. The Chii production duplicate is uncounted and cannot be replayed.

- [x] **Step 1: Refresh all current paid rooms and select the earliest safe non-Ryu item**

  Re-read Chii and both NPO rooms instead of assuming the planning inventory is unchanged. Exclude Ryu by owner record. The 2026-09-22/23 official orders snapshot contains exactly four open Coconala rooms: Ryu `18211957` (permanent manual owner), Chii `18180857` (`awaiting_buyer`), and NPO rooms `18223833` and `18250352` (both buyer-dependent). The natural canary selected `18223833` by paid admission ordering and had no unresolved effect fence.

- [x] **Step 2: Let one natural wake perform the real job**

  The natural wake completed conversation/attachment ingestion and the semantic decision for `18223833`. It correctly found four missing buyer facts and stopped at `await_buyer` instead of fabricating an artifact or sending an unnecessary DM. An actionable-room send path is intentionally still unproven and remains a separate TODO.

- [x] **Step 3: Verify the provider effect**

  The natural run produced `effect=0`, `readback=1`, `send_performed=false`, and `deduplicated=true` for `18223833`; official selected-talkroom readback at `2026-09-22T23:24:03Z` showed no new seller message, no compose draft, and no formal-delivery effect. This proves the no-effect/await-buyer branch, not an actionable send.

- [x] **Step 4: Prove replay-zero**

  The following natural wake completed at `2026-09-22T23:25:32Z` on release `4c6b1dc8a52952e31f13bcb26a5266e570169e1d`. It left `18223833` at `awaiting_buyer` with `effect=0`/`readback=1`; the official readback retained the same seller-message count/hash and empty draft. The same inventory still reports Chii awaiting buyer and Ryu reserved for owner with zero effect. No duplicate reply, attachment, or formal-delivery effect occurred.

## Task 9: Drain every remaining eligible Coconala paid room one by one

**Files:**
- Read/write outside Git: each non-Ryu project state and evidence

- [ ] **Step 1: Admit the next room only after the prior room has official readback and replay-zero**

  For each current and newly observed non-Ryu paid room, repeat Task 8. A blocked room remains explicit while the next independent eligible room may proceed.

- [ ] **Step 2: Repair quality failures before sending**

  If the verifier finds a missing requirement, stale buyer event, broken rendering, inaccessible link, wrong attachment, or placeholder, return to work for that same room. Do not send an apology or call an incomplete artifact delivered.

- [ ] **Step 3: Verify the terminal Coconala inventory**

  Fresh provider inventory must show every non-Ryu paid room as awaiting buyer, accepted, settled, or explicitly blocked with a concrete next action and no uncertain effect. Ryu remains manual and no Risa item exists.

- [ ] **Step 4: Record the provider milestone and next cursor**

  Update the cross-provider spec/TODO with Coconala receipts, release SHA, canary room, replay-zero evidence, remaining external blockers, and set the next cursor to the separate CrowdWorks plan. Do not claim the cross-platform goal complete at this milestone.

### Live cursor update — 2026-09-23

The replay-zero natural wake completed at `2026-09-22T23:25:32Z` on release `4c6b1dc8a52952e31f13bcb26a5266e570169e1d`. The official orders snapshot at `/Users/anicca/gig/evidence/paid-direct-live/orders/orders-only-snapshot.json` had four open cards; `/Users/anicca/gig/evidence/paid-direct-live/latest.json` classified Chii and both NPO rooms as `awaiting_buyer`, while Ryu remained `reserved_for_owner`. The run recorded no new send effect, no draft, and no formal-delivery click. Chii's seller history remains ten messages with the final report already answered; the historical campaign response count is three (two message-request approvals and one `配信中なので該当しません`).

An earlier natural wake (`18d7c7dcb40b2f90-7799`) was deferred before provider work by `host_admission_deferred:resource_capacity_busy`; its terminal evidence records `effect=0`, `readback=0`, and `admission_effect_unknown=false`. This was not replay-zero evidence because the room was not processed; the later natural wake above closed that cursor. Do not kickstart repeatedly or send manually.

The Chii state-machine fix is merged and deployed in immutable release `4c6b1dc8a52952e31f13bcb26a5266e570169e1d`. The target-only apply succeeded after the paid owner's FIFO reservation naturally expired, and loaded argv/env read back to the same SHA. The first natural run on that release (`18d7c73738bf4b78-1330`) reached the host admission/evidence boundary but terminated as `host_admission_deferred:resource_fifo_wait` after transient `No space left on device`; its evidence records `effect=0`, `readback=0`, and `admission_effect_unknown=false`. This is not a buyer failure or a Chii send. The live terminal proof and replay-zero remain open. The next cursor is storage/capacity recovery followed by one terminal natural Coconala run; no additional Chii message is allowed. Ryu remains a permanent manual-only exception.

The next natural run (`18d7c7825f5ec9e8-4234`) completed on the same SHA. It selected `18223833`, tolerated the missing first-cycle `context/paid-review-state.json`, reached semantic decision, and correctly produced `await_buyer` / `awaiting_buyer` with `effect=0`, `readback=1`. Its one shared admission occurrence was fenced as unknown; a fresh selected-talkroom official Coconala readback at `2026-09-22T23:16:31.972379+00:00` showed the existing ten seller messages, latest seller hash unchanged, no new seller message or draft, transaction still `取引中`, and formal delivery unconfirmed. The exact occurrence `hf-gig-paid-direct:18d749278b4dabe8-68475` was then released with `resolve_unknown_occurrence`; proof is `/Users/anicca/gig/evidence/paid-direct-live/reconciliation/hf-gig-paid-direct-18d749278b4dabe8-68475/reconciliation.json`, with `effect_unknown=false` afterward. The next natural wake is reserved for replay-zero; no Chii or Ryu message is permitted.
