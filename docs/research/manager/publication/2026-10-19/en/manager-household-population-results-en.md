# Building a synthetic population of 441,570 households without breaking household membership

Public data for Rhode Island produced a synthetic population of 441,570 households and 1,042,763 people. Each individual received a new ID, while people belonging to the same household remained linked. Checks that read the output back found 0 missing members, orphaned individuals, duplicate IDs, or mismatches with source attributes.

![Preserving household membership while expanding sample households into a synthetic population](https://aniccaai.com/blog/manager/media/d8594aa19f99f4514eddf6d7ef672b5f549b421ad228a64345e0a44e312c049d.png)

This AI-generated explanation separates measured results from an illustrative example. The chart below was drawn from saved measurements. Image labels are in Japanese.

## From a population table to linked individuals

Reconstructing counts in six age-by-poverty categories differs from constructing a roster that records which individuals belong to the same household. Here, household members were selected together.

For an illustrative example, suppose a sample contains a household of two adults and one child. Using it twice means creating two copies of the three-person set: two households and six people. Each copy receives a different household ID, and the individuals within each copy receive new IDs. The procedure does not take only two people out of the three. This small example is fictional; the actual generation used the public samples described below.

## Housing and person records from PUMS

The source was the Census Bureau's 2020–2024 ACS 5-year Public Use Microdata Sample, or PUMS. Housing and person records are distributed in separate files and can be linked through the shared `SERIALNO` field. The selected Rhode Island sample contained 20,182 occupied regular households and 45,755 associated person records. For every selected household, the number of people in the housing record matched the number in the person records.

PUMS also includes vacant units and records associated with group quarters such as dormitories or institutions. This experiment covered regular occupied households. It separated 1,503 vacant units, the group-quarters placeholders, and 4,070 corresponding person records. The synthetic output was not treated as a named roster of real residents or real addresses.

Expanding a sample into a regional population requires deciding how many households each sample household represents. PUMS `WGTP` is a household weight and supplied the starting weights. `PWGTP` is a person weight; it was not reused as if it were a household replication count.

## Matching household type and household size

The official B11016 table supplied totals for family versus nonfamily households and for households with one, two, or three or more people. Nonfamily households include people living alone and people living with unrelated others. A one-person family household is impossible under the definition, so that cell remained a structural zero.

The baseline scaled the original household weights proportionally to the target total. The adjusted method used IPF to match the known totals by household type and size. It changed how often each sample household was used, while preserving the members of every selected household.

Evaluation compared six household-type-by-size cells, including cross-classifications such as the number of two-person family households. Those evaluation cells were not provided as cross-tabulation inputs to reconstruction. However, PUMS and the official table both come from the ACS. This is not a test against a completely independent survey.

## Turning fractional weights into household counts

An adjusted weight of 12.4 cannot become 12.4 households in a roster. The procedure first takes the integer part—12 households—and samples the remaining required households according to the fractional parts. This is the existing truncate-replicate-sample method, or TRS.

It matched the total at 441,570 households. That does not guarantee exact agreement for every household type or size. Adding one three-person household adds one household but three people, so household totals and person totals impose different constraints.

## Measuring before and after integerization

![Household-composition TVD and remaining marginal-total differences before and after integerization](https://aniccaai.com/blog/manager/media/4b110ec2b9686fb8df07c78a5c5824ec00d2e1b7bfbf806ce5f87959280ed7dd.png)

| Stage | TVD across six cells | Maximum difference from marginal totals |
|---|---:|---:|
| Before adjustment | 0.00233938 | 1,021 households |
| Adjusted fractional weights | 0.00051085 | Approximately 0.000014 households |
| Adjusted integer households | 0.00054352 | 17 households |

TVD adds the absolute differences between the six category proportions and divides the sum by two. Zero means agreement. For the integer population, TVD was approximately 76.8% lower than before adjustment. This comparison concerns one state's particular household categories. It does not establish the same improvement for other regions or every attribute, and its categories and target differ from the age-by-poverty reconstruction experiment.

Integerization reintroduced a maximum difference of 17 households from the marginal totals. For example, the target for two-person households was 151,592, while the generated count was 151,575: 17 fewer. This measures a difference from a total used in adjustment; it does not say that every evaluation cross-cell was within 17 households.

Across 10 random seeds fixed in advance, TVD after integerization ranged from 0.00045519 to 0.00058201. This range describes sampling variation, not a confidence interval for the underlying ACS estimate. A favorable seed was not selected as the headline result.

## Matching households does not perfectly match individual distributions

The adjusted population contained 1,042,763 people. As a reference, weighting the original selected person records by `PWGTP` gave 1,057,168 people. The proportions in three age groups still differed by up to approximately 0.70 percentage points. Person totals and age were not included as adjustment constraints, so these differences were recorded separately.

Copying whole households preserves the relationships represented in the sample. It does not guarantee correct distributions for every regional attribute. Adjustment methods handling both household and person constraints, and integer optimization, are further comparison candidates. Propagating uncertainty from the original survey estimates was also not implemented in this experiment.

## Repeating the experiment under the same conditions

Acquisition, membership validation, weight adjustment, integerization, CSV output, readback checks, and scoring were separated into executable steps. The same inputs and seed can regenerate the output. The design drew on PopulationSim's household expansion and ID assignment, the original TRS method, and the existing open-source `ipfn` package for IPF. It does not reproduce PopulationSim, Aaru, or Simile as complete products.

The mission is **End suffering.** Technology is a means toward it. This implementation is a population component toward that aim. Behavior prediction needs a separate test: give synthetic individuals or households a situation, predict what they might choose, and evaluate against observations of actual behavior. This experiment did not measure any reduction in suffering.

## Sources

- [Official Census housing ZIP](https://www2.census.gov/programs-surveys/acs/data/pums/2024/5-Year/csv_hri.zip) and [person ZIP](https://www2.census.gov/programs-surveys/acs/data/pums/2024/5-Year/csv_pri.zip). Both distributions include official ReadMe files.
- [PUMS data dictionary](https://www2.census.gov/programs-surveys/acs/tech_docs/pums/data_dict/PUMS_Data_Dictionary_2024.pdf)
- [B11016 definitions](https://api.census.gov/data/2024/acs/acs5/groups/B11016.json) and [official aggregate file](https://www2.census.gov/programs-surveys/acs/summary_file/2024/table-based-SF/data/5YRData/acsdt5y2024-b11016.dat)
- [Pinned PopulationSim code](https://github.com/ActivitySim/populationsim/tree/21881f0094680afbe11e2839124dfca10e61a2d2)
- [Lovelace and Ballas on integerization](https://arxiv.org/abs/1303.5228)
