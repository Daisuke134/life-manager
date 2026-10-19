# Choosing data for Manager: populations, behavior, and interventions

Learning population composition, observed behavior, and intervention effects requires different data. This guide separates company descriptions, paper reports, and our design choices.

![Data selection by purpose](https://aniccaai.com/blog/manager/media/49b58c16621bc9af72513e0af67d148ab06ff208bf24fd04bb2792c1d2042061.png)

Illustration retains Japanese labels.

## Recommended starting combination

ACS 2024 five-year B17001 is suitable for a population-reconstruction lesson; the same 2020–2024 ACS PUMS series supports household/person synthesis. Choose time-use, health, travel, or experimental data once an initial intervention question is defined.

Population composition, observed choices, and causal intervention effects need different evidence. Census attributes alone cannot measure benefits of changing an environment. Anicca’s mission is **End suffering.** Reconstructing a population and reducing suffering require separate validation.

## Four roles for data

| Role | Observations | Examples | What it cannot establish alone |
|---|---|---|---|
| Population composition | Age, income, households, geography | ACS aggregates/PUMS, INSEE census | Choices in new situations or intervention effects |
| Life, behavior, and state | Diaries, travel, self-reported health, answers, purchases | ATUS, NHTS, BRFSS, surveys/experiments | Whether an association is causal |
| Intervention and outcome | Assignment, assignment probability, availability, later outcomes | Randomized trials, HeartSteps | Transfer to another population/environment |
| Our field evaluation | Executed changes, comparisons, outcomes, costs, adverse effects | Operational records and observations from affected parties | Unmeasured benefits or effects on all life |

## What predecessors use

| Research or company | Publicly described data | Purpose and transferable lesson | Scope and limits |
|---|---|---|---|
| RTI / rti_synth_pop | 2015–2019 ACS, PUMS, TIGER, LandScan USA | Combine attributes, households, spatial placement | Abstract and official README checked; code, distributed population, and location-data terms differ; current inputs are not identical to the 2019 distribution |
| ActivitySim / PopulationSim | Linked household/person samples, controls at multiple geographic levels; ACS/PUMS in US applications | Preserve households while fitting household and person totals | Documentation and selected code read; framework is not tied to one ACS year |
| Jones, Dawson, Mills 2026 | Newcastle 2021 UK Census aggregates; North East 10% safeguarded microdata for IPU comparison | Prompt from aggregates and feed generated statistics back when microdata is unavailable | Methods, results, limitations, author code read; safeguarded UK microdata is not unrestricted download |
| Lim, Yun et al. 2026 | 1,006,391 pooled Korean HTS records from 2010, 2016, 2021; 5% training sample | Compare LLM, network, and generative learning of combinations | Manuscript and code read; pooled surveys are not the complete actual population, nor measures of suffering |
| Darsel et al. 2026 | INSEE Île-de-France census data; preprocessing has 23 variables, paper compares 12 | Common-data comparison of networks, VAE, GAN, diffusion | Final methods/data/results read; weighted survey reference is not complete resident microdata; code/data terms separate |
| Hoehn et al., COMPASS, October 7, 2026 | Small-area aggregates and 1% household samples from artificial Meropis | Test household/person/geographic consistency and uncertainty against a known source population | Methods and experiments read; artificial-population reconstruction is not real-world benefit |
| Aaru | Census/demographic statistics, public material, licensed purchase/visit records, customer first-party data; evaluation uses questions, choices, population descriptions, held-out answer distributions | Align composition, behavior, and evaluation evidence by task | Official simulation page and September 24, 2026 research checked; private vendors/data/implementation unknown; company claims |
| Simile | Retail/delivery transactions, AI voice interviews, surveys, observed outcomes | Combine behavior and personal explanations; compare predicted/observed distributions | Confidence/what-if articles checked; complete current training data private |
| Park et al., personal simulation | Two-hour interviews with 1,052 US participants; GSS, Big Five and other self-reports | Compare demographic-only profiles with information obtained from participants | June 28, 2026 v3 abstract checked; formerly *Generative Agent Simulations of 1,000 People*; interviews not assumed freely obtainable; not the entire Simile product |

A company using a data type does not give us access to its data. Public purchase-prediction accuracy also does not guarantee causal accuracy for environmental changes.

## Why start with ACS?

The US Census Bureau’s American Community Survey offers geographic aggregate estimates and PUMS privacy-protected person/housing sample records. Having both in one survey family supports a staged path toward households. Official dictionaries, weights, accuracy guidance, and distributions make it possible to start without a paid external contract.

This is a reproducible learning choice, not a decision that the US is our final market. A Japanese target would require a new design around e-Stat aggregates and microdata access. Public aggregates do not imply anonymous microdata is available without review.

Five-year ACS estimates pool five years; they are not today’s resident registry. Avoid mixing one-year/five-year series, periods, boundaries, or target universes. Pin evaluation data even when changing models.

### First aggregate table: B17001

Collapse 2020–2024 B17001, “Poverty Status in the Past 12 Months by Sex by Age,” into three age groups × two poverty categories: six cells. Its universe is the population for whom poverty status is determined, not the entire population. Poverty is a reconstruction variable here, not an automatically adopted proxy for suffering.

Split 50 states and DC into six development, four validation, and 41 final-evaluation areas. Supply only target-area margins to reconstruction and keep cross-tabs on the scoring side. Build the seed table from development areas and compare independence with IPF.

This prevents answer leakage. Margins and hidden cells calculated from the same ACS are not independently collected evidence. Report recovery of withheld combinations, not future prediction or real-world improvement.

### Next microdata: ACS PUMS

Use 2020–2024 ACS five-year housing and person files. Rhode Island is a small, inspectable starting example, not a selected intervention site. Official files include housing `csv_hri.zip` and person `csv_pri.zip`.

| File | Initial fields | Role |
|---|---|---|
| Housing/households | SERIALNO, ST, PUMA, NP, WGTP | Household key, geography, size, household weight |
| Persons | SERIALNO, SPORDER, AGEP, RELSHIPP, PWGTP | Membership, within-household identifier, age, relationship, person weight |

Add fields such as HINCP, ESR, or POVPIP only with dictionary-defined meanings. Codes are not names, current addresses, or identities of real people. Housing includes vacant units; persons can include group quarters. Define the ordinary-household universe and exclusion reasons. Check NP against joined member count, duplicates, relationships, missing values, and allocation/processing flags.

Distinguish row count from weighted population estimates and household-selection weights from person-aggregation weights. Split at household ID so members do not leak across training and evaluation.

PUMS geography is coarse and does not identify exact neighborhood addresses. Small-area placement needs geographic correspondence and additional controls. PUMS weighted estimates need not exactly match detailed ACS tables; official guidance explains differences. These products share underlying surveys, so comparisons are not fully independent validation.

## Data for later behavior and intervention work

| Purpose | Candidate | Useful observations | Check before adoption |
|---|---|---|---|
| Time burden, chores, rest, care | BLS ATUS | Activity diaries, duration, respondent/household attributes | Respondent-centered diaries, not simultaneous whole-household behavior; wellbeing modules have specific years; saved time is not automatically reduced suffering |
| Travel burden | FHWA NHTS | Household/person/trip/mode records | Population coverage, version, weights, spatial scale; service-change effects may be absent |
| Health and subjective state | CDC BRFSS | Adult self-reported health and behaviors, including MENTHLTH | Adult telephone survey, not children or all life; not causal intervention data |
| Responses to questions/experiments | SocSci210 | Studies, conditions, questions, answers | Original-study rights, study-held-out splits, overlap/leakage; not a demographic population reference |
| Intervention-evaluation methods | HeartSteps V1 | Randomized activity suggestions and outcomes | Repository CC BY 4.0 and attribution; availability, assignment, outcomes, missingness; do not generalize individual activity effects to large environmental changes |

Manager’s first real environmental-change use case remains undecided. ATUS is a useful next reading candidate for time and care burdens, but should not determine an intervention before an actionable change and comparison design exist.

Two surveys containing people of the same age/income do not describe the same real person. Joining PUMS to ATUS or BRFSS by age cannot create an observed individual history. Statistical matching requires explicit assumptions, population compatibility, unmatched attributes, and post-match validation.

## Sources and reading scope

- [ACS PUMS overview](https://www.census.gov/programs-surveys/acs/microdata.html), [2024 dictionaries/accuracy/use guidance](https://www.census.gov/programs-surveys/acs/microdata/documentation/2024.html), [official five-year files](https://www2.census.gov/programs-surveys/acs/data/pums/2024/5-Year/): metadata and listings checked.
- [B17001 definitions](https://api.census.gov/data/2024/acs/acs5/groups/B17001.json): JSON retrieved; universe and example variables checked.
- [RTI paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC11762717/), [official repository](https://github.com/RTIInternational/rti_synth_pop): abstract and README; full code not run.
- [PopulationSim documentation](https://activitysim.github.io/populationsim/application_configuration.html): expansion/output code also read in related work.
- [Jones et al.](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0341704), [Lim/Yun et al.](https://doi.org/10.1016/j.trc.2026.105581): methods, results, author code read in related work.
- [Darsel final paper](https://hal.science/hal-05758634/document), [preprocessed data](https://doi.org/10.17632/p2gcy7x7sd.3): final data section/comparison checked; data files not downloaded here.
- [COMPASS](https://journals.sagepub.com/doi/10.1177/23998083261484652): artificial-population experiments and methods checked.
- [Aaru explanation](https://aaru.com/simulation), [evaluation](https://aaru.com/publications/population-simulation-at-the-replication-floor-research): source types and evaluation conditions.
- [Simile confidence](https://www.simile.com/blog/confidence), [what-if](https://www.simile.com/blog/what-if-machine): sources and validation.
- [Park et al. v3](https://arxiv.org/abs/2411.10109v3): latest added check covered revised abstract; older numbers are not automatically current results.
- [ATUS](https://www.bls.gov/tus/data/datafiles-2024.htm), [NHTS official guide](https://nhts.ornl.gov/media/2022/doc/DE_public.pdf), [BRFSS](https://www.cdc.gov/brfss/annual_data/annual_2024.html): distributions and applications checked; data not analyzed.
- [Pinned SocSci210](https://huggingface.co/datasets/socratesft/SocSci210/tree/048481111a4425ed83dc0eacf15f8431f252b21a), [HeartSteps V1](https://github.com/klasnja/HeartStepsV1): dataset card, and README/CC BY 4.0 respectively; no trial analysis.
- [Japanese anonymous microdata access](https://www.e-stat.go.jp/microdata/anonymity): aggregate versus microdata procedures checked.

Reading pages, downloading data, and analyzing data are distinct activities.
