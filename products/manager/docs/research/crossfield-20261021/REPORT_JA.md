# Manager Cross-Field Research — 人間行動予測・介入・暗号資産・UBI・学習の接続

**Research snapshot:** 2026-10-21 JST. **Scope:** 比較・技術調査・原典確認。**Status:** research only; no training performed, no real pilot, no welfare improvements measured.  
**Canonical Manager task statuses:** [tasks.json](../../roadmap/tasks.json)（別のタスク台帳は作らない）。**Source inventory:** [SOURCES.json](SOURCES.json)（35件、12分野、first-source prioritization, access/reuse status）.

## 0. Core argument — the missing loop

A behavioral simulator estimates `P(Y | X)`: observed answers, purchases or actions under a described context. A causal policy needs `E[Y(1)-Y(0)]` under justified intervention assignment, and a real Manager must verify the *actual* external action and independent beneficiary outcome. A simulated economic balance is P0, not a P1 receipt. A third-party payment ledger without a Manager-caused intervention is historical public observation, not a Blessing. There is NO shortcut from prediction fit to real-world causal gain.

```mermaid
flowchart LR
 P[Public rights-cleared evidence] --> B[Behavior distribution]
 B --> C[Predict own out-of-domain error]
 C --> H[Mechanisms + causal evidence]
 H --> A{Options incl NO_ACTION}
 A -->|No safe causal+authority basis| N[ABSTAIN]
 A --> S[Simulator / shadow / holdout]
 S --> G{Real issuer grant + consent + budget}
 G -->|Missing| N
 G --> O[Idempotent executor]
 O --> R[Independent world-state readback]
 R --> E[Preregistered comparator + harms + net impact]
 E --> L[Versioned safe policy rollback]
 E --> T[Transparent, challengeable record]
```

## 1. People simulation: what Aaru and Simile actually demonstrate

