# HelpSteer2 development-only candidate evaluation

> Agent procedure: use the already selected Superpowers SDD process. Root owns metadata, execution, reviews and integration; one bounded implementation task below. This is part of parent model plan Task2 preparation, not V003 or a new task registry.

**Goal:** Measure whether the pinned existing CPU model ranks eight exact published candidate pairs consistently with their published human preference. Reuse native Transformers loss. No new response quality, behavior effect or benefit is inferred.

**Architecture:** A local-only dataset-specific evaluator reconstructs the exact cases from pinned original files, verifies source/rights/protocol/model/tokenizer bindings, and reuses Source and an empty OutcomeBench EvidenceBundle. The normal kernel/owner/CLI/workflow are unchanged. Optional model dependencies load only during an explicit research invocation.

**Spec/protocol:** Parent `2026-10-23-behavior-transformation-model-plan.md` Task2. Frozen metadata: `experiments/behavior-model/helpsteer2-dev-protocol-v1.json`, SHA256 `586d8701a26305ea56ffab0d095db72d4fb64974977528d7581511ff7c8ef529`. This protocol was frozen before model outputs or scores were observed. The development-only run is now recorded in [the acceptance receipt](../verification/HELPSTEER2_DEV_CPU_EVALUATION_20261023.md). No final-test score is permitted.

## Fixed boundaries

- HelpSteer2 revision990b2711a36180dd19d9c94b8627844866f8982a; card declares CC BY4.0, actual legalcode reviewed. No independent dataset LICENSE file found. Attribute source/version/changes; third-party privacy/rights are not guaranteed. The existing rights manifest receives one source record; previous records remain unchanged. Commercial evaluation allowed_with_conditions, commercial training/product/raw redistribution hold for this operating purpose.
- Actual quality rows20324train/1038validation, preference9125rows with raw split8677train/448val. Normalize only the split name val→validation; preserve text. Reconstruct all eight dev pairs from raw train rows5609,5999,3783,5396,6863,1039,4200,4365, verify exact prompt/response hashes and quality joins. Negative preference selects response1, positive selects response2; no ties.
- Data-only rules and all56 proposed groups were fixed before model output. AI-assisted content eligibility review retained all8dev/16final-test, excluded5train (27remain). This is not human annotation or approval. The32train proposal is NOT_READY; no replacement, training or final-test evaluation occurs here. Exact/canonical selected-group and INTIMA hash overlap0; paraphrase/pretraining contamination UNKNOWN.
- Native Qwen3-0.6B BF16, fixed revision/files/tokenizer, private CPU-only dependencies. No GGUF training assumption, generation, optimizer, external inference/API, tool use, production activation or budget invention.
- Eight assigned groups/16candidate model forwards. Full rendered sequences<=256tokens, exact prompt-ID prefix, one assistant EOS151645. Native causal-LM labels mask prompt prefix and tokens after assistant EOS to−100. Candidate through EOS is scored. Native model loss supplies mean token NLL; summed NLL is mean×scored-token count. Raw text stays private.
- BASE_QWEN selects lower mean NLL; SHORTER_CANDIDATE_RULE selects fewer scored completion tokens; exact tie uses smaller response SHA256 for both. NO_ACTION abstains. All share the exact input batch and fixed bounds; rule/no-action do no dummy model work. Rule/no-action NLL and no-action conditional accuracy are null, never0/100%.
- Report assigned/attempted/completed/covered/failed/abstained/unattempted separately. Conditional accuracy uses covered completed groups; coverage uses assigned8. Preserve model losses, lengths/ties, original human preference and quality-label provenance, failures and null metrics. No response-harm, pressure/dependence, clinical competence, behavior change or suffering reduction is certified.
- One cumulative session bound900seconds from before model load and process-group RSS ceiling6GiB, threads2, seed42; no retry. Root watchdog records resource interruption and unfinished denominators. A valid finite result is not model promotion or V001/V002/V003 completion.

## One implementation task: guarded evaluator and private execution seam

**Owned files:** append one record in `docs/research/source-rights.json`; create `manager_core/helpsteer2_candidate_eval.py`, `scripts/evaluate_helpsteer2_dev.py`, `tests/test_helpsteer2_candidate_eval.py`. Protocol/plan are root-owned and must not be edited by the implementer. All production and existing mathematical scorer files are forbidden.

**Interfaces:** Thin helpers for strict protocol/source/rights validation, original-case reconstruction, exact tokenizer mask building and metadata-only result aggregation; a local CLI takes explicit protocol path/expected SHA256, local data/model directories and immutable code version. The model runner is lazy. Original human annotations are read only from pinned dataset files, never trusted from caller-supplied case text. Existing Source.verify_content and empty OutcomeBench reproduction metadata retain P0/NOT_MEASURED/can_execute=False. Rejected configuration returns static `HELPSTEER2_DEV_UNAVAILABLE` without source fragments. The script has no network or training mode.

- [x] Add meaningful synthetic-source tests first: tampered/missing permission/source/protocol/model pin, raw/semantic split drift, wrong preference sign, duplicate/extra/nondev rows and modified text, missing/nonunique quality join, mismatched token prefix/EOS/length, mask endpoints/causal count, hash tie-break, partial failure denominators, no-action0/0→null, no raw repr/export/error, no execution/human-benefit promotion. No upstream raw prompt in tests. Invalid/default configuration must initialize no optional model.
- [x] Record actual intended RED, implement the narrow interfaces and verify GREEN with existing rights/Source/OutcomeBench contracts. Use existing test-loader shape and native Transformers loss; no custom trainer, agent harness or new dependency in the core suite.
- [x] Run focused and full Manager suite once on final code, boundary/diff checks; commit only the four owned paths. Report exact results, self-review and untested live scope. Root sends fresh spec/quality review before actual model execution.

## Root execution and acceptance

- [x] Verify current code/model/data/protocol hashes, tests/review and private output paths; freeze private execution manifest with the actual code commit before scores. Run one bounded CPU child under an own-process watchdog. Do not score or inspect final-test model results.
- [x] Record actual resource/result/cleanup evidence, denominators, published-human preference agreement and limitations. No posthoc hyperparameter/filter/threshold change or training. If finite failures occur, retain partial/NOT_RUN rows.
- [x] Publish metadata-only receipt after independent verification. Keep V001/V002/V003 todo until their complete original acceptance is independently reviewed; this development slice is partial evidence.

## Self-review

This plan uses existing public data, native model loss and existing evidence/source contracts. It avoids treating public candidate labels as ratings of newly generated text, generic quality as behavioral benefit, an AI content review as human approval, or dependency installation as trainability. A measured dev gap can inform the later model hypothesis; it does not waive the parent V002→V003 gate.

## Accepted limited execution — 2026-10-23

Source9d05252e2c06; 22new tests / local1047 skip5 / official1021 skip6, zero failures. Fresh source and actual-result reviews each0 findings. Actual16/16 candidate forwards completed in27.856s with sampled process-group peak1,909,272,576bytes; model4/8, shorter-candidate rule4/8, NO_ACTION8abstentions/conditional accuracy=null. No demonstrated model advantage on this selected dev8. Native CPU inference works; backward/optimizer/training/final-test and human benefit remain unmeasured/not run. This checklist accepts only this subplan, not the parent V001/V002/V003 acceptance. Root review of independent evidence and the metadata-only receipt is complete; final whole-branch review is tracked separately.
