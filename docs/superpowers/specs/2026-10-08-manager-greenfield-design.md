# Manager — World Engineering / greenfield design

2026-10-08 UTC。2026-10-10にmacro/クラウド/評価事業の[更新仕様](2026-10-10-manager-macro-evaluation-design.md)を追加。状態: 調査を踏まえた設計提案。新Managerコア、simulation benchmark、実環境介入、サイト公開は未実施。

ユーザーの最新指示: 現Life Managerという収益agentの延長から考えず、目的と先行研究からManagerを独立設計する。2026-10-02のruntime必須継承・loops/managerへの配置を前提にした案を置き換える。既存事業・運用は別系統で維持し、変更しない。repo保管場所と製品architectureは別問題。

実行TODO・順序・状態は [統合SSOT](2026-09-25-life-manager-unified-ssot.md#manager-20261010) のみ。ここはarchitectureの設計契約。

## 1. 基本からの定義

**World Engineering:** 現実の状態を観測し、生活を決める構造への変更を比較・実行し、その結果から設計を更新する。環境には価格・供給・容量・空間・交通・取引・アクセス条件・共有資源が含まれる。

「environment engineering」は通常の環境工学を連想させるため、公開説明は **AI for world engineering** を中心にし、具体的な変更対象を添える。学術分野として確立した名称や独占領域とは主張しない。

**Agent-based model (ABM):** 個々の合成主体が共通の環境内で行動し、その相互作用から集団結果が生じる模型。**Behavior model:** 条件ごとの反応を予測する部分。**Environment transition:** 在庫・容量・資金・配分を更新する部分。**Policy:** 環境をどう変えるかを選ぶ方針。**Causal evaluation:** 変更がなかった場合との比較から効果を調べる部分。これらは同一のLLM promptではない。

Mission: **One entity, blessing for all.** 受益者がアプリを使わず、signup/login/氏名/メール/Telegram/個人credentialsを渡さずに恩恵を受ける。対象は長期的に全生命。個人の内面を環境データから断定しない。AGI達成、全世界の常時把握、万人の富と健康を現状の実績にしない。

## 2. 独立architecture

`Evidence ingest → Belief state → Candidate policy → Response model + Environment transition → Comparison → Action gate → Environment executor → Independent readback → Outcome evaluation → Model update`

採用案: 独立Python core + 明示された数値環境 + 差し替え可能なresponse model + append-only evidence。理由は、実験と生活成果をLLM文章から分離でき、既存収益agentに依存しないため。

代替案1: MiroFish中心のforkは資料→persona→SNS simulation/reportを速く見せられるが、資源・アクセス・所得の構造変更が中心ではなくZep Cloud/AGPL/依存整合を扱う必要がある。

代替案2: 大規模AgentSociety/Concordia統合は豊富な行動を扱えるが、互換性・計算費用・較正の負担が大きい。最初の25日で全面統合しない。

## 3. sourceとモジュール

追加予定root: `apps/manager/`。旧製品のschemas・Telegram・provider labelsから独立したpackage。必要になれば旧runtimeは外側のdeployment adapterとして使えるが、coreの必須依存にしない。

```text
apps/manager/
  pyproject.toml
  src/manager/
    contracts.py      # frozen typed recordsとstrict validation
    observations.py   # source/time/scope/unit/provenance
    store.py          # transactional state + append-only event references
    world.py          # population/resource/network/rules
    responses.py      # behavior model protocol / reference baseline
    transitions.py    # numerical environment changes
    candidates.py     # bounded structural policy proposals
    search.py         # simulation ensembleとcandidate ranking
    executor.py       # authority/idempotency/apply/readback
    evaluation.py     # outcome vector / distribution / comparison
    learning.py       # error calibration / parameter versioning
    runner.py         # one finite episode/checkpoint
    cli.py            # internal experiment entrypoint
  scenarios/
  tests/
```

配置はcloud/local中立で、クラウドを通常の実行先に選べる。APIなしのreference実行は再現性検査であり、ローカル必須ではない。Stack提案: core Python 3.12、stdlib dataclasses/json/sqlite3、unittest。graphは明示nodes/edges。統計・最適化libraryは必要な箇所だけ版固定で追加。FastAPI・Ray・graph DB・vector DBは最初の必須依存にしない。LLM providerはresponse/proposal boundaryから注入し、数値referenceはAPI・個人credentials無しで走る。全6 OSSを同じvenvに混ぜない。公開結果は既存Next.js siteの静的artifact。内部CLIや研究用可視化は受益者の操作UIではない。

## 4. データ契約

`Observation(source_ref, observed_at, valid_until, scope, variable, value, unit, mode, uncertainty)`。modeはobserved/estimated/simulated。個人identifierとcredentialsを収集しない。匿名集計の少数セル・推計人口の公開条件を固定。

`WorldState(environment_id, revision, resources, network, rules, cohorts, observations, model_version)`。stateは実測に接地した部分モデル。

`Intervention(intervention_id, expected_revision, mechanism, patch, target_scope, authority_ref, budget, stop_rule, fallback_ref, idempotency_key)`。patchは容量、ネットワーク、価格条件、供給・配分ルール等のtyped変更。LLMの自由文を直接外部操作へ渡さない。

`Projection(candidate_id, scenario_id, seed, outcome_vector, cohort_results, cost, uncertainty, assumption_refs)`。

`EffectReceipt(intervention_id, dispatch_id, state, applied_patch, independent_readback_ref)`。stateはapplied/failed/unknown。unknownに対し再送しない。

`OutcomeEvidence(intervention_id, mode, window, baseline_ref, comparison_method, metrics, cohort_results, uncertainty, cost, source_refs)`。

`EpisodeManifest(source_sha, model_version, scenario_hash, information_cutoff, seeds, candidate_set, baselines, objective_version, costs, trace_hash)`。

Outcome vectorはreal income/affordability、health又は名前を付けたproxy、time、access、agency、other-life/ecological effectsを区別。目的の重み・集団悪化上限・予算は版固定。Manager収益を受益者所得へ算入しない。

## 5. interfaceと処理

`ResponseModel.act(state: WorldState, cohort: Cohort, rng: Random) -> Demand`。

`Environment.step(state: WorldState, demands: list[Demand], patch: RulePatch | None, rng: Random) -> TransitionResult`。

`propose(state: WorldState, objective: Objective, budget: Budget) -> list[Intervention]`。

`simulate(initial: WorldState, intervention: Intervention, manifest: EpisodeManifest) -> Projection`。

`rank(projections: list[Projection], constraints: Constraints) -> Selection`。制約違反を先に除外し、confidence・worst-group・cost・Pareto trade-offを報告。no-change baselineを必ず含む。

`apply(intervention: Intervention) -> EffectReceipt` と `readback(receipt: EffectReceipt) -> EffectReceipt` はexecutorの別操作。simulation executorとlive executorの型・modeを分ける。

`evaluate(evidence: list[Observation], plan: OutcomePlan) -> OutcomeEvidence`。

`update(model: ModelVersion, evidence: OutcomeEvidence) -> ModelVersion`。更新は需要parameters、prediction error/confidence、mechanism成績、実費、model driftから始める。foundation model trainingは初期要件ではない。新modelをheld-outで検証し悪化時は旧版へ戻す。

一主体はstable manager_id・objective・intervention ledger・model versionsで継続する。finite episodeを終了しても主体の状態は継承する。sleep中も既知の全世界stateが真と仮定しない。

## 6. デモ提案と証拠の段階

Reference demoは **Shared-world redesign**。サービスへのアクセスと共有資源の配分という2つのscenarioを同じinterfaceで扱い、単一問題への硬直した最適化から一歩進む。

Scenario A: service networkで場所・容量・利用可能時間・移動接続を変更し、複数集団の到達・待ち時間・未充足需要を比較。診療効果・実際の健康改善は模型に含めたときだけの仮定であり、access改善を健康改善と呼ばない。

Scenario B: supply/common-resource環境で容量・配分・回復・予算の制約を変更し、必要品充足・負担・枯渇・集団差を比較。合成Coin・utilityを実所得と呼ばない。

どちらも最初の事業領域の決定ではない。候補は構造変更、baselineは現状維持と固定ルール。同じ初期値・exogenous shocks・paired seedsで比較。policy選択と評価を分離し、seed/scenarioをtuningとheld-outへ事前分割する。人数は計算費用を測って決め、大人数を精度や社会効果の根拠にしない。

Prototype→empirical calibration→shadow→authorized live comparisonの段階を明示。期限までにliveができなければ、reproducible simulation、較正の限界、具体的なoperatorとの検証計画を提示。partner署名・改善率・受益者数を創作しない。

live候補は供給・共有サービス・アクセス条件などから権限・比較・観測が揃う一件を選ぶ。受益者のsignupを要求せず、環境の運営者の操作境界から接続する。全生命はmissionとして保持し、初期human outcomeから動物・生態系への効果を外挿しない。

## 7. 収益・採用・関係づくりとの接続

旧Life Managerの売上はfunding sourceとして独立管理できる。売上現在値は今回未確認。新Managerの業績へ付け替えない。将来のpayerは環境運営者・資源提供者等で、契約・支払意思を検証する。beneficiary no-loginとoperator契約は両立する。

採用要件との対応はsimulation実装、evaluation harness、reproducibility、ML systems、causal reasoning、infra設計の成果物で示す。求人へ通るためにManagerのmissionを変えない。会社の非公開code/data/IPをManagerへ持ち込まない。副業・競業・発明帰属は各契約を確認する。YC期間は公式FAQのin-person SF要件も計画へ含む。

cold emailは相手のpaper/productと具体的な一問を合わせる。最初はfeedback又は研究対話で、cofounderを求めない。prototypeやpodcastの規模を架空に書かない。返答や出演は実receipt後に記録する。

## 8. リンクと現状

[Landscape・求人](../../research/manager/2026-10-08-landscape-jobs.md)、[研究者・個別outreach](../../research/manager/2026-10-08-people-outreach.md)、[OSS・under the hood](../../research/manager/2026-10-08-greenfield-architecture.md)、[サイト原稿](2026-10-08-manager-website-copy.md)。

仕様は研究とユーザーの最新方針からの提案。求人で要求される能力と実装済み能力は区別する。cold emailの下書きと送信、simulationと実測、source変更と本番公開は別状態として扱う。
