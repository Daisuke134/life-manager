# Manager — Open Research Book / Living Field Guide

> **2026-10-24 latest owner instruction:** 研究A01–A09を先行し、研究に沿う記事と無料公開書籍を並行執筆・配布する。旧「記事は本体後段」指定はこの範囲で更新された。GitHub原稿、owned blog、PDF/EPUB、既存の配信先を無料公開候補とし、媒体ごとに実URL/readbackで公開を確認する。外部媒体が未接続でもGitHub原稿公開を別に進め、未公開媒体を公開済みにしない。有料広告/配信契約を追加しない。全書籍の完成や全媒体公開は未達。

**最初の新しい完成原稿:** [AIによる説得を、どこまで確かめられるか](../articles/2026-10-24-ai-persuasion-reproduction-ja.md)。Costelloらの訂正済み研究を上流Rコードで再実行し、6表45行照合と7部validatorの実結果を説明する実習章。予測/介入/説得を学び始めるエンジニア向けに、単位・分母・欠測・追跡・baselineとモデル学習の関係を扱う。GitHubへのpush後の原稿公開と、blog/PDF等の公開状態は別管理。既存の2026-10-22 Artificial Societies章と同じ本へ接続し、第三のbook outlineを作らない。

**本書の現在の中心:** 行動の予測→働きかけ→行動/苦しみ/持続/害の観測→モデルと実施方法の更新。下記旧16章は参照可能な全体構成として保存し、環境制御/金融を現在の必須実装へ復帰させない。各章は出典、実習、実測、未実測、訂正履歴を持ち、企業の宣伝値と独立再現を区別する。

