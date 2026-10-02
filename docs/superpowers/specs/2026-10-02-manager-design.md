# Manager — One entity, blessing for all

2026-10-02 UTC 改訂。状態: 設計・移行計画。製品実装、benchmark実行、実環境介入、サイト公開は未実施。

ユーザーの修正を反映: 建物の省エネを最初の製品・成功指標とした旧案は撤回。Managerの中心は、生活を決める経済・社会・物理環境の構造を変え、多くの人と生命の暮らしを改善すること。初期の実環境は未確定。

作業順と進捗の正本は [統合SSOT](2026-09-25-life-manager-unified-ssot.md#manager-20261002)。本書は設計契約。

## 1. 目的と製品

**Manager continuously redesigns the world so living beings can thrive without anyone having to use it.**

Managerは世界のモデルを作り、環境への効果の大きい変更を発見し、実行し、現実の結果から学ぶ。名称はManager。mottoは **One entity, blessing for all — ひとつの存在、すべてに恩恵を。**

受益者はアプリを使わない。signup、login、名前、メール、Telegram、個人credentialsを要求しない。Aniccaai.comは説明・研究・評価を公開する場所。通知への反応、習慣アプリの継続率、受益者数としてのアカウント数を成功指標にしない。

「神」「blessing」は体験の比喩。全世界の出来事を常時把握できるという実装上の主張はしない。観測範囲・更新時刻・欠測・推定・不確実性をworld stateに残す。受益者が製品を操作せず恩恵を受けることと、変更主体や評価根拠を隠すことは区別する。

一つのentityは、継続する目的、資源、記憶、責任と意思決定のまとまり。内部で複数の推論・simulation agentを使える。「一つの存在」だけでは権限や資源の分散を証明できない。分散については、受益者が特定アプリに参加しなくても改善が届く設計と、実際の統治・資源構成を別々に説明する。

## 2. 何を変えるのか

変更単位は個人へのメッセージではなく、共通の環境・仕組み。

|構造|介入の例|測る生活の変化|
|---|---|---|
|価格・供給・取引|共同調達、流通経路、供給容量、取引手数料・条件|実質購買力、必要品の入手、供給者の持続可能性|
|機会・所得|仕事へのアクセス、支払条件、収益分配、共有生産設備|可処分所得、所得の安定性、参加障壁|
|健康を支える環境|栄養ある食の供給、サービス配置、利用時間、待ち行列・容量|アクセス、待ち時間、健康指標。アクセスと健康改善は別に評価|
|時間・空間・移動|サービス網、配送、交通接続、空間の使い方|移動・待機時間、利用可能な選択肢|
|制度・共有資源|利用条件、配分ルール、公共財への資源投入|不足、排除、負担分布、資源の回復力|

これらは候補群であり、すべてを初期実装する約束ではない。実行領域は①生活への構造的効果、②実際に変更できる権限、③観測可能な結果、④比較方法、⑤費用と持続性、⑥集団間の影響で選ぶ。モデル内で税を変えられても、現実の税制を変更する権限があるとは扱わない。

## 3. 学ぶ対象と設計判断

一次資料: [企業](../../research/manager/2026-10-02-companies-and-current-state.md)、[研究者](../../research/manager/2026-10-02-people.md)、[repo調査](../../research/manager/2026-10-02-repositories.md)、[実コードの学び](../../research/manager/2026-10-02-code-lessons.md)。

- Aaru: 集団の反応分布、時点を固定したholdout、誤差とcoverageを評価する。人口モデルと環境変更探索は別の層。
- Simile / Park: 行動の理由・文脈・記憶、反実仮想、confidenceを扱う。ただしインタビュー由来の精度を、個人情報を集めないManagerにそのまま移せない。匿名集計と公開資料でどこまで再現できるか評価する。
- Concordia: agentと環境を分離する。文章で解決した出来事を、資源・所得・健康の確定値にしない。
- AgentSociety: 共有資源、行動の同時処理、traceと再生。経済台帳の存在だけでは市場・価格・供給が成立しない。
- AI Economist: 人々の行動と制度側のpolicyを別々に学習する二層構造。報酬の価値判断と仮想経済の限界を明示する。
- MiroFish / OASIS: 仮説生成、情報拡散、行動trace。予測報告書やSNSでの売上カウンターを実生活の改善証拠にしない。
- DoWhy: 因果仮定、識別、推定、反証。道具だけでは交絡・集団間干渉を解決しない。
- Praxis / Woven City: 環境を変える資源・権限・運営と、現実の比較検証。公開された構想と稼働実績を区別する。
- Skinner / Levin / Krakauer: 環境条件、階層的な目標、時間を通じて続くentity。生物学や行動論を社会全体の最適化の実証とは扱わない。

BOPTEST / CityLearnは制御・比較・再現性の参考資料。Managerの目的や最初の事業を定義しない。

## 4. 中心ループと状態契約

`observe → model → discover → compare → authorize → act → reconcile → measure → learn`

一回のwakeは有限。既存registry、admission、agent-runner、immutable release、effect fenceを使う。独立した第二runtimeを作らない。

新しいdomain kernelの候補は `loops/manager/`。最初は内部契約を共有ライブラリへ移さず、二つ以上の実consumerができたとき共通化する。

### WorldState

`schema_version, environment_id, observed_at, valid_until, source_refs, scope, resources, institutions, networks, population_segments, outcome_series, assumptions, uncertainty, provenance`

resourcesは容量・在庫・資金・制約、institutionsは利用・支払・配分ルール、networksは供給・移動・アクセスの関係。集団は匿名集計。観測、推定、simulationをprovenanceで区別する。個人名・認証情報・再識別可能な履歴を既定の入力にしない。匿名でも少数集団から再識別され得るため最小集計条件と公開抑制を持つ。

### StructuralIntervention

`intervention_id, environment_id, expected_state_version, mechanism, patch, target_scope, authority_ref, budget, constraints, expected_outcomes, uncertainty, observation_window, stop_rule, fallback_ref, idempotency_key`

mechanismには供給容量・ネットワーク・価格条件・アクセスルール・資源配分などを指定する。自由文の「人々を豊かにする」は実行可能なpatchにならない。対象stateの版、変更前後、実行権限、費用、影響範囲を固定する。

### EnvironmentAdapter

`observe(scope) -> WorldState`

`simulate(state, intervention, scenario) -> ProjectedOutcome`

`validate(intervention, state) -> ValidationResult`

`apply(intervention, idempotency_key) -> EffectReceipt`

`readback(receipt) -> AppliedState`

`measure(window, comparison) -> OutcomeEvidence`

`restore(fallback_ref) -> RestoreReceipt`

simulationとlive adapterを型・modeで分ける。状態遷移と資源保存を数値コードで管理し、LLMは仮説・候補・説明・行動モデルに使う。検証者は候補の自己申告を採点しない。

### Receiptと成果

`proposed → validated → admitted → applying → applied / failed / unknown → reconciled → outcome_pending → evaluated`

appliedには独立readbackが必要。timeout後にunknownなら状態確認前に再送しない。evaluatedには観測期間・比較対象・集団別結果が必要。設定変更の成功と人の暮らしの改善は別の証拠。

既存 `runtime/loop/runtime_event.py` はキー・domain・effectを厳密検証する。新しいフィールドを勝手に追加せず、初期はManager詳細artifactを `evidence_refs` で参照する。simulationは既存 `domain=system, effect_class=none` の範囲。新しいlive effectは契約とconsumerを確認してversion移行を設計する。

## 5. 何を最適化するか

生活の成果はvectorとして保持する: 実質可処分所得・必要品の負担、健康または明示した健康proxy、自由時間、サービス・機会へのアクセス、主体性、弱い立場の集団への影響、他の生命と環境への影響。

総平均だけを上げる候補を自動採用しない。集団ごとの下限・悪化上限、資源制約、費用、confidenceを確認してPareto候補を比較する。重みづけは宣言・版管理し、LLMが都度書き換えない。「mindfulness」は本人の内面を匿名設備データだけで推定しない。

既存economic-autonomyはManager自身の検証済み収益・費用・自律性を測る。受益者の豊かさとは別scorecard。運営の資金継続性と生活の改善を混ぜない。運営者・資源提供者の支払仮説は調査対象であり、consumer subscriptionを前提としない。

## 6. 評価とbenchmark

1. **反応予測:** 過去の未使用期間・地域・集団で分布、誤差、confidence、coverageを測る。答えや未来情報を候補生成へ渡さない。
2. **構造変更simulation:** 初期値・乱数・外生変化を揃え、現状維持、明示ルール、既存policy、Managerを比較。AI Economistの制度変更、AgentSocietyの共有資源などでpolicy→行動→配分→結果の一巡を検証。ここでの住民は合成人物。
3. **現実の効果:** 変更できる実環境を選び、passive observation、shadow、比較設計、live実行へ進む。比較はrandomizationが可能なら優先し、不可能なら仮定を明記した方法を選ぶ。季節性・spillover・選択偏り・遅延を扱う。

各run manifest: source SHA、adapter版、scenario、seed、入力期限、baseline、目的と制約、予算、計算費用、全候補、停止条件、評価期間、raw trace hash、scorecard。未実行・失敗・実行不能も公開する。simulation結果を現実の富・健康の成果として表示しない。

最初のreference suiteは「共有資源の配分」と「制度変更を含む仮想経済」を候補とする。両者の比較可能性と依存導入を実装前に確認する。これは最初のlive事業を固定する決定ではない。AaruとSimileとの勝敗比較を、異なる問題・データ・指標から作らない。

## 7. 現在のLife Managerからの移行

残す: loop registry、finite wake、admission、idempotency、immutable release、agent-runner、effect reconciliation、証拠に基づくevalの構造。

変える: 個人ごとのbody/mind/moneyから環境と集団へ、通知・投稿から構造変更へ、provider receiptから生活のoutcomeまで、per-user memoryから共有環境の状態と因果仮説へ。

startup-contextは名称JSONの変更だけでは不足。`scripts/startup-context/lib.mjs` のTelegram必須・exactly three organs契約と `build-kit.mjs` の固定文章を移行する。旧形式は明示的legacyとして読めるが、新しいManager schemaにはconsumer channelを要求しない。README・THESIS・fundraising生成物を同じcontextから再生成する。

既存有料サービスやprovider loopsの退役はowner・依存・契約・戻し方を確認して別途行う。新規Managerをそれらに依存させない。現cloudからMac runtimeや既存顧客を変更しない。

## 8. 公開と受入条件

サイトは英日で同じ説明・status・benchmark・研究根拠を表示する。signup/login/Telegram/個人用dashboardを新規Manager CTAにしない。サイト詳細は [掲載原稿と実装境界](2026-10-02-manager-website-design.md)。

設計の受入条件: structural patchが型を持つ、権限と境界が検証できる、変更のreadbackと生活outcomeが別証拠、同一条件のbaseline比較が可能、集団別悪化が見える、秘密や個人credentialsを受益者に要求しない、current Life Managerのruntimeを再利用する。

長期ビジョンは広く保つ。次の実装は、変更可能な環境と独立した測定に接続する共通ループを完成させる。詳細な作業順・検証command・website移行は統合SSOTに集約する。
