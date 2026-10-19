# Generating populations with GANs: the generator and discriminator

![Conceptual GAN mechanism](https://aniccaai.com/blog/manager/media/508711f3df00ba5ce381dbeecb8c99351ebbc9733e4f351d1110d0ec2b2adfce.png)

Japanese labels. Resident-card values are fictional, not measured results.

GAN means Generative Adversarial Network, introduced by Goodfellow and colleagues in 2014.[1]

## What is learned?

Given survey records of resident attributes, a generator G takes random inputs and creates synthetic records. A discriminator D learns to distinguish observed survey records from generated records. G is then updated to produce records D finds harder to distinguish. Training alternates these updates.

One analogy is a person making practice questions alongside someone judging whether they resemble an existing collection. Both improve, but D is not a judge with knowledge of the entire real population.

A basic VAE uses encoding, decoding, reconstruction, and KL regularization. A basic GAN uses competition between G and D as its training signal. Hybrid methods exist, so this is not an absolute classification of every implementation.

## A population example

Suppose fictional source proportions are younger/employed 40%, younger/not employed 20%, older/employed 10%, and older/not employed 30%.

If G generates only younger employed people, D has evidence of a difference from the source. But successfully confusing D does not guarantee minority coverage or real-world accuracy. Check mode collapse—generating mostly a few kinds—and evaluate against independent evidence.

After training, generation follows `random input → trained G → attributes`. The basic procedure does not require D to rescore every generated record.

## Reading code

In `vdarsel/PopulationSynthesis`, `models/GAN/WGAN/model_WGAN_alone.py` defines `Generator_Tabular`, `Discriminator_Tabular`, and a gradient penalty. `train_WGAN_alone.py` uses separate optimizers for D and G. During D’s update, `fake_data.detach()` prevents simultaneously updating G through those generated values.[2]

This is a WGAN-family implementation with a different objective from a standard GAN. Do not apply the elementary description “outputs a probability of being real” to every WGAN. The retrieved code also ends D with Sigmoid; we should inspect that difference rather than assume an exact textbook WGAN-GP implementation. Code availability and reuse permission are separate questions.

## What we checked

We read generator/discriminator code statically; we did not train a GAN. Teaching calculations check how a standard GAN generator’s loss changes with D’s output and how even a copy-based generator can distort a distribution. These are not real-population performance measurements or reproduction of the authors’ experiments.

The adversarial training signal and mode collapse are useful comparison points when studying diffusion models’ denoising approach.

1. [Goodfellow et al. 2014, method section 3](https://arxiv.org/html/1406.2661v1).
2. [Public code read statically](https://github.com/vdarsel/PopulationSynthesis).
