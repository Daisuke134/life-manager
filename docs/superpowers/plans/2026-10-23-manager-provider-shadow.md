# Manager Catalog Provider Shadow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect existing validated public catalog context to checkpointed P0 advice and the existing deterministic baselines without enabling actions or scheduled inference.

**Architecture:** One explicit opt-in callable calls the existing catalog planner, rejects unsupported/unverified work, and uses the existing checkpointed provider only once per immutable operation. It returns an inert comparison record. There is no new runtime owner, database, workflow engine or evaluation engine.

**Tech Stack:** Python stdlib; current owned planner, PrivateCheckpoint and CheckpointedProvider; existing optional Ampersand client.

**Spec:** `docs/superpowers/specs/2026-10-23-manager-provider-shadow-design.md`; owner mission/priority is described in the research branch's `products/manager/docs/MANAGER_PRODUCT_SPEC.md` §§1.1–1.4/22.

## Global Constraints

- `enabled=False` is the default; disabled means zero planner/provider calls.
- Only exact legacy `TechnicalCriteria` actions `CORRECT_LINK` and `IMPROVE_ACCESSIBILITY` can reach the provider; no current-page cue inference.
- Reuse existing source/planner/browser validation and `prepare_owned_change`, public `render_prompt(..., fictional=False)`, existing baseline source and `CheckpointedProvider.initial`; no alternate transport, retry, journal or budget implementation.
- Existing provider intent in any state is never automatically resent. Operation IDs exclude run ID, observation clock and lease expiry; source and candidate byte changes define a new operation.
- Returned schema is `manager.catalog-shadow.v1`; all records have `proof_level=P0`, `authorized_execution=false`, `causal_support=false`, `human_outcome=NOT_MEASURED`, `action_writes=0`, settled cost null.
- Advice never becomes a publisher packet or execution callback. Preserve model UNKNOWN/invalid output separately from baseline decisions; never expose raw provider errors.
- Propagate CheckpointUnavailable/fenced owner and BaseException; never continue or release a broken checkpoint here.
- No secrets, live model calls, provider mutations, schedule/cadence/owner changes, registry changes, articles, outreach or approvals. Same acquired checkpoint lease is a caller precondition, not platform authentication.

## Review Focus

- A later run/time of the same immutable proposal must not create a second paid session.
- Planner/source/browser failure or stale/synthetic context must not reach the model.
- A checkpoint ACK failure must not be converted into a clean comparison or swallowed by generic failure handling.
- Invalid provider JSON and uncertain transport must stay visible with missing model comparison and unknown settled cost.
- Changing model output must not change any baseline/candidate bytes or original publisher intent.

---

### Task 1: Opt-in public catalog shadow caller

**Files:**
- Create `products/manager/manager_core/owned_provider_shadow.py`
- Promote unchanged `products/manager/manager_core/collaboration_baselines.py` from research commit `546a9d4446a91be94220c99112775309ef6d24b6`
- Create `products/manager/tests/test_owned_provider_shadow.py`
- Modify `products/manager/deploy/owned-digital/README.md` by appending usage/limits
- Modify `.github/workflows/manager-phase06-service.yml` ONLY to add `test_owned_provider_shadow` to the existing focused unittest list

**Interfaces:**
- Produces `run_catalog_shadow(checkpoint, client, checkout, workspace, source_commit, *, run_id: str, enabled: bool=False, cap_usd: Decimal, upper_usd: Decimal, deadline_monotonic: float) -> dict`.
- Consumes `plan_catalog_change(checkout, workspace, source_commit, now, *, run_id)` and its `(OwnedChangeContext, TechnicalAssessment, OwnedDigitalScope) | None`; compute actual current UTC before planning and after planning for freshness. No caller-controlled historical clock.
- Uses `prepare_owned_change(context, assessment, scope, now, schema='manager.digital-handoff.v2')` only for inert revalidation, never send its packet. Uses `render_prompt(context.planner, fictional=False)` for actual prompt hash.
- Uses exact already acquired `PrivateCheckpoint` via `CheckpointedProvider(checkpoint, cap_usd=...)`, then `.initial(client, planner_context, request_id=operation_id, upper_usd=..., deadline_monotonic=...)`.
- Existing `SessionJournal.get` is read-only and raises `SessionConflict` only for absent intent; treat all returned intent states as prior work requiring reconciliation, not retry.
- Uses `advisory_receipt`, `no_action_baseline`, `rule_baseline`. Model receipt is absent on unknown transport; invalid output keeps its `INVALID_MODEL_OUTPUT` status rather than counting a PASS as valid model agreement.
- Result statuses: `SKIPPED` for disabled/no candidate/unsupported/prior intent/expired deadline, `UNKNOWN` for planner/transport uncertainty, `COMPARED_P0` when a complete model response was parsed (including explicitly invalid output). Include a separate fixed reason and provider status. No fresh statistical superiority score.
- Record stable `operation_id`, actual `context_sha256`, baseline/candidate digest and source ID/URL/content hashes; baselines and model use the identical PlannerContext. Include provider session/turn/status and usage token nulls as observed; settled cost stays null.
- Canonical operation payload includes protocol, existing MODEL/DEFAULT_INSTRUCTIONS, immutable bundle digests, criteria version, candidate action/target and sorted source ID/URL/content hashes. Exclude candidate ID (contains workflow run ID), run ID, observation/retrieval clocks and scope ID/expiry. Prefix `catalog_shadow_` + lowercase SHA256.
- Validate exact boolean opt-in, active checkpoint and bounded absolute deadline before any provider call. Disabled is a cheap no-op. Planning can consume time; recheck deadline before constructing/calling provider. Do not add a whole-process signal/deadline around the existing browser planner.
- For provider failure distinguish `BudgetExceeded` (no provider send), `SessionFailure` (uncertain/failed; never retry), and checkpoint-broken/CheckpointUnavailable (propagate). Do not catch BaseException. Keep raw exception text out of returned records.

- [ ] **Step 1: Write regression tests before implementation.** Use real PrivateCheckpoint/SQLite with the existing MemoryGateway and real baseline/render/parser. Use existing catalog fixtures and mock only public network/browser/provider boundaries. Pin at least: disabled; no candidate; current-page cue; failed source audit; unverified/stale/synthetic context; eligible link and label comparisons; first-send checkpoint ACK order; repeated operation with different run/time; UNKNOWN and malformed JSON; budget exhaustion; elapsed deadline; checkpoint interruption/fence; packet/bundle invariance for PASS vs PROPOSE.
- [ ] **Step 2: Run `PYTHONPATH=products/manager:products/manager/tests python3 -m unittest test_owned_provider_shadow -v` and retain raw expected RED.** A missing interface/import can begin RED; behavior regressions must also prove the named boundary.
- [ ] **Step 3: Implement the minimal module and promote the existing baseline bytes unchanged.** Keep the function focused; use private helpers only where necessary. No edits to provider/session/budget/checkpoint/kernel/planner source.
- [ ] **Step 4: Add one test module to existing workflow verify, append operational README showing invocation inside an already acquired owner lifecycle and the exact source-only limits.** Do not add runtime flags, steps, secrets or dependencies.
- [ ] **Step 5: Run focused new tests plus existing provider/planner contracts, then full suite once:** `PYTHONPATH=products/manager python3 -m unittest discover -s products/manager/tests -q`. Run source boundary checker and `git diff --check`. Retain raw logs outside Git.
- [ ] **Step 6: Self-review then commit only the five owned files.** Report full RED/GREEN evidence and concerns in the private report. Controller owns design/plan/registry/integration and independent review.
