# EBA: Evaluating Beneficial Action — From Agent Evals to Measuring Whether AI Actually Improves Lives

**An open methodology and working developer benchmark from Manager / Anicca — October 22, 2026**  
**Version:** 0.1 research proposal. **Scientific status:** no verified reduction in human suffering. **Code:** [EBA open-source harness](https://github.com/Daisuke134/life-manager/tree/research/manager-product-r006-20261020/products/manager/eba). **Example service:** [public official-support navigator](https://daisuke134.github.io/life-manager/manager-support/).

Artificial intelligence has become capable of writing software, operating tools and simulating aspects of human behavior. But these capabilities leave out the question that matters most: *did the system leave people better off, compared with what would have happened without it?*

This is the question behind **EBA — Evaluation of Beneficial Action**, the working name for a proposed family of evaluation protocols. The project is part of Manager, an independent research effort studying how AI could improve the environments people live within. The motivating direction is to reduce suffering, not merely generate revenue, obtain higher engagement, or generate an aesthetically convincing simulation.

The first EBA developer harness is already open-source. Its tasks are intentionally **synthetic**. This article explains why it exists, what it can measure, what it absolutely cannot yet measure, how its scientific methodology should evolve, and how others can reproduce and extend it. We invite falsification, alternative metrics and independent validation, not an unsupported claim to have solved human welfare.

## 1. Evaluation and benchmark are not synonyms

An **evaluation** is a particular act of testing a system against specific criteria: an input, an environment, one or more trials, a grader, and a result. Evals can be highly specialized and private. A production agent's "did we accidentally send an unauthorized message?" regression test is a useful eval even if nobody else uses it.

A **benchmark** is an agreed, reproducible evaluation *protocol* designed for meaningful comparison. It includes not only examples but eligibility, split construction, runtime constraints, allowed tools, units, scoring implementation, uncertainty, baselines, aggregation, audits and versioned releases. A dataset by itself is not a benchmark, and a leaderboard without contamination controls or error bars is not a reliable comparison.

Anthropic's [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) usefully distinguishes task, trial, grader, trajectory, final environment state, evaluation harness and agent harness. Agents are multi-step systems that modify state. Their final prose may differ from the actual outcome. EBA accordingly evaluates the *state* and the *beneficiaries*, never a model's unverified "I completed it" assertion.

For a medical-information navigator, an eval might check whether it links to a legitimate official resource. A benchmark might compare many such systems on the same representative situations. A real-world effectiveness study, however, needs more: did anyone obtain appropriate care, and did outcomes improve without unacceptable harms? The three evidentiary claims are different.

## 2. The frontier playbook: representative tasks, validated graders, honest hill-climbing

Lance Martin's September 2026 [Automating eval design and hillclimbing with Claude](https://claude.dev/blog/automating-eval-design-and-hillclimbing/) describes four useful properties: represent the application distribution, separate stronger models/greater effort when capability genuinely differs, leave attainable frontier headroom, and minimize run-to-run noise. Failure-based case mining must not accidentally capture only one model's unique weaknesses.

The article's `/claude-api build-eval` workflow prioritizes real retained production traces where lawful, bug reports, expert-created cases and carefully grounded synthetic cases. It validates graders against people, uses exact programmatic checks when possible, and examines raw traces rather than trusting aggregates. Its `/claude-api hillclimb` workflow tests constrained incremental changes against a development set without granting access to truly held-out answers.

For EBA, this implies:
- Construct *cases from mechanisms*, not merely today's model mistakes: an unknown funding right, contradictory provider readback, future-information leakage, populations hurt by a superficially popular change, and a rational reason for `NO_ACTION`.
- Grade an identifiable failure assertion, not "helpfulness 4/5" alone. Calibrate any learned judge against independent, blinded human labels.
- Run repeated trials and report paired confidence intervals, variance and infrastructure failures. Publish cost/latency alongside quality.
- Separate the harness under optimization from the scorer, oracle labels and sealed final cases. Agent-visible gold or a grader edited by the candidate is contamination.
- Make every mutation reversible during development and maintain a safe fallback. High model-eval scores do not self-grant production permissions.

Anthropic's [infrastructure-noise investigation](https://www.anthropic.com/research/infrastructure-noise) also shows why benchmark hardware, timeouts and operating conditions are part of the specification: environmental variation can appear to be model improvement.

## 3. Evaluate the evaluator: thresholds, calibration and expensive misses

Hamel Husain and Antaripa Saha's October 20, 2026 paper-like article [How To Use Decision Models for Evals](https://hamel.dev/blog/posts/decision-model-evals/index.html) compares specialized decision models on labeled apartment-leasing agent traces. Their example warns against assuming a 0.50 classification threshold is appropriate.

A grader with failure probabilities needs **precision**, **recall** and the cost of each mistake. If an evaluator misses an unauthorized action, a false negative may be far more consequential than an unnecessary review. In other domains, false positives can impose serious costs or delays. Optimize the threshold on training folds, test it on untouched folds and *never relax declared minimum constraints merely because none of the candidate models meet them*.

EBA's eventual judges require their own dataset cards and performance report: human-label agreement, inter-rater disagreement, class prevalence, sensitivity under distribution shift, calibrated Brier/log loss, cost, run variance, confidence intervals and systematic failure examples. A model judge may suggest a missing qualitative failure; it cannot manufacture real causal outcome evidence.

## 4. Simulation: reproducing behavior is not predicting interventions

Simulation companies make essential but limited contributions.

[Aaru](https://aaru.com/publications/population-simulation-at-the-replication-floor-research) reported strong population-distribution replication on thousands of survey questions in September 2026. [Simile's confidence research](https://www.simile.com/blog/confidence) models how likely simulated distributions are to diverge from observed survey answers; it compares probe-based estimates with embeddings and model fine-tuning. These are company-reported results under specific datasets and scoring definitions, not independent evidence that a new policy will improve lives.

[Generative Agents](https://arxiv.org/abs/2304.03442) motivates memory, reflection and planning; [Concordia](https://github.com/google-deepmind/concordia) supplies interactions between agents and game environments; [AI Economist](https://github.com/salesforce/ai-economist) explores policy design among economic agents; [AgentSociety](https://github.com/tsinghua-fib-lab/AgentSociety) expands multi-agent social simulation. These should be reused as appropriate research tools, not conflated into a validated digital twin of humanity.

A simulator can match baseline public opinion while predicting the *wrong change* when an intervention is applied. This is the central EBA challenge. We distinguish (1) population distributional fidelity; (2) longitudinal individual behavior; (3) calibration of forecasts; (4) **intervention-response fidelity** — how accurately it predicts outcomes across randomized counterfactual choices; and (5) observed **causal net benefit** once a real intervention is applied with a credible comparator.

On a randomized study with treatment `A`, reference outcomes `Y` and simulated potential responses, compare predicted and observed effects by population, horizon and intervention. Report the error distribution and intervals; do not simply compare two simulated worlds. Real identifiable effects require assumptions about randomization, no interference, missingness, time trends and spillovers. A synthetic counterfactual oracle is not a real randomized trial.

## 5. The EBA evaluation stack

We propose seven separate benchmark families rather than a single global leaderboard score.

**EBA-Forecast** tests binary outcomes and event probabilities with Brier or log loss, observed frequencies, calibration and reliability slices. A confident wrong forecast must be penalized more heavily than an uncertain one.

**EBA-Sim** tests population distributions using total-variation distance, Wasserstein distances for ordered outcomes, subgroup errors and overdispersion. Always disclose the sampling frame and whether model access included future labels.

**EBA-Intervention** compares predictions of *differences* under interventions, ideally with real trial contrasts and uncertainty. Use causal ATE/CATE error only when the ground truth is genuinely identified, and separately label pedagogical synthetic effects.

**EBA-Decision** tests policies for comparing alternatives, sensible abstention, budget and permission compliance, expected utility, tail-risk controls and honest uncertainty. `NO_ACTION` is mandatory; it may be optimal when the estimated net benefit is uncertain. Future versions must also measure *regret* from perpetually abstaining when safe action is known to be beneficial — without trading away the hard right to refuse.

**EBA-Execution** measures whether a bounded, legitimate instruction changes the external world as intended. Use external independent state, hash-linked receipts, idempotency, timeout and reconciliation. A publisher's own success log is never proof that a beneficiary's situation improved.

**EBA-Welfare** evaluates real people's negative affect, functioning, financial hardship, pain, security, freedom to act, service access and adverse events where appropriate and consented. It requires independent measurement and a credible counterfactual. Financial savings, cognitive burden and clinical wellbeing must not be collapsed into one unsupported universal score.

**EBA-Generalization** tests replication across different groups, places, operators and periods; model performance under distribution shift; spillovers; and whether improved average outcomes conceal harm to vulnerable subgroups.

A multidimensional report allows everyone to inspect which capabilities are strong, weak or unknown. A real-world safety violation is a veto, not a small deduction offset by an excellent prediction score.

## 6. How would we measure suffering?

This is both an empirical and ethical question. A definition of suffering cannot be entirely delegated to a model, company or a single culture. People may disagree about pain, meaningful effort, autonomy, goals and what counts as harm. We should publish these disagreements and use participatory governance, not resolve them by silently choosing a universal scalar.

Useful established sources include the [OECD Guidelines on Measuring Subjective Well-being, 2025 update](https://www.oecd.org/en/publications/oecd-guidelines-on-measuring-subjective-well-being-2025-update_9203632a-en.html), which distinguishes life evaluation, affect and eudaimonic dimensions, and [WHO WHODAS](https://www.who.int/classifications/international-classification-of-functioning-disability-and-health/who-disability-assessment-schedule), which measures functional disability. Financial wellbeing and material hardship need their own validated, context-appropriate endpoints. Any copyrighted or consent-restricted instrument requires its own licensing and administration rules.

For each domain `d`, population slice `g`, intervention `a`, comparator `a0`, and follow-up time `t`, define the direction and units of a preregistered primary outcome `Y(d,g,t)`. When lower means greater wellbeing burden, one causal quantity is:

```
ATE(d,g,t;a,a0) = E[Y(d,g,t) | do(a)] - E[Y(d,g,t) | do(a0)]
```

A negative estimate might support improvement **only** if identification is credible, the measurement represents something important, uncertainty is quantified and harms, costs, missing participants and displaced consequences are considered. It does not establish that "all suffering" declined.

A rigorous outcome packet needs a frozen baseline, population and denominator, informed opt-in where required, time window, natural unit, validated questionnaire or independently verifiable event, credible assignment/comparator, clustering and missing-data policy, uncertainty interval, adverse events, costs, effect heterogeneity, site context and external audit trail.

**Do not infer zero suffering from missing measurements.** In mathematical terms, a universal declaration would require coverage of essentially all affected people and sentient beings over relevant time horizons, a complete definition, no unobserved harm and near-perfect measurement. Such completeness is not presently achievable. EBA can report transparent *bounded improvements in specified outcomes* and the size of what remains unknown; it cannot honestly declare the universe free of suffering.

## 7. Interventions: changing environments is broader than persuasion

AI persuasion is an example of an intervention, not the default or necessarily safest one. **Changing the available choices or barriers can matter without changing anybody's beliefs.**

Consider multiple classes:

1. **Information architecture:** clearer official instructions, accessible navigation and accurate referrals.
2. **Administrative simplification:** fewer duplicated forms, reduced wait times, language access and simpler benefit eligibility pathways.
3. **Service availability:** more operating hours, reachable appointment slots, queue coordination, transport or distribution logistics.
4. **Resource allocation:** authorized changes to subsidies, staffing, supply and price or allocation rules, with spillover accounting.
5. **Physical environmental design:** energy, air, heat, noise and accessibility measures under genuine site authority.
6. **Opt-in guidance:** reminders, education, coaching, supportive conversational assistance and personalization with constrained data handling.
7. **Policy and institutional design:** legally approved rule changes, public feedback mechanisms and equitable infrastructure.
8. **Persuasive communication:** transparent, consensual messages with right to opt out; no covert profiling or manipulation of distressed people.

For every class, EBA should compare `NO_ACTION` with relevant alternatives, estimate effects and harms separately, and ask who benefits and who may be worse off. A message that raises click-throughs but increases anxiety or delays appropriate care is not a demonstrated benefit.

The [GOV.UK service-design manual](https://www.gov.uk/service-manual/design/introduction-designing-government-services), [Code for America's GetCalFresh history](https://codeforamerica.org/news/reflecting-on-10-years-of-getcalfresh/) and [J-PAL's SNAP enrollment experiment](https://www.povertyactionlab.org/evaluation/impact-informational-mailings-snap-enrollment-united-states) illustrate why friction reduction and actual service access are promising targets. Their outcomes and contexts do not transfer automatically to Manager.

## 8. Recursive self-improvement: two loops, never one unconstrained reward

An eval-driven optimizer can legitimately improve its **software**, but it must not self-certify its **authority** or its own welfare effects.

The **engineering loop** uses versioned training cases, a human-calibrated or deterministic grader, candidate prompts/configurations, repeated paired runs, a validation set, hard safety regressions, cost/latency constraints and rollback. It can operate frequently with limited autonomy over an explicitly bounded software surface. Changes that affect graders, reward definitions, datasets, held-out cases or safety policies require a separate governance route.

The **field-evidence loop** begins only after a preauthorized, ethical protocol: consent where applicable, an agreed population and no-action control, bounded rollout, independent outcome observation, prespecified stopping rules and statistical analysis. It should not optimize unmeasured mental states, covert persuasion or vulnerable populations without human scientific and ethical oversight. Retain harm reporting even when average benefit is positive.

A useful conservative selection order is **hard legitimacy and safety constraints**, then credible beneficiary benefit, then cost-effectiveness, then convenience and latency. Unknown evidence blocks efficacy claims. This is a constrained optimization problem, not unrestricted reward maximization.

An important distinction from classic hill-climbing: a one-point score increase may fall inside ordinary run noise. Require paired differences, confidence intervals and enough replicates. When repeated comparisons accumulate, manage multiple testing and sequential peeking. Prevent agents from discovering and memorizing hidden gold answers, changing metric weights in their favor, or selectively showing only the best run.

## 9. Why existing benchmarks cannot already answer EBA's question

[Sierra's τ²-bench](https://github.com/sierra-research/tau2-bench) tests agent-task completion with environment and policy constraints. [Browser Use's rl-env-use](https://github.com/browser-use/rl-env-use) mines outcome-gradable cases from the public web to train or evaluate agent behavior. [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) provides transparent evaluation mechanics; [Hugging Face LightEval](https://github.com/huggingface/lighteval) provides broad LLM benchmarking capabilities. They should be used, not rewritten.

But a strong travel-booking or browser-completion score does not prove a population-level improvement in health, material security or agency. EBA would connect *task completion and simulation quality* to independently verified *effects on beneficiaries*. The novel research problem is the evidence linkage and its limits, not inventing another generic grading framework.

We also need to compare two different risks: **simulation error** (we predicted the intervention would work and were wrong) and **execution error** (we predicted the right intervention but failed to deliver it). A third risk is **value specification error** (our selected outcome was not what mattered to people). EBA should distinguish all three.

## 10. What is already runnable

The first version of EBA in [Manager's public repository](https://github.com/Daisuke134/life-manager/tree/research/manager-product-r006-20261020/products/manager/eba) is a zero-new-dependency Python harness using Manager's existing Brier and TVD calculations. It defines a strict public synthetic suite schema, a matching candidate submission schema, separated grading, by-domain outputs, safety vetoes, `NO_ACTION`, `UNKNOWN` for missing independent readback and a restricted shadow-only candidate selector.

Example:

```sh
cd products/manager
python3 -m eba
python3 -m unittest discover -s tests -p 'test_eba*.py' -v
```

The public fixture uses hand-written toy outputs across four domains. It does not evaluate Claude, GPT or any named simulator, and its publicly visible oracle cases must not be scored as if they were sealed research holdout. Its synthetic scores are **P0 development checks**. Its output always says `human_welfare: NOT_MEASURED`, `verified_causal_effect: false`, and `field_deployment_authorized: false`. All benchmark software inherits the [repository's MIT license](https://github.com/Daisuke134/life-manager/blob/research/manager-product-r006-20261020/LICENSE); third-party papers, surveys and data retain separate rights.

Manager separately [published a public official-support directory](https://daisuke134.github.io/life-manager/manager-support/) with six accessible HTML pages; its content was externally read back and verified. That is a genuine online environment change, not a claim of any user's wellbeing improving. The benchmark currently does not run field trials or send messages to beneficiaries.

## 11. The research roadmap and minimum criteria for a meaningful EBA release

**Stage A — Reproducible developer benchmark:** strict schemas, original synthetic cases, separated metrics, adversarial tests, open runner, pinned runtime, CI and baseline model traces. Current v0.1 completes a limited implementation, not the whole stage.

**Stage B — Real observational calibration:** legally reusable empirical datasets, source and license inventory, immutable train/dev/test splits, human and automatic grader calibration, drift/variance reports, subgroup errors and baselines. Claims remain observational unless causal identification supports more.

**Stage C — Intervention-response validation:** genuine randomized or otherwise defensible treatment/control studies, simulated forecasts frozen before real outcomes, intervention-effect error and decision regret on untouched data, explicit failures and negative effects.

**Stage D — Safe bounded field deployment:** actual operator authority, voluntary participation and protections as appropriate, documented legitimate decision rights, signed/independent receipts, expenses, adverse event stop conditions and independent outcome readback.

**Stage E — Causal benefit and replication:** preregistration, sufficient powered cohorts, effect estimates with uncertainty, heterogeneous harms, external replication by other researchers, independent audit and open peer criticism.

**Stage F — Sustained improvement and public accountability:** continuous monitoring for reversals or displacement; shadow challenger evaluations; standing governance with revocable limited capabilities; stable published benchmark versions, full uncertainty and negative result archives; public research reports, conference talks, and a methods book.

Even at Stage F, *an end to suffering everywhere* is a motivating ideal, not a scientifically verified binary condition. For any claim, ask: *whose suffering, which construct, in which domain, where, when, compared with what, measured by whom, under what uncertainty and with which harms?*

## 12. Open contribution invitation

We invite AI labs, simulation researchers, behavioral scientists, causal-inference experts, public-service designers and independent auditors to contribute **licensed cases, failure mechanisms, graders and independent validation protocols**, not restricted participant data or unverified efficacy claims. Contributions need a source locator, explicit reuse rights, construct validity explanation, leakage review, affected population, uncertainty and reason for inclusion. If a benchmark version is saturated, expand the science—not simply adversarially invent artificial problems that nobody encounters.

**Success for this research program is not a triumphant leaderboard entry. It is a chain of evidence that survives external scrutiny: an AI identified a modifiable environmental barrier, predicted alternatives, selected an authorized safe action, actually delivered it, and independently demonstrated a net benefit relative to a credible comparator — with the negative cases visible too.**

### Primary sources and reusable implementations

1. [Anthropic — Automating eval design and hillclimbing with Claude (2026)](https://claude.dev/blog/automating-eval-design-and-hillclimbing/)
2. [Anthropic — Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
3. [Anthropic — Infrastructure noise in evaluation](https://www.anthropic.com/research/infrastructure-noise)
4. [Hamel Husain & Antaripa Saha — How To Use Decision Models for Evals (2026)](https://hamel.dev/blog/posts/decision-model-evals/index.html)
5. [Browser Use — rl-env-use](https://github.com/browser-use/rl-env-use)
6. [Aaru — Population simulation at the replication floor (2026)](https://aaru.com/publications/population-simulation-at-the-replication-floor-research)
7. [Simile — Building confidence in Simile (2026)](https://www.simile.com/blog/confidence)
8. [Generative Agents (Park et al.)](https://arxiv.org/abs/2304.03442)
9. [Generative Agent Simulations of 1,000 People (Park et al.)](https://arxiv.org/abs/2411.10109)
10. [Google DeepMind — Concordia](https://github.com/google-deepmind/concordia)
11. [Salesforce — AI Economist](https://github.com/salesforce/ai-economist)
12. [AgentSociety](https://github.com/tsinghua-fib-lab/AgentSociety)
13. [Sierra — τ²-bench](https://github.com/sierra-research/tau2-bench)
14. [UK AISI — Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai)
15. [Hugging Face — LightEval](https://github.com/huggingface/lighteval)
16. [OECD — Guidelines on Measuring Subjective Well-being, 2025 update](https://www.oecd.org/en/publications/oecd-guidelines-on-measuring-subjective-well-being-2025-update_9203632a-en.html)
17. [WHO — WHODAS](https://www.who.int/classifications/international-classification-of-functioning-disability-and-health/who-disability-assessment-schedule)
18. [GOV.UK — Designing government services](https://www.gov.uk/service-manual/design/introduction-designing-government-services)
19. [Code for America — Reflecting on ten years of GetCalFresh](https://codeforamerica.org/news/reflecting-on-10-years-of-getcalfresh/)
20. [J-PAL — Impact of SNAP informational mailings](https://www.povertyactionlab.org/evaluation/impact-informational-mailings-snap-enrollment-united-states)

**Evidence note:** This methods proposal does not imply endorsement, licensing of source datasets, a validated universal welfare index, actual participants, or proof that Manager has reduced distress, poverty or illness. All company-reported performance is attributed to its publisher, not independently replicated by EBA v0.1.
