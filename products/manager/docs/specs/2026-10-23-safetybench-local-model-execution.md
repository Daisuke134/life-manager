# SafetyBench local base-model comparison — prospective scope

The root controller adopted this scientific implementation scope at
`2026-10-23T23:15:57.005322+00:00` under the user's delegated agent-development
authority. It is the existing V002 model-comparison lane in the
[behavior-model plan](https://github.com/Daisuke134/life-manager/blob/02ebc1553ac8edf2e73f0e507eb5c4c396f8da68/products/manager/docs/plans/2026-10-23-behavior-transformation-model-plan.md),
not a new task/status authority. **Implementation accepted; inference NOT_RUN;
actual execution acceptance remains pending.**

The separate private root decision is frozen read-only, SHA256
`c41c898e2a81cf0d212deaf9ff2428c667b4b5c67fb4bd5da74c6e73a172764a`.
It accepts one prospective private offline MCQ comparison and the unchanged
evaluation-use interpretation. It does not assert external legal approval or
authorize a model invocation before the later source, CI, resource and execution
configuration checks.

The existing [MCQ protocol](../../experiments/behavior-model/safetybench-mcq-protocol-v1.json)
(`6369fe7f5b9ead9569892acf77da9c8b60d1b4f0933cf79e55562f99041e394e`),
the `safetybench-mcq-private-evaluation-v1` rights record
(`07e6beea0bf5570a9b1fab8153c80306dde7a1f29159125109b6b03e16648fd4`),
all 18 existing research rights records and the earlier no-model event remain
unchanged. Private commercial evaluation keeps its existing conditions;
training, product use and raw redistribution remain held. All-row third-party
provenance is NOT_VERIFIED. This new prospective decision does not backdate
inference authorization into the earlier event. The base model's native
Apache-2.0 license and pinned provenance are separate from benchmark MIT.

Use only base `Qwen/Qwen3-0.6B`, revision
`c1899de289a04d12100db370d81485cdf75e47ca`, with its eight previously pinned native
model/tokenizer/license files. Reuse the upstream SafetyBench bare zero-shot
question/options prompt ending `Answer:(`, in original source and option order.
No chat wrapper, demonstrations, answer key or category enters the model input.
Native CPU BF16/eager evaluation uses two threads, batch one, seed 42,
`logits_to_keep=1`, `use_cache=False` and no gradient or generation. Require
singleton A/B/C/D token IDs 32/33/34/35 with exact decoded identity; choose the
first maximum finite label logit among the actual two to four options.

All 11,435 rows remain assigned. Input cap is 2,048 tokens, without truncation.
The completed input-only tokenizer audit found min 22/max 1,425/total 989,932
tokens and zero overflow; no gold, weights, model or forward was read/run by
that inspection. Audit SHA256 is
`206d1e07224af6e78c1ea207ceecb802aec925163714a0cf828d74f2d776e140`;
its terminal receipt is
`b9f69decda61a19ddab60559163afcf7795438f060a1de3f3ccb78f7c78e156b`.
This establishes token feasibility, not model throughput or memory fit.

The prospective policy is one cumulative **10,800-second** attempt and a
**6,442,450,944-byte sampled process-group RSS** bound on existing CPU resources.
No retry, resume, extension, scored pilot or posthoc method/model/row selection.
The unchanged external watchdog starts before large hashes, loading and
inference. Its RSS polling is sampled, can overshoot, can double-count shared
maps and is not a kernel hard cap. Fresh actual resource admission, immutable
source/review/official CI and an independently frozen root 0400 execution config
must be accepted before launch. Full coverage and fit are not promised.

Keep a private durable START/RESULT journal. Completed finite choices are VALID;
known failures are FAILED; an interrupted forward without durable result is
UNKNOWN; untouched assignments are NOT_RUN. NO_ACTION is ABSTAIN, not refusal.
Malformed/torn writes never become successful decisions. Reconcile only after
actual terminal/reap verification, then use the existing recorded-prediction
contract and scorer once. Preserve all-gold accuracy separately from
conditional-valid accuracy and coverage. A stopped source-order prefix is
operationally censored, not a representative sample.

Publish aggregate metadata only; keep raw rows, journal, predictions, native
output, config and receipts outside Git. Exact upstream prompt/decision-formula
reuse does not establish bitwise parity across CPU BF16 and upstream GPU FP32.
Forced choice measures MCQ key agreement, not free-response refusal, persuasion,
pressure, dependency, clinical validity, behavior change or human benefit.
P0/NOT_MEASURED, deployment `can_execute=False` and model adoption HOLD remain.
The old HelpSteer final16 is SCORED/NOT_PRISTINE and is not reused here. Existing
85 done / 18 todo / 10 skipped and U004 draft/zero participants/zero interventions
are unchanged. No production owner, intervention or publication channel is
enabled by this scope.
