---
license: apache-2.0
base_model: HuggingFaceTB/SmolLM2-135M-Instruct
language: en
tags: [uplift, intervention, behavior, lora, sft]
---

# Manager v0 — model card

## What this is

The first post-trained checkpoint of **Manager**, Anicca's behavior
model. v0 is deliberately the smallest end-to-end run that really
executes: it proves the full circuit — intervention data → post-training
→ preregistered uplift eval → product case format — with real numbers,
including where it fails.

The model is an outcome model: given a person's history and an
intervention arm, it estimates P(visit | history, arm). The uplift
score used for targeting is the treated-minus-control difference.

## Base model

`HuggingFaceTB/SmolLM2-135M-Instruct` (SmolLM2 135M, Apache-2.0).
Chosen because it is small enough to post-train and evaluate on free
CPU compute end to end, and openly licensed. Be.FM weights were
explicitly **not** used (rights not yet clear).

## Training

- Framework: TRL `SFTTrainer` + PEFT LoRA — the standard TRL SFT recipe
  (https://huggingface.co/docs/trl/sft_trainer). No custom training
  infrastructure.
- LoRA: r=16, alpha=32, dropout 0, target modules all-linear; merged
  into the base weights for release.
- Data: 1,000 Hillstrom intervention cases (prompt/completion),
  1 epoch — a uniform seed-0 subsample (`sft_train_v0.jsonl`) of the
  2,000 prepared cases, chosen to bound wall-clock on shared CPU
  (see Compute). See `DATA_CARD.md`.
- Hyperparameters: lr 1e-3, cosine schedule, warmup 4 steps,
  batch 16, max length 256, completion-only loss, seed 0.
- Compute: CPU (bf16) on the team VM (no GPU): the only Hugging Face
  credential available to the team is read-only, so no hosted GPU job
  could be launched, and no other free GPU credential exists. Paid
  compute was not used (standing rule: free routes only).
  Wall time and final loss are recorded in the run record
  (anicca-ops `files/manager-v0-start-2026-11-14.md`) and in
  `train_log.json` shipped with the weights.
- Run history, honestly: the first training attempt (fp32, 2,000 rows)
  was killed at ~32 minutes by a runtime service restart before any
  checkpoint existed (checkpoints were disabled in that configuration).
  A bf16 restart measured ~75 s/step on this shared VM (the cell's
  effective compute is ~1 core; bf16 matmuls are ~3.3x faster but
  end-to-end step time only ~1.4x), so the published run trains on a
  1,000-row subsample with checkpointing every 25 steps and
  auto-resume — the smallest configuration that finishes end to end
  here. Details and timestamps: run record §2.

## Evaluation (MG-06 protocol, frozen before scoring)

1,000-row stratified subsample of the frozen test split; arms compared
on identical rows. Primary metric: Qini coefficient (sklift) with a
500-resample bootstrap 95% CI. Gate (preregistered): lower CI must
exceed the random-targeting p95. Full numbers: `results/` and the v0
README. The base model scores Qini 0.0739, CI [−0.0458, 0.1853] —
**gate FAIL** (random p95 = 0.0715). Manager v0's own scores are in
`results/eval_manager-v0.json` and the v0 README; whatever they are,
they are the v0 result.

## Reproduce the eval

```bash
pip install torch transformers scikit-learn scikit-uplift pandas numpy
python eval_uplift.py --source hillstrom.csv.gz \
  --model <weights-dir-or-hf-id> --label manager-v0 \
  --out eval_manager-v0.json
```

The harness is verified to reproduce every classical-arm number of the
original base-model run exactly (prior / random / T-learner).

## Limitations

- One dataset (2008 e-mail marketing), one outcome (website visit in
  two weeks), 1,000 training rows, a 135M model, CPU compute. v0 is a
  circuit test, not a capability claim.
- The model has never seen product (Anicca) data; the product case
  pipeline exists but the app-side export it needs is still missing
  (see DATA_CARD.md).
- Probabilities are next-token probabilities over {0, 1}, normalized —
  a scoring convention, not calibrated probabilities.

## Feedback

Expert feedback is explicitly welcome — issues and PRs on
https://github.com/Daisuke134/anicca. Tell us what the eval gets wrong,
what the serialization loses, and what v1 should train on.
