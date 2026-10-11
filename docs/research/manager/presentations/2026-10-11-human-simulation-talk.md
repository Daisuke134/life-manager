# Human Simulation, Social World Models, and Environment Design

2026-10-11。英語slides、日本語speaker notes。約20分想定、main18枚＋appendix2枚。実際の発表は未実施。

## 1. Human simulation, social world models & environment design

Aaru · Simile · AI Economist · physical and predictive world models

**Research question** — Can changing shared conditions improve the lives of people who never use the AI?

**Today’s goal** — Understand what each approach models, optimizes, and actually validates.

**Manager** — Ambient AI for shared environments. Current stage: architecture and benchmark design.

発表ノート: 今日は、人間シミュレーションと環境設計を、Aaru、Simile、AI Economistから比較します。個人の相談に答えるAIだけでなく、人が選べる行動や資源へのアクセスを決める共有条件へ作用するAIを考えています。Managerは現在、アーキテクチャとベンチマークの設計段階です。完成済みの社会改善を発表する場ではありません。モデルの目的と、公開証拠が何を支持するかを区別して、研究室から測定と実験設計への批判をもらうことが目的です。

## 2. Four different questions

“Simulation” does not identify one method.

**Population** — Who is represented, and which traits co-vary?

**Behavior** — How will people respond under specified conditions?

**Institutions** — Which shared rules should change, accounting for adaptation?

**World dynamics** — What happens after an action, and can we plan with that model?

発表ノート: 最初に四つの問いを分けます。人口生成は、どんな人がどれだけいて、特性がどう結びつくか。行動予測は、その人々が条件にどう反応するか。制度設計は、応答を考慮して何を変えるべきか。世界の動態は、行動後に状態がどう変わるかです。人の会話を多数生成しても、この四つがすべて正しく解けるわけではありません。AaruとSimileは予測、AI Economistは共有ルールと適応を強く扱います。

