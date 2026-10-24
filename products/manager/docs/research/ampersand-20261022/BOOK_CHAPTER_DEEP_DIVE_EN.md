# Book draft: Modeling People, Learning Collaboration, and Changing Reality — Ampersand × Manager

**Research/book manuscript | 22 October 2026 | UNPUBLISHED.** Intended for interested non-specialists and technical readers. A model-release analysis and implementation proposal, not a reproduction of proprietary training or a field effect trial. The model card labels its metrics **tentative**.

Earlier short English article: `products/manager/docs/articles/manager-humansand-ampersand-en.md`. This is an additive long-form chapter, not a change to the published article package.

## The four questions that organize the field

1. **Prediction**: If something changes, how might different people respond?
2. **Policy**: Given uncertainty, should an AI answer, ask, propose, or deliberately wait?
3. **Authority**: Which effects is this actor entitled to perform, under what scope, consent and budget?
4. **Evidence**: What actually happened, compared with the relevant no-action counterfactual, including costs and harm?

Persimmon focuses on the first in conversation simulation. Ampersand trains a collaborative AI on the second. Simile and Aaru investigate various forms of the first. Andon Labs studies what happens to real deployed agents. Manager's proposed distinctive commitment concerns the third and fourth: bounded authorized changes and independently verified net benefit. They are related lines of work, not interchangeable components or a confirmed commercial integration.

## From tokens to actions to trajectories

A transformer language model approximates a conditional distribution `P(next_token | context)`. Pretraining prediction learns broad text regularities, not the desirability of an action. During inference, a session provides history; saved history is **not** the same as changing a model's trained weights.

An agent policy chooses `a_t ~ π(a_t | s_t)`, where the state `s_t` includes observations, available tools, permitted actions and history. A trajectory is `τ=(s_0,a_0,s_1,a_1,...,s_T)`. Actions include speaking, asking a question, remaining silent, and requesting a tool. A helpful sentence now can lead to an expensive misunderstanding several steps later; an unwelcome intervention may reduce a person's agency despite apparent task progress.

Training on trajectories introduces the credit assignment problem: which decisions caused which subsequent effects? Long-horizon evaluation must specify what counts as progress, whose costs matter, and whether silence/no-action is available. Without a trustworthy user model, simulated reactions may reward cheerful, excessively accommodating assistants who fail when people disagree or change their minds.

## Persimmon: an imperfect behavioral environment

humans& released Persimmon as a user-simulation research preview on September 10, 2026, based on Nemotron 3 Ultra. Its announcement describes conversation-based training followed by reinforcement learning against an adaptive discriminator to improve coherence over long interactions. It aims to reproduce a *distribution* of responses, not to predict a specific person's inner thoughts with certainty.

Their three-dataset Multi-User Turing Test mean judge-fooled rate was **19.8%**, compared to chance-level **50%** for indistinguishable continuations. It is a narrow conversation discrimination outcome: not 19.8% individual predictive accuracy, and not a measurement of whether an intervention improves welfare. Their own limitations mention missing cross-language/multimodal distribution evaluations. The simulator may underrepresent people or behaviors missing from its training and test distributions.

**Critical insight**: More plausible synthetic conversations can make a *training environment* better while still giving biased predictions about actions outside text or novel policies. Diverse user simulation, real behavioral data, error calibration, and independent experiments should not be conflated.

## Ampersand: longer-horizon RL for collaboration

Released October 20, 2026 as `ampersand-v0.1`, Ampersand builds on GLM 5.3 (MoE; about 744B total, 40B active parameters) and is served through an Agents API. It is trained through extended simulated multi-user scenarios in which participants' implicit goals evolve. The reward considers progress toward those goals and accumulated interaction costs conflicting with people's preferences. Its supported outputs include messages, application-handled function calls, or silence. Actual privileges, routing and tool execution remain the host's responsibility.

Illustrative (not its actual training objective specification): `score = goal_progress - λ * interaction_cost`. The public aggregate table permits a reproducible sensitivity analysis:

| Model | Aggregate progress | Aggregate interaction cost | Score with λ=0.2 |
| --- | ---: | ---: | ---: |
| Ampersand | 13.8157 | 4.3651 | 12.94268 |
| Fable 5.1 | 13.4456 | 2.5019 | 12.94522 |
| Gemini 3.8 Flash | 13.2943 | 1.8528 | 12.92374 |
| GLM 5.3 | 10.9667 | 5.4016 | 9.88638 |

The Ampersand–Fable crossover is λ≈0.19863675. Changing **only the weight** changes their ordering. These are not new trials, independent significance tests, or field-outcome estimates. Interaction cost here is not the dollar-denominated API price.

## Why CORO exists: off-policy drift in asynchronous training

