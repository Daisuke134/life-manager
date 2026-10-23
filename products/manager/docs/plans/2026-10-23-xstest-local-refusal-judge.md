# XSTest local refusal judge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox syntax. Root owns protocol, execution/reviews and integration. One source task below.

**Goal:** Measure a real local model judge against existing human labels of the exact same published450 responses, preserving partial failures and unknown validity.

**Architecture:** Thin source-bound research evaluator; reuse original XSTest definitions, native Transformers generation, Source hash verification and empty OutcomeBench metadata. No production consumer, trainer, new runtime, simulator or statistics framework.

**Tech Stack:** stdlib CSV/hash/JSON, existing Source/OutcomeBench, private pinned Transformers CPU dependencies and native Qwen3-0.6B already prepared.

**Spec:** Parent behavior-transformation model plan Task2 and MANAGER_PRODUCT_SPEC.md V001/V002. Immutable protocol `experiments/behavior-model/xstest-local-refusal-judge-protocol-v1.json`, SHA256 `8d5a20a4172d790ee8b0265ae44655ca35e289fed40207ac8baf6eee012cf010`.

## Global Constraints

- Mission: 行動変容を通じて、苦しみを終わらせることを目指す。Religious adherence is not a criterion. P0 / NOT_MEASURED / can_execute=False.
- 113IDs=80done/23todo/10skipped; V001/V002/V003 remaintodo. Person/study/time axes unavailable; scope/generalization/training promotion HOLD. No protocol rewrite to claim a missing holdout.
- Same450 original responses/source hashes; all human labels stay host-side. Preserve original prompt/completion text. No Meta/OpenAI completions, released GPT labels, separate unbound prompt CSV, HelpSteer2 final-test, training/fewshot/retrieval or raw redistribution.
- Root extends prior conditional private evaluation ruling to this local-only judge comparison; annotation per-column scope remains not explicit. Source classification follows authored constructed benchmark and nonidentifying categorical labels, not a general PII guarantee.
- Native0.6B,2threads/BF16/seed42/greedy/max16 output/context2048. Full input+16 reserve must fit; no truncation. Exact three-label parser and EOS; no retries/label repair. One cumulative900s/6GiB sampled own-process-group watchdog from before model load.
- Model/rule/no-action compare same assigned450. Rule gets full450 and matched-valid-model subset separately. NO_ACTION450abstentions/accuracy=null. No model superiority/adoption claim from this development run.
- Default OFF, owner/workflow/kernel/production behavior and all old protocol/results unchanged. New generation is labels of quoted responses only, never intervention or user advice.

## Review Focus

1. Gold or annotation accidentally in model messages: explicit message builder accepts only question/response; synthetic test asserts other fields excluded.
2. Corpus text injection or long sequences: quote with nativeJSON; no tools; input overflow stays null before forward, no silent truncation.
3. Complete generation misread as valid classification: strict whole-label plus EOS; invalid/length/UNKNOWN retain distinct denominators.
4. Killed/failed run loses assigned cases or bills again: initial checkpoint450 before optional imports, inflightUNKNOWN, failures stop lane, retry0.
5. Unavailable human/time split or useful-looking aggregate becomes validity/benefit: contract exposes unavailable axes and HOLD; metadata-only export/null tests.

## Task 1: Guarded source adapter, local judge and private CLI

**Files:** append exact root-proposed record in `docs/research/source-rights.json`; create `manager_core/xstest_refusal_eval.py`, `scripts/evaluate_xstest_refusal.py`, `tests/test_xstest_refusal_eval.py`. No other path is owned. Root-proposed record is in the private task brief directory; protocol/plan are root-owned.

**Interfaces:** `load_verified_inputs` validates built-in and caller protocol hash, canonical rights record hash, original2 CSV asset bytes/unique exact450 IDs/columns/gold, deterministic order membership, model8file pins and packages before optional model import. Frozen case carries raw text with repr=False. Explicit message builder contains only original question/response plus pinned instructions. Pure callback evaluator provides model/rule/noaction state/summary and strict label parsing. Lazy `run_local` uses AutoTokenizer/AutoModelForCausalLM(local_files_only=True,trust_remote_code=False,safetensors,CPU BF16); native `generate` under inference_mode. Metadata manifest reuses empty EvidenceBundle/reproduction_manifest. CLI requires explicit protocol/hash/data-dir/model-dir/rights/code-version and optional absolute private output; default/help invalid returns only XSTEST_REFUSAL_UNAVAILABLE/exit2. Atomic0600 checkpoint and third-party stdout/stderr suppression follow existing HelpSteer2 CLI shape. No source fragments/raw generated text/repr/exception messages in output.

- [ ] Write synthetic tests first: invalid/tampered protocol/rights/source/model/split/IDs/text/gold/booleans rejected before optional import; field-only message builder excludes gold; exact3 parser rejects surrounding prose/quotes/numbers/invalid EOS/length cap; full reserve overflow no inference; fixed order; same450 metadata denominator using small synthetic pure fixtures; noaction null; full and matched-rule metrics; zero denom null; native failure/UNKNOWN/stop preserve all unattempted; checkpoint before import/forward and output privacy. Original prompt/response text is forbidden in tests. Do not mock optional generation as evidence of real-model behavior.
- [ ] Record expected RED, implement narrow interfaces and GREEN. Use existing source validation and native libs; no duplicated trainer/client framework. Reuse original comparison confusion/null arithmetic shape; no ordinal score on class IDs.
- [ ] Run focused and full Manager suite once on final source, diff/boundary checks, commit only4owned files and report self-review/limits. Root sends fresh task review before actual model run.

## Root execution

- [ ] Verify exact code/protocol/model/source bindings and tests/review; push source and dispatch exact official researchCI. Freeze private execution config before predictions. Reuse existing private watchdog monitor and offline env.
- [ ] Run one cumulative bounded450-label session. Context overflow is unattempted; interrupted inflightUNKNOWN. Keep rule/noaction and all450 metadata. No resource/accuracy guarantee and no automatic retry.
- [ ] Independently verify original-data binding, arithmetic/coverage/status/hash/privacy/cleanup and publish only aggregate receipt. All V tasks remaintodo pending full acceptance; parentTask3 training gate unchanged.

## Self-review

The task directly addresses new-judge human-reference calibration missing from earlier released-label/NLL audits. It adds one explicit research seam while retaining original datasets/protocols and production OFF. It cannot supply missing person/time holdouts, pressure/dependency gold or human benefit and does not treat this diagnostic as closing those gates. Root chose native0.6B for already verified CPU footprint; the1.7B backend remains an alternative, not a prerequisite.
