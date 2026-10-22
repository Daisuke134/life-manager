# Population Is Not Behavior, and Behavior Is Not Causality

*Manager research notes · October 20, 2026 · Reading guide, not a claim of deployed human benefit.*

An agent that convincingly describes a person's day is not necessarily an accurate model of that person's choices. An accurate forecast of choices is not necessarily an accurate forecast of an intervention's effect. And an intervention that changes a measurable behavior does not necessarily improve welfare.

These distinctions are the starting point for Manager, Anicca's research-stage project with the mission **End suffering.** The product hypothesis is to connect public evidence, optional simulation, authorized changes to shared environments, and independent outcome evaluation. The current work is an offline prototype. It has not demonstrated real-world suffering reduction.

## Four different questions

**Population synthesis asks who is represented.** A synthetic population contains records whose attributes and relationships match specified population statistics. Matching age or household distributions does not supply evidence about what those people will do. The census-like description is an input, not a validated behavioral mechanism.

**Behavioral modeling asks how choices occur.** A rule-based model might use a small number of interpretable variables. A statistical model may estimate a probability distribution. An LLM-based agent may condition on a persona, remembered events, and a decision context. These are different implementations of a behavioral hypothesis, not interchangeable measures of realism.

**Social simulation asks what happens through interaction and time.** People compete for resources, share information, learn, and change their environment. The next state depends on both the individual policies and the environment's transition rules. A simulator is a way to run those assumptions forward. Its output is not automatically an observation of the world.

**Causal evaluation asks what changed because of an intervention.** It requires a defensible comparison with what would have happened without that intervention. Forecasting a person's stated preference and estimating the change caused by a policy are different targets.

A useful conceptual loop is:

```text
Population and context -> individual choices -> shared environment changes
       ^                                               |
       +---------------- observations ----------------+

Candidate intervention -> predicted change -> authorized action
                         -> independent measurement -> causal comparison
```

## A map of existing work: do not rebuild all the pieces

### Expected Parrot: reproducible instruments and human validation