> **2026-10-22 active production rule:** This is the canonical chapter outline. The separate three-volume curriculum is a packaging/teaching view of the same sources, not additional manuscripts to finish first. Start with one complete, source-checked chapter on prediction→intervention→verified benefit; use [the updated P plan](../plans/2026-10-22-manager-research-products-plan.md#2026-10-22-whole-project-alignment--concrete-editorial-and-founder-work). Older finance/indoor partner examples below are optional learning cases: F004/F007 are skipped and not prerequisites to the owned digital product. A book outline is not a completed book or research result.

**Working title:** *The What-If Machine Meets the Real World: Prediction, Intervention, and Verifiable Human Benefit*  
**Japanese companion:** 『予測から介入へ――AIは世界を本当に良くできるのか』  
**Status:** Book proposal and source/experiment outline, not a completed or publicly distributed book. **Owner:** Manager / Anicca research; GitHub version-controlled original text only.  
**Mission:** End suffering, a directional objective; human impacts must be observed and causally assessed, not declared from software tests.  
**Core first-source index:** [cross-field evidence](../research/crossfield-20261021/SOURCES.json) and [Japanese synthesis](../research/crossfield-20261021/REPORT_JA.md).

## Reader promise

For computer scientists, economists, policymakers, social scientists and founders: learn to connect behavioral simulation, causal experiments, economic and physical agent environments, finance/UBI, RL and trustworthy deployment. Work through reproducible exercises with real authorized public observations without mistaking virtual scores for human progress. No pretense to reproduce every proprietary model, own all data rights or have tested every possible intervention.

## Book architecture

### Part I — Understanding and forecasting people

**Chapter 1. Why the world needs a What-If Machine**
- A hypothetical electricity bill or administrative barrier as the running problem; observe / predict / intervene / verify.
- [Simile What-If](https://www.simile.com/blog/what-if-machine); [Aaru research](https://aaru.com/publications/population-simulation-at-the-replication-floor-research).
- *Lab:* calculate conditional frequency vs forecast and abstain where the units differ.

**Chapter 2. What people do and why they say they do it**
- Transactions, mobility, surveys, consented interviews; memory bias; distribution shift; sample selection.
- [Stanford interview-based generative agents](https://hai.stanford.edu/policy/simulating-human-behavior-with-ai-agents), [Socrates](https://aclanthology.org/2025.emnlp-main.1530/).
- *Lab:* provenance ledger and strict study/participant/semantic holdout.

**Chapter 3. Synthetic populations aren't real people**
- Demographic IPF/raking, microsimulation, model calibration, synthetic survey answer coherence and leakage.
- [Aaru response distributions](https://aaru.com/publications/population-simulation-at-the-replication-floor-summary).
- *Lab:* a toy, nonprivate population showing marginals and impossible joint outcomes.

**Chapter 4. Know when the model doesn't know**
- TVD, Brier, calibration, error predictors and out-of-distribution uncertainty.
- [Simile confidence predictor](https://www.simile.com/blog/confidence).
- *Lab:* train/read-only prediction-error estimator and coverage-abstention chart.

### Part II — Learning what actually causes change

**Chapter 5. The difference between correlation and intervention**
- Potential outcomes, DAGs, counterfactual nonidentification, positivity, instrumental designs.
- [DoWhy](https://github.com/py-why/dowhy), [CausalPy](https://github.com/pymc-labs/CausalPy).
- *Lab:* prove synthetic TVD=0 can coexist with ATE error; no causal claim.

**Chapter 6. The megastudy and the error of expert intuition**
- Many interventions, uniform measurement, RCT/cluster/MRT, preregistration, long-run follow-up.
- [Behavior Change for Good Nature megastudy](https://www.nature.com/articles/s41586-021-04128-4), [HeartSteps](https://pmc.ncbi.nlm.nih.gov/articles/PMC6401341/).
- *Lab:* error bars, multiple-comparison correction, no-action arm and 30-day vs 1-year separation.

**Chapter 7. Policies that change the people they model**
- The AI Economist, adaptive incentives and gaming, social influence, equilibrium/spillover harms.
- [AI Economist](https://pmc.ncbi.nlm.nih.gov/articles/PMC9067926/), [Kenya cash spillover](https://www.nber.org/papers/w26600).
- *Lab:* simulated competitive response to a newly introduced tax/subsidy, explicitly P0.

### Part III — Agents with tools, money and environments

**Chapter 8. From virtual vending machines to actual shops**
- Long-horizon coordination, tool uncertainty, human labor, pricing, refund, delivery and at-most-once execution.
- [Andon Bench](https://andonlabs.com/evals/vending-bench-2), [Anthropic Project Vend](https://www.anthropic.com/research/project-vend-2).
- *Lab:* simulate provider timeout-before-effect and after-effect; forbid blind re-send.

**Chapter 9. Prediction markets are not human simulators**
- Event forecasts, selection and resolution, population responses, speculative prices, causal interventions.
- [Polymarket orderbook rules](https://help.polymarket.com/en/articles/13364488-how-are-prices-calculated).
- *Lab:* compare read-only event probability calibration with a separate audience-response dataset.

**Chapter 10. Universal basic income versus new tokens**
- GiveDirectly grants, GoodDollar on-chain emission, Circles local merchant networks, World proof-of-uniqueness, corporate equity funds.
- [GiveDirectly UBI](https://www.givedirectly.org/2023-ubi-results), [GoodDollar](https://www.gooddollar.org/), [Circles case](https://www.frontiersin.org/journals/blockchain/articles/10.3389/fbloc.2024.1362939/full), [Anthropic fund](https://www.anthropic.com/news/public-benefit-fund).
- *Lab:* funding ledger vs actual purchasing power; track real/virtual and liquidity/fees/harms.

**Chapter 11. Physical interventions and the independent sensor**
- Smart buildings, indoor vs outdoor PM2.5, exposed dose, power/noise, controllable facility rights, randomized crossovers.
- [Opower RCT](https://www.sciencedirect.com/science/article/pii/S0047272711000478), [OpenAQ](https://docs.openaq.org/resources/measurements).
- *Lab:* study a public outside PM2.5 series, label indoor impact not measured.

### Part IV — Training without fooling ourselves

**Chapter 12. Fine-tuning behavioral models with open weights**
- Small Qwen/LoRA, base models vs frozen encoder, study-holdout, label semantics, license and server costs.
- [Tinker](https://tinker-docs.thinkingmachines.ai/tinker/quickstart/), [TRL](https://github.com/huggingface/trl).
- *Lab:* train on synthetic rights-cleared tasks only if meaning/ground truth valid; publish baseline vs new version.

**Chapter 13. Reinforcement learning needs a trustworthy reward**
- Offline RL, bandits, OPE, importance-weight support, reward hacking, individual/aggregate welfare separation.
- [ZOZO Open Bandit Pipeline](https://github.com/st-tech/zr-obp), [Tinker cookbook](https://github.com/thinking-machines-lab/tinker-cookbook).
- *Lab:* inspect low effective sample sizes and force abstention; never use fabricated beneficiary utility as RL reward.

### Part V — An accountable institution that can act

**Chapter 14. The Manager kernel**
- Typed sources, options, signing, budget, outbox, reconcile, readback, evaluation, version rollback, audit.
- [Phase05 actual code/verification](../verification/PHASE05_FINAL_OFFLINE_KERNEL_EVIDENCE_JA.md).
- *Lab:* two-domain offline fixture demonstration; P0 only.

**Chapter 15. The first legitimate field Blessing**
- Site/legal issuer partnership, preregistered RCT or valid comparator, independent P1-P4 and costs/displacement.
- [F004–F009 execution protocol](../research/crossfield-20261021/PHASE06_FIELD_BLUEPRINT.md).
- *Lab:* draft a detailed auditable protocol; do not claim a P4 without field data.

**Chapter 16. Why open source is not enough, and what comes next**
- Governed permission, privacy, rights, independent reviewers, incentives and model-data rights; separate foundation weight and hosted service.
- *Lab:* adversarial red-team claims and design an externally contestable audit.

## Every chapter's reusable deliverables

1. **Thesis in one sentence.** Why the method matters and which decisions it can legitimately inform.
2. **First-source table:** original organization, date/version, method, n, outcome, relevant code, license, and failure boundary.
3. **Worked math:** at least one simple example with explicit invented/real label and complete units.
4. **Counterexample:** what would make the headline false in a new scenario?
5. **One original diagram**, accessible alt text, reusable publication license only for owned visual elements.
6. **Executable or linked independent test** with exact dataset, version, environment, cost, results, nulls, and limitations.
7. **Application to Manager:** reuse as-is, wrap in adapter, train later, or reject.
8. **Evidence annotation:** P0/P1/P2/P3/P4/P5 and explicit unknown data.
9. **Question for the next field study**, not a fabricated beneficiary testimonial.

## Original publication plan (no auto-posting)

1. First original English field article already drafted: [Why Prediction Is Not Intervention](../articles/manager-prediction-intervention-blessing-en.md).
2. Next high-value individual articles: **(a)** "What Aaru and Simile Really Measure"; **(b)** "GoodDollar, GiveDirectly and the Difference Between a Token and Income"; **(c)** "Training a Qwen Confidence Model with Tinker Without Causal Hallucinations"; **(d)** "From OpenAQ to Verified Indoor Interventions"; **(e)** "How Manager's F004–F009 Evidence Gates Work".
3. Convert each to short Japanese reader notes, diagrams and publicly runnable, safe examples.
4. Technical independent review before any empirical numbers are introduced; verify original article sources and open-weight/data redistribution rights.
5. Source-vetted English manuscript then peer technical review; submit to editor/platform only with actual publishing permissions and source integrity readback.
6. Keep final book mutable as versions; current document is the **book production outline**, not evidence that chapters or a whole finished book were written.

## 2026-10-22 authorized Japanese mini-chapter

The owner explicitly requested writing AND publishing the Artificial Societies chapter on the existing owned blog; this supersedes the earlier no-auto-posting heading for this article only. Other platforms and a whole finished book are not implied to be published.

Mini-chapter between Parts I and II: **人工社会を借りて、現実から学ぶ――Rothko・説得研究・Managerの次の一歩**. Canonical source commit `a69a8a4a66e5b2f032c13efcc6bef18c446cf448`, path `docs/research/manager/articles/2026-10-22-artificial-societies-open-behavior-research-ja.md`; content-only PR #8550. It covers all 25 current official publication entries, 7 official case studies, open benchmark/data routes, 2026 persuasion corrections, an original conceptual diagram and actual aggregate inspection limits. Integrate its source manifest and executable inspection companion into the book rather than copying raw third-party full texts. Published status requires the actual existing-blog receipt/readback.

Published: [Japanese HTML chapter](https://aniccaai.com/blog/manager-artificial-societies-open-behavior-research-ja), with an 11-page Japanese PDF delivered in the owner session. [Verification record](../verification/ARTIFICIAL_SOCIETIES_CHAPTER_PUBLICATION_20261022.md) binds the source/content revisions to the real deploy and unauthenticated readback. This completes this mini-chapter's publication, not all16 planned chapters or the whole book; future source corrections remain versioned.