### Simile
Sources: [What-If Machine](https://www.simile.com/blog/what-if-machine), [Building confidence](https://www.simile.com/blog/confidence), [Itaú field research case](https://www.simile.com/blog/itau-at-esomar). Simile articulates **what** (actual transactions, applications, mobility) plus **why** (interviews/surveys). Its technical confidence-model writeup evaluates ~8,600 held-out questions, grouped and scored by five-fold CV. A binary distribution example predicted 93.4% tipping vs 87.3% observed (TVD ~0.0615), *not* "93.4% model accuracy". Its feature-only error-estimator AUROC was ~0.566, with model probe ~0.730 and continued fine-tuning of Qwen3.5-27B ~0.736 (the last versus probe not a statistically clear AUROC win). Confidence is a **prediction of TVD error**, not certainty that `do(action)` works. The Itaú case documents faster concept exploration with human downstream validation, not a randomized social-welfare improvement estimate. Simile's foundation/training data and exact models are not released as a drop-in open implementation.

### Aaru
Sources: [Full replication-floor methods](https://aaru.com/publications/population-simulation-at-the-replication-floor-research), [short version](https://aaru.com/publications/population-simulation-at-the-replication-floor-summary), [product scenarios](https://aaru.com/). Vendor-reported 2026-09-24 evaluation includes **2,993 survey questions from 186 studies**, **13,727 answer shares**, *unadjusted mean TVD 7.62 points*, *sample-adjusted mean TVD 5.98*, *adjusted MAE 2.78 percentage points*, Pearson r=0.970 pooled answer shares. A separate transaction-related brand-pair ranking comparison claims 92.4% versus stated-purchase consideration 77.8%. Aaru also predicts its own error; a claimed AUROC 0.845 compared against Simile 0.736 is **across DIFFERENT evaluations**, not a head-to-head on the same sample. Pooled 0.970 correlation is not 97% per-person response accuracy, nor out-of-distribution causal-effect accuracy. The article itself focuses on univariate answer distributions; full joint/trajectory fidelity remains a separate research question. Underlying model, private behavior data and redacted sources not independently reproducible.

### Reuse decision
Reuse Simile's **error/abstention head** and Aaru's **question-conditioned distribution and transaction cross-check evaluation protocol**. Do not blindly clone synthetic profiles of real people or train on private respondent rows. First build a truthful, rights-cleared benchmark retaining original response semantics, study/subject/time splits, baseline and intervals; train only if simple frequency/regularized baselines are beaten on the *same* holdout. Manager's earlier SocSci210 global numeric-code scores are useful engineering diagnostics but do not solve task-conditioned generalization or RCT causal fidelity.

## 2. Prediction markets are a different tool, not a better Aaru

[Polymarket's original price rules](https://help.polymarket.com/en/articles/13364488-how-are-prices-calculated): a market contract aggregates traders' beliefs for a **specific externally resolvable event**, with prices reflecting bid/ask (and other documented display rules). Aaru/Simile estimate **distribution of responses by a specified population conditional on a scenario**. Neither automatically identifies a causal treatment effect. A market price for "candidate wins" does not reveal which price reduction/aid intervention makes targeted recipients better off. Contrarian event bets, subgroup preferences and policy ATE are three different estimands. Market liquidity, selection, trader incentives, oracle resolution and timing must be checked. Manager can reuse public **read-only** resolved market forecasts as a baseline/calibration challenge; no trading or gambling execution is necessary, and an existing Life Manager trading loop must not be imported into Manager.

## 3. RL and economy design — do not confuse simulated rewards with welfare

[Salesforce AI Economist](https://pmc.ncbi.nlm.nih.gov/articles/PMC9067926/) shows **two-level RL** where economic agents adapt to a simulated planner/tax rule while the planner changes rules. This is the right way to model adaptation to interventions (gaming, prices, network effects), not an official AI tax policy to deploy. [Andon Vending-Bench 2](https://andonlabs.com/evals/vending-bench-2) measures 365-day virtual operational coherence; [Anthropic Project Vend](https://www.anthropic.com/research/project-vend-2) moves to physical shops with people and real operational messiness. Simulation and field operations must be scored separately, including suppliers, delayed effects, refunds, negotiated labor, and negative surprises. [Behavior Change for Good megastudy](https://www.nature.com/articles/s41586-021-04128-4) randomized 54 interventions across 61,293 gym members, measuring outcomes consistently; 45% increased visits during the short treatment window and only 8% had durable measured effect afterward. Expert guesses failed to identify the highest-impact interventions. **A prediction is useful for triage, not an excuse to skip a real comparative experiment.**

[HeartSteps](https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/) independently illustrates micro-randomization of up to five daily suggestions and 30-minute step outcomes, but the Manager H005 original cohort still cannot be reconstructed exactly from public files. Falsely declaring its skipped analysis a replicated RCT would damage scientific reliability.

## 4. Proactive basic income: distinguish distribution machinery from economic impact

**Real money / actual aid:** [GiveDirectly UBI research](https://www.givedirectly.org/2023-ubi-results) compares a long-term monthly transfer, short-term monthly transfer, one-off lump sum and control through assigned villages; the studied context favored lump sum over the short-time stream on several productive outcomes and short-term streams on some wellbeing outcomes. This finding is conditional, not a universal rule. [Kenya spillover study](https://www.nber.org/papers/w26600) found outside-recipient local multipliers and relatively little inflation in its studied rural context—crucially a reminder to measure spillovers and price changes rather than assume all transfers merely reshuffle identical totals.

**Crypto UBI:** [GoodDollar](https://www.gooddollar.org/) distributes G$ tokens, making an on-chain distribution *observable*, but claim count/transaction volume is not comparable to redeemed purchasing power, retained resources or measured wellbeing. [Circles UBI](https://www.frontiersin.org/journals/blockchain/articles/10.3389/fbloc.2024.1362939/full) and the [small qualitative pilot analysis](https://arxiv.org/html/2504.02714v1) underline local liquidity, merchant acceptance, governance and broader social organization constraints; a 25-person purposive survey is not a causal RCT. [World's whitepaper](https://whitepaper.world.org/designing-for-scale/2026-03-24) addresses uniqueness and token issuance; identity/anti-sybil proof is not itself consent, poverty relief or zero-privacy-risk certification.

**Corporate redistribution:** [Anthropic's 2026-10-18 Public Benefit Fund](https://www.anthropic.com/news/public-benefit-fund) proposes committing 5% of its shares **subject to shareholder approval**, and potentially more by valuation; direct population distributions are described as possibilities, not a launched crypto UBI. Elon Musk's *universal high income* rhetoric and 2026 SpaceX-share pledge are policy/proposed wealth-sharing statements, not proof he originated UBI or has delivered recurring universally available cash transfers. Avoid collapsing conditional company-equity commitments, token grants and actual settled cash into one category.

**Manager opportunity** — Proactive income support is a constrained social intervention, not merely a wallet-faucet bot:
1. Discover published *aggregate* service failures, missing infrastructure and lawful existing support programs; do not profile individuals without consent.
2. Compare **NO_ACTION**, process simplification, eligibility notification with consent, direct cash, recurring transfers, and local service improvement; each mechanism changes welfare differently.
3. Secure real issuer/operator money and rights; do not assume that "founder approved development" authorizes third-party transfers or tax filing.
4. Record external ledger receipts, realizable local purchasing power, net beneficiary resources, fees, leakage, displacement, privacy costs and harms.
5. Run a preregistered RCT or well-supported quasi-experiment with follow-up; show confidence interval and nonrecipient spillovers. Mere UBI token minting stays **P0/P1**, not automatic **P4**.
6. For crypto experiments, start with read-only on-chain observation; inspect smart contract and token governance, costs and compliance separately. Do NOT create a new token or marketplace merely to have something to deploy.

## 5. Intervention ecosystem: evidence from other fields

| External project | What it gets right | What Manager should reuse | What it cannot prove |
|---|---|---|---|
| [Behavior Change for Good megastudy](https://www.nature.com/articles/s41586-021-04128-4) | same outcome and horizon for many actions | intervention registry, head-to-head designs, cost/durability | universal portability |
| [HeartSteps](https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/) | availability/timing and momentary randomization | context gating, MRT policy logs, proximal windows | lifetime wellbeing or H005 exact replication |
| [Opower field trials](https://www.sciencedirect.com/science/article/pii/S0047272711000478) | external energy meters; hundreds of thousands of randomized households | independent measured kilowatt-hour change | permission-free home manipulation |
| [GiveDirectly](https://www.givedirectly.org/ubi) | payment, baseline and beneficiary outcomes separated | amount, duration, control, spillover outcomes | hypothetical free new money from tokens |
| [Open Bandit Pipeline](https://github.com/st-tech/zr-obp) | known logged propensities and OPE API | IPS/SNIPS/DR, effective sample size/overlap refusal | unsupported new action effect |
| [DoWhy](https://github.com/py-why/dowhy) / [CausalPy](https://github.com/pymc-labs/CausalPy) | transparent estimand and model/sensitivity | DAG/refuters/difference-in-differences | permission or randomization on demand |
| [OpenAQ](https://docs.openaq.org/resources/measurements) | public independent outside readings | environmental baseline/context readback | indoor air improvement without indoor sensor |
| [Open Collective](https://developers.opencollective.com/) | public historical finance ledger | F003 existing read-only integration | Manager-caused external transfer/benefit |

**Environment is not only 'physical.'** Existing stores, open-source maintainer reviews, community funds, public datasets, delivery services, regulated public benefits, open-source robots and verified applications can all provide legitimate observation–action–outcome cycles. Require actual rights for the *act*, not just a publicly accessible webpage. Reuse these settings before building a generic new agent marketplace. A marketplace is a coordination and settlement layer, not a causal welfare evaluator.

## 6. Research agenda for Manager's next actual scientific milestone

(1) **Question-meaning-preserving human forecast benchmark:** rights-reviewed choice text and study metadata; test random baseline, original encoder and Qwen with identical unseen studies; TVD/Brier, subgroup, OOD.  
(2) **Error-model challenge:** on heldout studies, train predicted TVD and calibrated abstention. Use at least one method that does not fine-tune a model. Report AUROC *and* coverage/error tradeoff.  
(3) **RCT effect benchmark:** randomized treatment/control labels from defensible openly released experimental data; compare estimated ATE errors separately from forecast fit. The [megastudy's paper](https://www.nature.com/articles/s41586-021-04128-4) reports open replication data/code subject to dataset terms; first inspect grants and license. Criteo Uplift dataset has CC BY-NC-SA terms and purposely perturbed samples which do not preserve original incrementality; do not claim original causal effect reproduction using it.  
(4) **Action benchmark:** evaluate budget, scope, identity, timeout, duplicate dispatch, self-authorizing requests and negative net outcomes with existing Phase05 kernel.  
(5) **Field bridge:** authorizing issuer, exposure limits, independent meter or financial provider, preregistration, potential outcomes assumptions, harms, matched timeline, null/negative publishing.  
(6) **No short-circuit:** zero end-to-end human welfare proof until actual P3/P4. Existing phase05 F002 design and F003 third-party historical ledger are necessary preparatory engineering only.

## 7. Peer writing and editorial design: what to copy as a method

[Simile blog](https://www.simile.com/blog): question-led titles, human stories, author/read time, descriptive illustration, clear numeric examples, figures, caveats and references. [Aaru publications](https://aaru.com/publications): narrow publication index, one memorable headline statistic, visual evidence panels, executive summary **plus** full transparent methodology (same paper, two levels). [Existing Manager page](https://aniccaai.com/blog/manager) already has many English and Japanese essays and prior simulations; it reads more like a long archive of text links than a research journal. **Do not build a competing site.** Improve existing `/blog/manager` as an original, accessible research magazine backed by GitHub versioned posts, interactive evidence/demos, visible proof levels, fixed citations, benchmark versions and reproducible notebooks. Do not copy Aaru/Simile branded art, website source, logos or proprietary content. See [research journal design](../../website/RESEARCH_JOURNAL_DESIGN.md).

## 8. Claim reliability checklist for every article and book chapter

- Original URL, organization, date/version and license/terms separately logged.
- Paper results, vendor assertions, reproduced Manager measurements and proposed hypotheses receive different attribution.
- A historical dataset/benchmark is NOT a Manager field intervention.
- Question/survey/population mismatch means invalid cross-model ranking, even when a metric has the same name.
- Model calibration / abstention / comparative randomized treatment efficacy / actual execution receipt / downstream net welfare are scored separately.
- NO_ACTION is always eligible; track conflicts and harmful or null findings.
- Dynamic model prices, market odds, founder announcements and website pages need an as-of date and independent re-verification.
- No copyrighted figures or private individual responses embedded in original content.
- No source text, paper content, images, video or personally sensitive data is represented as permissively licensed by virtue of public access.
- Evidence-open ≠ data-open ≠ code-open ≠ weight-open. Publicize exactly what can be independently reproduced.

**Manager science status:** Phase00–02 completed scoped engineering, Phase03 H005 scientifically skipped, Phase04 scoped research concluded but Gate1 unmet, Phase05 K001–K014 offline software accepted, Phase06 F001–F003 preparatory acceptance, F004/F007 legitimately blocked, F005/F006/F008/F009 require real field outcomes. No verified Manager-caused beneficiary gains. This research does not change `tasks.json`.
