# What Simile predicts: human behavior, uncertainty, and evidence before intervention

Before changing a price, a payment interface, or a pharmacy experience, a team wants to know how people will respond. Simile builds simulations for those questions. Its clearest supported use is to compare possibilities early and decide where real research is most valuable. Predicting a response, however, is only one step toward showing that a decision improves lives.[1–2]

This explainer draws on public material reviewed through October 12, 2026. It is not a firsthand product test. Four achievements need separate treatment: believable fictional behavior, reproducing individuals’ answers, predicting population distributions, and estimating the effects of an intervention.

## The company and its ambition

Simile’s founders are Joon Sung Park, CEO; Michael Bernstein, Chief Data Officer; and Percy Liang, Chief Scientist. Its official website associates their work with generative agents and individual simulation, human-centered AI, and foundation models and rigorous evaluation, respectively.[1]

The business thesis is that AI makes products, campaigns, and scripts easier to create, shifting the bottleneck toward deciding what to build and for whom. Simile’s mission to simulate all eight billion people describes an ambition, rather than demonstrated coverage of every person or validation of every possible policy.[2–3]

Its July 30 Series B announcement reports raising over $200 million at a $2 billion post-money valuation. It also reports fivefold revenue growth, tens of millions of enterprise simulations, and a team exceeding 50 people. These are company-reported claims. The announcement supplies neither an audited revenue baseline nor ARR; its funding wording should not be silently expanded into an independently verified cumulative funding breakdown.[3]

## Start with distributions

A large language model learns from data to generate language. Asking a general model to “act as a banking customer” can produce a persuasive answer, but persuasion does not establish representativeness.

Simile’s August technical post describes a more measurable interface: specify a population, situation, and available actions, then receive a predicted distribution over those actions.[4] Consider an illustrative prediction: 50% stay, 30% switch providers, and 20% stop using the service. This example is not a Simile result.

Suppose real observations yield 40%, 40%, and 20%. Total variation distance, or TVD, measures the discrepancy:

\[
\operatorname{TVD}(P,Q)=\tfrac12\sum_i|P_i-Q_i|
=\tfrac12(0.10+0.10+0)=0.10.
\]

The division by two avoids counting the same probability mass once where it leaves and again where it arrives. Zero means matching distributions; one means no overlap. A TVD of 0.10 means moving ten percentage points of probability mass would reconcile these distributions. It does not mean 90% of individual people were predicted correctly.

Observed data are uncertain too. A sample is only a subset of the population of interest, and a larger sample does not automatically repair biased recruitment. Statistical confidence intervals describe estimation uncertainty under assumptions. Simile’s product confidence buckets instead concern a learned prediction of simulation error.

## What the model learns from

Simile says it combines transactions, app usage, clickstreams, mobility, surveys, AI-led voice interviews, and experiments.[4–5] Behavioral records constrain what people did; self-reports offer evidence about motives, habits, beliefs, and constraints. Their disagreements matter: a stated preference for sustainable products may lose to a budget constraint at checkout.

Self-reports are imperfect accounts, subject to framing, memory, and retrospective explanation. Combining sources allows cross-checking rather than treating one source as complete psychological truth.

Fine-tuning updates a pretrained model’s weights using additional data. The confidence post’s diagram identifies a Simile fine-tune of Qwen3.5-27B as the simulation model. The commercial behavioral-training loss, dataset mixture weights, total data volume, and precise linkage of observations about the same person remain undisclosed.[4] The published confidence-model loss therefore cannot be presented as the entire behavioral model’s training objective.

Bernstein’s example of a price increase disrupting a shopping habit illustrates a possible mechanism. It is not itself an experimentally identified causal result.[5]

## Four different research contributions

**Generative Agents, 2023.** Smallville contained 25 fictional agents. A memory stream stored observations; retrieval combined recency, importance, and relevance. Reflection generated higher-level interpretations linked to supporting memories. Planning decomposed schedules into actions and adapted to events.[6]

These components produced continuity beyond a single conversational turn. Evaluation concerned human judgments of believability and the effects of removing components. It did not establish calibration to a real population. Retrieval failures and invented embellishments were documented. Simile says these ideas inform its current product, but the published 2023 implementation is not evidence of identical commercial code.[1,6]

**Individual grounding, current v3.** The June 2026 version of “LLM Agents Grounded in Self-Reports” studied 1,052 US adults. GPT-4o received approximately two-hour English interviews, structured surveys, or both. Grounding means conditioning predictions on evidence about actual people; this was not per-person fine-tuning.[7]

The system also generated reflections from four expert perspectives. Those interpretations should be distinguished from participants’ own testimony.

For General Social Survey answers, interview-only agents achieved 65.67% raw agreement. Participants’ own two-week retest agreement was 79.53%. The study normalizes against participant-level retest consistency and reports approximately 83%; the ratio of these aggregate values is also close to 83%, but does not fully specify the participant-level aggregation. The often-quoted 83% is relative to human retest consistency, not absolute answer accuracy.

Survey-only grounding achieved 82% normalized accuracy, and combined grounding 86%. The interview-versus-survey difference was not statistically significant. Differences between agent types on incentivized economic games were also nonsignificant. These findings do not establish that interviews are uniquely necessary or that the GSS score transfers to every behavior. English-language US sampling and imperfect demographic representation further limit generalization.[7]

