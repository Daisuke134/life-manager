---
title: "A Map of AI Evaluation: 90 Benchmarks and the Missing Measure of Human Benefit"
subtitle: "From coding and browser agents to human simulation, causal science and EBA"
author: "Manager Research / Anicca"
date: "2026-10-22"
status: "Open research synthesis / public article draft; not peer reviewed"
language: "en"
---

# A Map of AI Evaluation: 90 Benchmarks and the Missing Measure of Human Benefit

*An accessible, primary-source guide to the evaluation systems that already exist, what their code really tests, and what we still cannot measure.*

Imagine that two AI agents try to help people find public support. One writes a convincing answer. The other changes a confusing website so users can navigate official assistance with a keyboard and screen reader. Which agent helped more?

A language model judge might prefer the first answer. A software engineering benchmark might award the second agent full marks for passing tests. A browser benchmark might verify the updated page exists. None of these alone can establish that users received aid, avoided wasted time, or experienced improved mental or financial wellbeing. That requires observations of relevant human outcomes, comparison with what would have happened without the change, and accounting for costs, harms and uncertainty.

This is why we propose **Evaluation of Beneficial Actions (EBA)**: not another universal leaderboard but a set of connected evaluation protocols for prediction, intervention, agent execution and actual welfare. To see what needs to be built, we first mapped **90 existing systems in 14 families**. They include benchmarks, runners, datasets, simulation platforms, field studies and validated outcome measures. They should not be compared as though they shared the same ground truth.

This article is for engineers, founders, economists, psychologists and readers entirely new to AI. The full [source inventory](../evals/EVAL_LANDSCAPE_20261022.json) and [code audit](../evals/UPSTREAM_CODE_AUDIT_20261022.md) are open for inspection. Ninety means ninety selected, documented candidates, NOT all systems in the world or ninety benchmark executions.

## 1. Evaluation vs Benchmark

**Evaluation** is the process of measuring how a particular system behaves under a given task and conditions. It needs a target, a grader, an environment, a way to report uncertainty, and a use-specific decision rule. It can be a single regression test.

**Benchmark** means reusable and versioned evaluation tasks, comparable protocols, baselines, well-defined metrics, reference data and conditions. Its goal is to let more than one system be compared fairly. Benchmark quality depends on task realism, contamination protection and the validity of the target—not on the number of cases.

A **dataset** supplies examples, not necessarily a scientific interpretation or runner. An **evaluation harness** runs cases and graders, but cannot guarantee its labels are valid. A **simulation platform** supplies virtual world state and often artificial rewards. A **field study** can test real effects in a specified population under defensible research designs. A **validated outcome instrument** measures a human construct such as financial wellbeing; it does not create an RCT automatically.

Our 90-item atlas labels these types. That distinction alone prevents many misleading benchmark comparisons.

## 2. Knowledge and general reasoning: the classroom