出典: [Aaru methodology · Sep 24, 2026](https://aaru.com/publications/population-simulation-at-the-replication-floor-research)

出典: [Simile confidence · Aug 25, 2026](https://www.simile.com/blog/confidence)

出典: [AI Economist · extended paper, 2021](https://arxiv.org/abs/2108.02755)

## 3. What makes a model useful for action?

State, observation, action, transition, objective, uncertainty.

**Representation** — Observed evidence is not the complete world state.

**Prediction** — Estimate behavior and next states under candidate actions.

**Decision** — Compare candidates against a stated objective and constraints.

発表ノート: 世界モデルという言葉は、3D映像に限定しません。見えていない状態や構造を表し、予測と判断を支えるものです。観測と状態を分け、可能な操作、遷移、目的、不確実性を定義します。社会の状態には資源、関係、ルール、信念、権限もあります。ただし、表現を持つこと、予測すること、介入効果を識別することは別です。この区別を保つと、物理系と社会系の共通点と違いが明確になります。

出典: [Meta V-JEPA 2 · Jun 11, 2025](https://arxiv.org/html/2506.09985v1)

出典: [Simile What-If Machine · Sep 2, 2026](https://www.simile.com/blog/what-if-machine)

## 4. Aaru: evidence to a synthetic population

Core population and behavioral models are described as non-language models.

**1 · Define** — Decision, audience, questions, valid options, constraints.

**2 · Ground** — Public, licensed, and customer evidence; reconcile coverage and cadence.

**3 · Model** — Learn supported joint trait structure; sample complete profiles.

**4 · Predict** — Behavioral responses, microdata, distributions, cross-tabs.

Independent columns can match margins and still create the wrong population.

発表ノート: Aaruの人口生成と行動の中核は、同社の説明では言語モデルではありません。対象、質問、選択肢を決め、異なる粒度や時期のデータを統合し、特性の共同構造を学び、プロフィールを生成します。年齢と雇用の各分布が合っていても、年齢別の雇用が違えば世界は別物です。ただし、learned networkの種類や損失関数は非公開です。Bayesian networkやGNNと勝手に特定せず、公開説明の範囲で理解します。

出典: [Aaru simulation pipeline](https://aaru.com/simulation)

出典: [Aaru methodology · Sep 24, 2026](https://aaru.com/publications/population-simulation-at-the-replication-floor-research)

## 5. Aaru: what was validated?

Company-reported September 2026 evaluation.

**Survey shares** — 2,993 questions · 186 studies / Observed MAE: 3.53 pp / Mean TVD: 7.62 pp

**Purchasing ranks** — 92.4% brand-pair rank agreement / 14 category-period groups / Not individual purchase accuracy

**Scope** — Univariate shares and ranking. Higher-order response coherence and real policy effects remain separate tests.

Aggregate fit ≠ joint fidelity ≠ causal policy validity.

発表ノート: 公開研究では回答割合と購買順位を測っています。MAE3.53ポイント、平均TVD7.62ポイントは回答分布の誤差です。購買順位の92.4%はブランドの対比較で、個人購入や売上額の正答率ではありません。企業側の研究で、独立再現ではありません。過去資料への取得制限と評価用データ条件を設けていますが、高次の回答相関や個票の整合、現実政策の効果はこの数字で証明されません。異なるデータセットのSimile数値と単純なランキングにしないことも大切です。

出典: [Aaru methodology · Sep 24, 2026](https://aaru.com/publications/population-simulation-at-the-replication-floor-research)

## 6. Simile: learn from what people say and do

Current product descriptions go beyond prompted fictional personas.

**Grounding** — Behavior logs + surveys + interviews + experiments.

**Response model** — Population + situation + valid actions → action distribution.

**Error model** — Predict how far the simulation may be from observed human responses.

発表ノート: Simileは行動ログと調査・インタビュー・実験を接続する構想を説明します。ログは何をしたか、自己報告は背景と理由を捉え、say-do gapも学びます。confidence記事はQwen3.5-27Bをfine-tuneしたモデルを図示しています。入力は人口、状況、可能な行動。出力は分布です。人間データへの接地が核心で、一般LLMに架空人格を書くだけではありません。データの全容、学習の全損失、長期相互作用の実装は非公開です。

出典: [Simile What-If Machine · Sep 2, 2026](https://www.simile.com/blog/what-if-machine)

出典: [Simile confidence · Aug 25, 2026](https://www.simile.com/blog/confidence)

## 7. Three Simile research strands

Do not transfer one study’s metric to another system.

**Generative Agents · 2023** — 25 fictional agents / Memory / reflection / planning / Believability evaluation

**Individual agents · 2026 v3** — 1,052 real people / Self-report grounding / 83% normalized; 65.67% raw GSS accuracy

**Socrates · EMNLP 2025** — 170 train / 40 held-out studies / Human-response fine-tuning / 26.3% relative Wasserstein-error reduction for one model

発表ノート: 研究系譜も区別します。Smallvilleは自然な行動を出す記憶・振り返り・計画の研究です。個人研究は実在者の自己報告をGPT-4oへ与える方式で、83%は人間の再テストに対する比率です。実際の一致率は65.67%。経済ゲームでは方式間の有意差がありません。Socratesは社会科学実験から学習し、未知研究で分布を評価します。26.3%は特定モデルのWasserstein誤差削減です。これらを現行商用システムの一つの性能値にまとめないようにします。

出典: [Generative Agents · 2023](https://arxiv.org/abs/2304.03442)

出典: [Individual simulation · v3, Jun 28, 2026](https://arxiv.org/abs/2411.10109v3)

出典: [Socrates · EMNLP 2025](https://aclanthology.org/2025.emnlp-main.1530/)

## 8. Confidence predicts error, not certainty

TVD = 0.5 × sum of absolute differences in outcome shares.

**Illustrative distributions** — Observed: 50 / 30 / 20% / Predicted: 40 / 40 / 20% / TVD = 10 percentage points

**Published high bucket** — 95% met TVD < 0.16 on the evaluation set. This is not 95% correct individual behavior.

**Validation** — ~8,600 held-out questions / Grouped 5-fold validation / Question and sample leakage controlled

Selective prediction lowers retained risk while losing coverage.

発表ノート: TVDは回答分布の差です。ここは計算例で、実データではありません。50、30、20%と40、40、20%なら絶対差の合計は20ポイント、半分のTVDは10ポイントです。SimileのHigh95%は、評価セットでTVD0.16未満となった割合です。内部のdecision-quality評価から閾値を決めています。用途ごとの損失や未知条件で校正が変わる可能性があり、安全確率とは読めません。

出典: [Simile confidence · Aug 25, 2026](https://www.simile.com/blog/confidence)

## 9. AI Economist: two goals, one shared world

Residents adapt to institutions; institutions adapt to residents.

**Residents** — Gather, trade, build. Maximize private utility from wealth minus labor burden.

**Social planner** — Choose a common tax schedule. Maximize the specified social welfare objective.

**World** — Code enforces inventory, orders, escrow, labor, taxes, and redistribution.

発表ノート: AI Economistは二層の強化学習です。住民は個人効用を、plannerは指定された社会厚生を最大化します。住民は木や石を採り、売買し、家を作ってcoinを得ます。plannerは共有税率を変更します。資源と取引はコードの台帳にあり、agentが成功したと語って変わるものではありません。Managerに近いのは税そのものより、共有ルールと、それに適応する主体を別目的で扱う構造です。

出典: [AI Economist · extended paper, 2021](https://arxiv.org/abs/2108.02755)

出典: [AI Economist · fixed source, archived repo](https://github.com/salesforce/ai-economist/tree/a84d5f3fdcabb207d9fde7754d34906903b3e184)

## 10. The objective is a design choice

The model does not discover what society ought to value.

**Agent utility** — u = (C^(1−eta) − 1)/(1−eta) − alpha·L / C: coin holdings; L: cumulative labor / Reward: change in utility

**Planner objective** — One option: (1 − normalized Gini) × total wealth. Another weights individual utility toward lower endowments.

**Missing by default** — Physical / mental health, agency, non-users, and ecological effects require additional measures.

発表ノート: 個人効用はcoin保有の逓減効用から労働負担を引きます。coinは消費flowや実所得ではなく模型の富です。plannerには平等×生産性や低保有者を重く見る効用が用意されています。論文とコードのscale差もありますが、ここでは概念を示しています。重要なのは、どの目的も設計者が指定するということです。健康や尊厳、他の生命への影響は勝手にrewardに入っていません。社会目的の妥当性も実証・議論の対象です。

出典: [AI Economist · extended paper, 2021](https://arxiv.org/abs/2108.02755)

出典: [AI Economist · fixed source, archived repo](https://github.com/salesforce/ai-economist/tree/a84d5f3fdcabb207d9fde7754d34906903b3e184)

## 11. Changing a rule changes everyone’s response

A policy cannot be scored with behavior frozen in place.

**Interaction** — Higher tax → builder activity changes → resource demand changes → suppliers’ income changes.

**Learning** — Separate PPO policies co-adapt. This approximates learning; it does not prove equilibrium or global optimality.

**Evidence boundary** — Small human game transfer used modified conditions and a fixed schedule. It was not a national policy deployment.

発表ノート: 建設者にかける税でも、本人だけを見れば不十分です。建設量が減れば資源への需要が減り、採集して売る住民にも波及します。双方をPPOで共同適応させますが、毎回厳密な最適応答を解いた均衡証明ではありません。人間実験も変更された小ゲームへの固定税率transferです。最初のManagerでは、複数の応答モデルと固定ルールを比較し、適応を省くとpolicy順位が変わるかを測る方が有用です。

出典: [AI Economist · extended paper, 2021](https://arxiv.org/abs/2108.02755)

出典: [AI Economist · 2020 paper](https://arxiv.org/abs/2004.13332)

## 12. World Labs and JEPA ask different questions

Physical implementations, broader world-model ideas.

**World Labs** — Persistent spatial context and multimodal generation. Atlas goes beyond static 3D. R2S2R compares simulated and real policy behavior.

**LeCun / JEPA** — Predict useful abstract representations, not every pixel. V-JEPA 2 adds action-conditioned robot prediction and model-predictive control.

**Social models** — Population, beliefs, institutions, incentives, networks, resource access. Observational fit does not identify intervention effects.

発表ノート: World Labsを静的3D生成だけで説明するのは古いです。Atlasには時間と多モーダル、R2S2Rにはsim-realのpolicy比較があります。JEPAは画像を生成する名前ではなく、行動に有用な抽象表現を予測します。V-JEPA2では行動条件付き予測と再計画を使います。LeCunの構想全体はロボットに限定されません。Managerは社会的な状態と操作を扱うので、交絡、他者の反応、制度変更後の適応を追加で検証します。

出典: [World Labs Atlas · Sep 1, 2026](https://www.worldlabs.ai/blog/atlas)

出典: [World Labs R2S2R · Jul 28, 2026](https://www.worldlabs.ai/blog/real-to-sim-to-real)

出典: [Meta V-JEPA 2 · Jun 11, 2025](https://arxiv.org/html/2506.09985v1)

## 13. Prediction is not an intervention effect

Conditioning on an observed action is not automatically do(action).

**Observational** — People who used a service may already differ from those who did not.

**Interventional** — Changing access can change selection, capacity, incentives, and other people’s behavior.

**Real outcomes** — Predefine comparison, measurement window, subgroup harms, spillovers, and uncertainty.

Semantics → prediction → intervention validity → real impact: separate evidence.

発表ノート: 社会では、サービスを使った人が良い結果を持っていても、使ったことが原因とは限りません。アクセスを変えると選択や容量、インセンティブ、周囲の反応も変わります。行動条件付きモデルがあるだけでは、この交絡は消えません。無作為化や段階導入などを検討し、可能でない場合は識別仮定と感度分析を示します。模型の因果効果と現実への外的妥当性も分けます。

出典: [AI Economist · extended paper, 2021](https://arxiv.org/abs/2108.02755)

出典: [World Labs R2S2R · Jul 28, 2026](https://www.worldlabs.ai/blog/real-to-sim-to-real)

出典: [Simile confidence · Aug 25, 2026](https://www.simile.com/blog/confidence)

## 14. Manager Environment Lab

Proposed first build: a closed loop with auditable evidence.

**Model** — Evidence → population + constraints + response kernel.

**Compare** — Shared-rule candidates → numeric transitions → independent scores.

**Act and learn** — Apply / readback / measure / update. Cloud-ready core; no beneficiary account required.

Proposed architecture · implementation and field results pending

発表ノート: Manager Environment Labでは、人口と制約と応答をつなぎます。候補は供給、容量、接続、利用条件、配分などの構造変更です。数値worldが制約を守り、独立evaluatorが成果を採点します。初期はsimulation executor、現実接続は別modeです。クラウドで実行でき、受益者はアカウント不要です。私たちが設計しているpipelineの提案で、既に実装済みという表示ではありません。

## 15. Measure four tracks separately

Do not promote a completed tool call into a wellbeing claim.

**Prediction** — Held-out response distributions and calibration.

**Policy** — Same-budget baseline comparison; adaptation and group effects.

**Execution** — Typed actions, receipts, independent readback, failure recovery.

**Outcome** — Real-life results against a credible comparison, including costs and harms.

発表ノート: 四つのtrackを別にします。予測が当たるか、変更を選べるか、実行できるか、生活が改善したか。営業時間を変えるreceiptがあっても、健康改善の証拠ではありません。健康は健康指標、精神は妥当な尺度、富は可処分資源や負担などで測ります。平均改善と最低群を分け、他の地域や生命へ負担を押し出していないかも観測します。観測できない結果はunknownにします。

## 16. What we plan to build this month

A mechanism demo plus empirical checks; field claims only with field evidence.

**Working benchmark** — Two structural worlds, shared contracts, fixed baselines, held-out regimes.

**Evidence package** — Manifest, traces, failure cases, costs, group outcomes, reproducible scorecard.

**Grounding path** — Validate a real-data prediction slice; define an operator-specific shadow or field comparison.

Build target, not current achievement

発表ノート: 今月は二つのworldを同じ契約で動かし、baselineと未見条件を比較するcodeと証拠一式を目標にします。実データの予測検証を接続し、現実作用にはoperatorと比較計画を用意します。いきなり古い二層PPOを巨大訓練する計画ではありません。現実pilotが間に合わない場合は模型の成果と限界を示し、反証可能な次の実証を提示します。締切があっても未測定の生活改善を数字にしません。

## 17. Questions for the lab

Feedback that can change the experiment.

**Validity** — Which measurements distinguish plausible responses from intervention-valid predictions?

**Adaptation** — Which joint traits or behavioral changes can reverse the ranking of policies?

**Wellbeing** — What outcomes, comparisons, and subgroup tests would justify a benefit to non-users?

発表ノート: 研究室には、この三つを相談したいです。自然な反応ではなく制度変更に耐える予測をどう測るか。どの人口関係や適応がpolicy順位を逆転させるか。非利用者への恩恵を主張するために、どの指標と比較が必要か。研究者として批判できる具体的な模型と失敗を持ち込むことが、関係づくりにも技術の改善にもつながります。

## 18. Reading map

Methods before headlines; source versions matter.

**Aaru** — Population simulation at the replication floor: methodology and limitations.

**Simile** — Confidence + What-If Machine; Generative Agents, individual study v3, Socrates.

**AI Economist / world models** — Extended paper + fixed Foundation code; Atlas, R2S2R, V-JEPA 2.

発表ノート: 読む順番は、方法と評価からです。Aaruは人口と検証、Simileはconfidenceと研究系譜、AI Economistは数値world、目的、共同適応を追います。物理world modelsは、何を状態にし何を予測するかを比較します。すべて出典をノートに入れています。商用非公開部分は再現コードがあると誤認しないようにします。

出典: [Aaru methodology · Sep 24, 2026](https://aaru.com/publications/population-simulation-at-the-replication-floor-research)

出典: [Simile confidence · Aug 25, 2026](https://www.simile.com/blog/confidence)

出典: [AI Economist · extended paper, 2021](https://arxiv.org/abs/2108.02755)

出典: [Meta V-JEPA 2 · Jun 11, 2025](https://arxiv.org/html/2506.09985v1)

## 19. Appendix: one company, two intervention levels

Life Manager revenue supports execution traction; Manager adds environmental decisions.

**Life Manager** — AI that builds and operates businesses to create wealth. Quantify actual revenue, costs, customers, and human involvement.

**Manager** — Ambient AI that improves shared conditions. Report benchmark and field evidence at their actual stage.

**YC narrative** — Same direction, different scope. Existing business revenue is not population-level impact or new-product revenue.

Current revenue amount not verified in these materials

発表ノート: YCでは同じ目的の会社として説明します。Life Managerは事業を作り運営するexecution engine、Managerは環境レベルの判断を追加する構想です。売上があるというユーザーの申告を尊重し、現在金額を確認するまでは数値を埋めません。自社売上、顧客の利益、Manager売上を分け、人的作業と費用も示します。MRRではない売上をMRRとしません。

出典: [YC application deadline](https://www.ycombinator.com/apply)

## 20. Appendix: directly related teams

Human and population simulation, not generic AI adjacency.

**Simile** — Evaluations / Evaluations Engineering / Research: human-grounded models and measurement.

**Aaru** — Population Simulation / Simulation Engineering / Evaluation. Published visa + relocation support.

**Primitive** — Research / Founding Engineering / Intern: human behavior agents and product journeys.

発表ノート: 直接性を優先してSimileとAaruを中心にします。Primitiveは製品内行動の範囲で直接近い企業です。要求年数、GPU訓練、PhD相当の研究を作品だけで満たしたとは書きません。Aaruはビザと転居支援を明記しています。現在の専門イベントはSBP-BRiMSが確認でき、SimileとAaruの未来イベントは未確認です。

出典: [Simile Evaluations role](https://jobs.ashbyhq.com/simile/33d75074-c23b-4a1f-bfdb-129bcc5be662)

出典: [Aaru Evaluation role](https://aaru.com/careers/4490a4b7-ad45-4bf6-b00f-190a6d9f41ad)
