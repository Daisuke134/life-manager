# DD02 Runtime Trace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make `lm-loop status --explain` bind failure causes and run provenance to the exact fenced occurrence while showing registered cadence and honest gaps.

**Architecture:** Extend the existing read-only projection in `runtime/loop/lm_loop.py`. Select cause events by exact `occurrence_id`, then project their identity, release, runtime hashes, terminal, and effect receipts. Show cadence from the registry as registered cadence and label loaded cadence `not_reported` because this status path does not observe launchd's loaded job definition.

**Tech Stack:** Python 3, `unittest`, existing `lm-loop` runtime and JSONL event journal.

**Spec:** `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` (DD02).

## Global Constraints

- Do not resend, resolve, or clear any publication effect or admission fence.
- Do not mutate launchd, loop state, provider profiles, or external services.
- Match cause events by exact occurrence identity; never infer a match from the run-ID suffix.
- Never label registry cadence as the loaded launchd cadence.
- Expose hashes and safe identifiers only; do not expose raw argv or environment values.

## Review Focus

- A different event reuses the fenced run ID but has a different occurrence; it must not be selected (`test_status_reports_cause_event_by_exact_occurrence_not_run_id`).
- The exact occurrence has a different run ID than its suffix; the event's own run ID must be reported (`test_status_reports_cause_event_by_exact_occurrence_not_run_id`).
- Multiple journal rows share the exact occurrence; the latest valid timestamp wins (`test_status_reports_latest_exact_occurrence_event`).
- No journal row has the occurrence; cause stays absent and next action still requires official readback (`test_status_reports_no_journal_row_when_run_never_logged`).
- Registry schedule exists but loaded cadence is not observed; output separates registered values from `not_reported` (`test_status_explain_projects_run_identity_and_schedule_gap`).

---

### Task 1: Exact occurrence trace and explain projection

**Files:**
- Modify: `runtime/loop/lm_loop.py`
- Test: `runtime/loop/tests/test_lm_loop_readonly.py`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

**Interfaces:**
- Consumes: existing `status_rows(registry, ...)`, `_owner_runtime_rows(entry)`, and validated runtime-event dictionaries.
- Produces: exact occurrence cause selection; `run_identity`, `schedule`, and expanded `cause_event` output in `status --explain`.

- [ ] **Step 1: Write the failing tests.** Add tests for exact occurrence binding despite a run-ID mismatch, latest timestamp selection among duplicate exact occurrences, and explain output carrying run hashes/release plus registered cadence and `loaded_cadence_status="not_reported"`. Keep the existing no-journal-row behavior and assert its `run_id` is null.

- [ ] **Step 2: Run the focused tests and confirm RED.** Run: `python3 -m unittest runtime.loop.tests.test_lm_loop_readonly.AdmissionEffectUnknownDetailsTest.test_status_reports_cause_event_by_exact_occurrence_not_run_id runtime.loop.tests.test_lm_loop_readonly.AdmissionEffectUnknownDetailsTest.test_status_reports_latest_exact_occurrence_event runtime.loop.tests.test_lm_loop_readonly.AdmissionEffectUnknownDetailsTest.test_status_reports_no_journal_row_when_run_never_logged runtime.loop.tests.test_lm_loop_readonly.LmLoopReadonlyTest.test_status_explain_projects_run_identity_and_schedule_gap`. Expected: failures because cause selection uses `run_id` and the explain projection omits provenance and cadence.

- [ ] **Step 3: Implement the minimal projection change.** Replace run-ID selection with latest exact-`occurrence_id` selection. Derive the detail `run_id` from the matched event, or leave it null when no exact event exists. Project event/owner/job/run/wake/occurrence/release/provider/hash identifiers. Add `registered_cadence` from the registry and expose it with `next_eligible_run`; set loaded cadence status to `not_reported`.

- [ ] **Step 4: Run focused tests and confirm GREEN.** Run the same focused unittest command. Expected: all focused tests pass.

- [ ] **Step 5: Run acceptance checks.** Run `python3 -m unittest discover -s runtime/loop/tests -p 'test_*.py'`, `node --test apps/life-manager/lib/loop-adapter-registry.test.js`, `bash scripts/verify-source-boundary.sh`, and `git diff --check`. Do not run live provider reconciliation or mutation commands.

- [ ] **Step 6: Update the task record and integrate.** Update the DD02 row in the canonical SSOT with exact test, review, CI, and merge evidence; commit and push the dedicated branch, open a PR, finish exact-head checks and a fresh read-only review, then merge. Leave DD03 as the next cursor. Production apply is outside this source-only task.