[MMLU-Pro](https://github.com/TIGER-AI-Lab/MMLU-Pro), [GPQA](https://github.com/idavidrein/gpqa), [Humanity's Last Exam](https://lastexam.ai/), [LiveBench](https://github.com/LiveBench/LiveBench), [BIG-bench](https://github.com/google/BIG-bench) and [ARC-AGI-2](https://github.com/arcprize/ARC-AGI-2) test different aspects of difficult questions, abstract reasoning and generalization. They are useful prerequisites for capable agents. Their measured output is generally an answer, not a real-world intervention.

Even a perfect score here would not prove that an agent obeys a spending limit or makes anyone healthier. EBA should reuse these evaluations as capability diagnostics, never as welfare evidence.

## 3. Coding: when the world becomes executable

[SWE-bench](https://github.com/swe-bench/SWE-bench) tests whether agents repair real repository issues. [SWE-bench Verified](https://www.swebench.com/verified.html) is a human-filtered subset; harder variants including [SWE-bench Pro V2](https://labs.scale.com/blog/swe-bench-pro-v2) emphasize more difficult repository work. [SWE-Lancer](https://openai.com/index/swe-lancer/) focuses on realistic engineering tasks, [Terminal-Bench](https://github.com/laude-institute/terminal-bench) on terminal operations, [MLE-bench](https://github.com/openai/mle-bench) on machine-learning engineering, [LiveCodeBench](https://github.com/LiveCodeBench/LiveCodeBench) on fresher programming questions, and [DS-1000](https://github.com/xlang-ai/DS-1000) on data-science code.

An important lesson from the [actual SWE-bench grader](https://github.com/swe-bench/SWE-bench/blob/02e7a74ffd0b707aab73d203fe87bdc7c76afc8e/swebench/harness/grading.py) is that the grader must verify that tests actually ran. An empty result from a crashed test environment must not become a success. It also distinguishes fixing failing tests from breaking existing passing tests.

**Connection to EBA:** similarly, a financial-support link existing is not proof it was usable. A usable page is not proof a visitor found it. Finding it is not proof a person received a benefit. These are different evaluated events.

## 4. Web and desktop agents: the internet is part of reality

[WebArena](https://github.com/web-arena-x/webarena), [VisualWebArena](https://github.com/web-arena-x/visualwebarena), [BrowserGym](https://github.com/ServiceNow/BrowserGym), [WorkArena](https://github.com/ServiceNow/WorkArena), [Mind2Web](https://github.com/OSU-NLP-Group/Mind2Web), [Online-Mind2Web](https://github.com/OSU-NLP-Group/Online-Mind2Web) and [OSWorld](https://github.com/xlang-ai/OSWorld) challenge agents to operate software and reach target world states.

A subtle point is that old web tasks and live web tasks are not equivalent. The [Online-Mind2Web paper](https://arxiv.org/html/2504.01382v4) studies the gap between static test results and changing live sites. Environment version and task definitions are essential.

In [WebArena source](https://github.com/web-arena-x/webarena/blob/dce04686a56253aefba7b18a4fa0937cf1dc987b/evaluation_harness/evaluators.py), exact text matching, including required phrases, and fuzzy LLM matching are distinct. The evaluator receives a trajectory and browser state. Why score text with a vague language-model judge when an exact URL, database field or externally observed file can be checked deterministically?

## 5. Enterprise tool agents: correct words, correct actions, correct state

[τ-bench](https://github.com/sierra-research/tau-bench), [τ²-bench](https://github.com/sierra-research/tau2-bench), [TheAgentCompany](https://arxiv.org/abs/2412.14161), [ToolBench](https://github.com/OpenBMB/ToolBench), [Berkeley Function Calling](https://gorilla.cs.berkeley.edu/leaderboard.html) and [GAIA](https://huggingface.co/datasets/gaia-benchmark/GAIA) measure different forms of tool-based, business-like task completion.

Read [τ²-bench's evaluator](https://github.com/sierra-research/tau2-bench/blob/main/src/tau2/evaluator/evaluator.py). It separates ENV (database state), ACTION (tool calls), COMMUNICATE (user-facing communication), and optional natural-language assertions. A correct tool call need not produce the required database state, and a fluent answer need not reflect a correct action.

This is among the most directly reusable designs for Manager: measure the **message**, **action**, **external environment state** and **human consequence** separately. The first three are not substitutes for the fourth.

## 6. Long-horizon autonomy and research agents

[METR RE-Bench](https://github.com/METR/ai-rd-tasks) tests complex ML research engineering work; [METR time horizons](https://metr.org/time-horizons/) examines agents on tasks of different human-duration difficulty. [Andon Labs Vending-Bench 2](https://andonlabs.com/evals/vending-bench-2) measures simulated year-long business coherence; [Anthropic Project Vend](https://www.anthropic.com/research/project-vend-2) brings AI business operations into an actual physical shop. [BrowseComp](https://openai.com/index/browsecomp/) and [DeepResearch Bench](https://github.com/Ayanami0730/deep_research_bench) test hard information retrieval and long research reports.

A simulator's bank balance is fictional. A shop's real revenue is an observation. Revenue net of labor, fees, displacement and negative externalities is another result. A person's improved welfare is yet another. EBA must make those transitions explicit rather than claim that a simulated reward caused a human benefit.

## 7. Evaluation of the evaluator

AI judges must be graded, too. [JudgeBench](https://github.com/ScalerLab/JudgeBench) investigates the reliability of LLM evaluators; [RewardBench](https://github.com/allenai/reward-bench) tests reward-model preferences; [AlpacaEval](https://github.com/tatsu-lab/alpaca_eval) and [MT-Bench](https://github.com/lm-sys/FastChat) demonstrate answer ranking.

[JudgeBench's run_judge.py](https://github.com/ScalerLab/JudgeBench/blob/e2c52c284e735e139b3daa61c206ee208f36c461/run_judge.py) includes evaluation in both candidate answer orders. This is a straightforward test for position bias: does the judge prefer the first option for the wrong reason?

[Hamel Husain and Antaripa Saha's decision-model article](https://hamel.dev/blog/posts/decision-model-evals/) tests six graders on 100 human-labeled rental-agent traces. The authors recommend adjusting decision thresholds to the desired false-alarm/missed-failure tradeoff and testing calibration and cost. Their result is task-specific, not a global model leaderboard. A predicted 80% error probability should correspond to approximately 80% empirical failures in that score region.

For EBA, check a grader's human-label agreement, precision, recall, Brier/calibration, repeatability, swapped-order agreement and price *before* putting it in charge of automatic self-improvement.

## 8. Safety and attack resistance

[AgentDojo](https://github.com/ethz-spylab/agentdojo) separates user-task utility from prompt-injection security on the same scenario. [SHADE-Arena](https://www.anthropic.com/research/shade-arena-sabotage-monitoring), [AgentHarm](https://arxiv.org/abs/2410.09024), [HarmBench](https://www.harmbench.org/), [JailbreakBench](https://github.com/JailbreakBench/jailbreakbench) and [StrongREJECT](https://arxiv.org/abs/2402.10260) measure different harmful-activity and refusal vulnerabilities.

[AgentDojo's benchmark code](https://github.com/ethz-spylab/agentdojo/blob/089ed468cf3ed0322acc66b0211f26d9d90dbf60/src/agentdojo/benchmark.py) maintains utility and security result maps separately. This is what EBA needs: an intervention cannot become acceptable merely because its apparent benefit is large if it violates permissions, manipulates vulnerable people or fabricates records.

## 9. Human simulation: predictive accuracy is not causal fidelity

[OmniBehavior](https://github.com/icip-cas/OmniBehavior) evaluates next online actions, long-horizon trajectories and varied types of real-world user behavior. Its [metrics source](https://github.com/icip-cas/OmniBehavior/blob/main/src/evaluation/metrics.py) uses established scikit-learn log-loss, AUROC, F1 and regression metrics and treats single-class ROC-AUC as undefined.

[Simile's confidence research](https://www.simile.com/blog/confidence) predicts the total-variation-distance error of its human behavior forecasts using question features, embeddings or hidden-state representations. [Aaru's research](https://aaru.com/publications/population-simulation-at-the-replication-floor-research) compares simulated answer distributions against 2,993 published survey questions and reports a human-survey replication baseline. Both are company-reported studies, not independent EBA replications.

[Socrates](https://aclanthology.org/2025.emnlp-main.1530/), [Concordia](https://github.com/google-deepmind/concordia), [Generative Agents](https://github.com/joonspk-research/generative_agents), [OASIS](https://github.com/camel-ai/oasis) and [AI Economist](https://github.com/salesforce/ai-economist) represent still other approaches. A realistic fictional town, a good guess at survey proportions and a person's response to an actual government policy are different targets. We need separate validation before claiming a simulator predicts the effects of new interventions.

## 10. Causal models: what would have happened without the action?

An experiment measures a treatment's effect using comparable conditions and relevant outcome observations. It does not merely compare the people who chose to receive an intervention with those who did not. Randomization and other identification approaches are important because selection and confounding can produce impressive-looking but false impact.

[Open Bandit Pipeline](https://github.com/st-tech/zr-obp) implements real off-policy estimation interfaces for logged decisions. Its [estimators](https://github.com/st-tech/zr-obp/blob/8cbd5fa4558b7ad2ba4781546d6604e4cc3e07c4/obp/ope/estimators.py) make the logged-action and evaluation-policy relationship explicit. [DoWhy](https://github.com/py-why/dowhy) provides causal assumptions, estimation and refutation; [EconML](https://github.com/py-why/EconML) focuses on heterogeneous treatment effects. [Criteo Uplift](https://ailab.criteo.com/criteo-uplift-prediction-dataset/) supplies published treatment-response data with significant interpretation/rights caveats. [CausalBench](https://github.com/causalbench/causalbench) measures causal-graph inference in cell perturbations, while [CausalRivers](https://causalrivers.github.io/) evaluates time-series causal discovery.

These are *different tasks*. Recovering gene interaction graphs is not proof of a good public policy. A statistically good uplift model is not guaranteed to work in a new country, with a new treatment, outside the logged policy's action support.

## 11. Real interventions and meaningful outcomes

The strongest bridge toward human benefit is not another synthetic human but carefully designed field evidence. [HeartSteps](https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/) studied micro-randomized walking prompts and proximal steps. [Behavior Change for Good](https://pmc.ncbi.nlm.nih.gov/articles/PMC8822539/) compared 54 exercise interventions across more than 61,000 gym members. [J-PAL SNAP research](https://www.povertyactionlab.org/evaluation/impact-informational-mailings-snap-enrollment-united-states) examines real enrollment in food assistance. [GiveDirectly](https://www.givedirectly.org/2023-ubi-results) studies actual monetary transfers and recipient effects.

These researchers chose populations, interventions, comparators, observed outcomes, follow-up periods and study designs. We should reuse their *methods*, while resisting the temptation to claim that copying a web page or simulator creates the same effect.

Public digital environments matter. Removing inaccessible links, misleading information, excessive clicks and administrative friction can improve opportunities. Whether that translates into mental, physical or financial welfare must still be measured.

## 12. What does it mean to measure suffering?

There is no agreed single, all-purpose "suffering sensor." [WHO-5](https://www.who.int/publications/m/item/WHO-UCN-MSD-MHE-2024.01) measures mental wellbeing. [WHODAS 2.0](https://www.who.int/classifications/international-classification-of-functioning-disability-and-health/who-disability-assessment-schedule) measures functioning. [CFPB](https://www.consumerfinance.gov/consumer-tools/educator-tools/financial-well-being-resources/) measures financial wellbeing. [FAO FIES](https://www.fao.org/measuring-hunger/access-to-food/about-the-food-insecurity-experience-scale-%28fies%29/) measures food insecurity. [OECD guidelines](https://www.oecd.org/en/publications/oecd-guidelines-on-measuring-subjective-well-being-2025-update_9203632a-en.html) distinguish life satisfaction, feelings and meaningful functioning.

These instruments need correct language/setting validation, individual consent where applicable and respect for reproduction licenses. [MentalHealthBench](https://openai.com/index/introducing-mentalhealthbench/) instead evaluates the *quality and appropriateness of model responses*, not the real clinical outcomes of patients. It is a valuable benchmark—but fundamentally different from a treatment trial.

EBA should report mental, physical, economic, access and safety evidence with **their original units**, population coverage and uncertainty. A single universal number would require moral and empirical weights that we cannot silently invent.

## 13. The new connection: a five-layer evaluation rather than another leaderboard

EBA proposes five independent layers:

**Prediction:** Can the model predict behavior on valid, group- and time-held-out ground truth? Use TVD, Brier, log loss, RMSE, calibration and uncertainty models where valid.

**Decision:** With NO_ACTION among the alternatives, can it select an option with favorable expected effects and appropriate abstention, respecting risk and resources? Artificial oracle effects are labeled synthetic only.

**Execution:** Did the allowed action actually happen, once, with correct scope, verified external state, bounded cost and rollback? Use deterministic environment checks and distinguish missing evidence from failure or success.

**Welfare:** Did meaningful domain-specific outcomes improve compared to an identified counterfactual, with confidence intervals, costs, harms and spillovers? A person accessing a site is not yet proof of reduced suffering.

**Self-improvement:** Do changes to the model/prompt/policy help on truly unseen evaluations beyond variance, with regressions identified and changes reverted when necessary?

For operationalizing this, reuse [Inspect AI](https://inspect.aisi.org.uk/), [Browser Use's audit](https://github.com/browser-use/rl-env-use/blob/main/rl_env_use/audit.py), [τ²-bench's evaluator](https://github.com/sierra-research/tau2-bench), [GrowthBook](https://github.com/growthbook/growthbook-python), [Open Bandit Pipeline](https://github.com/st-tech/zr-obp), [DoWhy](https://github.com/py-why/dowhy) and original domain wellbeing measures. No need to invent their engines.

The open [EBA-v0 demonstration](../../../benchmarks/eba_v0/README.md) runs four fictional held-out cases, reports predictive error, artificial intervention regret, safe action violations and a strict human-benefit field of **NOT_MEASURED**. Its gold answers are public because it is an educational fixture. It cannot be promoted as an independent frontier leaderboard or a real-world clinical evaluation.

## 14. Recursive improvement without cheating

The [Anthropic eval design and hillclimbing playbook](https://claude.dev/blog/automating-eval-design-and-hillclimbing/) teaches small patches, accurate graders, heldout test splits, noise measurement, overfitting checks and rollback. The agent being improved must NOT rewrite its own evaluation cases, hidden answers, failure rules or human outcome definition. A final public benchmark should be evaluated once per declared version, not repeatedly inspected until it becomes training data.

A safe loop can run without per-action human supervision inside standing authority and a limited sandbox. It can improve a page or software, verify that the state actually changed, and compare against fixed validators. But experimenting on people about mental health, financial hardship or other personal outcomes requires appropriate voluntary participation and care. That is not the same as requiring a human to manually approve every ordinary software change.

## 15. What we still cannot honestly claim

Ninety catalog entries do not mean ninety benchmark implementations were cloned and executed. The selected code audit read original source files from nine+ projects. The cloned-code CI job is separately tracked; any clone result needs a real execution record. Published vendor benchmark claims are labeled as such and should not be compared across different datasets as a universal ranking.

No finite benchmark can verify that suffering has ended in the entire universe. What science can establish is a bounded claim: *for this measured population, during this window, under this intervention and valid comparison, this outcome changed by an estimated amount with this uncertainty, harm accounting and limited generalizability.* Missing human outcomes mean **NOT_MEASURED**, not zero.

## 16. Where to go from here

For AI labs: contribute realistic, de-identified cases and independent benchmark graders. For behavioral simulation teams: contribute results from genuinely held-out studies and actual treatment effects, not only plausible simulated stories. For causal researchers: bring randomized data, design assumptions and uncertainty. For public interest organizations: help define meaningful, consented, domain-valid outcomes. For startups: begin with an existing evaluation runner and a real problem before chasing a leaderboard score.

We will publish negative results and failures as prominently as successes; absence of improvement is an important measurement, not an embarrassment.\n\nOur next steps are to build a properly rights-cleared EBA dataset and versioned reproducibility package, integrate existing runner/adapters, preregister a true intervention protocol, and publish honest positive, negative and unresolved results. We will only upgrade human-welfare proof after actual externally observed results justify it.

**AI is becoming good at doing things. Its evaluations should become equally good at telling us what those things actually changed.**

---

### Reproduction, rights and corrections

- [Source atlas — 90 systems, 14 families](../evals/EVAL_LANDSCAPE_20261022.json)
- [Original pinned evaluator code audit](../evals/UPSTREAM_CODE_AUDIT_20261022.md)
- [Open EBA research proposal and methods](EBA_OPEN_BENCHMARK_ARTICLE_20261022.md)
- [EBA-v0 fictional runnable evaluation suite](../../../benchmarks/eba_v0/README.md)
- [Phase 06 and full-project completion plan](../../roadmap/EBA_TO_FIELD_COMPLETION_ATOMIC.md)

*Status: public educational research DRAFT saved in canonical Manager GitHub source. This text is not peer-reviewed. Its presence in GitHub is not confirmation of deployment to the production Anicca blog.*
