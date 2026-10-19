# Integerizing a synthetic population while preserving people, households, and geography

Small numerical examples here are fictional, not measured population-generation results.

![Integerization, households, and geographic consistency](https://aniccaai.com/blog/manager/media/f7abe9b37eac34af40253544d14d7d114dd7044345b5d9466370a1898ce7f690.png)

Illustration retains Japanese labels.

## Purpose

Population synthesis must represent not only attribute combinations but how many people and households belong in each area. Three records labeled “household size three” need not belong to the same household. A `household_id` makes membership explicit and preserves the composition.

## Integerization

Weights 1.4, 1.4, and 1.2 sum to four, but separate rounding gives `1 + 1 + 1 = 3`. Counts two, one, and one preserve a total of four, although this illustrative choice does not guarantee every attribute total. TRS replicates integer parts and samples the remaining required records with probabilities based on fractional remainders. With households, household count and person count are different constraints.

## Households and areas

Candidate A contains one adult, B contains two adults and one child, and C contains two adults. If an area requires two households, four people, three adults, and one child, choosing one A and one B matches all controls. We enumerated candidate counts with standard Python to check this combination. This is an optimization lesson, not deployment of a practical solver or real-world validation.

When copying a household, assign each copy a new household ID and attach that copy’s original members. The copies remain separate households.

## Existing implementations

We retrieved PopulationSim commit `21881f0094680afbe11e2839124dfca10e61a2d2` and read `populationsim/steps/expand_households.py` and `write_synthetic_population.py`. The former uses integer-weight `np.repeat`; the latter assigns `synthetic_hh_id` and joins seed attributes. PopulationSim uses methods including list balancing, not simply ordinary IPF. It was not run for this explainer.

COMPASS, published October 7, 2026, uses combinatorial optimization with household/person constraints. It reconstructs artificial Meropis populations from aggregates and samples. Matching totals does not guarantee unseen combinations or accuracy for a real population.

## Applying this to Manager

Record household/person/geographic IDs, distinguish observations from estimates, and report errors before and after integerization. Reconstructing a small aggregate table and producing household lists need different components. Add household structure when interactions or shared resources require it.

## Sources

- https://activitysim.github.io/populationsim/application_configuration.html
- https://github.com/ActivitySim/populationsim/tree/21881f0094680afbe11e2839124dfca10e61a2d2
- https://arxiv.org/abs/1303.5228
- https://robinlovelace.net/spatial-microsim-book/smsim-in-R.html
- https://journals.sagepub.com/doi/10.1177/23998083261484652