Expected Parrot's EDSL organizes research around questions, surveys, agent traits, scenarios, models, and results. It supplies execution, structured outputs, caching, and comparison tools. Its platform also lets researchers field studies to human respondents. It is therefore inaccurate to describe it as only a synthetic-survey generator. The company was co-founded by Robin Horton and John Horton; the latter's research includes Homo Silicus, Automated Social Science, and General Social Agents. [Official documentation](https://docs.expectedparrot.com/en/latest), [author account](https://john-joseph-horton.com/expected-parrot.html), [EDSL source](https://github.com/expectedparrot/edsl).

For Manager, this is a candidate research adapter, not a library we must install before the first useful experiment. Reuse its instrument and replay concepts when running comparable model experiments. Cached output makes an execution reproducible; it does not by itself establish human validity. Remote storage, personal data, model-provider costs, and recruitment each require their own review.

### Generative Agents and Concordia: the interaction layer

Park and colleagues' Generative Agents introduced a memory, reflection, and planning architecture and demonstrated a town of 25 computational agents. The motivating achievement was believable behavior and interaction, not a clinical or welfare effect. [Original paper](https://arxiv.org/abs/2304.03442), [author code](https://github.com/joonspk-research/generative_agents).

Concordia separates agent entities from an environment progression role, often described as a Game Master. An agent proposes an action; the environment resolves what occurs and returns observations. That separation is useful for testing social hypotheses without conflating a model's intended action with a real-world effect. [Technical report](https://arxiv.org/abs/2312.03664), [official code](https://github.com/google-deepmind/concordia).

A simulated environment can declare that a resource changed. A real executor must instead obtain permission, attempt the change, and verify it with the external provider. The Game Master does not become an authority over real people.

### SocSci210: learning from observed responses

Kolluri and colleagues constructed SocSci210 from 210 social-science experiments, with approximately 2.9 million responses from 400,491 participants. Their work evaluates generalization across studies as well as other held-out settings. The released research is useful for learning how to compare response distributions, individual accuracy, and different training objectives. [Paper](https://arxiv.org/html/2509.05830v1), [repository and mappings](https://github.com/akaashkolluri/socrates).

The original source conditions still matter. A public repository is not an unrestricted license for every contributing dataset. Manager's rights review leaves unresolved uses on hold rather than silently treating all data as commercially reusable. Nor should generated reasoning fields be mistaken for measurements of a participant's actual internal reasoning.

### Simile: predicting behavior and predicting the prediction's error

Simile describes training behavioral models with transactions, interviews, and surveys. Its confidence-method article evaluates a second model that predicts how far a simulated response distribution will be from observed data. The article describes roughly 8,600 evaluation questions, grouped cross-validation, and several uncertainty-estimation methods. These are company-reported methods and results, not an independent certification of universal performance. [Simile's primary technical article](https://www.simile.com/blog/confidence).

The useful lesson is that a forecast should have a measured error profile. A model's confidence, an empirical calibration result, and the benefit of acting on a forecast are different objects. A threshold acceptable for market research should not automatically become an intervention safety threshold.

### Aaru: do not assume every simulator is simply an LLM persona

Aaru's own evaluation distinguishes population survey results from purchasing behavior and states that its core row-level behavioral-trajectory model is not a language model. Its evaluation discusses sampling noise and repeat-survey variation. This is materially different from treating every company in the field as a prompt wrapped around a demographic persona. [Primary research](https://aaru.com/publications/population-simulation-at-the-replication-floor-research), [company summary](https://aaru.com/publications/population-simulation-at-the-replication-floor-summary).

Its vendor-reported figures cannot be ranked directly against Simile or a research paper with a different dataset, target, and split. Observed purchasing behavior is more than an opinion survey, but predicting purchases is still not evidence of reduced suffering.

### Centaur and AgentTorch: cognition and population dynamics are different layers

Binz and colleagues' Centaur fine-tunes a language model on trial-by-trial psychological data and evaluates held-out people and task changes. This provides another route beyond demographic prompting: learn a distribution over sequential choices and compare it with established cognitive models. [Original Nature paper](https://www.nature.com/articles/s41586-025-09215-4).

AgentTorch instead emphasizes scalable, differentiable population interaction. Its official repository describes composition with neural and mechanistic models. This is infrastructure for running and calibrating interacting-agent systems, not automatic evidence of valid social forecasts. [Original repository](https://github.com/AgentTorch/AgentTorch). Both are research leads; neither was installed as a prerequisite for our eight evidence cards.

## What the review literature adds

Larooij and Törnberg's critical review makes validation the central challenge for generative social simulation. It links contemporary LLM agents to longstanding agent-based modeling concerns: calibration, empirical grounding, interpretability, and the distinction between plausible narratives and models adequate for a purpose. [Published review](https://link.springer.com/article/10.1007/s10462-025-11412-6).

A review is a map into the field. It should lead to the cited methods and experiments, not be counted as another independent replication of every study it discusses. The practical response is to state an intended use, define observable acceptance criteria, and test against held-out human or environmental evidence. Model size and population size are not substitutes for that test.

## A precise warning: descriptive fit is not causal fidelity

Li and Ji's 2026 preprint compares LLM simulations with climate-intervention experiment data. Their key finding is a divergence between reproducing response patterns and recovering intervention effects. Some prompt refinements improved descriptive accuracy without corresponding improvement in behavioral effect estimates. The paper studies lightweight models and climate-related outcomes; it is not a proof that larger, trained, or future systems cannot learn useful causal predictions. [Version read](https://arxiv.org/html/2604.02458v1).

Our reading also records an unresolved sample-description discrepancy between that preprint and the original climate tournament. The original study reports 59,440 participants in 63 countries and found that none of its tested interventions increased the more effortful tree-planting task overall. [Original experiment abstract](https://pubmed.ncbi.nlm.nih.gov/38324680/). We do not merge the reported populations or claim to have reproduced the analyses.

Consider an invented example: a simulator predicts an average score of 61 without treatment and 65 with treatment. The real experiment reports 60 and 61. Predictions of the levels may look reasonably close, yet the simulator predicts an effect of four points instead of one. The gap is arithmetic, not a mystical property of intelligence. This illustration is not an empirical result.

## What Manager proposes to add

The defensible distinction is a product objective and architecture, not a claim that nobody else validates with humans. Manager aims to organize authorized, public-information-based interventions around independently measured net benefit, including failures, distributional harms, and unresolved outcomes. That integration and its generality remain to be demonstrated.

The first pilot candidate is publicly auditable aid amplification. A matching offer, for example, changes the resource conditions of a shared campaign rather than analyzing private beneficiaries. It still requires an authorized operator and a defined budget. The system would separate its own subsidy from new outside funding, check displacement from other campaigns, and avoid equating an on-chain transfer with improved living conditions. No money has been moved in this prototype.

A second candidate is an operator-authorized improvement to a shared indoor environment. Public outdoor air data alone cannot verify a room's improvement; the pilot needs independent indoor measurement and an honest account of energy, noise, exposure, and actual health outcomes. These are pilot requirements, not secured access.

An ambient system need not force every beneficiary to install an app. But no mandatory UI is not permission for hidden psychological manipulation, private profiling, or unconsented medical intervention. Public operator notices, explanations, correction channels, and appropriate human oversight remain part of the design.

## A research program rather than a claim of completion

Start with simple baselines. Compare predictions on genuinely held-out settings. Separate simulation output, external execution, measured outcomes, and causal evidence. Preserve uncertain and adverse results. Add a simulator only where interactions or counterfactual analysis actually require one.

The most valuable integration is not a giant diagram connecting every tool. It is a small working loop whose assumptions, actions, and outcomes another person can inspect. That is what our current evidence registry supports, and what our future field experiments must earn.
