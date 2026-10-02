# Manager向け原リポジトリ・原論文調査

調査日: 2026-10-02 UTC。Managerは「一つの主体が環境を観測し、介入を選び、実行し、観測結果から現実モデルを更新するもの」と解釈する。受益者にアカウント、認証情報、操作画面を求めない構想であり、既存シミュレータの住民・ユーザーはManagerの内部環境モデルであって製品ユーザーではない。

## 推奨

**改訂:** BOPTESTを最初の製品・実験基盤とする旧推奨は撤回した。生活を決める構造変更のreferenceとしてAI EconomistとAgentSocietyの共有資源環境を追加調査する。Concordiaは行動・環境分離、DoWhyは因果評価の参考。BOPTEST / CityLearnは制御・比較手法の参考に限定する。新たにcloneしたコードの機能と限界は [実コードの学び](2026-10-02-code-lessons.md) を参照。

**Concordia、AgentSociety、OASISは社会的仮説を生成・ストレステストする内部実験場として限定使用**。仮想住民を増やすことは現実での介入効果を保証しない。MiroFishの報告生成機能を現実予測器の証拠に扱わない。Manager自体は一つでよく、社会シミュレータを採用する場合も多数の役柄をその内部に置く構成でよい。

## 現行識別子・ライセンス

GitHub REST APIで取得したデフォルトブランチHEADを固定した。パッケージ版が確認できない場合はSHAを識別子とする。READMEのバッジだけでライセンスを判断せず、ライセンス原文も取得した。

|対象|現在の公式配置・HEAD SHA|ライセンス・版|
|---|---|---|
|Concordia|`google-deepmind/concordia` `b71d202750e23444ce1bf28d9f114bcd88aa41db`|Apache-2.0; setup.py 2.4.0|
|AgentSociety|`tsinghua-fib-lab/AgentSociety` `8cc5bb9a9c27d039ec5519375db9d73ccf508cba`|Apache-2.0、ただしAS1の`commercial`ディレクトリは商用別契約; agentsociety2 2.9.3|
|MiroFish|`666ghj/MiroFish` `7657031ac01184afe2cb220f5ee3545573b5e843`|AGPL-3.0; backend 0.1.0|
|Generative Agents|`joonspk/generative_agents`はGitHubページとREST APIの双方で404|現在のSHA・ライセンスを確認できない。原論文は取得できた|
|DoWhy|`microsoft/dowhy` → **`py-why/dowhy`** `cc23521127ba21ade40514539ae7b91db27ca54a`|MIT; pyproject版は0.0.0なので固定SHAを優先|
|BOPTEST|`ibpsa/project1-boptest` `0f8a467cb1823f005b6512937e9333c65e1e483e`|BSD 3-clause型にEnhancements条項を追加した原文。GitHub SPDXはNOASSERTION。純粋なBSD-3-Clauseと略記しない|
|CityLearn|`intelligent-environments-lab/CityLearn` → **`citylearn-project/CityLearn`** `834575c1a0194c8ae9d648ae858376a94dfceb78`|MIT; 現行READMEはv3。セットアップは動的版取得なのでSHAを優先|
|OASIS|`camel-ai/oasis` `affe52e8dcbc70bba0a4162bfea1057aa5df9316`|Apache-2.0; camel-oasis 0.2.5|

## 1. Concordia

**構成**: Entity（人物またはGame Master）、Component（記憶・知覚・推論）、Engine。人物が自然言語で行為を提案し、Game Masterが環境への効果を解決する。`sequential.py`で行動、GMによる解決、次の観測の順序を実装し、`switch_act.py`でGMの各種処理を分けている。

**検証の実態**: 原技術報告は社会ジレンマ、共有資源、デジタルアプリ等の例を示すが、Validation節で現実へ一般化できる条件は未確定と明記する。論文3.3.1はConcordiaの人物が強化学習者ではないと説明している。記憶が追加されることと、環境モデルの同定・介入最適化が進むことは異なる。リポジトリのpytest CIはソフトウェア動作確認の根拠であり、社会の予測精度の証明ではない。

**制約**: 現行setup.pyはPython >=3.12。LLM API互換のsamplingモデルと、記憶検索用embeddingを用意する。観測更新、行為提案、GM解決、振り返りそれぞれでLLM呼出しが増える。文章による物理的妥当性判定だけでは保存則・設備限界を保証できない。

