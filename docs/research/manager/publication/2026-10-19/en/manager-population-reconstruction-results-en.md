# Reconstructing a population from public statistics: IPF versus a simple baseline

Given only counts by age and counts by poverty status, we reconstructed how many people in each age group fell below the poverty threshold. The experiment ran on October 18, 2026, using the 50 US states and DC. Across the 41 regions reserved for final evaluation, mean total variation distance was 0.01435 for the simple baseline and 0.00888 for IPF. The average improved, but IPF performed worse in 12 regions.

![The population-reconstruction experiment and its connection to later behavior prediction](https://aniccaai.com/blog/manager/media/441e6c94305611e6e848ee00552f6e8d72ca30ea5cb22459685a86df76979ee1.png)

This AI-generated diagram explains the scope of the implementation; its result-card numbers come from measured results. The chart below was plotted from saved aggregate results with matplotlib. Image labels are in Japanese.

## What went into the reconstruction, and what was evaluated?

Suppose a region reports how many residents are children, adults, or older adults, and how many fall below or above the poverty threshold. Those totals do not uniquely determine how many children fall below the threshold. We reconstructed the six cells formed by three age groups and two poverty categories, then compared them with the source's cross-tabulation.

The source was ACS 2024 5-year Detailed Table B17001, an estimate based on the 2020–2024 survey period. Its population is people for whom poverty status can be determined. It does not directly measure income amounts or psychological suffering.

We compared two methods. The independence baseline multiplies each region's age proportions by its poverty proportions. Iterative proportional fitting, or IPF, starts from a detailed table built from six development states and adjusts it to match the target region's age totals and poverty totals. The comparison tests whether transferring the relationships represented in the initial table helps reconstruct another region.

The reconstruction command did not receive the target region's cross-tabulation. Only a separate scoring command opened that table. The split into six development states, four validation states, and 41 final-evaluation regions was fixed before execution. However, the marginal totals and evaluation cross-tabulations came from the same ACS source. This is not validation against an independently collected survey.

## Reading the results

Total variation distance, or TVD, adds the absolute differences between the six cell proportions and divides the sum by two. Zero means agreement; one is the maximum. A TVD of 0.01 corresponds to moving approximately 1% of the region's population between categories to make the allocations agree. It does not mean that individual behavior was predicted with 99% accuracy.

![Mean TVD for development, validation, and final-evaluation regions](https://aniccaai.com/blog/manager/media/c3e8ba63bd7fce272884fec4e10119de2c720047ca4a3ad16e1d4a55e2ce5e67.png)

| Evaluation group | Independence baseline | IPF |
|---|---:|---:|
| Unweighted regional mean TVD, six development states | 0.015544 | 0.003100 |
| Unweighted regional mean TVD, four validation states | 0.017104 | 0.005243 |
| Unweighted regional mean TVD, 41 final-evaluation regions | 0.014348 | 0.008881 |
| Population-weighted mean TVD, 41 final-evaluation regions | 0.015560 | 0.007666 |
| Maximum TVD, 41 final-evaluation regions | 0.033504 | 0.015971 |

The regional mean gives every region equal weight. The population-weighted mean gives larger populations more weight. The final-evaluation regional mean fell by approximately 38.1%, but the improvement was not universal: IPF was better in 29 regions and worse in 12.

Consider the proportion of children below the poverty threshold. Ohio's ACS estimate was 17.78%. The baseline reconstructed 13.29%, while IPF reconstructed 17.24%, bringing it closer. Utah's ACS estimate was 8.76%; the baseline produced 8.50% and IPF produced 10.96%. The denominator here is the number of children in each region.

For all six cells together, Utah's TVD was 0.002432 for the baseline and 0.012673 for IPF. In Utah, assuming independence between age and poverty status came closer to the ACS estimate than transferring the relationship observed in the development states. These failures were retained. The initial table and settings were not changed after inspecting the evaluation.

## What the implementation checked

Data acquisition, input validation, splitting, reconstruction, and scoring were separate operations. IPF used the existing open-source package `ipfn==1.4.4`, with an independent check of residual differences from the marginal totals. Missing values were not silently filled with zero, and failure to converge was not counted as success.

Both methods reconstructed all 51 regions. Repeating the run from the same inputs produced prediction files that matched byte for byte. Additional paid model calls numbered 0. Source references, input hashes, configuration hashes, and code hashes were recorded alongside the results for each split.

ACS values also have estimation error, which this experiment did not propagate into its results. The regional split was not a random sample, so no confidence interval for nationwide generalization is reported. The result establishes how closely these methods reconstructed public cross-tabulations under these particular conditions.

## Adding households and behavior

[A population component linking households and individuals](https://aniccaai.com/blog/manager-household-population-results-en) needs to retain who lives together, rather than recording age alone. It can select whole households and adjust their representation to match regional statistics. A model predicting choices or actions from attributes and circumstances is a further, separate component.

The mission is **End suffering.** Technology is a means toward it. Reconstructing population composition is one component toward that aim. Behavior prediction, comparison of interventions, execution, and real-world benefits each require their own measurements.

## Sources and reproducibility

- [Census official Summary File](https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b17001.dat)
- [B17001 variable definitions](https://api.census.gov/data/2024/acs/acs5/groups/B17001.json)
- [Pinned ipfn source](https://github.com/Dirguis/ipfn/tree/fa57b905291e4125c6e4f7ddacc8770218ad024e)

The SHA256 of the extracted state data was `316b602beb75129605d91ca7a9c440a37df7bc9c02271d86d3eb39cf25559a9d`. This is not the hash of the complete official distribution file.
