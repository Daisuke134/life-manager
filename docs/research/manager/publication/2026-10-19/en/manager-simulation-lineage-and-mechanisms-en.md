# Where did world-modeling, world-changing AI come from? MiroFish, Goodfire, Numerai, and Manager

![Different technical layers and the Manager vision](https://aniccaai.com/blog/manager/media/b2387a23cde5e752c5fec753ee553719d12263f33e5ce1a0cd20bcf824e1983d.png)

AI-generated conceptual illustration with Japanese labels. People, probabilities, and plots are illustrative, not model outputs, returns, or intervention effects.

Sources checked October 18, 2026. This explanation uses official sites, original papers, and public code, distinguishing company claims, research hypotheses, fictional examples, and our measured results.

Model the world, test proposed changes, act, and learn from outcomes: thinking about this brings together social simulation, language models, interpretability, and forecast aggregation. These solve different problems.

| Component | Main subject | Output | What it does not establish alone |
|---|---|---|---|
| Transformer language model | Input tokens | Next-token probabilities or text | Truth or intervention effectiveness |
| MiroFish | Documents, entity relationships, synthetic society | Agent actions and reports | Accuracy about the real future |
| Goodfire essay | Neurons and circuits | Mechanistic explanations and experiments | Accurate social prediction |
| Numerai | Stock features and submitted forecasts | Scored predictions and combined model | Population responses or improved lives |

These are not four population-generation methods. They occupy different layers: computation, simulated environment, internal inspection, and forecast evaluation.

## MiroFish: from documents to a synthetic society

We identify MiroFish as public repository `666ghj/MiroFish`, without assuming similarly named third-party services are official. We use the developer’s public account rather than inventing a real name.[1]

In the inspected code, documents are chunked and sent to Zep Cloud to build a graph of people, organizations, and relationships. `graph_builder.py` handles splitting, graph creation, relation schemas, and ingestion. `OasisProfileGenerator` builds person profiles or organizational representative accounts from graph elements and context, then formats Twitter-style CSV or Reddit-style JSON.[2][3]

`_generate_profile_with_llm` supplies names, entity types, summaries, attributes, and context to an LLM and receives JSON. It does not fine-tune the LLM. Rule-based fallback behavior exists. Profiles therefore cannot all be treated as measured information.[3]

Agents interact in OASIS’s simulated social network. ReportAgent searches and questions virtual agents to summarize results. A quoted virtual statement is not an interview with a real resident.[4][5]

For a fictional example, supply a document announcing bus-service cuts. Student, commuter, municipal, and media roles might exchange posts. This could suggest investigating concern about late-night travel. A claim that 32% of actual residents oppose the cuts would require separate validation against residents. This bus example is not a MiroFish execution result.

Manager can learn from the document → scenario → action-history → report workflow. Our population component instead matches geographic population statistics. More MiroFish characters do not automatically produce a representative population.

The inspected commit was `7657031ac01184afe2cb220f5ee3545573b5e843`. The architecture requires an LLM connection and Zep Cloud; configuration checks reject custom `ZEP_API_URL`. AGPL-3.0 code cannot be unconditionally folded into MIT code. We read key paths statically, without starting services, connecting paid APIs, or testing forecasts.[6]

## What happens inside a Transformer?

We use a common autoregressive decoder-only language model as the example. The original 2017 Transformer was an encoder–decoder translation model, not exactly every modern LLM.[7]

Suppose the input is:

```text
Age group is 30–39. Employment status is
```

Generating a continuation involves the following calculations. All splits, numbers, and probabilities below are fictional teaching examples, not extracted model values.

### 1. Convert text into token IDs

A tokenizer maps text to tokens. For teaching, imagine pieces such as `[Age][ group][ is][ 30][–39][.][ Employment][ status][ is]`; actual splits depend on the tokenizer.

Each ID retrieves an embedding vector, perhaps `[0.2, -0.4, 0.7, ...]`. The embedding table contains learned parameters. Position information enters calculations according to the architecture.

### 2. Combine preceding information with Attention

To calculate a continuation at the final position, the model can incorporate earlier information such as “30–39.” Learned matrices map representations to Query, Key, and Value:

```text
Q = X W_Q
K = X W_K
V = X W_V
Attention(Q,K,V) = softmax(QKᵀ / √d + mask) V
```

Query–Key dot products give scores; softmax converts them to mixture weights; those weights combine Values. A causal mask prevents a position from using future answer tokens.

For scores `[0, 2, 1]`, weights are approximately `[0.090, 0.665, 0.245]`. If the three Values were scalars `[0, 2, 1]`, their weighted sum would be approximately 1.575. Actual Values are vectors, with analogous weighted sums for each component.

“Attention to age” does not measure human attention. It names a numerical operation mixing information. Attention weights alone also do not establish the cause of a final decision.

### 3. Transform each position with an MLP

An MLP combines linear transformations and nonlinear functions. A simplified unit receiving `[1, 2]` might compute:

```text
1 × 0.4 + 2 × (−0.1) + 0.2 = 0.4
```

The coefficients 0.4, −0.1, and 0.2 are parameters—weights and bias. The computed value is an activation. A neuron is a computational unit, not a parameter itself or a biological cell.

Modern models may use gated MLPs such as SwiGLU: roughly `SiLU(xW_gate) ⊙ (xW_up)`, followed by an output projection. Architectures differ. Blocks containing normalization and residual connections add Attention/MLP updates to existing representations and repeat.[8]

### 4. Turn vocabulary scores into probabilities

The final representation is projected into vocabulary scores, or logits. With only three fictional candidates:

| Candidate | Logit | Softmax probability |
|---|---:|---:|
| Employed | 2 | About 66.52% |
| Not employed | 1 | About 24.47% |
| Student | 0 | About 9.00% |

Choose a next token, append it, and calculate the continuation. Real vocabularies are large and “employed” need not be one token. Placing student alongside employment categories is a simplification for arithmetic, not a recommended population schema.

### 5. During training, update parameters from loss

If the observed next answer is employed, a cross-entropy example gives `−log(0.6652) ≈ 0.4076`. Lower probability on the target gives larger loss.

Backpropagation follows the computation backward to determine each parameter’s loss gradient. Simple gradient descent updates:

```text
new parameter = old parameter − learning rate × gradient
```

In a tiny model whose only trainable parameters are the three output biases, one update with learning rate 0.1 changes logits to approximately `[2.0335, 0.9755, −0.0090]`. Employed probability rises to about 67.71% and loss falls. A real Transformer propagates gradients through many Attention and MLP matrices. Optimizers such as AdamW also use gradient history to choose update amounts.

Other records have “not employed” as the answer and update accordingly. The goal is a conditional distribution, not declaring everyone employed. Ordinary generation does not perform these parameter updates. Text and activations change while fixed-model parameters stay fixed.

We executed this arithmetic with Python’s standard library and checked gradients against numerical differentiation. It is not a Transformer-training experiment or population-prediction score.

## Goodfire investigates these internal mechanisms

Nick Cammarata’s *Neural Networks Are Already Clean*, published October 15, 2026, includes language-neuron work contributed by Curt Tigges. It presents a working hypothesis.[9]

The central proposal is that apparently unrelated meanings in one neuron may often become understandable as related generalizations after improving visualization, examining architecture, and tracing surrounding circuits. Explanations should be checked through connections, effects on outputs, and changed-input experiments—not just one large activation.

For example, in SwiGLU, negative gate and value branches multiply to a positive result. Collecting only large positive outputs can misidentify a role. Inspect the internal calculation. This MLP value branch is distinct from Attention’s V.

The essay does not establish that all LLMs are explained, superposition never exists, or safety is guaranteed. Read superposition toy models and direct-neuron research under their respective assumptions.[10][11]

For Manager, interpretability could help inspect information a model responds to and investigate errors. Reading internal weights/activations requires access to the model and runtime; ordinary text APIs may not allow it. Understanding a circuit does not replace evaluation of real behavior or intervention effects.

## Numerai: collect forecasts and score them later

Numerai, led by Richard Craib, gathers, scores, and combines stock forecasts. Its inputs and evaluation targets differ from synthetic-resident modeling.[12]

The October 16, 2026 Unity announcement introduced real stock IDs and 1,040 features, enabling external-feature joins. It did not remove every transformation or anonymization. Tournament/Meta Model unification was planned for January 1, 2027, not completed on the October 18 check date.[13]

Manager can borrow the discipline of saving forecasts before outcomes, comparing models under common conditions, and asking whether an ensemble adds information. This is our design interpretation, not evidence that Numerai validated social interventions.

Finance measures prices, risks, and costs. Reducing suffering requires purpose-appropriate measures such as self-reports, daily burdens, access, and the distribution of disadvantages. Stock scores cannot simply substitute. The [Unity explainer](https://aniccaai.com/blog/manager-numerai-unity-en) records its public-source and example-code reading scope.

## Related people and projects

“Related” means overlapping methods or problems, not a shared mission or a claim of direct historical influence on Manager.

| Period | Person or project | Connection and essential distinction |
|---|---|---|
| 1948 | Norbert Wiener, cybernetics | Observation and feedback control, not today’s LLMs or population models.[14] |
| 1950s onward | Jay Forrester, system dynamics | Social, organizational, resource dynamics; not individual LLM agents.[15] |
| 1971–73 | Stafford Beer, Fernando Flores and others, Cybersyn | Economic information, statistics, simulation, decision support; not autonomous AGI governing a country.[16] |
| 1996 | Joshua Epstein, Robert Axtell, Sugarscape | Agent-based investigation of social patterns from simple interactions.[17] |
| Around 2020–22 | Stephan Zheng, Alexander Trott and others, AI Economist | Two-level reinforcement learning for economic agents and a policy planner; close to shared-rule search, but results depend on the simulated economy.[18] |
| 2023 onward | Joon Sung Park, Michael Bernstein, Percy Liang and others | Generative Agents, participant-grounded simulation, Simile; memory/planning and human evidence are informative; research code is not necessarily the commercial model.[19][20][21] |
| 2023 onward | Alexander Sasha Vezhnevets, Joel Z. Leibo and others, Concordia | Separates actors from a Game Master handling environment changes; useful experimental architecture.[22] |
| 2025 onward | AgentSociety team | Connects LLM agents, urban environment, interactions; scale is separate from real intervention validity.[23] |
| Current | Aaru, Simile | Real-data population/behavior simulation for decisions; promotional or internal evaluation is not independent replication.[21][24] |

Aaru names Cam Fink, John Kessler, and Ned Koh as founders. Its public research explicitly says population generation and the core behavior-trajectory model are not language models. Calling every company an LLM simulator is inaccurate.[24][25]

Simile emphasizes surveys and behavior from real people and continued validation. Keep the evaluated subjects of Park, Bernstein, and Liang’s papers separate from commercial-service descriptions.[19][20][21]

We did not verify a single product that has demonstrated the complete observation → modeling → action → real-outcome loop under the mission **End suffering.** This is not proof none exists. It is more accurate to map components: Aaru/Simile for responses, AI Economist for policy search, Concordia/AgentSociety for environments.

## Science fiction explores both ambition and difficulty

Isaac Asimov’s *Foundation* imagines Hari Seldon’s psychohistory modeling large populations and reducing long-term catastrophe. Its predictive power is fictional, not a social-science result.[26]

Iain M. Banks’ Culture features Minds operating ships and habitats. His 1994 account discusses abundance, choice, and environmental operation, close to a vision of AI improving living conditions. This comparison is interpretation, not a claim of identical ethics or implementation.[27]

E. M. Forster’s *The Machine Stops* instead depicts dependence on machinery, raising questions about convenience and failure. Literary interpretation is not empirical evidence about AI.[28]

These are not one inevitable progress story. Fiction explores possible societies, cybernetics studies control, and social simulation examines hypotheses. Each can inform what to seek and what to test.

## What we bring back to Manager

Anicca’s mission is **End suffering.** Manager aims to connect behavior, environments, proposed changes, and observed outcomes. Population synthesis is a component when representing population composition is necessary.

Useful precedents include MiroFish’s scenarios and histories, Goodfire’s experimentally tested explanations, Numerai’s prospective scoring, and AI Economist’s co-adaptation of agents and policies. Adopting any one does not accomplish the mission.

We have implemented and measured a population component using public statistics and PUMS households. Behavior prediction and real intervention effects remain future validation tasks. Preserve this boundary in both research explanations and descriptions of our work.

## Sources

1. [MiroFish](https://github.com/666ghj/MiroFish).
2. [Pinned graph_builder.py](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/graph_builder.py).
3. [Pinned oasis_profile_generator.py](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/oasis_profile_generator.py).
4. [Pinned report_agent.py](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/report_agent.py).
5. [OASIS paper](https://arxiv.org/abs/2411.11581).
6. [MiroFish configuration](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/config.py), [dependencies](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/pyproject.toml), [license](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/LICENSE).
7. [Attention Is All You Need](https://arxiv.org/abs/1706.03762).
8. [nanoGPT teaching implementation](https://github.com/karpathy/nanoGPT/blob/3adf61e154c3fe3fca428ad6bc3818b27a3b8291/model.py), for Attention, MLP, residuals, and cross-entropy—not a SwiGLU example.
9. [Goodfire essay](https://already-clean.goodfire.com/), [official research list and date](https://www.goodfire.com/research).
10. [Toy Models of Superposition](https://arxiv.org/abs/2209.10652).
11. [Language Model Circuits Are Sparse in the Neuron Basis](https://arxiv.org/abs/2601.22594).
12. [Numerai](https://numer.ai/), [documentation](https://docs.numer.ai/).
13. [Unifying Numerai and Signals](https://blog.numer.ai/unifying-numerai-and-signals/).
14. [Wiener, Cybernetics, MIT Press](https://mitpress.mit.edu/9780262537841/cybernetics-or-control-and-communication-in-the-animal-and-the-machine/).
15. [MIT on Forrester](https://news.mit.edu/2016/professor-emeritus-jay-forrester-digital-computing-system-dynamics-pioneer-dies-1119).
16. [Eden Medina’s Cybersyn history](https://thereader.mitpress.mit.edu/project-cybersyn-chiles-radical-experiment-in-cybernetic-socialism/).
17. [Epstein and Axtell, Growing Artificial Societies](https://www.brookings.edu/books/growing-artificial-societies/).
18. [AI Economist paper](https://arxiv.org/abs/2108.02755), [public code](https://github.com/salesforce/ai-economist), a public archive when checked.
19. [Generative Agents](https://arxiv.org/abs/2304.03442).
20. [Participant-grounded simulation research](https://arxiv.org/abs/2411.10109).
21. [Simile](https://www.simile.com/).
22. [Concordia paper’s official introduction](https://deepmind.google/research/publications/64717/).
23. [AgentSociety paper](https://arxiv.org/abs/2502.08691).
24. [Aaru research](https://aaru.com/publications/population-simulation-at-the-replication-floor-research).
25. [Aaru founders](https://aaru.com/about).
26. [Publisher introduction to Foundation](https://www.penguinrandomhouse.com/books/5655/foundation-by-isaac-asimov/).
27. [Reproduction of Banks’ A Few Notes on the Culture](https://theculture.adactio.com/), an author essay reproduction, not a product site.
28. [The Machine Stops bibliography and discussion](https://sf-encyclopedia.com/entry/forster_e_m).
