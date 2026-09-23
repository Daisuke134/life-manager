# Paid Fulfillment Across Platforms Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the reopened Ryu Coconala cycle manually, then make the Paid fulfillment path produce correct buyer-visible work and official readback for Coconala, CrowdWorks, Lancers, and Upwork.

**Architecture:** Ryu `18211957` stays behind a permanent manual fence. Every other provider uses one durable item state machine: newest buyer event → complete request map → correct artifact/work → provider send/formal delivery → official receipt/readback → replay-zero. Provider DOM/API details remain in adapters; admission, effect fences, leases, retries, and terminal receipts stay in the shared loop kernel.

**Tech Stack:** Life Manager Python runtime and immutable loop releases; Coconala/CrowdWorks/Lancers/Upwork provider adapters; authenticated `gog` CLI for Drive/Docs/Sheets; shared CloakBrowser CDP; SQLite/state ledgers; focused Python tests and official provider readback.

**Spec:** `docs/superpowers/specs/2026-09-22-paid-fulfillment-all-platforms-design.md`

## Global Constraints

- Ryu is manual-only; the Paid loop must never reply, attach, or formally deliver for talkroom `18211957`.
- Do not press Coconala formal delivery for Ryu; send one ordinary seller message and read back the exact official message ID.
- Do not replay an effect without an occurrence-bound official receipt or an exact no-dispatch proof.
- Use `gog` before browser Docs/Sheets access; browser is fallback only after a recorded CLI failure.
- Use the canonical lifecycle CLI for loop stop/start; never raw-kill, bypass admission/FIFO, or edit effect fences by hand.
- Production must run only an immutable release whose installed SHA and loaded argv are read back.
- A client is complete only after correct-work verification, provider-visible submission, official readback, and replay-zero.

## Review Focus

- A newer buyer event must reopen a previously buyer-waiting item without duplicating its prior effect.
- A provider effect whose receipt is unknown must remain fenced through restart and reconciliation.
- Per-client option/form state must merge without deleting unrelated options or prior receipts.
- Missing artifacts or facts must result in an honest wait, never a partial “complete” delivery.
- A natural wake must recover child processes and record a terminal receipt before the next wake.

### Task 1: Ryu manual current-cycle completion

**Files/evidence:**
- Read: official Coconala talkroom `18211957`
- Read: `projects/18211957/delivery/current-cycle-v699-deploy-readback.json`
- Create: `projects/18211957/delivery/ryu-v699-manual-send-readback.json`
- Modify: current spec/TODO only after official send readback

- [ ] Stop `hf-gig-paid-direct` through `./bin/lm-loop stop hf-gig-paid-direct`; verify `launchd_state=unloaded`, `pid=null`.
- [ ] Re-read the official room and bind the reply to buyer events `222222979` and `222223030`; refuse stale or duplicate work.
- [ ] Send one concise ordinary seller message describing the v699 fix and management/public URLs; keep formal delivery OFF.
- [ ] Read back the seller message ID, timestamp, and formal-delivery state; write an atomic receipt with event IDs and SHA-256.
- [ ] Update the current spec/TODO and commit/push the evidence-backed cursor.

**Measured outcome (2026-09-23T10:06Z):** all Task 1 bullets are complete. The
current manual seller receipt is `js-talkroomMessage-222245383`; the loop did
not send or formally deliver for Ryu.

### Task 2: Coconala loop production proof

**Files:**
- Modify: shared Paid/recovery/admission code only where the observed `remote_resume`, child-reap, or terminal-recording boundary requires it
- Test: the focused Paid/runtime tests named by the affected module
- Read: `./bin/lm-loop status hf-gig-paid-direct`, official four-room readback, occurrence ledger

- [ ] Write a failing regression for the observed boundary before changing production code.
- [ ] Implement the minimal child-reap/terminal persistence or occurrence-index fix; keep Ryu permanently fenced.
- [ ] Run the focused suite, full relevant suite, `git diff --check`, and `./bin/lm-loop-contract`.
- [ ] Cut/apply an immutable release, read back installed SHA/argv, allow one natural wake, and verify all four rooms officially.
- [ ] Run a second replay-zero/readback pass; record no duplicate provider effect and honest states for Chii and both NPO rooms.

**Measured outcome (2026-09-23T10:02Z):** installed release `35e66d24` natural
run `18d7eadd914a5020-49082` reached terminal `pass` with `effect=0`, but its
producer result remains `pending=1` for NPO `18223833` because host free space
was below the `524288 KiB` guard. The loop is paused until safe headroom is
recovered; the natural `pending=0` and replay-zero bullets remain open.

