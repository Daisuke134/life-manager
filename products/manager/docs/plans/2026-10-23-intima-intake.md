# INTIMA Pinned Input Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reuse the published INTIMA prompt artifact as a rights-reviewed, frozen evaluation-only input, preserving actual counts, duplicates and evidence limits.

**Architecture:** A small dataset-specific adapter reuses Source.verify_content and OutcomeBench reproduction metadata. The CLI reads an explicit local file and emits metadata only. No model runner, judge, trainer or new agent framework.

**Tech Stack:** Existing Python/unittest, stdlib JSON/hashlib, existing Source and OutcomeBench.

**Spec:** `products/manager/docs/specs/2026-10-23-behavior-transformation-scope-amendment.md` §5; parent model plan Task2. This is only the input-intake portion of V001/V002, not their completion.

## Global Constraints

- Dataset revision `48537e5d3905152751964b48d0a2ef681ace74dc`, file `INTIMA.jsonl`, bytes98989, SHA256 `31b683f0592a88db078e9cd8f3b03eefbd59edeac14b7894a92894d1518eb136`.
- Actual380rows/376unique prompts/32codes; card368/31 is a discrepant source claim. Preserve all rows and four exact duplicates; never silently deduplicate.
- Dataset card declares CC-BY-4.0; no independent LICENSE file was found. Artifact role evaluation_only, commercial_evaluation allowed_with_conditions, commercial_training hold. Attribution/license link/changes and metadata-only public output required. This operational hold does not claim CC BY legally prohibits training.
- Existing source-rights.v1 and four permission meanings unchanged; missing use permission fails closed. No benchmark input used as training/few-shot/retrieval examples.
- Prompt generator model is distinct from evaluated model or judge. No participant/time columns exist; transfer/person/time validity is UNKNOWN.
- No raw prompts/responses in Git, stdout metadata, repr or exception messages. Raw prompts may exist only in a private in-memory case field for later evaluation.
- Stage INPUT_INTAKE_ONLY, evaluation NOT_RUN, P0/NOT_MEASURED/can_execute=False. Reuse existing empty EvidenceBundle/reproduction_manifest without claiming simulation or outcome evidence.
- No network, provider calls, dependency install, training, money, publication, runtime, sourceguard changes or other lane edits.

## Review Focus

1. Hash/schema/byte-count or taxonomy drift must reject before an item is consumed; card counts must not override actualdata (Task1 tests).
2. Missing/mismatched purpose/role/revision/license evidence must fail closed; public visibility is not authority (Task1 tests).
3. Exact duplicates must preserve row identity and common prompt grouping, without invented independent sample size or holdout validity (Task1 tests).
4. Private prompts, JSON parse exception fragments, and misleading generator names must not leak or become results (Task1 tests).
5. An intake success or empty evidence bundle must never become model evaluation/benefit/permission (Task1 tests).

### Task 1: Rights-bound INTIMA adapter and local inspector

**Files:** Modify `products/manager/docs/research/source-rights.json`; create `products/manager/manager_core/intima_benchmark.py`, `products/manager/scripts/inspect_intima_benchmark.py`, `products/manager/tests/test_intima_benchmark.py`. Existing Source/OutcomeBench/evaluation code remains unchanged.

**Interfaces:**
- `load_intima(payload: bytes, rights_manifest: Mapping) -> IntimaDataset` in the new module. Immutable `IntimaCase` holds `case_id`, `prompt_sha256`, `code`, `prompt_generator_model`, and private `prompt` with repr=False. Immutable `IntimaDataset` holds typed Source, artifact revision/path and cases; internal binding metadata may be added narrowly.
- `intima_intake_manifest(dataset: IntimaDataset, *, code_version: str) -> dict` emits deterministic metadata, actual counts/code distributions/duplicate hash+row references, source/rights/claim discrepancy and existing empty-bundle assessment. No labels/scores or raw prompts.
- CLI `python products/manager/scripts/inspect_intima_benchmark.py DATA_PATH --code-version FULL_GIT_SHA [--rights-manifest PATH]`: local bytes only; default rights file is the existing repository manifest; JSON metadata stdout; static `INTIMA_INTAKE_UNAVAILABLE`/exit2 on rejected input, not exception text. No download or model initialization.

- [ ] **Step1 RED:** Add meaningful authored synthetic JSONL fixtures (not copied benchmark prompts) with one duplicate. Pin production rights record facts independently from fixtures. Test missing/hold permission, training role, wrong revision/hash/length, duplicate source ID, malformed schema/empty strings, generator naming, preserved rows/grouping, no prompt in repr/export/error, unchanged existing permission requirements, P0/NOT_MEASURED/no execution, wrong code_version, CLI success/staticfailure. Fixture manifests clearly synthetic, never claimed as upstream data. No live dependencies.
- [ ] **Step2 verify RED:** `env PYTHONPATH=products/manager:products/manager/tests python -m unittest test_intima_benchmark -v`; record actual intended failure before implementation.
- [ ] **Step3 implement:** Append only `intima-prompts` to existing rights manifest, using the verified card URL/revision/hash and data-quality profile. Retain actual `code,prompt,model` values; case ID is `intima:{revision}:row-{1based}`, hash exact decoded prompt UTF8, never normalize/drop. Reject unknown schema and inconsistent profile. Keep Source public_nonpersonal/hash contract. Role/purpose gate is a declared rights review, not legal authentication. Metadata uses existing empty EvidenceBundle/reproduction_manifest to retain P0/NOT_MEASURED; do not create a simulation/human-outcome reference for mere input intake.
- [ ] **Step4 GREEN:** Run focused `test_intima_benchmark`, `test_r006_rights`, `test_evaluation`, `test_outcome_bench`; run fullManager once on final code, boundaries and diffcheck. Then run the actual local pinned98989-byte payload through CLI with actual sourceSHA, save metadata privately, independently check380/376/32/duplicates. Rawpayload remains outsideGit.
- [ ] **Step5 self-review/commit:** Commit only four owned paths; report actualRED/GREEN, hashes, CLI output metadata, absence of raw output, and limits. Independent task review and root officialCI follow. Keep V001/V002todo.

## Self-review

Parent Task2 artifact rights/version/public-test isolation and existing OutcomeBench reuse map here. This subplan intentionally does not implement unavailable upstream judge prompt/parser, invent human reference or claim V002 baseline. A separate dataset adapter follows existing external-behavior intake shape and keeps mathematical scorers unchanged. Training, transfer and real outcomes remain separate gates.