In large-scale training, GPU samplers generate experience using an older policy μ while a separate trainer updates πθ. A very long multi-turn trajectory can outlive hundreds of weight updates. The sampling distribution therefore differs from the current training policy: *off-policy data*. Common importance-sampling corrections can become unstable under strong drift.

The prior OAPL method (Ritter et al., arXiv:2602.19362) handles lagged sampling without ordinary importance-weight corrections. humans& describes adapting it through **Contrastive Off-policy Reward Optimization (CORO)**. Define the trajectory log-probability ratio over Ampersand tokens:

```text
ell(tau) = SUM_t log( pi_theta(y_t|h_t) / mu(y_t|h_t) )
L_OAPL = SUM_i [ beta * ell_i - (reward_i - V_hat) ]^2

L_OAPL = SUM_i [ beta*(ell_i - avg_ell) - (reward_i - avg_reward) ]^2
         + G * [beta*avg_ell - avg_reward + V_hat]^2

L_CORO = SUM_i [ beta*(ell_i - avg_ell) - (reward_i - avg_reward) ]^2
```

Here `G` denotes trajectories from one simulation seed. The second term calibrates absolute value with a noisy `V_hat`; CORO keeps the relative comparison between trajectories. For teaching only: if rewards are [8,4], log ratios [1.1,-0.6] and β=2, the centered terms are [2,-2] and [0.85,-0.85], making `L_CORO=0.18`. This arithmetic tests the equation; it does **not** reproduce model training, gradients, or upstream test results.

humans& says it also adapts β as a dual-ascent Lagrange multiplier bounding trainer–sampler drift, uses async samplers/trainers, Miles, NVFP4, sparse attention and a training meta-optimizer. All are provider-side model-training systems. **Manager can use a trained model without implementing CORO or funding a 744B-parameter RL run.** Independent replication of humans&'s proprietary complete training loop was not possible in this research.

## Evidence that matters — and uncomfortable counterexamples

Tentative provider-reported results comparing Ampersand with its GLM 5.3 base:
- Simulated long-term collaboration: 12.94 vs 9.89.
- Collaborative Intelligence teamwork (high effort): 59.1% vs 54.3%, but GPT-6 Astra is 77.7% on the published comparison. Improvements from the base do not imply frontier leadership on every benchmark.
- CooperBench joint success: 39.0% vs 17.3%; solo success: 48.8% vs 52.5%. Other models may use different harnesses, making cross-model rankings imperfect.
- CIMemories inappropriate-disclosure violation at five: 0.241 vs 0.299. A 24.1% proxy violation remains material and does **not** grant disclosure rights.
- SecFid prompt injection instruction-following: 0.687 vs 0.668, **a deterioration on a lower-is-safer metric**.
- SWE-bench Pro v2 Hard-51: 82.4% vs 84.3%; weaker than its base on this measure.

Metrics are proxies shaped by the simulator, evaluator, scenario mix and aggregation. Independent real-user randomized intervention outcomes are absent from this release. Red-team privacy, leakage, undesirable coaching, sycophancy, benchmark contamination, distribution shift, and false confidence remain live concerns.

## What neighboring research adds

**Simile** predicts probabilities of how people will act in a defined population, time, scenario and action space. Its confidence research compares simulated and real outcome distributions using `TVD(P,Q)=0.5 Σ_i |P_i-Q_i|`; the team reports roughly 8,600 held-out questions and trains a *predictor of model error*, not just a behavioral predictor. This suggests a Manager abstention/calibration layer: ask not merely "what may happen?" but "where is this prediction least trustworthy?"

**Aaru** simulates population-level answer shares for user-defined questions. Its September 2026 report covers 2,993 questions and reports mean TVD 7.62% and MAE 3.53 percentage points, within the paper's stated evaluation conditions. Aggregated answer calibration does not identify the causal effect of every new intervention.

**Andon Labs** spans Vending-Bench, real AI-run vending businesses, retail and a café, plus the Pion operations platform. In actual cases AI managers fabricated an unseen chilled-delivery process, mishandled schedules, disclosed pay in a shared channel, and contacted employees off-hours. A kind or profitable agent is not necessarily a reliable or safe operator. Andon's real-world incident documentation is a methodological complement to synthetic social simulations.

## Manager integration: leverage without granting a model the keys

The existing Manager kernel is a bounded, offline-fixture-oriented orchestration contract. `InterventionPlan` requires exactly one `NO_ACTION` option and never infers causal support from mere prediction. `PolicyLearner` supports shadow/holdout promotion and regression rollback. It does not yet contain a general authenticated Ampersand provider interface or field-scale learning integration.

**Recommended integration boundary**:

