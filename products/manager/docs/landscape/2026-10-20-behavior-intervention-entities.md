# The Behavior Simulation & Intervention Ecosystem: Company-First Chaos Map

**Reviewed:** 2026-10-21 (Radiant + economic-autonomy evaluation refresh); **30 distinct entities**; **7 categories**. Existing Artificial Societies entity updated, not counted twice.

This map is a **snapshot of who is building what**, not a technology flowchart or a list of paper titles. **Company names, research institutions and nonprofits are the unit of analysis.**

A label on this map does not claim competitive equivalence, commercial access, performance superiority, or an endorsement. Each organization can span multiple categories, and vendor-reported capabilities are not independently reproduced here. Selection is curated, not exhaustive.

**Do not claim all peers only simulate and never validate:** Simile and Aaru report behavioral validation; Expected Parrot supports real-human studies; Penn BCFG and GiveDirectly run or study real-world interventions.

## Behavioral world & audience simulation

| Organization | Entity type | What it works on | Official source |
|---|---|---|---|
| Simile | company | Human-behavior world models; compare simulated responses to changes | [Official source](https://www.simile.com/) |
| Aaru | company | Grounded population and purchasing behavior simulations | [Official source](https://aaru.com/simulation) |
| CulturePulse | company | Cultural/social dynamics and public reaction simulation | [Official source](https://www.culturepulse.ai/) |
| Artificial Societies (Radiant) | company | Grounded artificial societies, surveys, interactive interviews, focus groups, network influence and research-assistant analysis; company-reported human-panel benchmarking | [Radiant](https://societies.ai/radiant), [evaluation](https://societies.ai/eval) |
| Lakmoos | company | Synthetic research panels; real-world validation claims | [Official source](https://lakmoos.com/blog/validating-synthetic-panels) |
| Synthetic Users | company | Simulated participants for user/product research | [Official source](https://www.syntheticusers.com/) |

**Radiant investigation:** [Original primary-source review](../research/societies/RADIANT_2026-10-21_JA.md). Published 2026 comparison: 2,796 synthetic respondents / 68,280 answers, with company-reported population TVD 0.08 versus best generic LLM 0.31 on its seven-source benchmark. This supports survey-output fidelity on those benchmarks, **not** independently proven downstream actions or causal welfare. The peer-reviewed collective-agent paper studies 33,299 bots forming language/content affinity groups; it is **not** a human opinion-survey validation. The minimum society size varies across company pages (12 vs 20), so avoid asserting one immutable product limit.

## AI + human research platforms

| Organization | Entity type | What it works on | Official source |
|---|---|---|---|
| Expected Parrot | company | EDSL: AI and human research in a combined workflow | [Official source](https://www.expectedparrot.com/) |
| Evidenza | company | Synthetic B2B/consumer market research | [Official source](https://www.evidenza.ai/) |
| Qualtrics | company | Enterprise research and human/synthetic panels | [Official source](https://www.qualtrics.com/market-research/research/) |
| Listen Labs | company | AI-moderated interviews with real people | [Official source](https://listenlabs.com/) |
| Prolific | company | Recruitment and verification of human research participants | [Official source](https://www.prolific.com/behavioural-research) |

## Social simulation research labs and groups

| Organization | Entity type | What it works on | Official source |
|---|---|---|---|
| Stanford HAI | university_institute | Generative Agents and human simulation research | [Official source](https://hai.stanford.edu/policy/simulating-human-behavior-with-ai-agents) |
| Google DeepMind | research_lab | Concordia social agent/world simulation framework | [Official source](https://github.com/google-deepmind/concordia) |
| MIT Media Lab | university_lab | Large Population Models and AgentTorch | [Official source](https://www.media.mit.edu/projects/ai-lpm/overview/) |
| Microsoft Research | research_lab | TinyTroupe multi-agent persona simulation | [Official source](https://github.com/microsoft/TinyTroupe) |
| CAMEL-AI | open_source_research_community | OASIS LLM agent social-network simulation | [Official source](https://github.com/camel-ai/oasis) |

## Causal and behavioral decision design

| Organization | Entity type | What it works on | Official source |
|---|---|---|---|
| causaLens | company | Causal decision intelligence and explainable decision workflows | [Official source](https://causalens.com/) |
| Behavioural Insights Team (BIT) | consultancy | Behavioral interventions and public-sector evaluations | [Official source](https://www.bi.team/) |
| ideas42 | nonprofit | Field-tested behavioral design and social impact | [Official source](https://www.ideas42.org/offerings) |
| The Decision Lab | consultancy | Behavioral science applied to products and interventions | [Official source](https://thedecisionlab.com/) |

## Personalized interventions and field experiments

| Organization | Entity type | What it works on | Official source |
|---|---|---|---|
| Lirio | company | Health behavior intervention personalization | [Official source](https://lirio.com/) |
| Irrational Labs | consultancy | Behavioral diagnosis, design, and experiment testing | [Official source](https://irrationallabs.com/service/team-training/) |
| Penn Behavior Change for Good | university_initiative | Multi-intervention megastudies of health, education and saving | [Official source](https://bcfg.wharton.upenn.edu/approach/) |

## Real-world impact systems

| Organization | Entity type | What it works on | Official source |
|---|---|---|---|
| Oracle Opower | corporate_product | Behavioral energy-efficiency programs deployed via utilities | [Official source](https://www.oracle.com/utilities/opower-energy-efficiency/) |
| GiveDirectly | nonprofit | Unconditional cash transfers with experimental evaluation | [Official source](https://www.givedirectly.org/gdresearch/) |
| 412 Food Rescue | nonprofit | Food Rescue Hero: volunteer-powered surplus food logistics | [Official source](https://412foodrescue.org/food-rescue-hero/) |

## Autonomous business & economic evaluation

These organizations provide a bridge between simulated agents, historically valued work, real business operations and independent evaluation; the first three are **not** interchangeable. See [wealth evidence source map](../research/autonomous_wealth_eval/PRIMARY_SOURCES_2026-10-21.json) and [proposed dual-scorecard protocol](../research/autonomous_wealth_eval/WEALTH_BLESSING_EVAL_PROTOCOL.md).

| Organization | Entity type | What it works on | Official source |
|---|---|---|---|
| Andon Labs | company | Vending-Bench 2 long-horizon **simulated** shop balance; Project Vend/Pion and actual shops for **real** business operations (with human staff in physical deployments) | [Vending-Bench 2](https://andonlabs.com/evals/vending-bench-2), [Pion](https://andonlabs.com/blog/why-we-built-pion) |
| Anthropic | ai_research_company | Original field-research collaborator for Project Vend physical office-store operations | [Project Vend phase 2](https://www.anthropic.com/research/project-vend-2) |
| OpenAI | ai_research_company | SWE-Lancer historical Upwork dollar-valued task success; GDPval professional work deliverable evaluation; open-source eval code | [SWE-Lancer](https://openai.com/index/swe-lancer/), [GDPval](https://openai.com/index/gdpval/), [evaluation code](https://github.com/openai/frontier-evals) |
| METR | research_nonprofit | Time-to-complete agent horizons and empirical randomized developer productivity | [Time horizons](https://metr.org/time-horizons/), [productivity RCT](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/) |

**Boundary:** Vending-Bench's ending simulated cash is not a settled external payout; SWE-Lancer's historical task compensation is not payment to the AI; METR's time horizons do not measure company profit. Andon physical field businesses involve people, wages, customers and real operational costs, so they are not proof of wholly human-free labor. Existing Life Manager LM-EAB provides a separate operator-owned economic autonomy scorer, not an already achieved Manager field-benefit result.

## Where Manager sits

**Overlap with peers:** scenario simulation, behavior prediction, causal decision analysis, social interaction modeling, practical intervention studies and external outcome measurement.

**Proposed integration to prove:** Public evidence → problem observation → candidate interventions including no_action → optional simulation → authorized macro action → independent real-world readback → causal welfare impact assessment → safe learning loop.

**Critical distinction:** Manager has **not** yet executed an independently verified real-world intervention or measured human suffering reduction. Peer deployments and papers are not Manager milestones.

## Outreach and article discipline

- Re-check an organization’s current positioning before publication. Store dated official URLs, avoid made-up quotes and proprietary assertions.
- Do not present editorial groupings as mutually exclusive or as an exhaustive global census.
- Reserve in-depth company profiles, direct outreach and X distribution for separately scoped follow-up tasks.
- The image is original, generated for explanation; its simplified decorative icons are **not official logos**.