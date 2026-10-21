---
title: "EBA: A Benchmark for Evaluating Whether AI Actions Actually Help"
subtitle: "From LLM graders and behavioral simulators to causal effects, welfare outcomes, and safe recursive improvement"
author: "Daisuke Narita / Manager Research"
date: "2026-10-22"
language: "en"
status: "Open research proposal + runnable synthetic v0, not peer-reviewed"
source: "https://github.com/Daisuke134/life-manager/tree/research/manager-product-r006-20261020/products/manager"
---

# EBA: A Benchmark for Evaluating Whether AI Actions Actually Help

*An open research proposal for AI laboratories, behavioral simulation companies, founders, researchers, and people who need AI to improve the environments they live in.*

## Abstract

Artificial intelligence is increasingly capable of generating programs, operating a browser, and simulating human decisions. But a system that reproduces what people say is not necessarily able to predict how they react to an intervention; and an agent that completes an action has not necessarily improved a person's life.

We propose **Evaluation of Beneficial Actions (EBA)**: a **modular evaluation protocol**, not a new claim that suffering can be reduced to one universal number. Its purpose is to separate (1) predictive fidelity, (2) causal intervention fidelity, (3) agent execution and authority, (4) human welfare and externalities, and (5) improvement under a fixed, independent evaluation system. EBA-v0 is an MIT-scoped original **fictional data and software demonstration**, hosted in the [Manager GitHub repository](https://github.com/Daisuke134/life-manager/tree/research/manager-product-r006-20261020/products/manager/benchmarks/eba_v0). None of its labels or scores support claims of observed human effects or autonomous field intervention.

The long-term hypothesis is that progress toward useful, generally capable AI should be tested on what changes in the **world**, not just what a model **says**. That claim has to be experimentally investigated, not assumed.

## 1. Evaluation versus benchmark: the simplest distinction

An **evaluation** is a measurement procedure for a specified system and purpose: task, population, dataset, environment, grader, score, uncertainty, and decision rule. A **benchmark** is a reusable, versioned *agreement* about those elements that supports meaningful comparisons across models and teams.

- A unit test checking that an application never pays twice is an evaluation.
- A human reviewer examining a model's failures is an evaluation.
- A pre-registered controlled trial measuring service completion is an evaluation.
- A standard task suite, held-out protocol, baseline models, robust grading and comparable scorecards together constitute a benchmark.

A benchmark is not made scientifically valid by assigning a catchy name or putting JSON on GitHub. It must track the intended deployment distribution, defend its outcome measurements, define model access, prevent contamination, quantify sampling/measurement variation, and show that rankings generalize.

## 2. The industrial evaluation stack already exists; reuse it

The frontier AI community has developed many pieces. They are complementary, not substitutes.

**Anthropic / Lance Martin: realistic evals and hill climbing.** [Automating eval design and hillclimbing with Claude](https://claude.dev/blog/automating-eval-design-and-hillclimbing/) describes tasks sampled from real operation, improvement headroom without ambiguity, low grader/run variance, isolation from leaked answers and one-change-at-a-time improvements. Its `build-eval` skill develops a grader and baseline; `hillclimb` examines train failures, compares on a held-out split and reverts changes that overfit or regress. The paper is about optimizing an agent or application against useful measurements, not a proof that all optimization is safe. Keeping a sealed final test separate from reused development validation is essential: inspecting a holdout every round eventually turns it into training information.

**Anthropic / agents as state-changing programs.** [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) emphasizes the agent's trace, environment state, grader, task isolation and distinctions between grading the final world state and grading fluent text. EBA imports that discipline for external-effect evidence. A tool return saying `SUCCESS` is not an independent receipt; an account being debited is not evidence a beneficiary was helped.

**Hamel Husain and Antaripa Saha: evaluators need evaluation.** [How To Use Decision Models for Evals](https://hamel.dev/blog/posts/decision-model-evals/) (2026-10-20) studies 100 human-labeled apartment-leasing traces. At the initial 0.5 threshold, their F1 values included 0.84 for OpenAI Decisions, 0.80 for Liquid d1-ultra and 0.73 for Perplexity Decider. Importantly, these *particular labels and criteria* do not establish global model rankings. Their fivefold approach tunes classification threshold with training folds, checks precision/recall under required minimums, evaluates probability calibration (Brier and Platt scaling) and compares cost. A single cheap judge can supervise high-volume checks only if human disagreement, false-negative cost, threshold drift and calibration are measured.

**Browser Use: real cases and meaningful computer environments.** [rl-env-use](https://github.com/browser-use/rl-env-use) builds reinforcement learning/eval environments from web-mined cases and references Anthropic hillclimbing. Real-world derived tasks may expose time-cutoff leakage, labels appearing in the task, duplicated aliases crossing train/test, flaky web states or insufficient public rights. The repository's early open issues are reasons to audit each task, not evidence that it already solves these problems. EBA-v0 checks metadata dates and group isolation, while admitting that it cannot prove source text contains no future facts.

**METR: autonomy in difficult research tasks.** [RE-Bench](https://github.com/METR/ai-rd-tasks) evaluates agent ML research engineering on measurable tasks. A higher score is evidence about *that type of technical capability*; it is not a claim of human welfare. Research environments, time budgets, human comparisons and carefully verified rewards are transferable design patterns.

**UK AI Security Institute: shared infrastructure.** [Inspect AI](https://inspect.aisi.org.uk/) offers open evaluation execution and reporting scaffolding. It is a sensible runner to reuse for model calls, scoring and sandboxed agent traces. EBA should integrate through a thin adapter rather than invent a rival eval platform. Domain-specific data and causal protocols do not magically arrive with a runner.

**Google DeepMind: society-like sandboxes.** [Concordia](https://github.com/google-deepmind/concordia) models agents in interactive simulated environments. Agent episodes are valuable for controlled research into strategies, memory and multi-agent interactions. Credible fictional behavior is not proof that the environment predicts humans, and no simulated reward by itself establishes real-world causal benefit.

**Experiment/causal OSS.** [GrowthBook](https://github.com/growthbook/growthbook-python) can manage legitimate assignments, while [DoWhy](https://github.com/py-why/dowhy), [EconML](https://github.com/py-why/EconML), and established RCT/MRT statistics help estimate effects under explicit identification assumptions. EBA ought to invoke these specialized methods on valid data, not replace them with an LLM-provided certainty label.

## 3. What Aaru and Simile are solving — and what remains open

**Aaru:** The company describes a 2,993-question study of predicted *answer-share distributions* across 186 surveys, comparing variation to survey-to-survey reproducibility. See [Population simulation at the replication floor](https://aaru.com/publications/population-simulation-at-the-replication-floor-research). Different samples of real humans disagree; calling that disagreement the "replication floor" provides an empirical context for AI error. Still, the reported study focuses on univariate response distributions and not individual causal intervention effects. It is a **company report**, not an independent EBA replication.

**Simile:** Its research on [confidence in human behavior simulation](https://www.simile.com/blog/confidence) trains a model to estimate the TVD error of another model before the human ground truth arrives. It reports roughly 8,600 held-out questions and improvement in error-ranking AUROC from approximately 0.57 for basic metadata features to 0.73 for learned model activations. This illustrates the distinction between being *confident* and estimating how *wrong* a forecast is likely to be. It still measures errors in simulated population outcomes; not whether an intervention protects people.

**The causal gap:** [Li & Ji (2026)](https://arxiv.org/abs/2604.02458) warn that reproducing descriptive patterns need not preserve treatment-effect estimates. [Recent social-science experiment prediction research](https://doi.org/10.1038/s41586-026-10742-x) is valuable but still concerns particular datasets and has effect-magnitude generalization limits. Prediction and causal fidelity require different evidence streams. This is the major gap EBA is designed to make unignorable.

## 4. The formal unit of evaluation

Consider a population (G), person (i), environment state (S_t), action (a\in\{NO\_ACTION, a_1,\ldots\}), observation window (T), and predefined domain-specific welfare outcome (Y_{i,T}\). Its causal effect is not "did a user click a link?" but, in potential outcomes language:

[
\tau_G(a;T)=E[Y_{i,T}(a)-Y_{i,T}(NO\_ACTION)\mid i\in G].
]

The counterfactual outcomes cannot all be observed for the same person. Randomized assignment, appropriate measurement, handling of noncompliance/missingness and credible causal assumptions are what justify identifying an average effect. When treatment spills to neighboring people, those assumptions and estimands must change.

A different evaluation asks about **prediction** of the observed *distribution* (q) with predicted distribution (p):

[
TVD(p,q)=\frac12\sum_k|p_k-q_k|.
]

For binary-event calibrated forecasts:

[
Brier=\frac1N\sum_i(p_i-y_i)^2.
]

For a *synthetic* oracle effect (\tau^{*}_i) and model forecast (\hat\tau_i):

[
\operatorname{CausalMAE}_{synthetic}=\frac1N\sum_i|\hat\tau_i-\tau_i^*|.
]

The asterisk matters: simulation or a contrived oracle is not an observed real intervention effect.

For any proposed real action, evaluate its costs and externalities rather than only the positive outcome. A preregistered net-benefit estimand might include direct effects, harms, resource consumption, time, displacement, spillover and uncertainty **in separately interpretable units**. Monetary conversions or cross-domain weights require ethical and empirical justification; defaulting to one scalar "suffering score" invents a measure that does not exist.

## 5. Seven non-negotiable benchmark rules

**Realism and relevance:** realistic tasks, external constraints, abstention examples, out-of-distribution cases, consent limitations, cases where intervention is worse than doing nothing.

**Leakage control:** freeze observation/forecast time; do not allow published outcomes after the cutoff; isolate real individuals/studies/sites by group; quarantine similar paraphrases and aliases. Track model training cutoff and web retrieval freshness. Publish tests with a separate locked, independently held gold split.

**Grader calibration:** deterministic code for rights, budgets, receipts and hashes. For ambiguous text, claim-specific human-reviewed rubrics, blinded pairwise comparison, repeated-grader agreement, precision, recall, threshold and calibration curves. Never let evaluated model write its own gold standard.

**Uncertainty:** repeat stochastic agents; record seeds, version, effort, tools, time, tokens and environment; paired uncertainty intervals and minimum practical benefit. A 1% gain with a 5% run-to-run noise is not a win.

**Safety overrides leaderboard:** scope/consent violations, intrusive personal targeting, unauthorized transfers, hidden experimentation, unverified externally irreversible effects or fabricated welfare claims block deployment regardless of average score.

**Transparency with rights:** open the runner, schemas, toy cases, benchmark cards, source locators, and aggregate outputs under compatible terms. Publicly accessible human microdata or copyrighted questionnaires are not automatically redistributable. Real test gold can be sequestered by a stewardship process while its scoring methods remain auditable.

**External validity:** new people, site operators, countries, time periods, levels of income, abilities, and intervention families. Baselines must be evaluated under equal information budgets, not just in-sample.

## 6. How to build the v0 demonstration now

The [runnable EBA-v0](https://github.com/Daisuke134/life-manager/tree/research/manager-product-r006-20261020/products/manager/benchmarks/eba_v0) uses the existing Manager TVD/Brier code. Its only cases are fictional examples for four domains. Its test protocol rejects any overlap of train/test group IDs, sources dated after the forecast, outcomes dated before the forecast, invalid distributions, missing predictions, forged actions and claimed non-P0 proof. The deterministic report separates:
- mean TVD and Brier
- synthetic oracle causal MAE and regret
- number of forbidden actions and NO_ACTION choices
- per-domain scores
- **NOT_MEASURED** for real welfare, **null** for unknown participant counts, zero permission for real effects

A separate paired bootstrap computes an exploratory comparison interval on matched losses with sufficient repeated samples. It is a teaching implementation, not statistical validation of any real-world clinical or socioeconomic inference. There is no secret benchmark test set and no claim that this score ranks models.

## 7. Ways to change environments other than persuasion

Persuasion is only one potential action, and is frequently weaker or riskier than eliminating the reason someone needs persuading in the first place. We should evaluate at least:
- **Information architecture:** more understandable official-source navigation, accessibility, translations, clear evidence and eligibility guidance.
- **Removing administrative friction:** fewer broken forms, better handoffs, lower wait times, accessible completion workflows.
- **Infrastructure improvements:** indoor air quality, energy efficiency, noise, transit access, safe public spaces — only with site/operator rights.
- **Economic and institutional design:** rights-respecting subsidies, reminders users request, matching of support to eligible recipients, reduced transaction costs.
- **Coordination:** scheduling or allocation among authorized actors, elimination of avoidable conflict or duplication.
- **Optional choice support:** personal decision aids that explain consequences without targeting people using hidden psychological vulnerabilities.
- **Persuasion and reminders:** opt-in, transparent, withdrawable and suited to a validated task, never unchecked manipulation, coercion or fabricated pressure.
- **NO_ACTION:** always available, sometimes optimal when uncertainty or unintended harm outweighs possible benefits.

These are qualitatively different treatments. Their outcomes and ethical risks cannot be compared by a generic "number of clicks" reward. Where stakes are high, standing authority is limited, review and external monitoring remain necessary even if routine harmless optimization is automated.

## 8. Safe improvement, not reward hacking

An optimizer should be allowed to propose small changes to prompts, routing, task descriptions, sampling or choice of models in a **sandbox**. It cannot freely rewrite the scoring rubric, hidden gold, consent criteria, protection mechanisms or original outcomes.

Suggested loop:
1. Identify production-relevant failures in a lawful, de-identified learning set.
2. Classify the bug: lack of data, task ambiguity, solver capability, agent harness failure, grader error, true negative outcome.
3. Propose exactly one bounded patch; preserve the policy and evaluator versions.
4. Run representative training cases. Compare paired results; log cost, negative effects, groups, variance.
5. Compare to validation that the improver cannot see as examples. If validation does not improve beyond noise or safety regresses, automatically roll back.
6. Release *only* after predetermined rights and scope gates; keep final blind benchmark sealed for a preannounced one-time assessment.
7. Observe external results for a predefined follow-up window; count incomplete and harmful outcomes; stop or reverse if possible.
8. Update the hypothesis and publish both positive and null results. Model updates do not make previously published evidence stronger.

This is compatible with recursive optimization but **not** license for an unobserved system to experiment on vulnerable people without appropriate consent.

## 9. Can an evaluator report that suffering has ended?

Not in the universal sense. No finite set of observations can establish that all people, all animals and all possible future beings are free of every form of suffering. Suffering is multidimensional and partly subjective; measurement instruments have populations, language validity, administration constraints and blind spots. There are ethical disagreements about whose experiences count and how to weigh them.

A truthful practical alternative is **bounded and falsifiable claims**:

"Among the consented, measured population in these locations and months, program A versus NO_ACTION reduced the preregistered material-hardship measure by estimated \(x\) points, with CI [L,U], at cost C, observed harms H, attrition A, no known evidence beyond this study population, and public audit receipts."

If the CI includes zero, report inconclusive. If there are no actual observations, **NOT_MEASURED**, not zero suffering. If unknown populations exist, include coverage limitations. The moral goal may remain broad; empirical claims remain specific.

## 10. Minimum open research release package

For every benchmark task and version publish a machine-readable [dataset card](https://huggingface.co/docs/hub/datasets-cards), [model card](https://arxiv.org/abs/1810.03993) if a model is released, signed or hashed evaluation config, complete runnable runner in existing frameworks, code license, proven source rights, baseline, adverse-case suite, baseline confidence intervals, per-group metrics, error-analysis examples, limitations, and clear non-redistributable data boundaries.

For the eventual academic paper: report protocol and software version, preregistration, inclusion/exclusion, assignment and attrition, measurement validity, statistical identification, sensitivity analysis, comparator choices, negative outcomes, compute/costs, replication across settings and independent review. Avoid publishing participant-level mental health or financial records, even when technically accessible.

Aar u, Simile, Anthropic and METR illustrate pieces of the evaluation puzzle. EBA's contribution is to make the **transition from simulated competence to independently verified, net-beneficial action** explicit and testable. That contribution is a research hypothesis until sufficient evidence is collected.

---

### Reproducibility and limits

```bash
cd products/manager
python -m manager_core.eba_benchmark --check
python -m unittest discover -s tests -v
```

**Evidence status at release:** EBA-v0 is a fictional benchmark prototype (P0); the separate publicly published Manager support site has externally verified **artifact delivery only** (P2 artifact). Real-world beneficiary improvements, randomization and causal validation are **not measured**. None of the third-party results cited here was reproduced as an EBA result.

License: original benchmark code and synthetic cases scoped to the adjacent `benchmarks/eba_v0/LICENSE` and repository MIT provisions, not upstream third-party data.