**流用**: 行為提案と結果判定の分離、交換可能なcomponent、観測履歴。**避ける**: GMが文章生成した「結果」を現実の測定値として学習する循環。Managerには決定論的な環境アダプタ、介入ID、観測時刻を別途追加する。

- [原論文 2312.03664](https://arxiv.org/abs/2312.03664)、[Design Pattern 2507.08892](https://arxiv.org/abs/2507.08892)
- [固定engine](https://github.com/google-deepmind/concordia/blob/b71d202750e23444ce1bf28d9f114bcd88aa41db/concordia/environment/engines/sequential.py)、[固定GM component](https://github.com/google-deepmind/concordia/blob/b71d202750e23444ce1bf28d9f114bcd88aa41db/concordia/components/game_master/switch_act.py)

## 2. AgentSociety — AS1とAS2を区別

**構成**: 現行mainはAS2とAS1を同梱するmonorepo。AS1はRay、MQTT、gRPC接続の都市環境、心理状態・移動・雇用消費・社会関係のモデル。AS2はworkspace単位のagent records、Ray Tasks、ServiceProxy、CodeGen/ReAct等のenvironment router、trace/replay、研究ワークフローを統合する。現在のコード説明に2025年AS1論文だけを対応させると設計を取り違える。

**検証の実態**: AS1原論文2502.08691の取得版は2026-04-10 v2。10k超のLLM agent、約500万interaction、偏極・扇動的発言・UBI・ハリケーン・都市持続性の5事例を報告する。これは規模と選択された既存現象の再現例であり、未知の都市施策の前向き予測性能ではない。AS2論文2607.11895は7事例と、環境呼出しベンチマークで最大31.6%の相互作用信頼性向上、キャッシュ等による66.5%のLLM呼出し削減を報告する。この数字は主にツール操作・計算効率の指標で、政策効果の外的妥当性とは分ける。AS2論文自体が人間に仮説・概念妥当性・介入仕様・結果解釈を留保している。

**制約**: AS2 Python >=3.11,<3.14、LLM接続、Ray等。AS1は都市地図・人口・移動等の入力、外部環境サービスが必要。モデルのAPI価格、活性agent数、simulation timestep、キャッシュヒット率を固定しない費用見積りは意味を持たない。DailyMobility/HurricaneMobility benchmarkのデータ調達・形式・評価設定も必要。AS1`commercial`は開源ライセンス対象外。

**流用**: replay、介入を区別した研究実験、環境toolの統合、実データとgroundtruthの別扱い。**避ける**: 小さなManager試作で都市全体・VSCode拡張・研究論文生成を一括導入。社会科学的な結論をManagerが自動承認する設計。

- [AS1原論文](https://arxiv.org/abs/2502.08691)、[AS2原論文](https://arxiv.org/abs/2607.11895)
- [固定society](https://github.com/tsinghua-fib-lab/AgentSociety/blob/8cc5bb9a9c27d039ec5519375db9d73ccf508cba/packages/agentsociety2/agentsociety2/society/society.py)
- [商用領域の明記](https://github.com/tsinghua-fib-lab/AgentSociety/blob/8cc5bb9a9c27d039ec5519375db9d73ccf508cba/packages/agentsociety/agentsociety/commercial/README.md)、[DailyMobility benchmark](https://github.com/tsinghua-fib-lab/AgentSociety/blob/8cc5bb9a9c27d039ec5519375db9d73ccf508cba/packages/agentsociety-benchmark/agentsociety_benchmark/benchmarks/DailyMobility/README.md)

## 3. MiroFish

**構成**: 文書入力 → Zep Cloudのgraph/memory → persona/環境設定 → OASISによるTwitter/Redditの二系統シミュレーション → ReportAgentによる結果説明。Vue系frontendとPython backend。`simulation_runner.py`はsimulation processと状態管理、`report_agent.py`は結果照会と報告生成を担う。

**検証の実態**: 取得した一次リポジトリ内で、MiroFish自身の独立した原論文・未知イベントの事前登録予測・時系列holdout比較を確認できなかった。READMEの世論事例、文学結末デモ、予測をうたう説明は性能検証ではない。追加されているテスト群はZep契約、JSON応答、ontology、simulation準備失敗等の動作検証。OASISの原論文の結果を、その上に載るgraph抽出・persona化・report生成まで含む予測精度として転用できない。

**制約**: Python >=3.11,<3.13、Node >=18、LLM互換API、Zep Cloud APIが標準構成で必要。`zep-cloud==3.25.0`、`camel-oasis==0.2.5`を依存に固定。README自身が消費量が大きく最初は40 round未満を勧める。Zepへのseedデータ送信と継続費用を考慮。AGPL-3.0のnetwork提供・改変ソース提供条件を設計段階で確認する。

**流用**: データ入力からtrace、scenario、reportを結ぶUXの参考。**避ける**: 根拠の弱い数値未来予測、ReportAgentの文章を評価者にする構造、Manager MVPにZep/二系統social platform/frontを必須化。

- [原リポジトリ](https://github.com/666ghj/MiroFish)
- [固定依存](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/pyproject.toml)、[固定simulation runner](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/simulation_runner.py)、[固定report agent](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/report_agent.py)

## 4. Generative Agents

**アクセス状態**: 指定された原リポジトリと研究配布サイトは今回404。存在しない、非公開化、移動、接続側制約のどれかは確定できない。第三者forkを原配布物として扱わず、現在のSHA・コードライセンスは未確認とする。

**原論文で確認できる構成**: 観測記憶stream、importance/recency/relevance検索、reflection、階層的plan、Smallvilleの25住民。これはManagerのmemory設計の歴史的参考になる。

**検証の実態**: 100人によるinterview応答のbelievability順位比較、記憶/反省/計画のablation、2 simulation daysの情報拡散・関係形成・party参加。研究が示すのは役柄としての一貫性と社会的にもっともらしい振る舞いであり、現実の個人予測や介入効用の正確性ではない。論文Limitationsでは25 agentを2日模擬するのにtoken creditsが数千ドル、実行に複数日を要したと報告。これは2023年の歴史的測定であり現在価格へ転用しない。

**流用**: 記憶検索、反省を仮説として保持する区別、長期計画の分解。**避ける**: 全住民が毎step LLM思考する構造、believabilityを現実妥当性の評価指標にすること。原配布物が復旧するまでManagerの直接依存にはしない。

- [原論文2304.03442](https://arxiv.org/abs/2304.03442)、[指定原リポジトリ（今回404）](https://github.com/joonspk/generative_agents)

## 5. DoWhy

**構成**: 因果graphを明示し、`model → identify → estimate → refute`。Graphical Causal Modelsでは構造方程式・機構をモデル化し、介入、反実仮想、graph falsificationを扱う。単独では環境へ作用するcontrollerではない。

**検証の実態**: 原論文は既知のgroundtruthがない因果問題に対して、仮定、識別条件、感度・反証を前面に出す。`placebo_treatment_refuter.py`はtreatmentを置換して推定値が期待通り変わるかを検査し、`gcm/falsify.py`は観測分布からgraph仮説の適合を調べる。これらを通過しても未観測交絡、選択バイアス、positivity不足、干渉が消えるわけではない。「DoWhyが因果を証明した」と報告しない。

**制約**: 本体はPython・数値処理でLLM API不要。表形式の測定データ、介入変数、アウトカム、共変量、因果graphが必要。graphと推定器の仮定が結果を左右する。現在mainの依存はNumPy >2.0等へ更新されており、過去環境への無固定導入を避ける。大量のpermutation/bootstrapやGCM学習は計算費用が増える。

**流用**: Managerの介入履歴をtreatment/outcome/covariateへ写像、反証結果・信頼区間・仮定の記録。実介入が可能な段階ではランダム化・switchback等の実験設計を優先し、観測推定を補助に使う。**避ける**: LLMがもっともらしいDAGを生成しただけで識別済みとすること。

- [原論文2011.04216](https://arxiv.org/abs/2011.04216)
- [固定CausalModel](https://github.com/py-why/dowhy/blob/cc23521127ba21ade40514539ae7b91db27ca54a/dowhy/causal_model.py)、[placebo refuter](https://github.com/py-why/dowhy/blob/cc23521127ba21ade40514539ae7b91db27ca54a/dowhy/causal_refuters/placebo_treatment_refuter.py)、[graph falsification](https://github.com/py-why/dowhy/blob/cc23521127ba21ade40514539ae7b91db27ca54a/dowhy/gcm/falsify.py)

## 6. BOPTEST

**構成**: Modelica建物・設備モデルをFMUへ変換し、RESTの`initialize/advance/measurements/inputs/forecast/kpi`でcontrollerと環境を接続。外部Managerは設定値を送り、advance後の測定値を受け取る。web/Redis/worker/object storage構成、local Docker/Podmanでも運用可能。受益者アカウントは不要で、Managerがservice clientになる。

**検証の実態**: 原論文はbuilding controlのsimulation-based benchmark設計。取得したコードにKPI計算、unit/functionalテスト、testcaseテスト、baseline CSVが実在する。`test_kpis.py`と`kpi_calculator.py`でエネルギー・熱快適性等を検査し、baseline CSVに比較用結果を保持する。これは同じモデル・気象・scenarioで制御手法を比較する強い基盤であり、現実設備への閉ループ改善を証明するものではない。原論文のDOI・書誌はCrossrefで確認したが、出版社本文は403で取得できず、本文の未確認数値は引用しない。

**制約**: FMU runtime、Docker/Podman、testcaseモデルと気象/価格/occupancy入力。ソースからモデルを再生成する場合はModelicaのtoolchain・ライブラリ版も必要。LLM不要。simulation timestepとwarmup期間、forecastが正解情報を先取りしていないかを固定する。公式serviceは実験用接続先であり、本番SLAの根拠ではない。原licenseは追加条項を持つ。

**流用**: 観測・作用のAPI契約、外部controllerの交換、同一scenarioでのbaseline比較、多目的KPI、初期化・warmup。**避ける**: 快適性を落として省エネだけ最大化、truth forecastの漏洩、FMU上の勝利を現実に転用。

- [原論文DOI](https://doi.org/10.1080/19401493.2021.1986574)、[公式docs](https://ibpsa.github.io/project1-boptest/)
- [固定KPI計算](https://github.com/ibpsa/project1-boptest/blob/0f8a467cb1823f005b6512937e9333c65e1e483e/kpis/kpi_calculator.py)、[KPIテスト](https://github.com/ibpsa/project1-boptest/blob/0f8a467cb1823f005b6512937e9333c65e1e483e/testing/test_kpis.py)、[baseline結果](https://github.com/ibpsa/project1-boptest/blob/0f8a467cb1823f005b6512937e9333c65e1e483e/baselines/csv/df_kpi_bestest_air.csv)、[license原文](https://github.com/ibpsa/project1-boptest/blob/0f8a467cb1823f005b6512937e9333c65e1e483e/license.md)

## 7. CityLearn

**構成**: Gymnasiumのreset/step環境、建物、PV、battery、EV、thermal system、flexible load。中央controllerまたは複数agent。現行v3はcommunity member/asset変更、電気的制約、local settlement、DR、データ/装置故障も扱う。単一Managerからcentralized action vectorを出せる。

**検証の実態**: [v2査読論文](https://doi.org/10.1080/19401493.2024.2418813)と、2026-09-18の[v3原preprint](https://arxiv.org/abs/2609.21570)を区別する。v3本文はsoftware checksとapplication scenarios、8760-step年間baseline比較、故障・設備変更・DR/EV service、15秒trace集約でpeakが隠れる例を報告。コードでは物理不変条件、seed再現性、KPI golden比較、baseline snapshotが実在する。新しいv3 preprintを査読済みとして扱わない。これもシミュレーション内の測定・整合性の証拠であり、住宅での実稼働介入試験ではない。

**制約**: Python >=3.9、public dataset取得、NumPy/Pandas等、学習方法によりPyTorch/GPU。標準制御・小規模simulationはLLM不要。schema、時刻解像度、weather、price、carbon、load、EV schedule、equipment capacityを揃える。学習episode数が費用を支配し、外部dataset downloadの再現性も固定する。

**流用**: requested actionとapplied actionの区別、装置/観測故障の注入、service-aware scorecard、centralized環境、episode export。**避ける**: 単一cost rewardだけで評価、電力量だけ一致する粗い時間集約でpeak/rampを見落とす、EV出発未達やparticipant差を平均で隠す。

- [v3原論文](https://arxiv.org/abs/2609.21570)、[v2原論文DOI](https://doi.org/10.1080/19401493.2024.2418813)
- [固定env](https://github.com/citylearn-project/CityLearn/blob/834575c1a0194c8ae9d648ae858376a94dfceb78/citylearn/citylearn.py)、[KPI](https://github.com/citylearn-project/CityLearn/blob/834575c1a0194c8ae9d648ae858376a94dfceb78/citylearn/internal/kpi.py)、[物理不変条件テスト](https://github.com/citylearn-project/CityLearn/blob/834575c1a0194c8ae9d648ae858376a94dfceb78/tests/unit/test_physics_invariants.py)、[再現性テスト](https://github.com/citylearn-project/CityLearn/blob/834575c1a0194c8ae9d648ae858376a94dfceb78/tests/test_reproducibility_and_agent_learn.py)

## 8. OASIS

**構成**: Twitter/Reddit型social platform、recommendation、user graph、SQLite等のdatabase、CAMEL LLM social agents。environmentはmanual actionとLLM actionを処理するため、Managerが介入役として明示操作する構成を作りやすい。MiroFishの基盤でもある。

**検証の実態**: 原論文2411.11581は実投稿伝播曲線のnormalized RMSE、偏極、Reddit herd effectを測定する。196実ユーザーから生成userへ拡張、116,932 real comments・3,600 synthetic usersによるherd試験、21,919 counterfactual posts・10,000 users、million scale実験などを区別する。論文3.3.2は初期downvoteに対してagentが人間より追従しやすく、結果が大きく異なると報告する。平均伝播curveの評価はpost間の誤差が相殺しうることも明記。よって「100万agent」は規模の主張であり社会予測の保証ではない。取得example YAMLには著者環境の絶対pathとprivate IPが残り、論文設定をそのまま実行できる配布状態とは限らない。

**制約**: CAMEL依存、LLM APIまたはlocal inference、profile/social graph/投稿dataset、SQLiteの保存容量。READMEのtoken測定表は参考値であり、2024年価格は現在見積りに使わない。activated agents × timestep × 入出力tokenを計測し、small pilotから推定する。現実social platformの操作権限は付属しない。

**流用**: 操作種類を制限した実験環境、manual intervention、action/event log、推薦規則のablation。**避ける**: synthetic persona数の増加を実データ量と同視、人間との差を説明なしに政策判断へ転用、社会platformの仮想操作を実操作と混同。

- [原論文](https://arxiv.org/abs/2411.11581)
- [固定env](https://github.com/camel-ai/oasis/blob/affe52e8dcbc70bba0a4162bfea1057aa5df9316/oasis/environment/env.py)、[固定platform](https://github.com/camel-ai/oasis/blob/affe52e8dcbc70bba0a4162bfea1057aa5df9316/oasis/social_platform/platform.py)、[論文再現exampleの設定](https://github.com/camel-ai/oasis/blob/affe52e8dcbc70bba0a4162bfea1057aa5df9316/examples/experiment/reddit_simulation_align_with_human/politics_360_test.yaml)

## Managerへの統合判断

1. **環境の真値を文章生成から独立させる**。sensor/simulator値、requested action、applied action、outcomeを分ける。
2. **介入単位をログにする**。`intervention_id, policy_version, context, time, intended_action, applied_action, outcome_window, constraints, cost`を保存。
3. **baselineと比較する**。固定ルール、無介入、既存controllerに対し、同じ初期条件と未使用scenario/seedで比較。操作成功率、効果、費用、快適性/サービス未達、制約違反を並列で測る。
4. **モデル学習の対象を明示する**。memory追加、自然言語reflection、因果model更新、policy更新を別扱い。仮想環境で学んだmodelと現実測定で更新したmodelを区別する。
5. **受益者の認証を前提にしない**。Manager側の設備・環境service adapterへ接続権限を集約する。ただし実機操作権限・sensor可用性は研究repoが提供するものではない。

証拠の順序は「実測・実介入 → 校正済み数値モデル → シミュレーション内比較 → 人間によるbelievability → demo/marketing」とする。対象8件のうち、実介入での未知施策予測を普遍的に保証するものは確認できない。

## 調査範囲・再現可能性

取得したGitHub metadata、tree、license、選定source/test/設定、および原論文HTML/本文テキストは`/workspace/scratch/manager-research/repos/`に保存した。一次URLの公開readのみを使用し、製品依存のinstall、model/APIの有料実行、repoのtest実行はしていない。テストの存在・内容を検査したことと、今回そのテストがpassしたことを区別している。Generative Agentsの404とBOPTEST出版社本文403は未解決の証拠欠落として残した。
