# Population simulation fundamentals: building a population and predicting its response

Suppose a community facility is considering different opening hours. Opening on weekday afternoons and opening in the evening will serve different people. To examine the difference before making a change, we need to consider who lives in the area and how those people might respond.

Population simulation represents the composition of a target group computationally and estimates outcomes under specified conditions. Separating population construction from response prediction also makes Aaru and Simile easier to understand. This is a useful distinction, not a claim that every method has the same architecture.

## 1. Population and sample

A population is the whole group we want to understand. Adults in Japan, residents of a neighborhood, and people eligible to use a facility are different populations. “Population” does not necessarily mean everyone in a country.

When we cannot observe everyone, we observe a subset: a sample. Survey respondents and users included in an administrative record are examples. The behavior of people absent from that sample is not directly observed. Studying only daytime visitors misses people who cannot visit during the day. We must ask who was observed, not just how many records we have.

## 2. Models and synthetic populations

A model represents the features and relationships needed for a question in a computable form. Working hours, travel time, and caring responsibilities may matter for facility opening hours. We do not need to reproduce every feature of reality.

A synthetic population consists of computational people represented through profiles such as age, employment, location, and household composition. These are not complete copies of identifiable real individuals. Synthesis creates records from evidence; it does not increase the number of people actually surveyed.

![Four tasks: evidence, population, response, and validation](https://aniccaai.com/blog/manager/media/114cbab43a81483edea3efce24fde9fc9fef353918f1598b96002efebd479ea4.png)

Conceptual illustration, with Japanese labels. It does not depict Aaru’s or Simile’s private implementation.

## 3. Distributions describe proportions

A distribution says how many people, or how much probability, belongs to each value or category. If a population of 100 contains 50 younger and 50 older people, the age-group distribution is 50% and 50%.

Matching age alone does not reproduce a population. The relationship between age and employment may also matter. The following is a fictional teaching example, not observed data or an Aaru result.

| Combination | Population A | Population B |
|---|---:|---:|
| Younger, employed | 40 | 10 |
| Younger, not employed | 10 | 40 |
| Older, employed | 10 | 40 |
| Older, not employed | 40 | 10 |
| Total | 100 | 100 |

Both populations have 50 younger people, 50 older people, 50 employed people, and 50 people not employed. Yet A has 40 employed younger people and B has only 10.

A distribution of one attribute is a marginal distribution. A distribution of combinations is a joint distribution. All individual totals can match while combinations differ.

![Two populations with identical margins and different joint distributions](https://aniccaai.com/blog/manager/media/6bcad6bc5e1bbfed8177e9605ddb8aecc3303b553ea31e9dd7fb9f4c4cc9f81a.png)

Japanese labels. The example does not claim age and employment alone determine facility use. It shows that separate totals do not identify the combinations.

## 4. Conditional probability

Conditional probability restricts the group being counted. Among A’s 50 younger people, 40 are employed: 40/50 = 80%. For B, the corresponding proportion is 10/50 = 20%. Overall employment is 50% in both populations.

Specifying the conditions under which a proportion applies is fundamental to response prediction. But association between age and employment does not establish that age causes employment. A conditional proportion and the effect of changing a condition are different quantities.

## 5. Population construction and behavior prediction

A population model answers “Who is there, and how many?” A behavior model answers “What might those people choose under these conditions?”

Suppose a profile has an estimated 70% probability of using the facility in the evening. This, too, is an illustrative assumption. It does not mean that person is certain to attend. A simulation can sample individual actions and add them up, calculate expected attendance directly from probabilities, or use representative profiles with population weights. It need not make everyone converse.

A correct population with incorrect choice probabilities gives incorrect results. Accurate behavior estimates also give incorrect population totals if important groups are missing. The two components need separate evaluations.

Training adjusts model settings using observations—for example, estimating the relationship between attendance, opening hours, and travel time from past visits. A loss function quantifies a discrepancy between predictions and observations so settings can be chosen to reduce it.

Settings that fit training records may fail in a new period or area. We therefore separate data used to select settings from data used for final evaluation. Population generation and behavior prediction do not have to use the same methods or training procedures.

## 6. Reading Aaru’s public description

Aaru describes users specifying an objective, target population, and questions or conditions. It then combines evidence, constructs a population, estimates responses, and returns analyzable records.[1]

Its stated sources include public demographic statistics, licensed behavioral data, and customer-provided material; the American Community Survey appears among public examples. The complete source list and integration weights are not public.[1]

Aaru describes learning a network of data-supported dependencies and sampling profiles from it, rather than generating age, employment, and income independently. That description alone does not establish a particular algorithm or graph structure.[1]

For responses, it describes learning against observed individual differences and population distributions. Its public evaluation explicitly says the core model predicting individual behavioral trajectories is not a language model. That does not mean no part of Aaru uses language models.[1][2]

The research compares predicted answer shares with public survey shares, given questions, choices, and population descriptions. It also reports purchase-ranking comparisons. Answer distributions, purchase rankings, and intervention effects remain separate evaluation targets.[2]

## 7. A general implementation flow

A basic implementation can:

1. Read sources and check column definitions, periods, and populations.
2. Count age, employment, and relevant combinations.
3. Construct profiles or weights matching those counts.
4. Supply conditions such as prices, times, or rules.
5. Predict responses under each condition.
6. Aggregate using the target population’s weights.
7. Compare with observations not used for training.

This is a teaching architecture, not a reproduction of Aaru’s code. Behavior models may use statistical choice models, rules, neural networks, or language models. The target and available observations determine the choice. Population synthesis and agent-based simulation existed before generative AI.[3]

Simile also predicts population behavior distributions. It describes learning from transaction records, interviews, surveys, and experiments. Saying “Aaru does populations, Simile does individuals” misses their overlap.[4]

## 8. Checking predictions

Keep evaluation evidence separate from model training and tuning. Choosing settings after seeing answers and claiming high accuracy on those same answers is not a fair evaluation.

If predicted attendance is 60% and observed attendance is 55%, the difference is five percentage points. It does not mean 95% of individual actions were predicted correctly. Overall agreement can also hide errors that cancel across age groups, so examine relevant subgroups.

Variation from repeatedly sampling synthetic populations differs from error caused by misrepresenting reality. Increasing generated population size can reduce sampling variation without repairing missing groups or incorrect behavioral relationships.

After population construction, response modeling, held-out evaluation, time and interactions, and real intervention effects remain distinct tasks.

## Sources

1. [Aaru, How a simulation works](https://aaru.com/simulation)
2. [Aaru, Population simulation at the replication floor](https://aaru.com/publications/population-simulation-at-the-replication-floor-summary)
3. [Farooq et al., Simulation based population synthesis, 2013](https://doi.org/10.1016/j.trb.2013.09.012). Included as a pointer to prior population-synthesis work; the method is examined separately.
4. [Simile, Building the What-If Machine](https://www.simile.com/blog/what-if-machine)

Learning draft, revised through discussion. Sources checked October 12, 2026. Illustrative numbers and company-reported claims are distinguished throughout.
