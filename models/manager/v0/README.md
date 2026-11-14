# Manager v0 — first post-training run (2026-11-14)

*A short write-up, in paper form: what we did, what we measured, what we
conclude, and what is still missing. Every number below is produced by
code in this directory; every design decision cites its source.*

## 1. Question

Can a small open-weight language model, post-trained on randomized
intervention data, rank people by **uplift** — who changes behavior
*because of* the intervention — better than random targeting and simple
priors? This is the capability Manager needs: Anicca delivers
interventions (notifications, affirmations) and must choose *which*
intervention for *which* person. The eval discipline was fixed before
this run by the MG-06 preregistration (anicca-ops
`files/mg06-prereg-2026-11-14.md`, 2026-11-14): the model is judged on
intervention cases — where a population prior has no answer — by the
Qini coefficient with bootstrap confidence intervals, never pooled
across data families (prereg section 4).

## 2. Method

**Data.** Hillstrom MineThatData e-mail challenge (2008), the two arms
frozen by the prereg (Womens E-Mail vs No E-Mail; 42,693 rows), split
70/30 stratified by treatment × visit, seed 0 (train 29,885 / test
12,808) — the identical split as our published MG-06 baseline, whose
numbers this pipeline reproduces exactly. `DATA_CARD.md` has
provenance and the license note.

**Serialization.** Each case becomes one prompt (person history +
intervention arm) with completion `" 1"` / `" 0"` = the measured visit
outcome under the delivered arm (`serialize.py`). The same format is
used for training and for scoring, so the model's next-token
distribution over {0, 1} under each arm is an outcome model and the
score difference is an uplift estimate. The renderer is mechanically
verified against the shipped training file (2,000/2,000 pairs).

**Training.** TRL `SFTTrainer` + PEFT LoRA (r=16, alpha=32, all-linear,
merged) on `HuggingFaceTB/SmolLM2-135M-Instruct` (Apache-2.0), 1,000
cases (a seed-0 subsample of the 2,000 prepared; see the compute note
below), 1 epoch, lr 1e-3 cosine, completion-only loss (`train_sft.py`).
The recipe is the standard TRL SFT pattern
(https://huggingface.co/docs/trl/sft_trainer); we wrote no custom
training infrastructure. Be.FM weights were not used (rights unclear).

**Compute — stated plainly.** This run executed on **CPU** on the team
VM. The team's only Hugging Face credential is read-only (verified:
`create_repo` returns 403), so no hosted GPU job could be launched;
no Kaggle/Colab credential exists; paid compute is against standing
rules. v0 is therefore the smallest run that executes end to end for
real. {{TRAIN_RUNTIME}}

**Eval.** `eval_uplift.py`: a fixed 1,000-row stratified subsample of
the frozen test split, declared before scoring. Arms on identical
rows: population prior (constant score), random targeting (200 draws),
T-learner logistic regression (the MG-06 classical baseline), the base
model, and Manager v0. Primary metric: Qini (sklift) + 500-resample
bootstrap 95% CI; gate: **lower CI > random p95** (prereg section 4).
The harness was itself verified: it reproduces every classical-arm
number of the original base-model run exactly.

**Product connection.** `product/` defines the wire format by which
Anicca product events become ManagerBench cases
(situation → stimulus → measured response): the intervention-case
schema v1 (copied byte-identically from the ManagerBench harness), a
converter from app event exports, and a validator. Fixtures round-trip
through both our validator and the ManagerBench checker
(`check_intervention_cases.py`: cases=3, invalid=0). Real product cases
today: **0** — the app does not yet export `delivery_id` +
`assigned_probability`; that wiring is specified in
`product/case-format.md` and handed to the app lane (record §5).

## 3. Results

Eval rows: n=1,000. ATE on eval rows: 0.0455. Random targeting:
mean Qini −0.0070, p95 **0.0715**.

{{RESULTS_TABLE}}

{{RESULTS_INTERPRETATION}}

## 4. What we conclude

- The circuit is real: intervention data → post-training → a
  preregistered uplift eval → a product case format, all executable
  from this directory. That circuit — not any single score — is the
  v0 deliverable, because every later version plugs into it.
- A 135M model with 2,000 SFT rows is, at best, in the same band as a
  logistic-regression T-learner on this task. Nobody should read more
  into v0 than that; the preregistered gate, not enthusiasm, decides
  what gets promoted.
- The binding constraint is now product data: Manager cannot learn
  from Anicca until the app exports deliveries with assignment
  probabilities. That is an app-side change, specified and handed off.

## 5. Feedback — explicitly requested

This is published to be criticized. If you work on uplift modeling,
behavior models, or eval design, we want your objections: open an
issue or PR at https://github.com/Daisuke134/anicca (directory
`models/manager/v0`). Reproduction: `DATA_CARD.md` (data),
`MODEL_CARD.md` (training + eval commands). If your numbers differ
from ours, that is exactly the report we want.

Run record with primary sources (commands, hashes, URLs, blockers):
anicca-ops `files/manager-v0-start-2026-11-14.md`.
