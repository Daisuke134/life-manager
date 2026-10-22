# Radiant: What Happens When a Synthetic Audience Becomes a Society?

*An evidence-first field guide to Artificial Societies, the human-behavior-simulation industry, and the limitations of predicting people. Updated 21 October 2026.*

Most AI survey demos ask a model to pretend to be a customer. Radiant asks a more ambitious question: what happens if those customers are grounded in observations of actual people, given coherent belief systems, and connected to one another before answering?

Radiant is the research product of **Artificial Societies**. Its promise is to make hard-to-recruit audiences—including senior executives, policymakers, institutional investors and specialist consumer groups—available for simulated surveys, follow-up interviews, and group discussions. The result is not a panel of newly interviewed human decision-makers. It is a model-generated research environment built from observations and assumptions. Understanding what it can and cannot establish is essential to anyone building with LLM-based behavioral simulation. [Official Radiant product](https://societies.ai/radiant).

![The evidence path from a model prediction to an independently checked real-world outcome](https://aniccaai.com/blog/manager/media/8b828c20d083053461c13a7afaa983829ecfaf22678d1d35e9b994ba84f0b64f.png)

*An original evidence-path illustration: a realistic simulation belongs at the beginning of an evidence chain, not the end.*

## The five user-facing research workflows

First, **Societies** lets a team inspect a networked simulated audience in two or three dimensions, filter by characteristics and choose which stakeholders it wants to study. The product page describes societies of 20–3,500 personas. A separate methods page describes 12–3,500, so even the documented minimum differs by page. Treat neither number as a timeless software limit.

Second, **Surveys** lets analysts create questions, run them across a society, and see simulated answers by population and segment. Third, **Interviews** lets the analyst ask a particular persona why it responded in a particular way, followed by more questions. Fourth, **Focus Groups** allows multiple personas to discuss a prompt, disagree, revise positions and produce an interaction log. Fifth, a **Research Assistant** reads across the project's simulated survey, interview and group outputs to create charts and summaries. The interface makes it possible to examine both counts and individual explanations. [Product walkthrough](https://societies.ai/radiant).

The examples are instructive. A demo about billing for an AI engineering agent shows 38% of simulated respondents preferring payment per resolved ticket, 31% preferring seats, 19% preferring time and 12% preferring a flat annual license. The follow-up interview reveals concerns about who defines a resolved ticket, whether reopened tickets are double-billed and whether monthly spend is capped. The focus-group demonstration stages a dispute about these terms.

**Those demo percentages are simulated outputs displayed on a product page, not an independently representative human survey.** The value of the example is the research workflow, not an established market share.

## The company’s technical architecture: five stages, several scientific commitments

Artificial Societies describes a proprietary pipeline rather than an open-source foundation model. [Its methods page](https://societies.ai/eval) explains that it begins with published research, commentary, reviews, anonymized social data and public records, including behavior from social networks and investment or voting contexts. Clients may add first-party data, which the company says it segregates within the EU and does not use to train its models. That data-governance policy is the company's account; a public website does not provide an independent privacy audit.

**Persona Genesis** maps observations into inferred belief systems using psychometric methods and validates the personas against prior behavior and audience benchmarks. **Society Assembly** groups those personas and models their connections and influence patterns. The **Simulation Engine** places them in a new scenario—pricing, communications, financial disclosure, or product design—and predicts their responses. The research platform then reports aggregate, group and persona-level results.

This is importantly different from sending a biography prompt to a generic LLM. But the precise model weights, learning procedure, graph construction and degree to which each persona matches real individuals are proprietary. A believable response explanation is not direct access to a human mind. Network dynamics also require validation beyond checking a final poll percentage. [Technical overview](https://societies.ai/knowledge/the-science-behind-artificial-societies).

## What do the published accuracy claims mean?

Artificial Societies reports **86% overlap between simulated and human answer distributions**, versus **67% for biography-prompted LLMs** and a **91% human self-retest reference**, in its January 2026 internal evaluation covering 1,000 real-world surveys. That is **distribution overlap**, not 86% accuracy at predicting any individual's consequential behavior.

The same report describes under 2% *self-contradiction* in persona answers, 89% internal coherence on related survey items and 93% open-response language richness. The company's label “hallucination” concerns inconsistencies in responses, **not** errors about outside-world facts or verified personal thoughts. These metrics test different things. [Company methodology and evaluation](https://societies.ai/eval).

In a newer October 1, 2026 comparison, the company reports using the same questionnaire inputs and scoring code with **2,796 represented respondents, 68,280 synthetic answers and seven human survey sources**. Its mean top-line **total variation distance (TVD)** was **0.08**, compared with **0.31** for the best of the nine benchmarked general-purpose LLMs. For the subgroup distribution test on the General Social Survey, it reports **0.063 versus 0.222**. It reports 1.4 percentage points of error in a question-wording experiment, versus 6.2 for the strongest comparison model on that measure. These are company-published results on specified survey tasks—not external confirmation of accurate real-world policy impact. [October evaluation](https://societies.ai/as-benchmark).

Why use TVD? For distributions \(p\) and \(q\) across response options, it is:

\[
\mathrm{TVD}(p,q)=\frac{1}{2}\sum_i |p_i-q_i|.
\]

A TVD of 0.08 means the simulated option proportions differ from the measured proportions in aggregate by that distributional distance. It does **not** imply an 8% mistake rate for predicting the private opinions of any particular person.

## The most important research contribution may be its 11-test framework

In the company-affiliated September 2026 preprint *Artificial Societies Benchmark: A Validation Framework for Synthetic Research* (arXiv:2609.30030v2), the authors divide eleven checks into three families:

| Validity family | Questions asked |
|---|---|
| **Internal** (4) | Do repeated, logically connected, paraphrased or perturbed questions reproduce human response patterns? |
| **Construct** (3) | Do related items, external criteria and separate latent traits relate as they do in human data? |
| **External** (4) | Do distributions, subgroups, individuals, randomized experimental effects and latent structures correspond to human observations? |

This matters because a model can be excellent on population averages but distort minority-group opinions or estimate the wrong direction or magnitude of an intervention's effect. A companion preprint, *Consequential Behaviour and Representational Fairness in the Validation of Synthetic Research* (arXiv:2609.27690), develops the argument that what respondents say is not automatically what they will do and highlights representational harms. The benchmark papers are preprints, not an independent demonstration that the commercial system always passes every check. [Eleven-test original preprint](https://arxiv.org/html/2609.30030) · [Companion study](https://arxiv.org/abs/2609.27690).

The team's earlier peer-reviewed paper, *Artificial intelligence chatbots mimic human collective behaviour* (British Journal of Psychology, online December 2024), describes a simulated online society of **33,299 chatbots** forming communities according to language and related content. That is empirical work on **homophily**, a particular group behavior. It does not independently validate every subsequent Radiant survey or make the platform a real-world causal policy evaluator. [Original study](https://doi.org/10.1111/bjop.12764).

## How does Radiant compare with Simile, Aaru, Expected Parrot and Concordia?

**Simile** describes a behavior foundation model trained on actual transactions and other observed behaviors alongside interviews, surveys and experiments. It validates predictions against held-out human outcomes and separately predicts expected distribution error using a confidence model. Its What-If Machine explicitly covers different products, prices and policies. Radiant should therefore not be credited with inventing scenario testing or being the only company to validate with people. [Simile What-If Machine](https://www.simile.com/blog/what-if-machine) · [Simile confidence research](https://www.simile.com/blog/confidence).

**Aaru** works on simulated market and population decisions and describes its own validation research; its method, target users and comparisons should be studied directly, not reduced to “generic LLM personas.” [Aaru](https://aaru.com/simulation).

**Expected Parrot's EDSL** is a programmable research-instrument layer. Questions, surveys, agents, models, scenarios and results can be manipulated and reproduced; the ecosystem also supports research involving actual human respondents. It is not necessarily a direct substitute for Radiant's finished corporate-audience product. [EDSL code](https://github.com/expectedparrot/edsl).

**Google DeepMind's Concordia** is an open framework for running entities in an environment whose Game Master resolves their actions and provides observations. It is a useful general-purpose simulation kernel, not a claim that a model's world-state changes happened outside a program. [Concordia](https://github.com/google-deepmind/concordia).

These companies, infrastructures and labs occupy different layers of a large field: who is represented; how people respond; how groups interact; which counterfactuals are plausible; and whether an intervention really helps.

## The question for Manager is not merely what they predict

Manager (Anicca) is a **research-stage project** aiming to reduce suffering through legitimate, general-purpose interventions. Its proposed path is:

**Public observation → competing hypotheses → behavioral modeling when useful → alternative interventions, including NO_ACTION → scoped authority → real execution → independent measurement → causal net-benefit analysis → accountable learning.**

The present distinction is a proposed product objective, not a proven commercial moat or a successful world-changing intervention. Manager has not demonstrated independently verified net improvements in welfare. Its HeartSteps investigation reported a real source-analysis discrepancy rather than falsely reproducing a randomized trial. A separate held-out dataset experiment used public daily bike-rental aggregates, not individual treatment effects.

A worthwhile next experiment would compare Radiant-style network-structured behavioral modeling, a basic frequency baseline and individual LLM persona prompts on a **rights-cleared human experimental dataset**. In addition to overall TVD, score subgroup accuracy, response-process stability and **error in the magnitude of actual randomized treatment effects**. Do not let a low TVD certify an unauthorized or ineffective real-world action.

The ambition can be enormous. The proof must be specific.

---

**Evidence categories:** Corporate product claims are attributed to Artificial Societies, Simile and Aaru. The 2024 homophily study is a peer-reviewed, narrower result. The 2026 11-test paper is an original preprint. None of those is a Manager-owned field intervention or proof that a simulated buyer actually purchased a product.