**Socrates, EMNLP 2025.** This public research trained models on reconstructed social-science experiments. SocSci210 contains 210 studies, 400,491 participants, and approximately 2.9 million responses. Supervised fine-tuning learns from observed responses; DPO adjusts outputs using comparative preferences. The methods differed in their strengths for population distributions and individual answer accuracy.[8]

The unseen-study evaluation trained on 170 studies and tested on 40. Socrates-Qwen14B reduced Wasserstein distributional error by 26.3% relative to its base model. Wasserstein distance accounts for the movement of responses along an ordered scale. The number is a relative error reduction, not 26.3% accuracy or a gain of 26.3 percentage points.

Reasoning traces generated with known answers are explanations produced by another model, not direct observations of participants’ psychological processes. Socrates’ public data, models, and code also do not make Simile’s current proprietary model public.[8]

**The commercial system.** Its important disclosed addition is a model that predicts simulation error alongside behavioral distributions. Results from fictional agents, individual grounding, and Socrates cannot simply be added together as a commercial-product accuracy claim.[4]

## Learning when a simulation may be wrong

True TVD requires human outcomes that are unavailable when a new question arrives. Simile trains a confidence model on comparisons between past simulations and human observations to estimate that error.[4]

The post describes roughly 8,600 evaluation questions held out from both simulation-model and confidence-model training. Confidence evaluation uses five-fold cross-validation: train on four groups, test on the fifth, then rotate. Question text and the entire associated experimental sample remain together, reducing leakage across training and evaluation.

Simple features such as option count and distribution shape provided weak signals. A stronger approach probes the simulation model’s hidden numerical representations. It reuses the same forward pass, without another model call. Another continues fine-tuning the simulation model with a scalar error-prediction head and RMSE loss.

That approach achieved RMSE 0.0776 versus the probe’s 0.0792. RMSE measures the size of discrepancies between predicted and observed errors. AUROC, which measures discrimination around an error threshold, was 0.736 versus 0.730; this difference was not statistically significant. Neither metric is individual behavioral accuracy.[4]

In the evaluation set, 95% of the “High” bucket had TVD below 0.16, compared with 38% of the “Low” bucket. The 0.16 threshold came from approximately 2,750 internal ratings by 14 raters. The company expects the definition to evolve with external raters and broader evaluations.

Thus “95%” does not establish 95% person-level accuracy or safe interventions. A close aggregate distribution can hide serious errors for a small group. Calibration under new countries, institutional changes, or long-term interactions needs separate evidence.

## What customer cases establish

CVS Health describes testing pharmacist access, waiting times, communication, refill intent, and service adoption. Simulation helps prioritize subsequent pilots.[9] Refill intent is not observed medication adherence or improved health.

The CVS whitepaper reports agreement with known historical results “up to 95%,” but does not supply the denominator, comparison count, agreement definition, or confidence intervals. The roughly 2.9 million responses and 400,000 participants overlap with academic research figures; they should not be portrayed as a newly interviewed panel consisting entirely of CVS patients.[9–10]

Itaú used customer-archetype-based simulations for Pix Automático, examining trust, comprehension, control, and adoption intent. It reports reducing a five-week research cycle to four business days and two-week concept exploration to under three hours. High confidence and population representation justified greater weight; lower confidence directed questions to human research. Researchers retained responsibility for framing, interpretation, and decisions.[11]

These are research-speed claims, not measured improvements in customer wealth or wellbeing. They provide a useful pattern for combining simulation with fieldwork.

## Sources and claim references

- [1] [Official homepage](https://www.simile.com/): founders, roles, research/product positioning.
- [2] [The Simulation Company](https://www.simile.com/blog/the-simulation-company): business vision.
- [3] [Series B announcement](https://www.simile.com/blog/series-b), July 30, 2026: company-reported funding, scale, mission.
- [4] [Building confidence in Simile](https://www.simile.com/blog/confidence), August 25, 2026: interface, model diagram, TVD, holdouts, error prediction, buckets.
- [5] [Building the What-If Machine](https://www.simile.com/blog/what-if-machine), September 2, 2026: data modalities and mechanism examples.
- [6] [Generative Agents](https://arxiv.org/abs/2304.03442): 25 fictional agents, architecture, believability.
- [7] [Individual grounding, v3](https://arxiv.org/abs/2411.10109v3), June 28, 2026: sample, raw/normalized scores, economic games, limitations.
- [8] [Socrates final EMNLP paper](https://aclanthology.org/2025.emnlp-main.1530/): dataset, 170/40 split, relative Wasserstein improvement. [Public artifacts](https://stanfordhci.github.io/socrates/).
- [9] [CVS case](https://www.simile.com/blog/simile-cvs-health); [10] [CVS whitepaper](https://www.cvshealth.com/content/dam/enterprise/cvs-enterprise/pdfs/2026/CVS_WhitepaperCVSxSimile.pdf): use cases and qualified validation claims.
- [11] [Itaú case](https://www.simile.com/blog/itau-at-esomar), September 11, 2026: research speed and human oversight.
