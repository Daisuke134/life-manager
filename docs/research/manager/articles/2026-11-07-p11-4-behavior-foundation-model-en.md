# A Bigger Language Model Is Not Automatically a Better Model of Human Behavior

*Anicca Research · Manager Masterclass P11-4 · November 7, 2026*

A language model can write a convincing explanation of why someone might choose an option. That does not mean it can accurately predict what an unfamiliar person will choose.

For a behavioral foundation model, the real test is whether representations learned from observed human choices generalize beyond the people, studies, eras, and cultures in the training set.

**Running a large model, fine-tuning a model, and demonstrating general behavioral prediction are three different milestones.**

![Original synthetic chart comparing shared and task-specific prediction on two conflicting domains](https://aniccaai.com/blog/manager/media/9b654e122d5ccbc55b8f5f4f2ae65b04d4cfe4101164c11c6018bdc67caf9d1f.png)

## What Centaur actually did

The 2025 Nature paper on *Centaur* brought behavioral foundation models into sharp focus. Psych-101 contains 160 psychological experiments, 60,092 participants, and 10,681,650 trial-by-trial choices.

Centaur used Llama 3.1 70B as a backbone with quantized low-rank adapters (QLoRA). The authors applied rank-eight adapters and masked the training loss so that learning targeted **the tokens corresponding to human responses**, not the experimental instructions. Their paper reports roughly five days of fine-tuning on an A100 80GB GPU.

The evaluation extended beyond held-out people to modified task descriptions, altered problem structures, and unseen domains. These are substantial results within the paper's experimental scope. They are not evidence that the model can predict every real-world interaction, nor that it can safely improve a person's life through interventions.

The 2026 BehaviorBench work asks an additional question: how well do foundation models reproduce both **individual responses and population distributions**? It evaluates behavioral prediction, strategic decisions, subject-trait inference, and behavioral knowledge. Behavioral adaptation improved the distributional performance of Be.FM under the study's benchmarks, but different capabilities require distinct metrics.

## Sharing parameters can hurt

A common model may exploit useful regularities across tasks. But what happens when the same feature has opposite meanings in two domains?

We created a synthetic example with two binary-choice tasks. In domain A, higher values of a feature make choice 1 more likely. In domain B, the relationship reverses. We trained one pooled logistic coefficient and compared it with separate task-specific coefficients.

On held-out synthetic rows, the shared model had log losses of approximately 0.677 and 0.717. The task-specific models achieved approximately 0.395 and 0.433.

This is not an observed failure of a trained behavioral foundation model. We intentionally designed conflicting artificial tasks to demonstrate **negative transfer**. A richer model might share an encoder while keeping separate task heads, route through experts, or use methods such as gradient surgery. Each alternative still requires a fair held-out comparison.

## What would justify the word foundation?

Independent evaluation across people, studies, time, culture, and domains; well-calibrated probabilities; meaningful abstention under shift; and comparisons against simple statistical baselines and specialized models. The licensing status of code, base weights, training data, and derivatives must also be examined independently.

And the central distinction remains: predicting a behavior under observed conditions is not the same as identifying the causal effect of an intervention.

For Manager, the goal should not be an impressive model-size announcement. It should be a falsifiable account of where a shared model beats alternatives—and where it does not.

### Primary research
- [Binz et al., Centaur, Nature (2025)](https://www.nature.com/articles/s41586-025-09215-4)
- [Huang et al., BehaviorBench (2026)](https://arxiv.org/abs/2606.24162)
- [LoRA (2021)](https://arxiv.org/abs/2106.09685)
- [QLoRA (2023)](https://arxiv.org/abs/2305.14314)
- [Yu et al., Gradient Surgery (2020)](https://arxiv.org/abs/2001.06782)

*Evidence boundary: the synthetic log-loss numbers are not scores for Centaur, Be.FM, or a trained Manager shared BFM. Public model-card licensing and linked terms must be reconciled before commercial reuse.*
