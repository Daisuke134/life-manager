# 根拠から選ぶManagerの実証と構成

状態と実行順は[統合SSOT](2026-09-25-life-manager-unified-ssot.md#manager-evidence-first-20261012)にのみ記録する。コード実装・学習・現実の効果を完成済みとはしない。

## 更新した方針

Managerを作り、共有環境の変更による生活上の効果を測ることが主目的。求人条件は、必要な専門能力と証拠を確認する資料として使う。採用のためにManagerの使命や対象を変更しない。

所得機会アクセスを第一候補にした前の提案は、先行研究・協力先・測定データの根拠が足りなかったため優先を撤回する。否定されたのは第一候補としての根拠であり、この分野に効果がないと証明されたわけではない。現実の最初の実証対象はまだ決まっていない。

## 用途の根拠と限界

|対象|確認した根拠|支持すること|支持しないこと|
|---|---|---|---|
|医療・サービスアクセス|Simile/CVSの公式事例|待ち時間、薬剤師アクセス、給付設計を人間シミュレーションで検討する用途|健康改善幅、Managerでの成功|
|予約・供給の構造変更|Rose/Ross/Horwitz 2011のsystematic review抄録、doi10.1001/archinternmed.2011.168|24研究のレビューで待ち時間改善を報告。構造変更に実証の蓄積がある|全研究にbias懸念。満足度は混在、臨床成果の証拠は限定的。AIの追加効果ではない|
|経済ルールと適応|AI Economistの公開論文・コード|個人の目的と設計者の目的を分け、制度変更後の適応を模型内で評価する|現実政府での税制改善、短期の人口所得改善|
|価格・顧客体験|Aaru EY/Breakwater、Simile Itaú、Primitive Instinct|人口予測・顧客判断・製品改善の商用用途|売上や研究速度がそのまま受益者wellbeingを示すこと|
|所得機会配分|前のManager提案|測定案を具体化できる|現時点で根拠ある最優先とすること|

2011レビュー抄録はEurope PMCの索引本文を確認、全文XMLは取得できず。新しい2026レビューの抄録も取得したが、初期の選定を最新要約一件の数値だけで決めない。一次観測研究と介入研究の質、対象の運営条件を次に確認する。

実証対象の選定は、構造変更の先行証拠、変更権限、実在需要・人口、事前データ、比較可能性、成果が出る期間、支払者、悪化する可能性を持つ群を項目にする。候補の不足欄を架空のscoreで埋めない。CVSの用途が近いことは調査の優先理由になるが、協力先なしで医療を今月の確定対象にしない。

## 共通構成

```text
観測と出典 → 世界の状態と不確実性 → 人口 → 行動予測
                                        ↓
                            環境変更候補と結果の比較
                                        ↓
                            制約に沿った変更の実行
                                        ↓
                            実行後の観測と独立評価
                                        ↓
                             データ・モデルの更新
```

Managerが把握するのは、観測できた世界とその不確実性。常時すべてを知る世界状態は仮定しない。初期は一つの運営環境と限定された人口で、同じ構成を他環境にも適用できるかを測る。

### 観測と状態

観測には時刻、対象範囲、出典、単位、取得時点、欠測、利用できる条件を付ける。実世界の状態と合成模型の状態を区別する。供給量、利用可能な時間、費用、需要、関係、変更可能なルールを別項目にする。

数値の資源会計、容量、予算、可能な操作はコードで管理する。モデルの文章に予算や完了状態を自由に作らせない。受益者へManagerへの登録や個人credential提出を求めず、運営者の許諾された集計・既存運営データから始める。

### 人口

PopulationSamplerは属性の周辺分布、根拠がある結合関係、個人の制約を保つ合成人口を生成する。年齢や所得の分布だけが分かる場合、両者の相関が分かった扱いにはしない。IPF/raking等は周辺分布調整の候補で、未知の結合分布を自動的に実証する手法ではない。

個人を表す行と、標本の重み、集団、相互作用ネットワークを区別する。珍しいがあり得るプロフィールを落として、平均指標だけ改善しない。

### 行動モデル

ResponseKernelは、状態・人口の制約・候補変更から選択の確率分布を返す。最初にmultinomial/logistic、単純segment予測などの統計baselineを置く。公開された学習モデル、追加学習モデル、LLM接地モデルは同じ入出力で比較する。

`P(action | profile, state, rule)`は提案する表現で、AaruまたはSimileの非公開モデル式ではない。入力に観測されない事情があれば、特定個人の次行動を確定することはできない。観測条件での予測を、`do(rule)`による介入効果と同一視しない。

### 環境と設計者

WorldTransitionは主体の選択と容量・費用・共有資源から次状態を計算する。混雑、機会の取り合い、他者への波及、時間を表す。Architectは変更権限があるルールの候補を生成する。ManagerPolicyは予算、品質、群別制約と複数目的を踏まえて選ぶ。

LLMを使う場合も、その役割は候補の説明や調査情報の解釈等として分ける。最初の選択器は有限候補探索と単純最適化から比較し、二層RLを必須にしない。人々の適応で施策順位が変わるかを確認し、必要なら内側の行動学習、その後に外側の設計者学習を追加する。

### 実行と評価

Executorは変更前状態、変更ID、対象、許諾範囲、適用、readbackを記録する。予測結果を実行結果として扱わない。sim executorとfield executorの観測源・状態を分ける。

IndependentEvaluatorは開発用の報酬やモデル出力とは別に最終結果を採点する。モデルが採点基準、未来状態、保護された実測結果へアクセスできない構成にする。失敗、費用、最低群、データ不足をreportへ含める。

## 評価とbenchmark

|段階|測定|比較・未見条件|
|---|---|---|
|Population|周辺/結合/条件付き分布、rare coverage、矛盾・不可能な人物|独立属性生成、単純重み調整、未見集団|
|Prediction|TVD、連続値のWasserstein、個別結果のBrier/log loss、校正、confidence|直接統計予測、単純segment、LLM persona、実測の標本誤差|
|Policy|同じ予算での成果、費用、群別結果、適応、spillover|no-change、固定ルール、heuristic、制約付き最適化。未見network/rule/response family|
|Execution|適用とreadbackの一致、失敗、再開、重複、費用|部分失敗・変化した外部状態での再現|
|Field outcome|実際の所得・負担・アクセス等の事前定義した成果|変更単位と対照、期間、干渉、支払/健康成果の遅延|

TVDは選択比率差の絶対値の合計の半分。予測50/30/20と実測40/40/20なら0.10。個人の正答率と分布誤差は別の問い。Brierは実際の選択に対応する0/1と予測確率の二乗差を平均するproper scoreで、平均的な文章の自然さを採点しない。

Confidenceは、予測を出す前に大きな誤差を見分ける問題。error discriminationとcalibrationを分け、低信頼度を棄却したときの誤差とcoverageを一緒に示す。未知集団を除いた高精度を全人口の高精度としない。

splitはsubject、question、experiment、timeの単位に合わせる。同じ実験の回答を無作為に行で分けて、未知実験の評価と呼ばない。開発・validation・最終held-outを分け、反復調整で最終setを開発用にしない。bootstrapや区間推定の単位も、独立な観測・cluster・時系列依存に合わせる。

再現manifestにはdata/model/code/policy/evaluatorのバージョン、seed、予算、観測時点、split、費用、trace、claim scopeを付ける。公開は許諾データまたは取得手順と合成fixtureにし、受益者の原票を公開条件にしない。

## 八つの求人と同じ制作物の関係

人口モジュールはAaru Populationの分布・profile fidelity、予測評価はAaru/Simile Evaluations、run/data基盤はAaru SimulationとSimile Evaluations Engineeringへ対応する。モデルの実際の学習と再現研究はSimile Research、認知/記憶/意思決定のablationはPrimitive Research、運営者の実利用と改善はPrimitive Founding Engineerへ対応する。

歓迎条件まで強い証拠を作るなら、Bayesian/causal reasoning、社会科学、モデル追加学習、multi-agent/network、評価grader、論文の再現・批評・technical report、実際のdeploymentとfeedbackを、Managerに必要な範囲で制作する。全項目を揃えたことは、結果と本人の説明から判断する。数週間の制作を3年の経験、PhD、査読採択、分散大規模学習へ言い換えない。

## 出典

- [CVSとSimile](https://www.simile.com/blog/simile-cvs-health)
- [Advanced access systematic review 2011](https://doi.org/10.1001/archinternmed.2011.168)
- [AI Economist](https://arxiv.org/abs/2108.02755)
- [Aaru methods](https://aaru.com/publications/population-simulation-at-the-replication-floor-research)
- [Simile confidence](https://www.simile.com/blog/confidence)
- [Aaru Population role](https://aaru.com/careers/f718d12f-67e9-4fe9-91cc-9e3b69ff00fe)