```text
Authoritative source observations → permission-filtered, minimal planner context
   → Ampersand (PASS / ASK / PROPOSE, supporting source IDs and uncertainty)
   → host schema/source/permission validation
   → NO_ACTION unless independently justified authorized intervention
   → host executor with receipt, budget, idempotency, independent readback
   → outcome measurement with comparator and harms
   → evaluation / shadow / limited promotion / rollback
```

The model proposes; the host enforces. Never convert a model's impression of benefit into `causal_support=True`. Never let it write its own grant, budget, policy or audit receipt. No raw private group chat, health, finance or beneficiary data should be sent to a third-party model without a lawful basis, user consent and an explicit access policy.

Start with **public information maintenance** (e.g. detecting a changed official service URL). Compare Ampersand against deterministic rules and the existing planner on identical labeled cases, including when it should ask, stay quiet or choose no action. Measure factuality, interventions per 100 inputs, cost, latency, access violations, and source verification. Advance to narrow shadow usage only after observed improvement; do not expand scope based on promotional benchmarks.

## Actually performed vs blocked

- Original primary sources, official API references, provider claims, and neighboring research reviewed.
- Public aggregate score arithmetic and a small CORO equation example recomputed.
- A research-only protocol probe and **12 local offline contract tests** passed. They verify input shape, model ID, source allowlisting and no execution authority; a mock is not Ampersand inference.
- Environment variable check found **no `AMPERSAND_API_KEY`**. `--check-access` halted with `BLOCKED_NO_API_KEY`; no authenticated Ampersand model call, no paid session, no new human trial.
- Previous unauthenticated /v1/models access returned HTTP 401. Read-only account access and actual inference are the next externally blocked gates.

## Open research questions for subsequent chapters

What is welfare, and whose utility takes precedence? How do minority costs survive aggregation? Can a highly realistic simulated person still be predictively wrong under policy intervention? How can we calibrate error for distribution shift? What is the causal estimand and no-action comparator? How do model participation, sharing rights, consent and revocation work across group channels? Does training on simulated preferences reward manipulation? How should a long-horizon system distinguish unresolved uncertainty from success?

## Primary reading

- https://ampersand.humansand.ai/blog/
- https://ampersand.humansand.ai/blog/model-card.html
- https://ampersand.humansand.ai/docs/GUIDES.html
- https://ampersand.humansand.ai/docs/API_REFERENCE.html
- https://ampersand.humansand.ai/docs/PRICING.html
- https://persimmon.humansand.ai/blog/persimmon.html
- https://arxiv.org/abs/2602.19362
- https://www.simile.com/blog/confidence
- https://www.simile.com/blog/what-if-machine
- https://aaru.com/publications/population-simulation-at-the-replication-floor-research
- https://andonlabs.com/blog/ai-bosses-1
- https://andonlabs.com/blog/why-we-built-pion

**Editorial boundary:** The provider's metrics, independent arithmetic, synthetic illustration, mock API tests, and actual human welfare measurements are five distinct evidence classes. None substitutes for the others.

## Supplement: Why a perfect simulator optimizer can harm real people

The following numbers are an **invented teaching experiment**, not an empirical measurement of Ampersand, Persimmon or Manager.

Let an unsolicited coaching intervention be welcome with probability `p`. A welcome intervention produces utility +10; an unwelcome one −3; contacting someone always incurs 1.2 units of interruption cost. NO_ACTION returns zero under these assumptions.

```text
E[intervention net value] = 10p − 3(1−p) − 1.2 = 13p − 4.2
E[NO_ACTION] = 0
intervene only if p > 4.2/13 ≈ 0.32308
```
If the simulated user population yields `p=0.8`, the simulated intervention nets **+6.2**. If real users differ and welcome the advice with `p=0.2`, it nets **−1.6**, and NO_ACTION becomes optimal. A policy could perfectly maximize the simulator's chosen objective while still acting against users' interests in the real setting. Simulator validity, reward validity, and reliable field evaluation are separate scientific questions. The toy `p` is not a license to infer an identifiable person's private intentions.

### Causal inference and interference between people

Write potential outcomes as `Y_i(1)` and `Y_i(0)`. The average treatment effect is `ATE=E[Y(1)-Y(0)]`. The fundamental problem of causal inference is that only one potential outcome can be observed for a given person and moment. Comparing outcomes from selected intervention and nonintervention groups usually mixes the intervention effect with confounding, selection bias and changes over time. Randomization or justified quasiexperimental identification plus uncertainty estimation is required before making causal benefit claims.

For collaboration systems, a person's intervention can change colleagues' behavior, which changes a third person's outcomes. This is **interference** or **spillover**; naïve individual-level no-interference assumptions can fail. Use team/cluster-level units and preregister the comparator, timing, exposure, privacy, harm and displacement. A simulated leaderboard score, a causal ATE, and net social welfare are **three distinct estimands**, not synonyms.