**Recheck (2026-09-23T10:10Z):** run `18d7eb621cefe660-54972` also ended
terminal `pass` with `effect=0`, but free space dropped from `1558452 KiB` at
admission to `506880 KiB` before project queue mutation. NPO `18223833` stayed
`pending` with no artifact/provider effect. The Paid loop is stopped again;
this wake does not satisfy the gate. The next safe action is one start only
after headroom remains stable for the whole wake, then official readback and
replay-zero.

**Follow-up read-only check:** `lm-loop doctor` is clean, Ryu remains at
`js-talkroomMessage-222245383` with no newer buyer event, and the Coconala Paid
owner is still `unloaded` on the same SHA. Free space is `444128 KiB` (below
the `524288 KiB` guard); the canonical cleanup receipt reports no safe reclaim.
The next action remains one guarded natural wake only after durable headroom,
not a duplicate send or a manual bypass.
A short read-only capacity poll then fell to `177660 KiB`; the poll was stopped
without starting Paid. Keep the Coconala gate open until free space is stable
above the guard for the complete wake.

**Continuation (2026-09-23T10:37Z):** after removing only five verified stale
paid-fulfillment temporary worktrees, the installed SHA was started once.
Natural run `18d7ec494aa203a8-68253` failed closed at
`resource_database_busy`; the next wake `18d7eca1acb6b798-72766` failed closed
at `resource_fifo_wait`. Both are effect-zero and occurrence-safe. Paid is now
canonically unloaded again (`pid=null`), with producer `pending=1` for NPO
`18223833`; the next step remains stable headroom above the 512 MiB guard,
one natural wake, four-room official readback, and replay-zero. No provider
send was made in this continuation.

### Task 3: CrowdWorks completion and Paid canary

**Files:**
- Modify: CrowdWorks adapter/kernel files identified by the failing focused test
- Test: affected CrowdWorks focused suite plus loop contract gate
- Read: provider contracts, milestone receipts, `gog drive get/download` evidence, occurrence ledger

- [ ] Reconcile `crowdworks-revenue-paid` unknown occurrence `18d62cf32eb0c678-48194`; keep it fenced unless an exact provider receipt/no-dispatch proof exists.
- [ ] Obtain acceptance/settlement/payout readback for `63712784`, `63659463`, `63657015`, and `63570481` without replaying delivery.
- [ ] Wait for the five LINE/Note materials or an accessible LINE session for `63568785`; then complete the five forms, verify, formally deliver once, and read back acceptance/settlement/payout.
- [ ] Prove one natural installed-release canary and replay-zero.

### Task 4: Lancers Paid path

**Files:**
- Modify: Lancers Paid adapter and registry only after official funded-contract DOM/API capture
- Test: new red test for `lancers_paid_effect_not_implemented`, then focused adapter/runtime suite

- [ ] Reconcile unknown occurrence `18d67a28e56c4b58-6829`; do not clear it by owner-wide guess.
- [ ] Confirm a live funded contract; derive the smallest official mutation/readback path from the authenticated page/API.
- [ ] Implement form/message/formal-delivery receipts with idempotency and replay-zero; prove one canary and payout readback.

### Task 5: Upwork lifecycle and canary

**Files:**
- Modify: `config/loop-registry.json` and existing Upwork adapter registration only after live inventory
- Test: lifecycle/adapter focused tests and loop contract gate

- [ ] Obtain fresh authenticated Upwork inventory; do not treat the stale 2026-08-26 snapshot as live proof.
- [ ] Register one Paid owner, prove one funded contract from context through buyer-visible delivery and official payment readback, then replay-zero.

### Task 6: Fleet acceptance and self-healing

**Files:**
- Modify: shared kernel only for regression failures found in Tasks 2–5
- Test: no-starvation, crash recovery, browser lease, cadence, revision, settlement, duplicate-zero suites
- Read: all provider official receipts and installed release manifests

- [ ] Verify each provider uses the same request-map/quality/effect-fence vocabulary while retaining provider-specific adapters.
- [ ] Run the fleet gate with unrelated owners active; verify no starvation, child cleanup, lease isolation, and durable terminal receipts.
- [ ] Update the spec/TODO with measured receipts, push the final branch, and only then promote the proven release.
