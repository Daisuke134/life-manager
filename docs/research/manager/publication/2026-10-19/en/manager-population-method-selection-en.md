# Which population-synthesis method should we use? Reviews and recent comparisons

Sources checked October 17, 2026. A recent paper does not determine a winner for every use case. Compare inputs, objectives, and evaluation conditions. Population synthesis and social simulation that assigns behavior to a population are separate tasks.

## Before choosing a method name

La, Vu, Kamruzzaman, and Miller’s 2025 review organizes problems around data limitations, population diversity, dimensionality, and adaptability. We read its classification, household relationships, computational considerations, transfer, and conclusions in the author manuscript. Accuracy in one place does not establish transferability or household consistency. Start with required attributes and available evidence, not “VAE or LLM?”[1]

Chapuis, Taillandier, and Drogoul distinguish generation methods from their actual use to initialize social simulations. Their review emphasizes reporting implementation and initialization. It surveys JASSS, not every discipline or a universal ranking.[2]

## Recent comparative evidence

### Darsel and colleagues: deep models and Bayesian networks

We retrieved the final 2026 PDF from HAL and read methods, results, conclusions, and limitations. Distinguish it from the 2025 hEART short paper, including data versions and metrics. The final paper proposes evaluation of distributions, realism, and privacy, comparing Bayesian networks, MCMC, VAEs, GANs, and diffusion on 12 attributes from French population data with smaller and larger training sets.[3][4]

In that setting, Bayesian networks offered the strongest trade-off, and diffusion was promising among deep models. This does not establish the ordering with more attributes or in another region. The comparison did not include LLMs or IPF.

Metrics include average three-way distribution error (SRMSE3), the share of generated records containing attribute pairs absent from the reference (SSCIOD), and a training-proximity measure compared with evaluation records (WDCR). Pair checks can miss contradictions visible only in three or more attributes. Privacy metrics are not formal privacy guarantees. Absence from a finite reference is not logical impossibility.

We read beta-VAE, WGAN, and aggregate-error code in the author repository. Distinguish later metric/code revisions from earlier manuscripts. No root LICENSE was verified, so public availability is not unconditional permission to redistribute or incorporate the code in a product.

### Yun and colleagues: what does the LLM improve?

We read the public manuscript associated with the 2026 journal article and inspected `HyunsooYun/llm-pop-synth`. It serializes records to fine-tune a small language model and compares ordering guided by Bayesian-network dependencies. Its tables favor LLM methods on a feasibility proxy, while VAE/WGAN methods have better marginal and bivariate distribution agreement. There is no single winner.[5]

The roughly one-million-record h-population is a combined survey reference, not complete ground truth for every resident. An unobserved combination is not automatically impossible. Feasibility is a proxy dependent on this finite reference. Code is MIT; data conditions require a separate check.

### Jones, Dawson, and Mills: LLMs without local microdata

The 2026 PLOS ONE paper generates households from aggregates and feeds discrepancies into later prompts. In its Newcastle comparison, the LLM did well on attributes such as age, while IPU did better on household composition, the all-variable average, speed, and cost. The choice depends on attributes and evidence. This compares IPU, not every IPF implementation.[6]

Aggregate agreement does not guarantee unknown higher-order relationships, and prompts affect results. We also read the August 19, 2026 correction: Figure 10 was replaced with results from 20 repetitions rather than a preliminary experiment.[7]

## Beyond population generation

Larooij and Törnberg review validation of LLM-based agent models. Purpose-specific evaluation, comparison with observations, repeated runs, and sensitivity checks matter. Natural dialogue alone does not establish reproduction of a social phenomenon.[8]

Reproducing age distributions does not establish accurate purchase response to price changes. Evaluate population, behavior, interactions, and causal intervention effects separately.

## Selection criteria

| Available evidence or task | First candidates to compare | Main caveat |
|---|---|---|
| A table matching a few aggregates | Simple baseline and IPF | Dependence on the initial table and unknown relationships |
| Microdata for learning dependencies | Bayesian network and resampling | Rare conditions and structure-learning burden |
| Many mixed attributes and new combinations | Add VAE, GAN, diffusion | Cost, violations, and coverage |
| Household proposals without microdata | Conventional sample-free methods and LLM | Unknown joint distributions and prompt dependence |
| Interactions and policy effects | Separate behavior model and agent simulation | A population generator is insufficient |

This is a source-based selection proposal, not our own completed benchmark of every method. Compare the same evidence, held-out cross-tabs, structural constraints, minority coverage, seeds, and computational cost. If accuracy differs slightly but cost differs greatly, report the trade-off instead of hiding it in one score.

## Sources and reading scope

1. La et al. 2025, [author manuscript](https://www.researchgate.net/publication/389527876_Population_synthesis_a_problem-based_review); [journal DOI](https://doi.org/10.1080/01441647.2025.2469069).
2. Chapuis et al. 2022, [methods, evaluation, and discussion](https://www.jasss.org/25/2/6.html).
3. Darsel et al. 2026, [final methods, results, and limitations](https://hal.science/hal-05758634/document); [DOI](https://doi.org/10.1016/j.trc.2026.105627).
4. [2025 preliminary short paper](https://transp-or.epfl.ch/heart/2025/abstracts/hEART_2025_shortpaper_95.pdf); [code](https://github.com/vdarsel/PopulationSynthesis).
5. Yun et al., [2026 journal DOI](https://doi.org/10.1016/j.trc.2026.105581); [manuscript read](https://arxiv.org/pdf/2505.04196); [code](https://github.com/HyunsooYun/llm-pop-synth).
6. Jones et al. 2026, [methods, comparison, and limitations](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0341704).
7. [Figure correction](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0356492).
8. Larooij and Törnberg, [review published in 2025, in the 2026 volume](https://pmc.ncbi.nlm.nih.gov/articles/PMC12627210/).

This is not an exhaustive systematic review of the latest literature.
