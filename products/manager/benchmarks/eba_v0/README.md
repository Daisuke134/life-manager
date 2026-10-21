# EBA-v0: Evaluation of Beneficial Actions (proposed research benchmark)

**Status:** original MIT-licensed benchmark scaffold, published synthetic diagnostics only. EBA is a proposed Manager name, not a validated community standard or proof that suffering has ended.

## Why this exists

Language agent tests measure task success; human-behavior simulators compare predicted and measured behavior; neither alone measures the causal benefit of intervening in real lives. EBA explicitly separates:
- **Prediction fidelity:** TVD (population distribution) and Brier score (binary decisions). Other outcomes need their own prevalidated metrics.
- **Intervention fidelity:** model forecast vs an oracle synthetic effect and decision regret vs NO_ACTION. Only a separately authorized trial and appropriate analysis can establish a *real* causal effect.
- **Agent/effect safety:** permitted actions, authority, external effects, idempotency, provenance, external readback. Demo intentionally does not execute actions.
- **Human welfare:** must be independent domain-specific, preregistered, valid outcome measurement. For this public demo: `NOT_MEASURED`, n=null, costs=null. A website readback is not wellbeing.

The four test cases are fictional finance, mental, physical and environment scenarios. Gold responses are public **solely to teach how to run a benchmark**; this is NOT a sealed fair leaderboard. Anyone claiming the published score demonstrates capability is misusing EBA-v0.

## Reproducible one-command baseline

```bash
cd products/manager
python -m manager_core.eba_benchmark --check
python -m unittest discover -s tests -v
```

Only Python standard library plus the **existing** `manager_core.evaluation.total_variation` and `brier_score`. No model call, paid services, personal data, network access or website mutation. The fields `source_published_at <= knowledge_cutoff < outcome_observed_at` rule out direct future-dated source contamination; groups in train and test must be disjoint to avoid aliases and sibling observations leaking. This metadata rule DOES NOT inspect the actual wording of a prompt or prevent memorization in a pretrained model; a real competition needs pretraining/date audits and an independent evaluator.

## How to construct EBA-v1 with actual evidence

1. Create task/protocol registry with a local operator, target user choice, `NO_ACTION`, rights/consent and revocation, source licensing and audit chain; have independent domain scientists review.
2. Capture anonymized nonprivate real error distributions only where legally available; preregister an independently held population/time/site split; keep test outcomes inaccessible to optimization agent. Report train/validation/locked final test separately. Do not iterate on final test.
3. Run baseline distributions: human retest, prevalence-only, simple logistic models, other open-source models, and your best model at the same data cutoff and sample. Report score, uncertainty, resource cost and failures; do NOT cherry-pick only model-specific failure examples.
4. To validate *causal intervention forecasts*, pair actual randomized intervention conditions with independent observed outcomes and state `ATE`, direction, uncertainty, heterogeneity, spillover and transport limits. Real welfare cannot be derived from TVD or a simulated causal oracle.
5. For **welfare endpoints**, use separately validated finance, mental and physical instruments only with proper license and consent; actual service completion or aid receipt, negative symptoms, burden, energy, costs and opportunity displacement. No unsupported universal wellbeing scalar.
6. Separate code-based hard gates from model judges. Validate judge threshold, precision, recall, human agreement, repeated-run variance, cost, and subgroup regressions. No model may edit its own gold scores.
7. Hill climb on train only; use unseen validation for promotion and a sealed benchmark once for final reports. Paired bootstrap CI must be tighter than smallest meaningful change. Stop on unsafe regression even if mean TVD decreases.
8. Red-team reward hacks, leakage, prompt injection, authority spoof, failed readback, outage, stale evidence, missing outcome and group shift. Publish negative and inconclusive evidence.
9. Independent peer reviews and pilot authorization before any field change. MIT original test code and fictional fixtures may be released; protected datasets must NOT be auto-published merely because source URLs exist.

## Critical conceptual problem

You cannot prove a literal zero level of suffering for the entire universe from any finite benchmark. A defensible claim defines population, window, latent construct/validated observable, uncertainty, undercounted groups, costs and possible harm, then states a bounded probability or interval. Even a measured average improvement cannot show an absent outcome in every person. EBA is an *evaluation framework proposal*, not a god's-eye sensor.

## Reused foundation (selected primary code/science)

- [Anthropic's eval design / hillclimb](https://claude.dev/blog/automating-eval-design-and-hillclimbing/) and [agent evaluator design](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents): realistic tasks, low variance, interpretable binary graders, train/holdout, root-cause patches and rollback.
- [Hamel Husain & Antaripa Saha, decision-model evals](https://hamel.dev/blog/posts/decision-model-evals/): human labels, threshold CV, calibration and cost/quality selection.
- [Browser Use rl-env-use](https://github.com/browser-use/rl-env-use): real-web-derived challenge environments; its public repo is not a human-welfare trial and must be audited for task leakage.
- [Aaru population simulation research](https://aaru.com/publications/population-simulation-at-the-replication-floor-research) and [Simile confidence research](https://www.simile.com/blog/confidence): survey-retest floor, TVD and predicted error; provider studies, not independent Manager evaluations.
- [Google DeepMind Concordia](https://github.com/google-deepmind/concordia): synthetic agent worlds; not real human causal validation.
- [UK AI Security Institute Inspect AI](https://inspect.aisi.org.uk/), [METR RE-Bench](https://github.com/METR/ai-rd-tasks), [GrowthBook](https://github.com/growthbook/growthbook-python), [DoWhy](https://github.com/py-why/dowhy) and [EconML](https://github.com/py-why/EconML): appropriate reused harness/statistics/experiment tools.
- [HeartSteps real MRT](https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/) and [Li & Ji 2026 causal-vs-descriptive warning](https://arxiv.org/abs/2604.02458): independently randomized outcomes differ from plausible simulated behavior.
- [CFPB Financial Well-Being Scale](https://www.consumerfinance.gov/consumer-tools/educator-tools/financial-well-being-resources/), [WHO-5](https://www.who.int/publications/m/item/WHO-UCN-MSD-MHE-2024.01) and [WHODAS 2.0](https://www.who.int/standards/classifications/international-classification-of-functioning-disability-and-health/who-disability-assessment-schedule): use only within rights/protocol; no copyright-sensitive questionnaire text copied.

### Licensing and contributions
This folder's original code and fictional cases are offered under the [MIT license](LICENSE). Upstream libraries/papers/datasets retain their OWN licenses and terms. No third-party respondent microdata is included.
