# Comparing population-generation methods for Manager

Choose population methods from available evidence and required constraints. Our initial six-cell reconstruction compares an independence baseline with existing IPF. At household/person level, resampling intact households and fitting aggregates is the starting design, with Bayesian networks as a comparison. Higher dimensionality may justify diffusion or LLM comparisons. These are research-informed design decisions, not our measured ranking of every method.

## Strengths and limitations

| Method | Main input and operation | Strength | Limitation | Role for Manager |
|---|---|---|---|---|
| Independence baseline | Multiply separate attribute proportions | Cheap, reproducible baseline for added value | Cannot represent associations | Required population-v0 comparator |
| IPF/reweighting | Fit an initial table or sample weights to controls | Clear fitting objective and inspectable calculations | Initial relationships matter; multiplication cannot fill zeros; unknown combinations unguaranteed | Existing `ipfn` for aggregate v0 |
| Household resampling, IPU/list balancing | Linked household/person samples and controls | Preserves household links and multiple levels | Missing examples, extreme weights, integerization errors; IPU is not PopulationSim’s exact algorithm | Baseline PUMS household design; assess existing implementations |
| Bayesian network | Learn dependencies and probabilities from microdata | Inspectable dependencies; relatively light generation | Conditional-independence assumptions, sparse rare conditions; no automatic household/control guarantee | Strong microdata-generation comparator |
| MCMC/conditional sampling | Repeated state updates using conditional distributions | Can construct conditional samplers | Mixing, convergence, autocorrelation; can combine with networks | When conditional generation is needed |
| Combinatorial/annealing/integer optimization | Search household combinations under local constraints | Explicit integer, household, and geographic requirements | Runtime, local solutions, insufficient candidates, infeasible constraints, approximate solvers | Existing allocation/integerization candidates |
| VAE | Learn latent distributions and reconstruction | Often manageable training and fast sampling | Rare combinations, violations, latent interpretation | Test added value |
| GAN | Alternate generator/discriminator updates | Complex distributions and fast trained generation | Tuning, mode collapse, minority omission | Select by comparison, not initial default |
| Diffusion | Learn denoising updates and generate iteratively | Promising comparisons on mixed attributes | Iterative cost, categories, constraint checks | Strong deep-model candidate |
| Fine-tuned LLM | Serialize microdata and learn token prediction | Combines attribute meanings with survey patterns | Cost, memorization, distribution errors, invalid outputs, order/settings sensitivity | Compare when microdata and a plausible added benefit exist |
| Prompt/statistical-feedback LLM | Prompt with controls/schema and feed discrepancies back | Can work without local microdata; textual conditioning | Unknown combinations supplied by model; accuracy, realism, prompt robustness, and cost need testing | Candidate without microdata, not required when PUMS is available |

These components play different roles and can be combined. Installing all of them is not a strategy for obtaining the best result. TRS and integer optimization can turn fractional weights into record counts; do not rank that role indiscriminately against attribute-learning models.

## What the comparisons support

Darsel et al. 2026 found Bayesian networks a strong accuracy/cost compromise and diffusion promising among deep models on 12 French attributes. This is not a result for every domain or dimensionality, nor a direct IPF/LLM comparison. In Lim, Yun, and colleagues, fine-tuned LLMs did well on a reference-combination metric while VAE/WGAN had lower distribution errors. Jones and colleagues’ LLM/IPU ordering varied by attribute; IPU led on average, speed, and cost.

Define “best” using the same evidence, held-out evaluation, units, generated counts, household requirements, minority groups, seeds, runtime, and cost. Report supplied-control fit, unused higher-order combinations, logical contradictions, copying, and privacy separately rather than hiding everything in one number.

See the [method-selection review](https://aniccaai.com/blog/manager-population-method-selection-en), [dataset guide](https://aniccaai.com/blog/manager-population-dataset-selection-en), and [household/integerization guide](https://aniccaai.com/blog/manager-household-integerization-en) for primary sources and reading scope.

## Deep generation and LLM internals

| Method | Training | New-record generation |
|---|---|---|
| Variational Autoencoder (VAE) | Encode attributes, reconstruct records, regularize latent distributions | Sample a prior and decode |
| Generative Adversarial Network (GAN) | Alternate generator and discriminator updates | Pass random input to the trained generator |
| Diffusion | Predict noise or original data from corrupted records | Repeatedly update fresh noise using the trained model |
| Large Language Model (LLM) | Predict successive tokens; optionally fine-tune on population records | Generate attributes as text/structured output, optionally conditioned on aggregates |

The same “30s, employed, three-person household” can arise from different calculations. LLM fine-tuning updates parameters; statistical prompt feedback need not. Hybrid models include diffusion in VAE latent space and Bayesian-network ordering for LLM training. Bayesian networks explicitly represent dependencies and conditional distributions and remain another candidate.

Evaluate proportions, unknown relationships, rare groups, violations, copying, and cost under common conditions. Population-generation success is separate from behavior prediction or real intervention success. This is an explanation of methods, not our own model leaderboard.

Further explanations and checked sources:

- [VAE](https://aniccaai.com/blog/manager-vae-population-en)
- [GAN](https://aniccaai.com/blog/manager-gan-population-en)
- [Diffusion](https://aniccaai.com/blog/manager-diffusion-population-en)
- [LLM](https://aniccaai.com/blog/manager-llm-population-en)

![Deep generative models and LLMs](https://aniccaai.com/blog/manager/media/77f5eba6ed1ce20119a9fe77c4204c19194a26e47b6706277d676fff84236944.png)

Illustration retains Japanese labels.
