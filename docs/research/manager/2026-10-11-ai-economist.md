# AI Economist: Managerの制度介入を学ぶための深読ノート

調査日: 2026-10-11 UTC。対象はSalesforceの一次論文・公開実装。Managerはambient AIとして、利用者個人の作業でなく共有環境・制度を変更し、非利用者も含むwellbeingを改善する構想と解釈した。本書は研究参照。実行順と状態は統合SSOTに置く。

## まず何が重要か

AI Economistは「経済学の質問に答えるLLM」ではない。住民に相当する経済agentsと、税制を変えるsocial plannerを同じシミュレーターで学習させる二層の強化学習である。個人は自分の税引後効用を最大化し、plannerは社会厚生を最大化する。Plannerがルールを変えると個人の最善行動も変わるため、その応答を含めて制度を評価する。Managerに最も近いのはこの構造であり、税という介入そのものではない。

ただし、最適化できたのは人間が指定した効用・地形・市場・行動の世界である。「非利用者のwellbeingを推論して自動改善できる」実証ではない。共有ルールの変更で誰がどう適応し、その適応が他人にどう波及するかを計算する研究基盤として読むべきである。

## 一次資料と現在の実装状態

- 2020原論文: [The AI Economist: Improving Equality and Productivity with AI-Driven Tax Policies](https://arxiv.org/abs/2004.13332)。初期の4-agent経済、人間参加実験、16%というheadlineはこの版の結果。
- 2021拡張論文: [The AI Economist: Optimal Economic Policy Design via Two-level Deep Reinforcement Learning](https://arxiv.org/abs/2108.02755)。one-step理論照合、4/10-agent、6空間設定、二つの社会目的を含む。今回の主要機構の参照。
- 最終出版は**PNASではなくScience Advances**: [The AI Economist: Taxation policy design via two-level deep multiagent reinforcement learning](https://doi.org/10.1126/sciadv.abk2607)、2022-05-06、8(18)、eabk2607。Crossref metadataでタイトル・DOI・日付確認。誌面サイトは403のため全文未読で、数値は読んだarXiv版に帰属させる。
- 現実データへの拡張: [Building a Foundation for Data-Driven, Interpretable, and Robust Policy Design using the AI Economist](https://arxiv.org/abs/2108.02904)。COVID-19の州stringencyと連邦subsidyを二層で扱う。
- [公開repo](https://github.com/salesforce/ai-economist)、Foundation framework、BSD-3-Clause、setup.py version 1.7.1。確認commit **a84d5f3fdcabb207d9fde7754d34906903b3e184**、commit日時2022-05-09。GitHub APIのarchived=true、pushed_at=2023-08-20。updated_at=2026-09-28はコード更新の証拠ではない。現在の公開masterを固定して読んだ。
- repo内Simulation Cardは2020-10-14更新。社会モデルは特定社会の観測データから作ったものではないと明記。
- READMEにリンクされた公式旧ブログ `blog.einstein.ai/the-ai-economist/`、`the-ai-economist-moonshot/`、`ai-economist-covid-case-study-ethics/` は接続403。代替 `salesforce.com/blog/ai-economist/` は404。これらの本文を読んだとは扱わない。

PDF、text、API metadata、git cloneは `/workspace/scratch/manager-research/oct11/ai-economist/` に保存。学習・install・外部連絡は実施していない。

## 基本語彙から動作まで

**State**は地形、資源、家、各agentの位置・在庫・escrow・累積labor・skill、注文板、税率、税期の位置など。**Observation**はそのうちactorが見える部分。**Action**はactorが実行できる選択。**Transition**はそれを受けて経済の帳簿と世界を更新するコード。**Reward**は学習の採点。**Policy**はobservationからaction分布を出すニューラルネットであり、公共政策と同語だが意味が違う。

FoundationはGym風の `reset()` と `step(actions)` を備える。Scenarioが地形・初期条件・報酬を定義し、Componentが市場、建設、採集、税などを追加する。Componentは行動数、追加state、transition、observation、mask、metrics、dense logを同じinterfaceで供給する。RLはこの外側にあり、simulator自体はPPO専用ではない。

Gather-Trade-Buildは25×25の格子上の小経済。木と石を採り、交換し、木1＋石1から家を建てるとcoinが生まれる。家は実物の住宅サービス効用ではなく建設による収入源兼障害物。Build-skillによって1軒の報酬が10〜30coinとなり、技能差と資源へのアクセス差が不平等を生む。移動・採集・取引・建設にlabor costがある。再生する資源、水、家、他agentの位置が行動を制約する。

低build-skill agentが資源を採って売り、高skill agentがそれを買って家を建てる分業が出現する。税は個人の労働量だけでなく買い手の需要を変え、売り手の価格・収入にも影響する。ここが共有環境の介入にとって重要な外部性である。

## 観測と行動の正確な形

Agentは近傍11×11空間、資源/coin在庫、自分のskill、市場の注文分布と価格履歴、現在税率、税期の進捗、前期所得の匿名sorted list、自分の現在所得に対応する限界税率を観測する。Plannerは市場、各agentの在庫、前期所得/限界税率、税情報を観測するがprivate skillを直接観測しない。論文設定ではplannerの空間観測は無効。知識非対称性があるが、完全に匿名な統計だけを使うplannerでもない。

Agentの離散行動は計50: NO-OP1、移動4、建設1、取引44。取引は木/石×bid/ask×価格0〜10。論文configは `multi_action_mode_agents:false` で一歩に一行動。Plannerは7税bracketそれぞれに21税率(0,0.05,…,1)＋NO-OPの22選択を出すmulti-discrete。7つのheadの組合せは大きいが、ひとつのflat巨大action setを作るわけではない。

Action maskは不可能な移動、資源/coin不足で履行できない注文、建設できない場所、税率curriculum上限などを禁止する。Plannerは毎step観測してLSTM状態を更新できる一方、税期開始以外ではNO-OPしか許されない。観測頻度と制度変更頻度を分離している。

## 遷移と税の仕組み

`BaseEnvironment.step`はactionをparse、乱数状態とactionをreplay logに記録し、timestepを進め、config順にcomponentsの `component_step`、次に `scenario_step` を実行し、更新済みstateからobservations/rewards/doneを作る。Component順序もモデルの一部である。

Continuous double auctionは一単位の木/石にbid/askを出す注文板。bid>=askで成立し、高bid/低ask、次に時間優先で照合し、先に置かれた注文の価格で取引する。同一agentの自己取引はskip。未約定注文のcoin/資源はescrowへ移され、50stepでexpire、各資源5件まで。単なる均衡価格の一括計算ではなく個別取引の逐次市場。

1episode=1000step、100stepの税期が10回。初日に7bracketの限界税率を固定し、最終日に徴収・均等再配分。bracket境界はUS federal 2018を縮尺して固定(0,9,39,84,160,204,510、最上位は無限)。Plannerは境界や個人別税を変えない。

所得は前期の再配分後coin総保有からの増分 `z_i = C_i(now)-C_i(period start)`。税額は各bracketに入った所得部分の合計:

`T(z) = Σ_j τ_j min(max(z-b_j,0), b_(j+1)-b_j)`。

限界税率は最後のbracketの率を全所得に掛ける率ではない。全員が同一scheduleに従い、徴収額をN人で均等割りして返す。コードでは税をescrowから取らず、inventory coinと税額の小さい方まで徴収する。この流動性/注文escrow処理も現実適用前には評価すべき仕様。

## Reward、社会厚生と最適化対象

Agent効用は `u_i(C,L)=(C^(1-η)-1)/(1-η)-αL`。貨幣の限界効用は逓減し、労働は累積の負担。主configはη=0.23、labor係数の基準0.21。報酬は毎stepの `u_i(t)-u_i(t-1)`。割引なしなら合計は終状態効用の差へtelescopingするが、γ=0.998の設定では早い効用増加と遅い負担にも影響され、単なる終状態評価と完全同値ではない。

Plannerも `SW(t)-SW(t-1)` をrewardとする。二種類を比較する:

1. 逆所得weighted utilitarian: 個人効用のweighted sum。論文はinverse incomeと記述するが、inspectしたcode `inv_income_weighted_utility` は**現在coin endowment**の `1/max(C_i,1)` を正規化して使う。weightもstateで変わる。pre-tax period incomeに固定したweightとは区別する必要がある。
2. equality×productivity: normalized Giniの補数 × coin合計。実装rewardは平均coin(合計/N)を使い、`equality_weight`で純productivityまでmixできる。paperのproductivity metricとrewardのscaleは区別する。

したがってwellbeingという価値判断は自動で発見されない。「全員のcoinを均等にする」「低保有者の効用を重視する」「labor負担も含める」は人間が選ぶ。非利用者・健康・尊厳・自由・時間・環境被害は自動でrewardへ入らない。Managerではbeneficiary集合、measurement、minimum保障、分布評価を明示することが先で、LLMでscoreを補完するだけではこの問題を解決しない。

## 二層RLの最深部

数学的な意図は、plannerが `max_πp SW(πp,π*(πp))` を解き、agentsは制度πpを所与として各自効用を最大化すること。Planner外側とagent内側は異なる目的を持つ。実装は内側を毎回厳密に解いてから外側を更新するsolverではなく、同一simulatorから経験を集め、それぞれのPPOを更新してco-adaptする近似である。税を微分してagentsの最適応答の勾配を伝播するimplicit differentiationでもない。二層だからStackelberg均衡やglobal optimumが保証されるわけではない。

Agent全員で一つのpolicy重みを共有し、個人観測と各自LSTM hidden stateで異なる行動を出す。Plannerには別policy/value network。空間にはCNN、数値にはfully connected、履歴にはLSTMを使う。Action headとvalue head、GAE/PPO clipping等は通常のactor-critic技術だが、planner変更でagentの報酬関数が変わり、agent改善でplannerの制御対象が変わる。環境が二重に非定常になる。

安定化は三つのcurriculum:

- Phase 1: no-taxのfree marketでagentsだけを学ぶ。Labor costを低い所から導入し、探索中に損を重ね「何もしない」へ崩れるのを避ける。
- Phase 2: agents checkpointを継承し、plannerも学ぶ。最大許可税率をmaskで徐々に上げ、初期の100%課税が収入探索を潰すのを避ける。
- Planner entropyを最初は高くし多様な税制にagentsを慣らし、その後下げplannerが適応済み応答を評価できるようにする。双方のentropyを維持しpremature convergenceを防ぐ。

30replica×200stepで1iterationにplanner6000transition、agentはN倍。論文本文にはPhase1 50M、Table4と公開tutorial configには25Mという不一致があるため単一の正確な再現step数とは断定しない。Phase2は約1B samples級。公開手順は16CPU/60GB、15 rollout workers、TF1.14、RLlib0.8.4、Gym0.21、Python3.7。論文の有効性と、2026年にその環境をすぐ実行できることは別。公開configは4agent/Open-Quadrant/eq×prodの具体例であり全論文実験の完全な現代互換reproductionではない。

## Baseline、戦略的応答、generalization、実証の強さ

One-step economyではSaez解析解と税率/厚生が整合し、基本的な税の学習をsanity checkする。複雑世界は無税、縮尺US federal、empirical所得分布とelasticityから計算するSaezと比較。Saezにはelasticityをgrid-searchして有利な条件を与えても比較した。これは任意の制度optimizer全般に勝った結果ではなく、指定したbaselinesとの比較。

2021版では6設定(Open-Quadrant4/10人＋Split-World10人4配置)、二つの目的で優位を報告。Open-Quadrant4/10人で対Saezのutilitarian改善>8%/2%、eq×prod>12%/8.6%。これらは各設定で学習した結果で、ひとつのplannerを未見社会へzero-shot transferした証明ではない。2020版の16%をこれらと合成して普遍的効果量にしない。

税は非単調のcamelback型にもなる。Agentは期ごとの所得を不均等にして同じ平均所得でも税を減らすtax-gamingを学ぶ。高技能者への高bracket税が購買を減らし、低技能の売り手所得も下がる。Observed elasticityが約0.87でもSaez内で最良の値は約3となる例は、単純な個人独立応答モデルの不足を示す。Tax-gamingを含んでもこのsimulatorで厚生が高いことと、将来の未知の操作へ頑健であることは違う。

人間実験は2020版にある。MTurkでUS参加者4人/ゲーム、5分、四税制をrandom orderで体験。最初のbatchは58人57episode、第二は57人68episode、低productivity<1000をそれぞれ6/8episode除外。図で分析対象参加人数が異なることに注意。結果はeq×prodがSaezとcompetitive、inverse-endowment weighted welfareが有意に高い、という限定的なもの。

さらに人間gameはtrading無効、移動/採集labor無料、建設labor15(元10)、3000step/税期300。低entropy学習から選んだ固定camelback scheduleを使い、bracket境界を1/3に再較正した。「AI plannerが実社会にそのまま移植された」「人間に対して動的二層RLが優位」「追加calibration不要」とは言えない。人間にはblocking等の敵対行動、通信問題、learning effectがあり小実験の外的妥当性には制限。

COVID拡張は現実USデータへ疫学/失業/economyをfitし、州agentsのstringencyと連邦plannerの補助を学ぶ。Log-linear policyで解釈可能性、infection等parameter摂動でrobustnessを検討する。これは純toyから一歩進むが、historical dataにfitしたsimulator内counterfactualであり政策実施の因果効果測定ではない。ここまでの一次資料に国家税制やCOVID施策の実運用成功実証はない。

## ソース読みの入口（上記commit固定）

[固定tree](https://github.com/salesforce/ai-economist/tree/a84d5f3fdcabb207d9fde7754d34906903b3e184)。ローカルrootは `oct11/ai-economist/repo`。

| path / function | 読み取る責務 |
|---|---|
| `foundation/base/base_env.py:929` `BaseEnvironment.step` | parse→component順→scenario→obs/reward、replay、done |
| 同`:614` `_generate_observations`, `:706` `_generate_masks` | component/scenario観測の合成、planner agent別観測、mask |
| `foundation/components/redistribution.py:419` `set_new_period_rates_model` | planner actionから税率へ |
| 同`:846` `taxes_due`, `:853` `enact_taxes` | bracket税計算、inventory上限制約、均等rebate、所得cache |
| 同`:945` `component_step`, `:974` `generate_observations`, `:1025` `generate_masks` | 税期初日/最終日、情報非対称、変更タイミング |
| `foundation/components/continuous_double_auction.py:168/200` `create_bid/create_ask`, `:231` `match_orders`, `:352` `remove_expired_orders` | escrowと個別market mechanism |
| `foundation/components/build.py:112` `Build.component_step` | wood+stone→house+coin、技能・labor |
| `foundation/components/move.py:93` `Gather.component_step` | movementと採集、衝突・labor |
| `foundation/scenarios/simple_wood_and_stone/layout_from_file.py:269` `get_current_optimization_metrics`, `:412` `generate_observations`, `:519` `compute_reward` | welfare選択、可視範囲、差分reward |
| `foundation/scenarios/utils/rewards.py` | isoelastic、inverse-endowment weights、mixable equality×mean-coin |
| `foundation/scenarios/utils/social_metrics.py` | normalized Gini、小N/大Nで異なるalgorithm |
| `tutorials/rllib/tf_models.py`, `training_script.py`, `phase1/config.yaml`, `phase2/config.yaml` | neural policy、PPO、checkpoint継承、curriculum具体例 |

## Managerへ何を移すか

**再利用する設計:** ①住民の目的とManager社会目的を別に定義、②world/actors/component/scenarioを分離、③制度policyをversion付きで全員に共通適用、④observationsと権限の境界をコード化、⑤高頻度観測と低頻度介入をmaskで分離、⑥介入→個人適応→他者影響→厚生のevent trace、⑦固定ルール・単純heuristic・既存制度との同一simulator比較、⑧部分集団/地形/skill/応答model摂動で評価。

**そのまま再利用しないもの:** 木と石をwellbeingとみなす世界、coinのみの報酬、模擬合理性を現実人間応答とみなす仮定、旧TF/RLlib依存一式、1Bsample訓練、camelback税率そのもの。Component interfaceやtransition codeは読む価値が高く、Managerの現代stackへ独立に再実装する方が合理的。

最小のManager研究は、供給・アクセス・経済的機会を決める共有環境で、予算・容量・接続・利用条件・資源配分の少数leverを明示し、scripted住民＋複数behavior modelで制度候補を比較する。最初から二層PPOにせず、fixed policy、search、小さいcontextual optimizer等でbaselineを作る。適応が結論を変えると判明してから内側behavior learningを追加する。

Wellbeingをcoin一値に潰す代わり、可処分資源、time burden、access、health、他の生命/生態系への影響等を分布として記録し、平均改善と最低保障を別に比較する。Rewardを指定する機構と、社会的にそのrewardを承認するプロセスは別に設計する。AI Economistが教えるのは、制度を選ぶ前に適応と波及を評価する技術であって、価値の決定権をplannerへ渡すことではない。

## 読み進める順番

1. READMEとeconomic_simulation_basic notebookでreset/stepとstateを理解。
2. Build→Gather→ContinuousDoubleAuctionを読み、coin・labor・escrowの会計を追う。
3. PeriodicBracketTaxの `taxes_due/enact_taxes/component_step/generate_masks` を読み、一期を手計算。
4. LayoutFromFileのobservation/rewardとrewards.pyでprivate skillと社会目的の意味を確認。
5. 2108.02755 Section2/3、Methods、Algorithm1、公開phase configsを照合。正文とtableのstep数不一致も残す。
6. Paperのinteraction/tax gaming図→2020 human experiment→2108.02904のdata fitting/robustnessを読み、simulation内成果と現実効果を分ける。

これにより「政策を生成するAI」という表面から、「ルールが個人の最善応答を変え、その連鎖を別目的の制御者が評価する」というManagerに必要な技術構造へ進める。
