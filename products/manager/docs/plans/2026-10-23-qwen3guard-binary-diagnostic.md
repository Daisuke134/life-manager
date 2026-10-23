# Qwen3Guard binary refusal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Root owns protocol, execution, status and integration. One source implementation task below; root then runs and verifies the frozen experiment.

**Goal:** Evaluate a purpose-built existing native binary judge on the exact original450 responses, with423 extreme-label agreement targets and27 unscored partials.

**Architecture:** New thin binary adapter reuses existing exact source/rights/model verification and native offline HF inference. No new runtime, scoring framework, trainer or production consumer.

**Tech Stack:** stdlib, existing Source/OutcomeBench, torch2.8.0+cpu, Transformers4.56.2, existing own-process watchdog.

**Spec:** [design](../specs/2026-10-23-qwen3guard-binary-diagnostic.md); [protocol](../../experiments/behavior-model/xstest-qwen3guard-binary-protocol-v1.json), SHA256 `58c15f812202236e92b27bd704ea37f3803288749f03c1fcb4039f58600cec7f`.

## Global Constraints

- Mission: 行動変容を通じて、苦しみを終わらせることを目指す。P0 / NOT_MEASURED / can_execute=False; 113=80done/23todo/10skipped; V001/V002/V003 todo.
- Fixed model/source/membership/rights/package hashes from protocol. Reuse old pure source helpers without modifying old files/protocols/receipts/contract. No raw benchmark text in tests, source, stdout or published documentation.
- All450 assigned in old hash order. Primary423: full_refusal→Yes49/full_compliance→No374; partial27 GOLD_NOT_BINARY. No binary gold for partial, no direct old3class comparison. Adoption/generalization/training HOLD; unavailable person/study/time axes retained.
- Native user+assistant messages only; fixed tokenizer template; no gold in input. Three-line whole-schema parser, Refusal only, terminal EOS, no repair/retry/resume/truncation.
- CPU BF16/2threads/seed42/greedy/max128/context4096. One cumulative3600s/6GiB own-PGID watchdog before load. No new dependencies/paid API/remote code/pickle/training/finaltest/production effects.
- Private result includes raw suffix/token IDs for audit, original text stays in private source only. CLI stdout aggregate metadata only; checkpoint0600 atomic+fsync before imports/load and generation. UNKNOWN stays unknown.

## Review Focus

1. Invalid schema/EOS or injection disguised as a native answer must not become a binary prediction.
2. Partial gold and missing observations must not contaminate423 primary denominators or paired comparisons.
3. Encode/load/generation failures and interruption must retain all assigned rows and durable uncertainty.
4. Caller-supplied protocol/model paths or digests must not replace built-in immutable bindings; no optional ML before checks.
5. Raw suffix and source text must stay private even on CLI/native-library failure.

### Task 1: native binary research adapter

**Files:**
- Create `manager_core/xstest_binary_refusal_eval.py`.
- Create `scripts/evaluate_xstest_binary_refusal.py`.
- Create `tests/test_xstest_binary_refusal_eval.py`.
Paths are relative to `products/manager/`. Existing files are read-only.

**Interfaces:**
- Reuse `RefusalCase`, `Generation`, exact `_reconstruct_cases`/`_membership_sha256`, source/model-file/rights/JSON primitives in `manager_core/xstest_refusal_eval.py`; preserve their meaning and original experiment.
- Produce `validate_protocol(payload: bytes, expected_sha256: str) -> dict`, `load_verified_inputs(...) -> (protocol, rights, sources, cases)` matching the old keyword configuration, `build_messages(question: str, response: str) -> list[dict]`, `parse_generation(generation: Generation) -> (status, prediction, native_fields)`, `evaluate_cases(cases, encode, generate, *, progress=None) -> dict`, `result_manifest(results, *, code_version: str) -> dict`, `run_local(*, progress=None, **configuration) -> dict`.
- Result rows carry source hash IDs/order, host-only original gold/eligibility/rule projection, operation/status/stage counters, input/output tokens, private raw suffix/token IDs/native fields. Recompute and validate summaries from rows; detect inconsistent metrics, status/counter/prediction fields and paired membership.
- CLI takes the same explicit6configuration args and required private `--output` as the existing CLI; reject existing/symlink output or symlink parents, no help/abbreviated args, print only aggregate status/code/protocol metadata. Reuse existing FD silence helper; use existing atomic checkpoint recipe without editing old CLI.

- [x] Write RED tests with synthetic RefusalCase/Generation only: native two-message shape; protocol mutation rejection; exact parser valid Yes/No; extra/duplicate/unsafe category/invalid EOS/128 length cases; partial-only/empty/one-class/null metrics; rule full vs same-ID matched and paired4counts; encode overflow/no generation; encode/generation failure; durable UNKNOWN; checkpoint before optional model import/load; output0600/privacy/existing/symlink failures.
- [x] Run focused unittest and record expected RED. Implement the narrow adapter, private CLI and standard offline model loader. Implement native stage semantics from protocol; load failure keeps450 NOT_RUN with FAILED lane. On row exception fail-stop, no retry. Reject inconsistent result metadata before export.
- [x] Run focused suite GREEN, then full Manager suite once on final source with no ML/downloads. From `products/manager/` cwd, run `python -m unittest discover -s tests -q` (the existing CI/README invocation); from repo root run `git diff --check`. Self-review and commit only3owned new paths via sparse staging. No push/CI/model run by worker.
- [x] Root obtains fresh combined spec+quality task review before source acceptance, pushes named research branch, dispatches exact official CI and waits for full terminal success before real inference.

## Root execution and integration

- [x] Independently verify native asset SHA/size, protocol/source/rights/CI and runtime. Freeze0400 private execution config and reuse accepted watchdog with new one-shot wrapper. No predictions before protocol freeze/source acceptance.
- [x] Run the single bounded450-assigned experiment. Independently check native parser outputs, arithmetic/partitions/paired IDs, resource receipt, private output and own process cleanup. Fresh result verification:46 checks PASS; retain monitoring-gap protocol deviation and unreaped terminal orphan. No repeat inference on report defects.
- [ ] Publish aggregate receipt and update existing spec/README/parent plan/SSOT header, preserving task counts and old bytes. Final broad independent review, scoped fixes only, secret scan, nonforce push and authoritative ref readback. Retain active parent worktree and private scientific evidence.

## Self-review

Protocol values, eligibility and resource budget are fixed before any new prediction. Existing completed experiments remain immutable. The new adapter addresses the observed collapse of a generic judge without creating independent human binary gold or closing missing holdout/harm/benefit gates. The diagnostic is allowed to fail or remain partial; its outcome does not trigger training or adoption automatically.

## Actual execution checkpoint — 2026-10-23

[Aggregate receipt](../verification/QWEN3GUARD_BINARY_CPU_20261023.md):450/450 native format-valid,primary377/423 vs released rule383/423. Partial27 remain unscored. Original parent monitor was lost at reconnect; same model process continued and was monitored again under the original deadline. Keep the infrastructure deviation, unknown full-gap RSS and unreaped orphan explicit. No experiment retry/resume/budget extension; no automatic adoption. Independent result verification and broad integration review are recorded separately before acceptance.

Ruling: Recover monitoring of the same existing process under the original absolute deadline instead of starting another inference attempt. Cost if wrong: the lost monitoring interval and non-parent cleanup cannot be reconstructed; report those limits, preserve the original stale receipt, and withhold full resource-protocol compliance/adoption.
