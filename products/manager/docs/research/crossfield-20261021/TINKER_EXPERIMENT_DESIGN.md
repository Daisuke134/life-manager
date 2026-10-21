# Manager Model Post-Training Decision — Tinker vs TRL, not reinventing the wheel

**Date:** 2026-10-21. **Stage:** training proposal, **NO training job, checkpoint, spending, private dataset acquisition or inference deployment executed**.

## Research-based decision

Primary sources:
- [Thinking Machines Lab Tinker](https://thinkingmachines.ai/tinker/)
- [Official Tinker quickstart SFT/RL](https://tinker-docs.thinkingmachines.ai/tinker/quickstart/)
- [Tinker model availability and prices](https://tinker-docs.thinkingmachines.ai/tinker/models/models_and_pricing/) — dynamic; consult at run time
- [Tinker official recipe repository](https://github.com/thinking-machines-lab/tinker-cookbook)
- [Hugging Face TRL](https://github.com/huggingface/trl) and [LoRA/QLoRA/GRPO](https://github.com/huggingface/trl/blob/main/docs/source/peft_integration.md)
- [Simile trained confidence-model explanation](https://www.simile.com/blog/confidence)
- [Socrates original human-behavior finetuning](https://aclanthology.org/2025.emnlp-main.1530/)
- [Manager Phase04 limitations](../socsci/PHASE04_REAL_210_STUDY_COUNTS.json) and [current Phase05 code](../../../manager_core/forecast.py)

### Service boundaries

Tinker is a **managed distributed-training API**; our machine may execute the Python loop and evaluate data locally while Tinker performs gradient updates and sampling on its own hardware. Its documented primitive operations are `sample`, `forward_backward`, `optim_step`, `save_state`; it supports SFT and reward-based RL on supported open-weight base models using **LoRA**, not arbitrary unrestricted full-weight training. The platform can export the resulting weights/adapters subject to underlying model and dataset licenses. The model catalog includes Qwen families, but IDs, availability and token prices change. Tinker itself is a proprietary hosted service, so using it is not equivalent to open-sourcing the full training stack.

Alternative: **Hugging Face TRL + PEFT** (open-source, local/cloud GPUs, SFT/GRPO). The decision is about infrastructure cost and control, not the idea that one magically yields scientific causal fidelity. Reuse a pinned official cookbook instead of writing gradient code from scratch.

## What Simile taught that we can reproduce responsibly

Simile's [confidence article](https://www.simile.com/blog/confidence) evaluates whether a model can predict **its own distribution error** on unseen questions, using basic features, text embeddings, hidden-state probes and continued finetuning of Qwen3.5-27B. A score of `0.736 AUROC` is *a method's ability to discriminate low/high TVD error under the authors' specific held-out evaluation*, not a calibrated estimate of an action's causal improvement. Aaru likewise predicts per-question TVD and can abstain based on confidence but uses a different evaluation dataset, making its raw AUROC not directly rankable against Simile.

A faithful Manager reproduction requires **question text, answer options and population definition preserved**. Our older global 12-code SocSci210 prior cannot be converted into valid response semantics merely by swapping to Qwen. First rebuild safe source adapters with rights review and condition-aware labels. Some respondent-level use licenses prohibit unrestricted redistribution or model training; consent and source-specific conditions apply even to a public URL.

## Four *distinct* training/evaluation problems

| Track | Model input → output | Baseline | Immutable score | Data evidence gate |
|---|---|---|---|---|
| T1. Behavior | population+condition+question+named options → normalized response distribution | train-frequency, majority, logistic head, original frozen MiniLM | TVD/Brier/MAE, calibration by unseen-study, repeated time holdout | real meaning-preserved human answer fractions, rights allowed |
| T2. Error confidence | T1 task+prediction+embedding → estimated future TVD/risk | simple entropy/regression, fitted embedding probe | heldout RMSE; AUROC(error beyond prereg threshold); coverage vs observed TVD | disjoint task/study partition, no use of scored target outcome |
| T3. Causal-effect estimate | action vs NO_ACTION + valid randomization/comparator → predicted effect distribution | trial mean, hierarchical model, OPE IPS/DR | ATE error, CI coverage, overlap and ESS, negative effects separately | actual valid treatment assignments; no faked do-operation |
| T4. Agent safety/operations | bounded task trace → next legal action or abstention | Phase05 deterministic authority/outbox/state machine | replay safety, grant violations=0, idempotency, rollback, latency/cost | synthetic/controlled sandbox only; no self-issued permissions |

**Do not train one optimizer against a combined "better world" scalar.** Until observed human P3/P4 data and a credible experiment exist, rewards for causal welfare are unknowable. Training to satisfy unit tests on synthetic utility numbers teaches benchmark gaming, not alleviating suffering.

## Minimal genuine experiment: cheap first, then paid training only after usefulness

1. **Dataset clearance:** snapshot exact original license, study IDs, population, date, counterfactual and response choices. Sensitive data should not leave authorized research environment. If unsupported: HOLD/ABSTAIN.
2. **Split freeze:** study-disjoint train/development/test; separate temporal and population out-of-distribution groups, anti-leak checks. No reward/test contamination, store locked hash, source origin and subgroup sizes.
3. **Start cheap:** deterministic probabilities; majority, train-frequency, MiniLM/linear logistic baseline; choose fixed training/eval budget with cost and carbon/compute accounted for.
4. **Qwen3.5-4B candidate:** use a supported model revision if current; adapt only via LoRA. Compare SFT with same data and SAME holdout; reject if invalid numeric answer rate, calibration or negative-case failures worsen.
5. **Error-model candidate:** use already-generated T1 heldout development predictions, train scalar/rank error estimators as separate models; **seal heldout test until final evaluation**. Compare entropy + embedding probe before costly model fine-tuning.
6. **Optional RL:** train **only** on controlled environments with independently machine-verifiable safety/calculation rewards, e.g., verifying source links, choosing NO_ACTION under forged grants, maintaining budget, truthful failure reporting. Start with published [Tinker RL recipe](https://github.com/thinking-machines-lab/tinker-cookbook/blob/main/tinker_cookbook/recipes/README.md) or [TRL GRPO](https://github.com/huggingface/trl). An RL environment cannot grade "decreased poverty" from model-generated text.
7. **A/B shadow test:** compare candidate against frozen baseline on identical unseen studies; preregister non-inferiority safety gates and meaningful improvement; no training/checkpoint promotion merely for prettier rationales.
8. **Reproduce and publish:** version, model license, data terms, code, prompts, cost receipts, heldout splits, failures, subgroup/OOD, SHA, model card and adapter weights **only where distribution permitted**. Keep private individuals out of public Git. Reject unsafe update or roll back to earlier version.

### What a Phase05/06-linked training interface might look like

```python
# PSEUDOCODE: no API key, no live model call.
task = {
    "population": "Publicly aggregated eligible cohort",
    "scenario": "Existing public conditions with one intervention option",
    "answers": ["A", "B", "NO_ACTION"],  # only if genuinely valid action space
    "source_snapshot": "sha256:...",
    "study_split": "unseen-study-locked"
}

# 1. Behavior forecast must be evaluated on actual human outcome data.
prediction = behavior_model.predict_distribution(task)
calibration = error_model.predict_tvd(task, prediction)

# 2. Separately obtain a scientifically defensible causal effect estimate.
causal = randomized_or_valid_ope_estimator(task)  # may return UNKNOWN

# 3. Phase05 kernel's authorization and idempotence cannot be skipped.
if calibration.is_unreliable or causal is UNKNOWN:
    option = "NO_ACTION"
else:
    option = policy.choose_including_no_action(task, causal)

# 4. Do not give RL a fake reward for having predicted successfully.
assert field_benefit_status == "NOT_MEASURED"
```

**Tinker call names are documented, but pseudocode above is an architectural sketch, not runnable Tinker SDK code.** For actual Tinker use, copy/version the maintained official Python recipe, use a dedicated training credential and expense limit, and keep it independent from Manager runtime, Life Manager, financial accounts and donor profiles.

## Explicit stop / promotion criteria

- **T1/T2:** compare same test studies and exact semantic answer spaces; no pooled cross-version different cohort leaderboard. Publish negative/null performance.
- **T3:** if effect support assumptions fail, no policy deployment even with low Brier or great TVD.
- **T4:** any forged grant, unsafe external action, privacy breach, wrong budget, duplicate effect or undocumented overhead = reject candidate.
- **Cost:** no paid training without current model pricing, total expected train/sample token budget, max spend, permitted dataset use and reproducible expected improvement. If no quality advantage over baseline, cancel the training track.
- **Open source/weight promise:** source code, training recipes, schema and earned rights-cleared model adapters can be open; an unavailable vendor foundation model or closed raw data must be explicitly labeled as such. "Open weights" never implies open training data.
