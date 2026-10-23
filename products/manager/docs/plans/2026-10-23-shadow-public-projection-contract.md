# Shadow Public Projection Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject inconsistent public P0 comparison records without changing valid reports or exposing private fields.
**Architecture:** Extend the existing projection's parsed-field checks; status/reason has one mapping and completed evidence is cross-checked locally. Never call the private validator from the public projection.
**Tech Stack:** Existing Python stdlib/unittest; no dependency or framework.
**Spec:** `2026-10-23-shadow-public-projection-contract-design.md` in this directory; PR8710 automated review4359623048, independently reproduced on main6b5390133.

## Global Constraints

- Keep the existing fixed19-key public projection and static ValueError text `invalid catalog shadow record`.
- Keep P0, authorized_execution=False, causal_support=False, human_outcome=NOT_MEASURED, action_writes=0, settled_cost_usd=None.
- Private reasons/provider IDs/unknown fields stay ignored and absent from public output. This validates consistency, not authentic remote completion.
- No storage/provider/parser/schema/host/CLI/workflow/runtime changes, model calls, new dependencies, guard relaxation, or registry changes.

## Review Focus

1. A completed claim with a skipped/unknown reason must reject before output (Task1 status/reason regression).
2. Missing completed time/hash/baseline/model evidence must not normalize into a claimed completed record (Task1 required-evidence regression).
3. Comparison booleans must agree with decisions; invalid output has no model evidence (Task1 required-evidence regression).
4. Non-completed records may carry prepared baseline/hash fields but not completed model evidence (Task1 noncompared regression).
5. The saved-result validator calls this projection; avoid recursion/private-ID requirements and retain valid restore/privacy behavior (focused persistence suite and existing privacy test).

---

### Task 1: Cross-field public comparison validation

**Files:** Modify `products/manager/manager_core/owned_provider_shadow.py`; Test `products/manager/tests/test_owned_provider_shadow.py`. Only these two tracked paths belong to implementer.
**Interfaces:** Consume existing `_record`, `public_catalog_shadow_summary`, `_validated_result`, and offline `run_shadow` fixture. Preserve public function signature/output19keys. Produce one private status/reason mapping (all-reasons set, if retained, is derived), plus consistency checks on already parsed public values. Do not call `_validated_result` from projection.

- [ ] **Step 1: Write meaningful failing tests.** Add `test_public_projection_rejects_inconsistent_status_reason`, `test_public_projection_requires_completed_comparison_evidence`, `test_public_projection_rejects_model_evidence_on_noncompared_results` using valid existing comparison fixture and isolated dictionary mutations.
  - Mismatches include COMPARED_P0/DISABLED; COMPARED_P0/PROVIDER_TRANSPORT_UNKNOWN; UNKNOWN/MODEL_RESPONSE_PARSED; SKIPPED/PRIOR_INTENT_RECONCILIATION_REQUIRED. Assert the exact static ValueError.
  - Completed record requires non-None UTC compared_at, operation_id/context_sha256/baseline_digest/candidate_digest, no_action/rules baseline decisions, and model_status. Remove each independently. MODEL_ADVICE_P0 requires model decision and both exact comparison booleans; assert rejection of missing and inverted comparisons. INVALID_MODEL_OUTPUT accepts absent/None model_advice/model_comparison only.
  - Valid SKIPPED/DISABLED and UNKNOWN/PROVIDER_TRANSPORT_UNKNOWN records still project. Attach completed time, model_status, model_advice, or comparison evidence independently to otherwise valid non-compared records and require rejection. Prepared baseline/hash fields without model evidence remain accepted.
  - Existing privacy test modifies private reason/provider ID and unknown markers; it must continue to pass with fixed output keys and no markers.
- [ ] **Step 2: Actual RED.** Run only the three named tests against unchanged production source and save actual nonzero log/exit.
- [ ] **Step 3: Minimal implementation.** Follow design's exact mapping and invariants. Preserve absent/None compatibility, enum/type/date/hash checks, current returned field names, and all P0 flags.
- [ ] **Step 4: GREEN.** Run new tests plus `env PYTHONPATH=.:tests python -m unittest test_owned_provider_shadow test_owned_catalog_shadow_results test_owned_checkpoint -v`; full `python -B -m unittest discover -s tests -v` once after source change; Manager boundaries and diff check. No skips/xfail/retries/timeouts added.
- [ ] **Step 5: Commit explicit two paths.** Report actual commands/logs/counts and HEAD to private task-1-report.md; root owns metadata, reviews, CI, push and normal main integration.

## Self-review

The design's status/reason, required completed evidence, decision/boolean consistency, noncompared metadata, and public/privacy/restore constraints all have tests. No new interface is left undefined; no implementation body is prescribed. This is source validation only; original registry remains80/30/3.
