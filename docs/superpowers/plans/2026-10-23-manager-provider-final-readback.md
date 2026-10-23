# Manager Provider Final Readback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix response/turn binding and cancellation state handling against the actual pinned SDK without enabling live inference.

**Architecture:** Reuse current exact-turn item pagination and provider journal/checkpoint. SSE signals completion; saved completed assistant items provide followup text. Keep public interfaces and owner lifecycle unchanged.

**Tech Stack:** Python stdlib, existing provider adapter/checkpoint/budget, SDK-shaped injected transport fixtures.

**Spec:** `docs/superpowers/specs/2026-10-23-manager-provider-final-readback-design.md`.

## Global Constraints

- Existing public signatures and P0/NOT_MEASURED/non-authority contracts remain unchanged.
- Followup final text comes only from complete saved assistant output_text items of the exact completed turn; join blocks with `''`, never use last SSE part as the whole answer.
- Completed assistant messages accept phase None or final_answer; commentary is excluded. Missing/non-completed status or unknown phase/content shape is uncertainty, not silence. Total output limit remains16000 characters and bounded pagination requires explicit bool has_more.
- Initial result.turn_id must exist and equal the independently saved completed turn ID before returning text. SDK Turn lacks output_text; metadata absence alone is not silent completion.
- Recheck latest completed exact turn after saved-item scan before writer release; uncertainty retains writer/event/usage exposure. Existing explicit silent-completion flag is required for genuinely complete empty text.
- Cancellation requestable Turn states are exactly queued/in_progress/waiting; unknown states including Session-only requires_action stay UNKNOWN. No new cancel args, provider CAS claims, ACK-as-completion or reservation refunds.
- Preserve checkpoint ACK-before-send, permanent fences/BaseException, no automatic UNKNOWN resend, cumulative exposure cap and deadline behavior. Do not edit schema, journal/checkpoint implementation, prompts, model, SDK transport construction or runtimeowner.
- No network/model/provider calls, SDK install, secrets, public actions, new dependencies/articles/outreach/registry changes. Workflow diff adds only one test module.

## Review Focus

- Multi-part or multiple-message output must not lose text or include commentary/foreign turns.
- Empty stream text must not hide actual saved text; failed/incomplete pagination must not be accepted as silence even with opt-in.
- A saved turn advancing during pagination must not release the previous application writer.
- Initial collected text must not be labeled with a different latest saved turn ID.
- Queued/waiting cancels must preserve exact-target readback and UNKNOWN/ACK distinction.

---

### Task 1: Canonical final text and Turn-state handling

**Files owned:**
- Modify `products/manager/manager_core/ampersand_api.py`
- Modify `products/manager/manager_core/provider_budget.py`
- Create `products/manager/tests/test_provider_final_readback.py`
- Modify fixture shapes only as needed in `products/manager/tests/test_provider_session_recovery.py`, `test_provider_budget.py`, `test_provider_deadlines.py`, `test_owned_provider.py`, `test_owned_provider_shadow.py`
- Modify `.github/workflows/manager-phase06-service.yml` only by adding `test_provider_final_readback` to focused unittest modules
- Append limits/provenance to `products/manager/deploy/owned-digital/README.md`

**Interfaces and primary-source evidence:**
- Keep `read_initial_turn`, `read_followup_turn`, `read_completed_turn`, `read_saved_assistant_items`, `cancel_and_reconcile` signatures.
- Official wheel source (private only) `/workspace/scratch/manager-provider-shadow-20261023/sdk-audit/wheel/openai/`; audit `/workspace/scratch/manager-provider-shadow-20261023/sdk-compatibility.md`. Do not vendor SDK code or import/install it. Existing clients/fakes stay injection-based.
- Pinned SDK collector `lib/beta/agents/_result.py` accepts completed message items whose phase is not commentary and joins output_text blocks with no separator. `AgentSessionMessage.phase` permits commentary/final_answer/None; its status is in_progress/completed/incomplete. Assistant output blocks are output_text. Unknown shapes fail closed in our bounded reader.
- SSE turn.completed identifies target `turn_id`. Use existing `_latest_completed_turn` and require its ID==target; call existing `read_saved_assistant_items(client, session_id, target)`, then recheck latest completed target before release/settlement. Remove reliance on SSE output_text.done content for final answer. Budget and journal logic otherwise remain intact.
- In initial, require actual result.turn_id and compare against the independent completed saved turn before returning result.output_text; no new saved-items requirement on initial's existing SDK result collector.
- In helper, enforce exact turn/role/type, completed status, permitted nullable phase, output_text strings, total16000 while appending, and existing pagination/duplicate guards. Commentary is excluded; malformed or incomplete selected final messages cannot yield SILENT_COMPLETED.
- In cancellation, replace incorrect pre-send Session-state set with canonical queued/in_progress/waiting only. Retain all terminal/mismatch/no-retry/fence code.

- [ ] **Step 1: Add behavior regressions FIRST and retain raw RED.** At least cover multipart/multiple saved messages with misleading SSE lastpart, commentary/foreign/user exclusion, no SSE text with saved text, complete empty items with and without explicit silence, incomplete/malformed pagination despite silence opt-in, incomplete/missing-status/unknown-phase final messages, nullablephase, >16000 total on an intermediate page, latestturn advances while scanning (writer held), initial collected vs latestID mismatch and missingresultturnID, queued/waiting cancel exact completion, unsupported requires_action Turn state, contradictory cancellation readback remains UNKNOWN. Use real SessionJournal/PrivateCheckpoint where fence persistence matters.
- [ ] **Step 2: Run `PYTHONPATH=products/manager:products/manager/tests python3 -m unittest test_provider_final_readback -v` before source edits.** Existing functions must fail the named behavior assertions; save actual failures, not only import errors.
- [ ] **Step 3: Implement minimal fixes in the two owned source modules using existing helpers.** Do not create new clients, endpoints, schema, recovery engine or transport retry. Preserve interruption/fencing and billing uncertainty.
- [ ] **Step 4: Update existing fake responses only to match actual required SDK result.turn_id, completed message status, turns.retrieve/items.list.** Do not remove existing assertions or loosen guards. If an additional fixture file outside the list fails, ask root before touching it.
- [ ] **Step 5: Add the one CI test module and append README evidence/limits.** Static SDK conformance is not provider/live inference acceptance.
- [ ] **Step 6: Run new focused regressions, existing provider/session/budget/deadline/shadow contracts, full suite once, source boundary checker and diffcheck.** Full command `PYTHONPATH=products/manager python3 -m unittest discover -s products/manager/tests -q`. Retain raw logs outside Git. Baseline main-derived source is381 tests.
- [ ] **Step 7: Self-review and commit only owned files.** Report commands, failures/passes, actual RED/GREEN raw paths and remaining concerns. Root owns plan/design, review, integration, registry and any live operations.
