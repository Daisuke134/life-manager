# From synthetic populations to behavior prediction: statistical models, LLMs, Aaru, and Simile

“Create synthetic people, then predict their responses” describes a basic architecture for individual-level social simulation: represent the target population, provide a situation, predict responses, and aggregate. Some approaches instead predict response distributions directly from a population description and situation, without explicitly generating each individual.

![Connecting synthetic populations and behavior prediction](https://aniccaai.com/blog/manager/media/9c26978fbafba515d22d1518336043ca1b4c13d05106d08e3ea5d876a61ff212.png)

Illustration with Japanese labels.

## Separate population synthesis from behavior prediction

Population synthesis estimates what kinds of people and households exist and in what numbers—for example, combinations of age, income, and household structure. Behavior prediction estimates what someone chooses in a situation. Accurate population attributes do not guarantee accurate responses to new prices or service conditions.

A film analogy is casting versus deciding how characters act in a scene. Here the goal is agreement with observed attributes and behavior, not an entertaining story.

## IPF is not the only population method

One family changes sample weights: how many people each existing record represents. IPF iteratively adjusts tables; extensions such as IPU address household and person controls. Changing weights alone cannot add missing combinations.

A second assigns attributes from conditional probabilities. After drawing age, for example, draw employment conditional on age. Bayesian networks express dependencies with a graph and conditional distributions. Arrows are not automatically causal. Sun and Erath demonstrate population synthesis with this approach.[1]

A third uses combinatorial optimization, changing selected sample records and their combinations to reduce aggregate discrepancies. Simulated annealing can accept some worsening moves early to avoid getting stuck locally. Harland and colleagues compare reweighting, conditional probabilities, and annealing, evaluating cross-tabs and uncontrolled variables as well as fitting controls.[2]

A fourth learns a generative model, such as a VAE, to produce attribute combinations. Borysov and colleagues apply VAEs to population synthesis; neural population models need not be language models. Novel combinations still require checks for structural zeros, rare-group omission, and distributional error.[3]

A fifth generates people or households with LLMs. Jones and colleagues’ 2026 framework prompts with aggregates, attribute formats, and current synthetic-population statistics, feeding discrepancies into later prompts without requiring fine-tuning.[4]

These are not mutually exclusive. A generative model can propose records before reweighting them to local totals. Whether a method uses samples or only aggregates, and whether it outputs people or households, are additional classification axes.

## Public LLM population code

We retrieved the authors’ LLM-Population-Generator. `PopulationGenerator.generate_households` prepares prompts, invokes generation, accumulates results, and updates prompts with statistics for the next batch:

```text
population_generator/engine/generator.py
  generate_households
    → batch_processor.run_batch
    → households.extend
    → batch_processor.update_prompt_with_statistics
```

Validation is separated into components such as `data/validation.py`. We loaded only an upstream validation component offline and checked acceptance of fictional age 30 and rejection of −1. We did not generate households, run model inference, or reproduce paper outcomes.

The companion Synthetic-Population-Experiments repository includes `validate_full_cross_tab.py` for age × sex × household size × composition and `09_compare_methods.py` for IPU/LLM comparisons. The existence of scripts does not establish a fair comparison: input, splits, and definitions must align.

Matching supplied totals does not establish unknown combinations. Consult the August 2026 correction to Figure 10.[5] Public household rules also contain domain-specific assumptions; they are not universal specifications for every geography.

## Two LLM response-prediction approaches

One supplies personal information at inference time. Records relevant to a question can be retrieved and included in a prompt without retraining the LLM for that person.

`GenerativeAgent` in StanfordHCI/genagents stores personal information and a `memory_stream`. `categorical_resp` delegates to `interaction.py`; `_main_agent_desc` retrieves relevant memories and adds them to the description. The LLM receives the description, question, and choices, then returns a structured response. Retrieval combines relevance, recency, and importance. External memory retrieval differs from retraining model parameters whenever a memory is added.[6]

Another approach fine-tunes the model on human experiments. Socrates uses personal attributes, experimental conditions, and questions as inputs, with observed answers as targets. SFT increases probability of observed answers. DPO compares answer pairs to increase the relative probability of the answer favored by the training objective. Socrates describes pair construction using differences in attributes and conditions. Here “preference” is an experimental training label, not necessarily an ethical judgment about an answer.[7]

We read the paper’s method and evaluation sections. Of 210 studies, 170 are used for training and 40 held out. It evaluates individual answers and population response distributions separately. The GitHub repository mainly points to data, models, and splits and directs users to LLaMA-Factory for fine-tuning; do not describe it as containing a complete custom training implementation. Data, base-model, and derived-model terms require separate checks.[7][8]

## What Aaru publicly discloses

Aaru describes constructing a target-matched agent population and producing responses per agent. It explicitly states its population generator and core individual-trajectory prediction model are not language models. Public sources do not establish that they use IPF, a VAE, or a particular network.

Its September 2026 evaluation primarily concerns question-level answer shares; within-person logical consistency and higher-order relationships remain separate tasks. Population-share accuracy does not prove individual accuracy or unknown intervention effects. These are company-reported results, not our independent replication.[9]

## What Simile publicly discloses

One related research line constructs LLM agents from real participants’ interviews and surveys, then evaluates answers to other questions. Public genagents is a related research implementation, not the current commercial Simile codebase.[6]

Current technical articles describe learning behavior-prediction models from purchases, interviews, and surveys. Examples accept textual descriptions of a population, situation, and possible actions, then output an action distribution. They also discuss Qwen3.5-27B fine-tuning and uncertainty prediction experiments. This does not reveal the entire product architecture or every population-aggregation step.[10]

“Aaru does populations; Simile does individuals” is an inaccurate split. Both concern individual and group behavior, with different public descriptions, data, and evaluation units.

## Sources and scope

1. [Sun and Erath, A Bayesian network approach for population synthesis](https://lijunsun.github.io/files/papers/2015-TRC-BN-Population.pdf).
2. [Harland et al., Creating Realistic Synthetic Populations at Varying Spatial Scales](https://www.jasss.org/15/1/1.html).
3. [Borysov et al., Scalable Population Synthesis with Deep Generative Modeling](https://arxiv.org/abs/1808.06910).
4. [Jones et al., A large language model framework for sample-free population synthesis](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0341704).
5. [Correction](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0356492).
6. [StanfordHCI/genagents](https://github.com/StanfordHCI/genagents); [corresponding personal-simulation research](https://arxiv.org/abs/2411.10109).
7. [Kolluri et al., Finetuning LLMs for Human Behavior Prediction in Social Science Experiments](https://aclanthology.org/2025.emnlp-main.1530/), methods and evaluation read in PDF.
8. [Socrates public repository](https://github.com/akaashkolluri/socrates).
9. [Aaru public research](https://aaru.com/publications/population-simulation-at-the-replication-floor-research).
10. [Simile, Building confidence in Simile](https://www.simile.com/blog/confidence).

Retrieved author repositories: https://github.com/MJones235/LLM-Population-Generator and https://github.com/MJones235/Synthetic-Population-Experiments. Reading selected code does not mean every file in all four referenced repositories was read.
