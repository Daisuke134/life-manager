# What Aaru simulates: populations, behavior, and the evidence behind the predictions

A new price can change which customers stay. A financial announcement can reassure one investor group and unsettle another. Decisions like these require an estimate of responses to conditions that have not yet occurred. Historical sales and surveys help, but neither automatically answers that question.

Aaru builds simulated populations grounded in real demographic and behavioral data, then estimates their responses to products, prices, messages, policies, and other conditions. It is worth examining for research and decision support. Its strongest published evidence concerns survey-answer distributions and a separate purchase-ranking task. Those results do not establish that a new intervention will causally improve health, income, or wellbeing.[1][2]

## The founders’ question

Aaru describes its starting question as whether human behavior can be simulated at the scale and complexity of the real world. John Kessler, its co-founder and CTO, previously conducted simulation research at MIT’s City Science Lab and now leads technical research and simulation-system development. Aaru’s Breakwater case identifies Cam Fink as co-founder and CEO.[3][5]

The ambition extends beyond faster surveys: test consequential choices before committing money, time, or reputation. Its stated principles include examining consequences rather than treating good intentions as sufficient, making assumptions explicit, and updating beliefs when evidence changes. These are company commitments, not evidence that every engagement has produced a social benefit.[3]

## A simulated person is a model, not a chatbot personality

A statistical model uses relationships in observed data to estimate unknown quantities. If past data links income and price to purchase probability, a model can estimate responses to a proposed price. The estimate can fail when the relationships change.

A large language model, or LLM, learns from extensive text and other training material to generate output. A persona prompt can produce a plausible answer, but plausibility and population accuracy are different. Fluent respondents can still overrepresent consensus and omit minority views.

Aaru explicitly says that neither its core population-generation model nor its core model for predicting an agent’s behavioral trajectory is a language model. Their detailed topology and training losses are not public. Treating Aaru as simply thousands of chatbot personas would overlook a distinction its research makes explicitly.[1]

An agent here is a computational representation of a person who could plausibly exist. It is not a complete copy of a named individual. Aaru describes its target as distributions of possible behavior under specified conditions, rather than a promise about one person’s next action.[2]

## Define the decision before generating the population

The product workflow begins with the alternatives, success criteria, and constraints. Users then specify audiences and questions, including stimuli such as product descriptions, prices, messages, and hypothetical conditions. Formats include single choice, multiple selection, ranking, free response, and branching.[2]

An audience can be broad or tightly constrained by income, shopping frequency, family structure, and behavior. A precise description still needs supporting evidence. Narrow wording alone does not make a hard-to-observe population accurate. The objective matters too: maximizing sales and increasing access among low-income households require different success criteria.

## Data and joint distributions

Aaru describes three data layers: public sources covering demographics, labor, health, prices, and geography; licensed behavioral signals including anonymized transactions, visits, search demand, and media use; and customer context such as segments, purchase histories, research, product details, and operating constraints.[2]

Sources differ in geography, refresh schedules, coverage, and bias. Card transactions, for example, incompletely represent cash-only behavior. Aaru says it weighs sources against one another and carries coverage gaps into model limitations and reporting. The complete catalog and weighting procedure are not public.

Matching each attribute separately is insufficient. A *marginal distribution* describes one attribute; a *joint distribution* describes combinations. Consider this illustrative example, not an Aaru result:

|Population of 100|Younger, employed|Younger, not employed|Older, employed|Older, not employed|
|---|---:|---:|---:|---:|
|A|40|10|10|40|
|B|10|40|40|10|

Both populations contain 50 younger people, 50 older people, and 50 employed people. Yet their commuting needs could differ substantially because employment occurs in different age groups.

Even matching two-way tables may miss three-way relationships, such as caregiving-related employment patterns concentrated at particular ages. Aaru says it learns a network of data-supported relationships and samples coherent complete profiles from it, rather than turning source rows directly into agents. The number of possible combinations grows rapidly with the number of traits. Selecting supported relationships matters because fitting every sparse combination can learn noise. The public narrative does not identify the proprietary algorithm, network structure, weights, or training loss.[2]

## Population construction and response trajectories

Population construction answers: who exists in this audience, and in what proportions? Response modeling answers: how do these people respond under the specified conditions? Either component can spoil the aggregate prediction.

Aaru describes training against both population distributions and differences in responses across people and conditions. Fitting only individuals can let totals drift; fitting only totals can conceal incoherent people. Learned relationships are then applied to new conditions, with results remaining conditional on evidence and assumptions.[2]

The term “behavioral trajectory” does not itself prove validated long-term life simulation or social interaction. The large public study mainly tests question-level answer shares. Longitudinal change, influence between groups, and within-person consistency require additional evaluations.[1]

## What comes back

The research produces microdata: one record per simulated agent, which can be aggregated, segmented, and cross-tabulated. The product page shows interactive artifacts traceable to questions and audiences, with sheet and presentation outputs.[1][2]

Having respondent-level rows does not establish cross-tab accuracy. Two questions’ answer shares can each match while the proportion of people agreeing with both is wrong. Aaru explicitly limits the published study to univariate distributions and leaves higher-order accuracy and logical row coherence for future publications. Buyers need validation at the granularity they intend to use.[1]

