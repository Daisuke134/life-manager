# Generating populations with LLMs: fine-tuning versus prompting

![Two LLM population-generation approaches](https://aniccaai.com/blog/manager/media/c75b55eb16b7e3914ac451c9684efee3a7e435eb77ce6bdb699ffb17972acc92.png)

Japanese labels. Sources checked October 18, 2026. An LLM is a Large Language Model. This article concerns generating attributes of synthetic individuals and households. Behavior prediction and intervention-effect measurement are separate tasks.

## 1. Why text generation can produce population records

A population-table row can be written as “Age group is 30–39, occupation is office work, household size is three.” An LLM divides text into tokens and assigns probabilities to the next token given preceding tokens. Repeatedly choosing continuations can produce one person’s record.

Natural prose does not guarantee realistic population totals or attribute combinations. Producing mostly linguistically typical people can underrepresent minority groups.

## 2. Approach A: fine-tune on microdata

Serialize target survey records and train an existing language model on them. Fine-tuning updates internal numerical parameters from data; temporarily supplying records in a prompt does not.

SFT means supervised fine-tuning. In the inspected population code, serialized records are target sequences and training increases the probability of their successive tokens. This differs in inputs and evaluation from chat instruction-following, despite sharing the SFT name. These parameters also differ from population weights.

Yun and colleagues serialize attributes in orders informed by a Bayesian network’s dependency structure. The network guides ordering for LLM training, rather than generating the entire population itself. The implementation can choose among orders consistent with the structure rather than fixing just one.[1][2]

If household size comes first, later attribute generation can use it as context. Ordering alone does not guarantee causal meaning or household consistency.

## 3. Code read and operation executed

In `HyunsooYun/llm-pop-synth`, `utils/text_encoder.py` maps numeric codes to meaningful phrases and combines fields in a specified order. `LLM-BN/train.ipynb` uses network-informed ordering, and `BN_generator.py` loads DistilGPT-2. Passing `labels=input_ids` computes a loss, followed by backpropagation and optimizer updates.

We ran upstream `TextEncoder.encode_row` with three fictional attributes. Its literal output was `Age group is 30-39, Work type is マネージャー/Office, Number of household members is 3.` This is serialization, not LLM training or inference. The code is MIT; data and model terms need separate checks.[2]

## 4. Approach B: prompt with aggregates

When local microdata is unavailable, prompts can contain public statistics and the required output format. Jones, Dawson, and Mills’ 2026 study generates households from aggregates and feeds discrepancies between current and target statistics into subsequent prompts. It does not require fine-tuning the model.[3]

Consider a fictional target of 100 people: 60 younger and 40 older. If 50 generated people contain 20 younger and 30 older people, exact completion would require another 40 younger and 10 older people. Software can calculate that difference. Expressing it in a prompt does not guarantee the LLM produces precisely those counts.

In the public code, `generate_households` in `engine/generator.py` advances batch generation and calls `update_prompt_with_statistics`. `generation/prompts.py` inserts statistics into templates. Output schemas and optional consistency checks can be configured.[4]

This loop changes the population under construction and the prompt, not necessarily internal model parameters. Reducing a statistical discrepancy is also different from learning whether a real intervention improves lives.

## 5. Comparing the approaches

| Aspect | Fine-tuning on microdata | Prompting with aggregates |
|---|---|---|
| Main input | Individual survey records | Public aggregates, format, context |
| Internal model parameters | Updated during training | Unchanged in this example |
| Aggregate agreement | Check after generation | Check even with statistical feedback |
| Main concerns | Sampling bias, training cost, memorization | Unknown joint distributions, prompt sensitivity, generation cost |

“Sample-free” means target-area microdata is not required. It does not mean no pretrained model or public statistics are needed. Unknown relationships may depend on pretraining tendencies.

## 6. Evaluation

Check schema and definitional consistency programmatically, then supplied aggregate agreement, then relationships in cross-tabulations withheld from generation and fitting. Examine prompt wording, randomness, model versions, cost, minority groups, and record copying.

In Yun and colleagues’ public manuscript, LLM methods perform well on a feasibility proxy while VAE/WGAN methods perform better on some distributional measures. A combination missing from a finite reference dataset is not automatically logically impossible. Jones and colleagues’ IPU comparison likewise depends on variables, cost, and available evidence. Novelty alone is not a result.

## 7. Scope

We read papers and code and executed the upstream serialization function. We did not fine-tune on real data, download a model, run LLM inference, call an API, or measure generated real-population performance. Numerical examples are fictional.

Evaluate household–person consistency, distributional agreement, and performance on unused data separately.

## Sources

1. Yun et al., [public manuscript](https://arxiv.org/pdf/2505.04196); [2026 journal version](https://doi.org/10.1016/j.trc.2026.105581).
2. [Author code](https://github.com/HyunsooYun/llm-pop-synth).
3. Jones, Dawson, Mills, [2026 paper](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0341704); [Figure 10 correction checked](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0356492).
4. [Author code](https://github.com/MJones235/LLM-Population-Generator). Do not assume the current code is identical to the paper’s release.

![Language-model generation and parameter updates](https://aniccaai.com/blog/manager/media/29800756ba241a433e6e8e24d07807f378f37ad40158fb525e2d1365ac694ecb.png)
