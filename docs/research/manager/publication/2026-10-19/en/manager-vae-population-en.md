# Generating populations with VAEs: learning combinations of attributes

Sources checked October 17, 2026. This introduction distinguishes the basic model, paper-specific extensions, and the code we read.

## Learning combinations

We want synthetic residents with attributes such as age, employment, and income. IPF adjusts an initial table to known aggregates. A Bayesian network represents a joint distribution through dependencies and local probabilities. A VAE instead uses a neural network to learn the distribution of attribute combinations. These do not exhaust population-synthesis methods. Generating people and predicting their responses also remain separate tasks.

![VAE training and generation](https://aniccaai.com/blog/manager/media/af487ccd0c5d711816bfa1ca60335c08ebe98284cf15e2bf524136e4cc504f17.png)

Figures retain Japanese labels.

## 1. What training changes

A survey row might describe a 35-year-old, employed person in income category B and a four-person household. Many rows let a model learn which attributes tend to occur together. Training gradually changes internal numerical parameters to reduce an objective function. Those parameters are different from population-representation weights.

VAE means Variational Autoencoder, building on Kingma and Welling’s original paper. It is a general generative-model family and does not require an LLM.

## 2. Encoder and decoder

An ordinary autoencoder’s encoder converts a record into an internal representation, and its decoder reconstructs attributes from it. Think of a compact internal note about a recipe, followed by practicing reconstruction from the note. The note need not be readable by people.

A typical VAE encoder outputs the mean and spread of a Gaussian distribution over latent variables. A sample from that distribution enters the decoder. Latent variables are internal variables absent from the original record; an axis need not correspond neatly to age or income. “Variational” refers to approximating a difficult posterior distribution with a tractable one.

Training follows `observed record → encoder → sample from that record’s latent distribution → decoder → reconstruction`. New generation follows `sample from prior → trained decoder → new record`. A new real person’s input record is not required for every generated person.

## 3. Two training objectives

The first objective reduces reconstruction error. Numerical and categorical attributes require appropriate treatments; for categories, the model should assign high probability to the correct category.

The second prevents the encoder’s distributions from straying too far from a prior, often a standard normal distribution. A KL-divergence term measures that discrepancy. KL divergence is not symmetric like an ordinary distance.

The minimized objective is roughly reconstruction loss plus a KL term. Reconstruction alone does not guarantee good samples from the prior. Overemphasizing KL can lose attribute information. Weights, architecture, and training behavior matter.

For a diagonal Gaussian, sampling can be written `z = mu + sigma * epsilon`, with epsilon standard normal. This reparameterization enables gradient-based training through a model containing sampling. Mu is the mean, sigma the standard deviation, and variance is sigma squared.

## 4. What generation produces

The output is a record such as “28, not employed, income category A,” not a new observation. A combination absent from the original sample is not thereby proven to exist. Logical contradictions are not automatically prevented.

Some decoders output per-attribute category probabilities. Check how each implementation turns those probabilities into records. Sampling procedures differ, and neural networks do not guarantee accurate minority-group distributions.

## 5. Research examples

### Borysov, Rich, and Pereira (2019)

Using Danish travel-survey data, the study compared VAE, Gibbs sampling, and Bayesian networks. Alternatives performed better in lower dimensions; VAE’s advantages were examined with many attributes. “Newer is always more accurate” is not the conclusion. A VAE can generate candidate records before a separate geographic fitting step; VAE generation and IPF are not necessarily alternatives.[1]

### Kim and Bansal (2023), and PopSynth

This work addresses feasibility and diversity together. Its public VAE notebook adds a sample-based Hamming-distance term to reconstruction and KL. Merely copying training rows or inventing arbitrary combinations is insufficient. The code’s distance measure is not a complete oracle for real-world feasibility.[2]

### Sané and colleagues (2025)

The study compares VAEs representing households and their members together. SVAE-Pop2 uses padding for different household sizes; MVAE-Pop2 separates models by household size. Padding slots in the figure are not people. This addresses inconsistent household size and member records that can arise when individuals are generated independently. Results should not be generalized beyond the study’s population, size limits, and evaluation conditions. We did not verify author implementation code.[3]

![Generating households and individuals together](https://aniccaai.com/blog/manager/media/f1b0f3aa23b8141b3d33d9ec57b098cc09525d51c569ed98f9e8f4637361df12.png)

## 6. Public code

In `Eui-Jin/PopSynth`, `VAE_OOSDivH_SampleCode.ipynb` builds an encoder outputting mean and log variance, a sampling operation, and a decoder with attribute-specific softmax outputs. `vae_loss` combines reconstruction, KL, and Hamming terms. The generation model reuses the decoder with standard-normal inputs. Despite its name, `generate_images` outputs population attributes in this application, not images.

A shortened teaching sketch—not a fully executed training program—is:

```python
mu, log_variance = encoder(records)
sigma = exp(log_variance / 2)
z = mu + sigma * standard_normal()
reconstructed = decoder(z)
# Update the model using reconstruction, KL, and any additional loss terms.
# After training, generate with decoder(standard_normal(...)).
```

We also read `ctgan/synthesizers/tvae.py` in `sdv-dev/CTGAN`. This general tabular TVAE is not Borysov’s author implementation. The inspected version uses Business Source License 1.1; public code does not imply unrestricted commercial reuse. PopSynth’s code is MIT, while attached data needs a separate rights check. Neither model was trained or used for generation here.

## 7. Evaluating a population

Choose held-out evidence and comparison conditions before training. Evaluate not only supplied age totals but unused age × employment × income tables. Compare simple methods, IPF, Bayesian networks, and VAEs on the same target and underlying evidence. Report differences in input requirements.

Check aggregate and held-out combination errors, structural contradictions, rare-group coverage, copied records, cost, runtime, and variation across seeds. Publishing generated records does not guarantee anonymity; privacy also needs evaluation. Distributional agreement does not prove an ability to predict causal policy effects.

## 8. Comparing methods responsibly

When comparing GANs, diffusion models, and LLMs, distinguish training from generation. Include household structure, missingness, rare combinations, conditioning, evaluation, privacy, and geographic or temporal transfer. Reading a paper, reading code, executing it, and reproducing results are different achievements.

## Sources

1. Borysov, Rich, Pereira, [Scalable Population Synthesis with Deep Generative Modeling](https://arxiv.org/html/1808.06910v2). The 2019 journal version is *How to generate micro-agents?*, DOI:10.1016/j.trc.2019.07.006.
2. Kim, Bansal, [A deep generative model for feasible and diverse population synthesis](https://doi.org/10.1016/j.trc.2023.104053), 2023; [author code](https://github.com/Eui-Jin/PopSynth).
3. Sané et al., [Population synthesis with deep generative model: a joint household-individual approach](https://link.springer.com/article/10.1007/s43762-025-00195-9), 2025.
4. Kingma, Welling, [Auto-Encoding Variational Bayes](https://arxiv.org/abs/1312.6114).
5. [TVAE code inspected](https://github.com/sdv-dev/CTGAN); consult the pinned version’s LICENSE.
6. [Darsel et al., reproducible population-synthesis comparison repository](https://github.com/vdarsel/PopulationSynthesis). README, beta-VAE, and aggregate-error functions were read statically; no training/evaluation run. No root LICENSE was found in the retrieved version, so reuse permission remains unverified.

This article explains public sources. It does not establish commercial companies’ private implementations.
