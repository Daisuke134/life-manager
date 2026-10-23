# Manager checkpointed advisory provider implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the existing Ampersand session and budget stores to the owned cycle's private checkpoint, so a restored runner cannot silently recreate an uncertain session or erase reserved exposure.

**Architecture:** Reuse the four provider modules from research commit `7be0d77d3a84d9ef126a418a1c5c6db255250dbd`. An explicit advisory owner binds both stores to the exact acquired `PrivateCheckpoint.db`, saving every mutation after SQLite COMMIT/close and before returning to a possible HTTP send. The scheduled deterministic planner remains unchanged; this deliverable is a callable, tested connection, not evidence of scheduled production inference or human benefit.

**Tech Stack:** Python standard library, SQLite, existing private checkpoint/CAS gateway; optional existing OpenAI SDK adapter, no new runtime dependency.

**Spec:** [Manager specification §1.3 at pinned source](https://github.com/Daisuke134/life-manager/blob/7be0d77d3a84d9ef126a418a1c5c6db255250dbd/products/manager/docs/MANAGER_PRODUCT_SPEC.md#13-いま終える範囲と残作業の実行順). The design below resolves this bounded subproblem under the owner's instruction to decide and continue without another approval round.

## Global Constraints

- Manager is a Buddhist AI entity / Digital Buddha; no dedicated daily UI is introduced.
- Existing Actions owner, schedule, source/scope/browser/CAS checks, current-page cue, publisher, checkpoint endpoint/schema and runtime state remain unchanged.
- No networked inference, credential access, workflow dispatch, release, publication or external message is performed by implementation/tests.
- Both provider stores use exactly `checkpoint.db`; every effect reservation is remotely acknowledged before provider send.
- A checkpoint uncertainty permanently fences that checkpoint object, including interruption by `BaseException`; preserve the original non-Exception interrupt.
- UNKNOWN remains UNKNOWN. No automatic recreation/resend, no refund of UNKNOWN/cancelled reservations, no provider effect promoted from model text.
- Reservation cap is not a provider-enforced token/spend ceiling or settled cost. Existing usage estimates and null settlement retain that meaning.
- The callable entrypoint returns strict parsed P0 advice with `authorized_execution=False`, `causal_support=False`, and `human_outcome=NOT_MEASURED`.
- Do not claim automatic exact-turn recovery: existing journal retains session/event identities, not persisted turn IDs. Read-only session reconciliation and exact IDs supplied by an operator are distinct.
- Original 113-task registry, done counts and dependencies are untouched by this task.

## Design decisions and reuse

The existing owned publisher already uses durable pre-send intent followed by checkpoint ACK. Reuse that ordering rather than add another workflow engine or DB. Separate provider SQLite files are unsuitable for fresh Actions runners. Bundling arbitrary DB files into the remote snapshot would broaden the state contract unnecessarily; adding the existing provider tables to `cycle.sqlite` preserves one existing owner and Backup API.

Optional post-commit hooks preserve standalone research tests. They execute after connection close (never inside a SQLite write lock), before returning; hook failure propagates. The owned wrapper fixes these hooks to its checkpoint, derives a unique budget ID for each logical operation, and verifies its acquired session before use. Initial and followup namespaces must be disjoint; arbitrary caller-supplied `budget_run_id` is not exposed.

The current collaboration prompt says every scenario is fictional. Preserve that default for old research callers, add a keyword-only `fictional: bool = True`, and use `fictional=False` in the new public-fact wrapper. Reject synthetic facts in that route; no real-world outcome is inferred from the response.

Provider snapshot tables are optional for old snapshots, but if any are present require the complete group (`amp_sessions`, `amp_events`, `budget_policy`, `budget_reservations`). Validate schema/IDs/status, session-event/writer consistency, bounded integer reservations and cumulative cap, usage JSON/estimate/status consistency. Missing/invalid state is never replaced by empty tables on acquire. Validation must allow RESERVED budget rows without a session (a conservative crash before begin), and measured overexposure (which blocks new reservations rather than corrupts evidence).

## Review Focus

1. Lost ACK or process alarm during remote checkpoint: no later create/event/cancel/release may escape the fenced owner.
2. Crash after ACK or provider send: fresh runner sees the same UNKNOWN/event and reserved exposure; no automatic send is recreated.
3. Distinct requests sharing a caller budget identifier: derive operation-bound IDs so one reservation cannot finance multiple logical operations.
4. Cancel is an external write too: checkpoint the exact cancellation event first; terminal readback remains required and exposure stays reserved.
5. Old/partial/corrupt provider snapshots and public-source/model injection: restore old valid snapshots, reject partial state, retain strict P0 authority and public provenance boundaries.

## Task 1: Deliver the checkpoint-bound advisory owner

**Files:**
- Promote from pinned research source: `products/manager/manager_core/ampersand_api.py`, `provider_sessions.py`, `provider_budget.py`, `provider_deadline.py`.
- Modify: `products/manager/manager_core/owned_checkpoint.py`, `collaboration.py`.
- Create: `products/manager/manager_core/owned_provider.py`.
- Promote tests: `products/manager/tests/test_provider_session_recovery.py`, `test_provider_budget.py`, `test_provider_deadlines.py`. Reuse their original tests without weakening them.
- Create: `products/manager/tests/test_owned_provider.py` (real SQLite/Backup API, injected MemoryGateway and minimal provider boundary).
- Modify: `products/manager/deploy/owned-digital/README.md` for the callable connection and limits only.
- This plan is controller-owned; no other file or workflow may be edited.

**Interfaces:**
- `SessionJournal(path, *, after_commit=None)` and `BudgetLedger(path, *, cap_usd, after_commit=None)`; callable validation, same standalone behavior when omitted.
- `render_prompt(context: PlannerContext, *, fictional: bool = True) -> str`; old default retained, actual public mode has no fictional-scenario instruction.
- `ProviderAdvice(evidence: SessionEvidence, advice: AdvisoryResult)` frozen result.
- `CheckpointedProvider(checkpoint: PrivateCheckpoint, *, cap_usd: Decimal)`; exact acquired, unbroken checkpoint, both stores on its one private DB.
- `initial(client, context: PlannerContext, *, request_id: str, upper_usd: Decimal, deadline_monotonic: float) -> ProviderAdvice`.
- `followup(client, session_id: str, context: PlannerContext, *, key: str, upper_usd: Decimal, deadline_monotonic: float) -> ProviderAdvice`; derive stable writer and budget IDs from session+key.
- `reconcile(client, request_id: str, *, deadline_monotonic: float) -> Intent`; bounded read-only scan with existing pagination and durable bind, never creates a session/turn.
- Initial budget ID is `initial_` + SHA256(request_id UTF-8); followup ID is `followup_` + SHA256(session_id + NUL + key UTF-8). These bind namespace and operation, not a workflow run.
- Optional readonly provider-state validator may live in `owned_provider.py` and be called lazily by `_validate_database`; no table creation in validation.

- [ ] **Step 1: Write focused regressions before implementation.** Promote the existing source/tests unchanged as the reuse baseline, then demonstrate failing new assertions for missing hooks/wrapper and BaseException fencing. Store actual RED command/output outside Git.

New tests must assert these observable behaviors:

```python
# At fake sessions.create, decode the acknowledged remote SQLite snapshot.
assert remote_session_status == 'UNKNOWN'
assert remote_reserved_usd == Decimal('0.030000')
# Reserve cap .05, first operation .03: a DISTINCT .03 operation cannot send.
assert provider_create_count == 1
# After a lost ACK or interrupt (including remote write then lost response):
assert checkpoint.broken is True
assert provider_create_count == 0
```

Also cover followup and cancel event/writer ACK before HTTP; early BIND, usage and writer release survive save/restore; crash-before/after-send quarantines same creation/event; cap survives fresh runner; malformed output cannot mint execution; old snapshot compatibility, partial-table and invalid cap/usage/reference rejection. For UNKNOWN reconciliation, absent/ambiguous/incomplete provider pages remain fenced with no send. Include explicit rejection of synthetic facts in public mode and acceptance of a real typed public context.

- [ ] **Step 2: Run RED.** `PYTHONPATH=products/manager:products/manager/tests python3 -m unittest test_owned_provider -v`. Name missing behavior rather than accept unrelated import/fixture errors as evidence.
- [ ] **Step 3: Implement the interfaces above minimally.** Use existing API/deadline/session/budget functions; no new retry loop. Add exception fencing without swallowing original process interrupts. New initial/followup always use public-mode prompt and existing strict `safe_advisory` parsing.
- [ ] **Step 4: Run focused GREEN.** `PYTHONPATH=products/manager:products/manager/tests python3 -m unittest test_owned_provider test_owned_checkpoint test_owned_checkpoint_order test_provider_session_recovery test_provider_budget test_provider_deadlines -v`.
- [ ] **Step 5: Verify the main-derived Manager suite.** `PYTHONPATH=products/manager python3 -m unittest discover -s products/manager/tests -q`; `git diff --check`. Record totals and any warnings/failures; no claim of networked inference or human benefit.
- [ ] **Step 6: Update the deploy README.** Explain opt-in callable use, shared snapshot, UNKNOWN policy, reservation-vs-cost limits, and that scheduled planner stays deterministic.
- [ ] **Step 7: Commit only owned files, self-review and report.** No push/PR/merge/provider effects by worker. Controller handles fresh read-only review, normal checks/PR/merge, then any separately justified canary. Completion of this bounded component does not complete U002 or the Manager entity.
