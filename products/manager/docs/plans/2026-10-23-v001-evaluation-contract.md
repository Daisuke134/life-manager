# V001 — existing diagnostic contract mapping

> **For agentic workers:** Use superpowers:subagent-driven-development. Root owns scope, integration and acceptance. One metadata task; no runtime feature.

**Goal:** Bind the already frozen INTIMA, HelpSteer2 and XSTest diagnostics to their exact source, model roles, scorer, rights, observational unit, split limitations, failure denominators and existing OutcomeBench export.

**Design:** One metadata-only mapping referencing existing protocol/rights records and receipts. INTIMA stays intake/unscored; HelpSteer2 stays generic preference/NLL; XSTest stays original-response refusal calibration with the failed local setting declined. This is a retrospective mapping of previously frozen experiments, not a new preregistration. Missing person/study/time holdouts remain unavailable/HOLD. No full V001 acceptance is inferred.

**Alternatives:** A new common evaluator would duplicate working wrappers. Requiring another model run would not fix the missing mapping. Reusing the existing protocols and Source/OutcomeBench metadata is sufficient for this bounded task.

**Spec:** Parent model plan Task2; scope amendment section4; existing registry V001. Original113 states80done/23todo/10skipped remain unchanged.

## Task 1 — metadata mapping

**Owned file:** `experiments/behavior-model/v001-evaluation-contract-v1.json` only.

**Interface:** Public nonpersonal metadata; three named slices, no raw text/labels. Refer to existing rights record IDs with canonical record hashes rather than redefining permissions. Bind immutable repo protocol/public receipt file bytes and source commit references. INTIMA's private frozen protocol/selection is represented by evidence ID/hash and public receipt, not copied private content. Explicitly distinguish upstream completion generator, current response generator, candidate evaluator and judge. Bind existing empty EvidenceBundle/reproduction_manifest and preserve P0/NOT_MEASURED/can_execute=false.

- [x] Read the actual three protocols, source-rights records, evaluators and public receipts; extract hashes/roles without ML imports or model/CI re-execution.
- [x] Write a compact contract with slice scope/adoption limits, native/semantic split, unavailable axes, purpose isolation, scoring/refusal/abstention/null/failure denominators, and protected authority boundaries. Reference results via receipts instead of creating another result ledger.
- [x] Validate JSON, local references and their hashes; confirm old artifacts/registry/runtime source unchanged. Commit only the owned metadata file and report evidence/limits. No source tests for this nonbehavioral metadata change.

## Root acceptance

- [x] Fresh combined task review verifies the mapping against original metadata. Fix genuine findings only.
- [x] Verify bound protocol/rights/receipt bytes and existing Source/OutcomeBench empty-evidence behavior with a bounded private check; no raw data/model downloads, inference, training, new runtime or full-suite rerun.
- [x] Record exactly which mapping gap is closed and which holdout/validity gaps remain; update parent/spec/README without changing registry status.

## Boundaries

No new model/judge, scorer, trainer, production consumer, framework, scheduler, permission, participants, clinical/behavioral benefit, independent holdout or task completion is created by this file. Missing source facts remain unknown; retrieval times are not observation times. HelpSteer2 NO_ACTION abstention is not response refusal, and XSTest labels do not apply to INTIMA or newly generated responses. New content publication remains held.

Metadata task source accepted: `e1e27153d3c12bc8c2fea54677bf10d8de17e8a5`; bounded worker112 checks and independent task review0 findings / SPEC PASS / QUALITY Approved, root actual binding/export checks. [Receipt and remaining holdout gap](../verification/V001_EVALUATION_CONTRACT_MAPPING_20261023.md). Whole-change review, named-branch push and remote readback are separate root integration evidence; they do not promote V001 or a model.