## Reading the accuracy numbers

The September 2026 research evaluates 2,993 questions from 186 studies across nine industries, comprising 13,727 answer shares. It reports raw mean absolute error, or MAE, of 3.53 percentage points and mean total variation distance, or TVD, of 7.62 points.[1]

MAE averages absolute differences between predicted and observed shares. A prediction of 40% against an observed 35% differs by five percentage points, not five percent relative error. In an illustrative three-option question, observed shares of 50%, 30%, 20% and predicted shares of 45%, 35%, 20% have differences of five, five, and zero points: MAE is approximately 3.33 points.

TVD is half the sum of those differences: five points. Moving five points of probability from the first option to the second makes the distributions agree. MAE averages option-level discrepancies; TVD describes the discrepancy across the whole question.

The reported pooled Pearson correlation of 0.970 measures linear association, **not 97% accuracy**. Predictions can track relative magnitudes while systematically overshooting them. Spearman correlation measures rank agreement, another distinct property.

A sampling-adjusted MAE of 2.78 points subtracts an approximation to expected survey sampling error. It is an assumption-dependent reference, not complete removal of survey bias or direct error against an unknowable population truth. Read it alongside the raw 3.53-point result.

Aaru also compares its error with disagreement in published repeat-survey studies, calling this a “replication floor.” Those studies involve differing populations, instruments, and timing. They are not a matched head-to-head survey replication, so the comparison does not establish universal human-equivalent accuracy.[1]

## Protecting the evaluation

Aaru says the evaluation questions and published answers were not used to develop or tune either the simulation or confidence predictor. External retrieval used only Exa, restricted to records at least one day before fieldwork began, excluding publisher domains and prediction markets. Some confidential alternative data and processing practices were removed for this constrained evaluation.[1]

These choices address leakage: information about an outcome entering a model supposedly predicting it in advance. The non-language-model cores also relate to concerns about memorized answers in LLM pretraining. Public descriptions are useful evidence about the protocol; they are not an independent audit of every private data pathway.

On the same random 500-question subset, one-call direct distribution elicitation yielded TVD of 12.4 points for Kimi K3 and 21.6 for gpt-oss-120b. These baselines had no retrieval and produced toplines only. The comparison does not equalize data, retrieval, or computational resources, and does not establish superiority over every LLM-based method.[1]

## Uncertainty includes more than sampling noise

Generating a population repeatedly creates random variation. More simulated agents can reduce that variation, but cannot remove a missing population or incorrect behavioral relationship. Forty thousand simulated people are not forty thousand newly observed participants.

Aaru separately predicts its likely error. Retaining about half the questions, 1,525, based on lower predicted error yields observed mean TVD of 4.54 points. This is selective prediction: accepting a more reliable subset, not improving every original prediction.[1]

The research reports AUROC of 0.845 under its comparison definition for distinguishing errors below versus at least 16 points. AUROC measures ranking discrimination. It does not mean the error probabilities are calibrated. Calibration would mean, for example, that events assigned a 20% probability occur about 20% of the time. Some high-error predictions remain optimistic; important decisions need tail-error and subgroup analysis as well as averages.

A separate purchase evaluation compares brand rankings against card-panel transactions. Aaru reports 92.4% pairwise ranking agreement versus 77.8% for purchase-consideration scores across 340 brand pairs. This is purchase-order agreement, not individual purchase accuracy or sales lift. It also compares different targets, simulated purchases versus stated consideration, within a panel whose coverage is not the whole population.[1]

## Applications and the limits of customer cases

Aaru’s EY case describes a blinded reconstruction of the 2025 Global Wealth Study: 3,600 affluent investors across more than 30 markets. Across 53 matched single-choice questions, it reports median Spearman correlation of 0.90, average difference of 7.1 percentage points, and a one-day run. This customer-site account is a different study from the 2,993-question evaluation. It supports a rapid research-complement use case, not a causal claim about increasing investor wealth.[4]

Breakwater’s Conviction Advantage uses 40,000 simulated investors and 71 judgments in a quarterly capital-markets tracker. It examines differences across investor types, turnover, benchmark sensitivity, and investment horizon. This is neither a 40,000-person human survey nor an experiment demonstrating higher investment returns.[5]

Other proposed uses include product innovation, pricing, brand messaging, segmentation, strategic communications, and scenario planning. The latter includes adaptations by customers, employees, policymakers, and competitors. Some website scenarios are explicitly illustrative. Application lists for politics or public affairs do not establish a particular election forecast’s success or a policy intervention’s measured benefit.[1][6]

## Sources

1. [Aaru, Population simulation at the replication floor, Research, September 24, 2026](https://aaru.com/publications/population-simulation-at-the-replication-floor-research)
2. [Aaru, How a simulation works](https://aaru.com/simulation)
3. [Aaru, About](https://aaru.com/about)
4. [Aaru, EY Global Wealth Study](https://aaru.com/case-studies/ey-wealth-research)
5. [Aaru, Breakwater Conviction Advantage](https://aaru.com/case-studies/breakwater-conviction-advantage)
6. [Aaru, Scenario Planning](https://aaru.com/use-cases/scenario-planning)

Public-material review date: October 12, 2026. Product descriptions, customer-site claims, and published research results are distinguished throughout.
