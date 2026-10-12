# Manager Environment Lab の制作設計

2026-10-11。研究の精読を踏まえた設計。実行順と状態は[統合SSOT](2026-09-25-life-manager-unified-ssot.md#manager-20261011)のみ。10/8の独立core、10/10のmacro使命と4track評価を継承する。Manager code、実証成果、本番公開を完成済みとは扱わない。

## 目的と共有理解

Life Managerは **AI that builds businesses and creates wealth**。Managerは **Ambient AI that improves the conditions of life for all beings**。富とwellbeingという方向を共有し、介入の単位が違う。前者は事業を作り運営する作用、後者は多くの主体が生きる供給・機会・アクセス・共有ルールへの作用。一つの会社で、現在のexecution能力と収益を生かしながら、環境レベルの意思決定と検証を新しく作る。

主な学習先はAaru、Simile、AI Economist。一般のLLM評価やAI product職は隣接能力として残し、直接性の優先はSimile/Aaruの人口・行動モデルと評価、Primitiveの人間行動simulationへ移す。

研究室向けの題名は **Human Simulation, Social World Models, and Environment Design**。User simulationは製品利用者のjourneyを連想させる。World simulationは物理/ゲーム/宇宙まで広すぎる。Social world modelsは説明用の呼称として使い、統一された学術カテゴリや研究上の新規性を保証しない。World EngineeringはManagerのbrand説明、研究基盤はCSS/ABM/制度設計/因果推論。

## 一次資料による設計の修正

Aaru中核は同社の公開説明では非language-model。人口のjoint structure→profile sampling→behavior distribution→microdataとaggregate validation。network種類、loss、weightsは非公開。Managerに同一algorithmを採用したとは書かない。

Simileの現行製品は人間の行動/自己報告を使って学習したモデル。2023memory/reflection/planning研究と同一実装ではない。現行confidenceは予測誤差を学ぶ別問題。High95%は評価セットのTVD<.16確率で95%の全人間行動正答率ではない。

AI Economistは住民policyと制度plannerが別目的で適応する二層RL。環境変更に対して行動が固定だとpolicy順位を誤る。この構造は学ぶが、旧TF/RLlibと1Bsample trainingを初期要求にしない。公開repoはarchived、最終journalはScience Advances。

World Labs/JEPAからはstateとobservationの分離、行動条件付き予測、候補比較→再計画、sim-realのpolicy順位検証を学ぶ。社会では選択・交絡・ネットワーク干渉があるため、action-conditioned predictionだけで介入効果を識別したことにならない。

## 今月の制作物

採用案は **Manager Environment Lab**: 共通契約の下で人口、行動応答、数値world、共有ルール、独立評価を接続した再現可能なclosed-loop benchmark。巨大人口の会話動画より、変更が主体の選択と集団成果をどう変えるかを示す。

基盤は既存D0–D5。Service-accessとcommons/economic allocationの2worldで、容量・接続・利用条件・供給/配分ルールを候補にする。個人への通知だけを変更として扱わない。財や機会に対する未充足、アクセス費用、時間負担、資源使用、群別格差を測る。合成income/healthを実所得/実健康へ言い換えない。

### 提案する追加interface

```python
PopulationSampler.sample(evidence, n, seed) -> Population
ResponseKernel.predict(state, intervention, cohort) -> ActionDistribution
ErrorPredictor.assess(query, model_version, evidence) -> ErrorEstimate
WorldTransition.step(state, demands, intervention) -> TransitionResult
ManagerPolicy.choose(projections, constraints) -> Selection
IndependentEvaluator.score(manifest, trace, hidden_state) -> TrackResults
```

Populationはcohort数値表またはsynthetic rowsから始める。根拠のあるmarginsと重要jointを検査し、ないjointは仮定として保存。各行を同じLLMへ毎tick送る必要はない。ResponseKernelは数値reference/統計モデル/学習モデルを差し替え可能にする。

StateとActionDistributionとOutcomeは別。例えば営業時間を変えるactionは利用可能集合を変え、住民が時間/費用制約の下で再選択し、実利用はcapacityの台帳で上限が決まる。そこから未充足と負担の分布が変わる。健康を測らなければ健康改善とは採点しない。

Confidenceは初回から大モデルのhidden-state回帰を訓練する必要はない。held-out残差、データcoverage、距離/期間のshift、response-model間のpolicy順位不一致を公開する。学習error predictorは十分な独立ground truthが集まった後。棄却で弱い集団が消える場合もcoverage lossとして報告。

### 受入条件

- 同じbudget/initial conditions/shocksでno-change、fixed-rule、heuristic、Manager候補探索を比較できる。
- 同じ契約で2worldを実行し、action/response/transition/evaluationを別に検査できる。
- held-out seedだけでなくnetwork/rule/response familyの変化を検査し、agentがhidden rubricやfuture stateを読めない。
- failure trace、worst-group、spillover、資源保存、費用を保存。平均だけのleaderboardにしない。
- typed介入とsimulation executorでapply→readback→evaluate→更新がつながる。外部作用はauthorized field adapterの別mode。
- 実行した結果にだけ数値を記載。参考datasetのprediction validation、simulation policy効果、field outcomeを別statusにする。

二層RLは候補探索より良いと測れる場合に追加する。まず固定住民と複数応答モデルを比較し、行動適応を無視すると順位が変わるかを測る。必要ならinner behavior adaptationを追加し、その後outer learnerを検討。LLM proposal、population生成、confidence訓練、RLを一度に新規実装しない。

## 測れるimpact

|証拠の段階|測れるもの|claimの上限|
|---|---|---|
|Synthetic mechanism|共有ルールの変更が模型の選択/配分/負担を変える|条件付きsimulationの結果|
|Empirical prediction|未見の実測分布に対する誤差と校正|そのdataset/population/timeの予測|
|Shadow decision|現実の運営判断に対する候補比較、操作可能性|未適用の予測/判断支援|
|Field intervention|実行receiptと、対照による生活成果の差|測った範囲の現実効果|

健康は適切な健康指標、精神は妥当性のある尺度、富は可処分資源/所得/費用/変動等を定義する。現実成果を示すならoperatorと測定source、変更単位、対照、期間、spilloverが必要。受益者はManagerへ登録しない。許諾されたaggregate・既存運営データで観測し、必要な調査もManager account/credentials提出と切り離す。

今月のfield実証は、相手とデータが揃った場合の上位目標。締切までに健康/所得の効果が出る約束はしない。模型だけの場合でも、予測検証・失敗・次の反証可能なfield protocolを明示する。

## YCでの事業説明

Life Managerの売上は現在のexecution tractionとして積極的に説明できる。10/11ユーザーは売上があると述べた。今回の資料では現在額・顧客数・費用・自律性を独立確認していないので数値欄を埋めない。旧SSOTのゼロ/未確認は古いsnapshotで、今も売上ゼロと推定しない。

一つの会社の説明: **We build AI that creates wealth and improves the conditions of life. Life Manager is our first execution engine: it builds and operates businesses. Manager extends this to shared environments, combining behavioral prediction, structural intervention, and measured outcomes.**

売上を示すならproduct、期間、通貨、gross sales、refund、手数料、モデル/hosting費、net contribution、入金status、購入者、repeat、創業者の作業時間を記録。自社事業売上/顧客自身の利益/Manager eval売上を別scopeへ。定期収益でなければMRRとしない。投資入金/社内移動/売上予測をrevenueへ混ぜない。

数値あり版のdraftは: **Our Life Manager product generated [verified amount and currency] from [paying customers] during [period], with [costs/net contribution and human involvement]. This validates [specific executed workflow], not yet population-level wellbeing. In parallel, we are building Manager’s environment-level decision loop; the demo shows [actually run capability and benchmark results].** 本文の角括弧は内部draftの未入力で、提出版へ残さない。

初期Managerのpayer仮説はsimulation/evalを必要とする環境運営者・事業者、またはresearch collaboration。beneficiaryはpayerと同一とは限らない。将来は効果を生む運営/実行を含められるが、AI labによるデータ購入は既定の収益にしない。

## 講義と記事

元研究室に20分、英語slide＋日本語notesを初期想定。三者の方法、world-model比較、測定、Managerの制作案を扱い、意見をもらう問いは『回答予測から制度変更へ、何を追加測定するべきか』『どのjoint/適応がpolicy順位を変えるか』『wellbeing指標は何で妥当化するか』。発表会や出演を確定済みとは書かない。

記事は3者それぞれのexplainer英日版。読者は行動/計算神経科学を学び、human simulationと環境設計を理解したい研究者。方法・目的・検証・限界・Managerへの学びを接続し、ブログ性能数値を宣伝の形で並べない。公開sourceは本書からリンクする[研究report一覧](../../research/manager/2026-10-11-simile-blog-papers.md)。

## 10月12日の使命と成果の優先順位

Managerそのものを作り、環境変更の効果を検証することが主目的。採用応募、YC/Speedrun、OSS、記事、発表はその成果を伝える経路。求人ごとの小さなmockを主制作にしない。研究経験の証明は実装・実験・説明を揃える。内部目標版履歴書と提出版を区別し、予定を完成実績としない。

人口予測の実測評価と、閉ループ環境介入の評価を接続する。同時に現実のoperator・変更権限・測定データを探索する。fieldの条件が揃ったら、変更した環境単位と対照、期間、spilloverを明示して比較する。simulationの改善を実際の富・健康改善と呼ばない。

[資金調達・創業者活動の説明原稿](../../research/manager/2026-10-12-founder-fundraising-brief.md)はYC/Speedrun、journal club、英日発信へ共通の説明を提供する。状態と順序は統合SSOTの10/12節にのみ記録する。
