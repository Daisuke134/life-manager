# Are AI neurons more readable than we thought? Reading Goodfire’s “Already Clean”

Goodfire’s Nick Cammarata argues that directly investigating neurons may be more promising than commonly assumed. His research essay *Neural Networks Are Already Clean* revisits why neural networks seem difficult to interpret. The author explicitly describes the proposal as a working hypothesis.[1]

“Clean” here does not mean safe or trained on clean data. It refers to regularities in internal computational units that people can investigate and understand. This article explains primary sources; it is not our independent reproduction of their experiments.

## The disagreement

An artificial neuron is a computational unit that weights and sums numerical inputs and applies operations such as an activation function. Collecting inputs that strongly activate a unit can suggest hypotheses about its role.

A unit may respond to apparently unrelated inputs: polysemanticity. One explanation is superposition, in which many features occupy overlapping directions within limited representational dimensions.[2]

Sparse Autoencoders (SAEs) are one approach to investigating such representations. An SAE learns to decompose original activations into many features, only a few active at once, and reconstruct the original values. SAE features are not the original neurons.[3]

Cammarata argues that some classic observations were misread as evidence for superposition. Reexamining measurement procedures and training can make original neurons directly understandable more often. This does not disprove superposition’s mathematical possibility or its existence in every real-model setting.

## A neuron responding to cats and cars

The essay examines InceptionV1 neuron `4e:55`, known for responding to cat faces and car fronts and interpreted as combining unrelated meanings.

The proposed reinterpretation is a shared V-shaped structure. The author examines upstream/downstream connections, responses to pointed shapes, and negative effects of rounded shapes. Looking only at human labels such as “cat” and “car” can obscure a common visual property.[1]

Feature visualization also needs care. Optimizing an image to increase a unit’s activation can favor an easy route rather than reveal its complete role. The essay examines an example where dog-heavy synthetic images were mistaken for a unit’s overall function. Compare optimized images with highly activating natural images and circuit connections.

## Do small models have to pack in unrelated meanings?

The article compares image models with similar parameter counts and the same data, including models with residual connections and LayerNorm. Tool improvements, retraining, and architectural changes are distinct comparisons.

The author reports approximately 0–5% interpretability of original InceptionV1 final-layer neurons with older tools, around 50% with improved tools, around 70% after modern regularized retraining of the same architecture, and around 99% for a similarly sized ConvNeXt. The introduction also describes improved final layers as 99–100% interpretable.[1]

These are not universal rates from a standardized interpretability benchmark. They depend on comparison conditions and the author’s judgments. Image-model results cannot be converted into a percentage of an LLM understood.

## Recursive generalization

The essay proposes “recursive generalization”: during training, a unit’s responses expand in related directions, then expand further.

Examples include a neuron responding to “iy,” then “diy,” then “do it yourself,” despite the final phrase lacking those letters; and a geology-related neuron responding to the geography-oriented JavaScript library Cesium.[1]

Apparently unrelated final examples may have intelligible connections in training histories or circuits. This has not independently established an explanation for every polysemantic neuron.

## What the Qwen investigation reports

Curt Tigges contributed to the language-neuron work. For preliminary Qwen3-32B analysis, the essay reports roughly 90% with one main role, 7% with two related roles, and 2–4% not understood, considering positive and negative sides. These rounded estimates should not be added as an exact partition.[1]

The essay also provides a browser for 1,000-neuron investigations in Qwen3-32B and Qwen3.6-35B-A3B. The author notes that including weak responses or changing the definition of one role changes these numbers. This does not mean “90% of AI thought has been explained.”

Qwen3-32B unit `L1/N20736` is particularly concrete. Its highest-activation texts include references to Colossians, suggesting a detector for that New Testament text. Examining SwiGLU’s branches instead supports an interpretation involving tokens that complete Russia-related words.[1]

SwiGLU multiplies a gate branch and a value branch. The gate is not a simple 0/1 switch and may be negative. Two negative values multiply to a positive output, so collecting only positive outputs can mix different internal regimes. The essay investigates this “double-negative regime.” This MLP value branch is not Attention’s V.

The lesson is that naming a neuron from its highest outputs alone can miss the computation producing them.

## Testing explanations

Collect activating texts and propose a common feature. Then test inputs the hypothesis predicts should activate the unit and similar inputs that should not. Inspect connected units and, where appropriate, alter activations or remove circuit components to measure output changes.

Observed correlation and causal contribution to output differ. Even an internal intervention needs checks for strength, specificity, and side effects across inputs before establishing a complete natural-inference role.

## Why this matters, and what remains

If the proposal replicates broadly, it supports greater effort on original-network investigation. The essay also envisages AI agents repeatedly forming hypotheses, running experiments, inspecting connections, and cross-checking explanations across circuits.

It remains a working hypothesis, with detailed language-model methodology deferred to a technical follow-up. Successful examples, neuron interpretability rates, whole-network prediction, and safety are different targets. Independent replication, criteria, untested inputs, intervention specificity, and comparisons with SAE approaches remain important.

## Connection to Manager

Future internal analysis could suggest why a behavior model responds to fares or age. A model’s verbal explanation of its answer is different from experimental evidence about its mechanisms.

Causation inside a model also differs from causation in society. Changing a neuron and moving a use prediction does not show that lowering actual fares increases real use. Such analysis usually requires access to weights or activations; a text API alone may not provide it.

## Sources and scope

Based on the original essay as checked October 18, 2026. No independent replication or quantitative study of public attention was performed.

1. Nick Cammarata, [Neural Networks Are Already Clean](https://already-clean.goodfire.com/), with language-neuron contributions from Curt Tigges; working hypothesis.
2. Elhage et al., [Toy Models of Superposition](https://transformer-circuits.pub/2022/toy_model/index.html), 2022.
3. Bricken et al., [Towards Monosemanticity](https://transformer-circuits.pub/2023/monosemantic-features/index.html), 2023.
