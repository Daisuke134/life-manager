# 独立Managerをゼロから作るためのOSS実装調査・最小設計

調査日: 2026-10-08。対象は **新規Manager**。既存のmoney-printing Life Managerのコード、データモデル、ジョブ、意思決定器を起点にしない。これは設計レポートであり、実装・API利用・実世界への介入・性能測定は実施していない。

## 結論

Managerの核は「観測を取り込む → 不確かな状態を更新する → 実行可能な制度・運営の変更を列挙する → 人の反応と資源の遷移を別々に計算する → 制約と分配を含めて比較する → 承認された変更を現実の運営に反映する → 結果でモデルを修正する」という閉ループにする。

6個のOSSを一つに接合する構成は採用しない。最初は独立したPythonの数値モデル、SQLite/JSONLの観測・介入台帳、固定候補の探索、ローカルCSVアダプタで作れる。DoWhyは因果評価の境界に追加する候補。Concordia/AgentSocietyは後から人の反応モデルを差し替える参考。MiroFish/OASISはSNS反応を検討する必要が生じた場合の別プロセス。AI Economistからは数値環境とplannerの分離を学び、古い学習環境を丸ごと導入しない。

最初のデモは **受診アクセスを改善する診療所運営** を推奨する。診療枠・夜間開院・交通支援・欠勤損失の制約を変え、誰が利用できるようになるかを示す。HVACや説得文面の最適化より、健康へのアクセスと所得の構造を変えるManagerの意義を説明しやすい。短いデモで主張できるのは、明示した仮定内での利用可能性・待ち時間・可処分所得の改善まで。疾病改善は実測なしに主張しない。

## 1. 調査対象と固定版

確認は各repoの `git show HEAD:<path>` から行った。dirty worktreeの内容を根拠にしない。確認用のHEAD抽出を `/workspace/scratch/manager-research/jobs-oct08/head-sources/` に保存した。以下のSHAが調査の固定点であり、パッケージ番号と同一性を保証するものではない。

| repo | HEAD SHA | ソース記載版 / ライセンス | 導入コストと判断 |
|---|---|---|---|
| MiroFish | `7657031ac01184afe2cb220f5ee3545573b5e843` | backend依存 `zep-cloud==3.25.0`, `camel-oasis==0.2.5`, `camel-ai==0.2.78`; AGPL v3本文 | Zep CloudとLLMの認証・サービス依存。AGPLのコード移植・改変ネットワーク提供にはソース提供義務等の検討が必要。初期核へのコピーは避け、処理構造だけを参考にする |
| Concordia | `b71d202750e23444ce1bf28d9f114bcd88aa41db` | `setup.py`: `gdm-concordia 2.4.0`, Python >=3.12; Apache-2.0 | coreはローカルで利用可能な構成。LLMは選んだbackend次第。自然言語GMの呼出数、プロンプト、モデル版、行動校正を管理する作業が必要 |
| AgentSociety | `8cc5bb9a9c27d039ec5519375db9d73ccf508cba` | active SDK `agentsociety2 2.9.3`, Python >=3.11,<3.14; Apache-2.0 | Ray、LiteLLM、mem0、FAISS、地理関連など広い依存。v1 `1.5.7` はHEADのAGENTS.mdでreference-only。初期の単機能デモには過大 |
| OASIS | `affe52e8dcbc70bba0a4162bfea1057aa5df9316` | `camel-oasis 0.2.5`, Python >=3.10,<3.12, `camel-ai==0.2.90`; Apache-2.0 | SNS DB・推薦・agentの統合。sentence-transformers等のモデル資源も考慮。ManualActionはあるが、一般の生活資源遷移器ではない |
| AI Economist | `a84d5f3fdcabb207d9fde7754d34906903b3e184` | `setup.py`: `1.7.1`, Python >=3.7; BSD 3条件本文 | 2022年のHEAD、requirementsにnumpy 1.21.0/pandas 1.2.4等の大量固定。現代Pythonへの互換性作業・任意のRL訓練が別途必要。設計参照を優先 |
| DoWhy | `cc23521127ba21ade40514539ae7b91db27ca54a` | dynamic version、`0.0.0` はplaceholder; MIT | API課金はcoreの必須条件ではない。DAG、データ、推定法、識別仮定は利用者側の仕事。optionalなeconml/torch/plottingは初期に不要 |

根拠ファイルは各repoの `LICENSE`（AI Economistは `LICENSE.txt`）、MiroFish `backend/requirements.txt`、Concordia/AI Economist `setup.py`、OASIS `pyproject.toml`、AgentSociety `packages/agentsociety2/pyproject.toml` と `AGENTS.md`、DoWhy `pyproject.toml`。

Apache/MIT/BSDでもコード再利用時の著作権・ライセンス表示等は残す。モデル・データ・外部サービスのライセンスはrepoライセンスと別。金額、速度、精度、必要GPUを実測・契約確認なしに決めない。ローカル数値デモならAPI支出をゼロにできるが、計算機・人の作業コストはゼロではない。

**互換性の重要点:** この固定OASISのPython `<3.12` とConcordiaの `>=3.12` は同じPython環境に入らない。MiroFishのCAMEL固定 `0.2.78` と、この固定OASISソースの要求 `0.2.90` も違う。MiroFishのPyPI依存と今回読んだOASIS HEADが同じ挙動とは扱わない。必要になった時点で個別環境・API境界を設ける。

追加OSSはcloneしなかった。Mesa等は将来のABMスケジューリング候補だが、最初の数百agent・有限候補・日次遷移は標準ライブラリで仕様を明示でき、今は追加frameworkを必要とする欠落がない。

## 2. 基本プロセスを実際のコードフローに対応づける

以下の `path:line` は上記HEAD内の位置。公開リンクもSHAを固定する。

### MiroFish: 文書 → グラフ → SNS agent → 投稿行動 → レポート

1. `backend/app/services/ontology_generator.py:203` の `OntologyGenerator.generate()` が文書をもとに型・関係のontologyを生成する。
2. `graph_builder.py:75` の `build_graph_async()` → `:121` `_build_graph_worker()`。テキスト分割とpayload検証 → `:218` `create_graph()` → `:313` `set_ontology()` → `:407` `add_text_batches()`。`zep_cloud` のgraph APIを使い、batch/episodeの取り込み完了を待つ。
3. `simulation_manager.py:244` の `prepare_simulation()` → `ZepEntityReader.filter_defined_entities(...enrich_with_edges=True)` → `OasisProfileGenerator.generate_profiles_from_entities()` → `SimulationConfigGenerator.generate_config()` → profiles/configを保存する。`use_llm_for_profiles=False` でも最初のZep読み出しとconfig生成の経路は残る。
4. `simulation_runner.py:371` の `start_simulation()` が `:539` の `subprocess.Popen` でSNS実行スクリプトを起動。`backend/scripts/run_reddit_simulation.py:577` で `oasis.make()`、`:639` 付近でagentごとに `LLMAction()`、`:643` で `await env.step(actions)`。
5. runnerがaction logを回収。`report_agent.py:1576` の `generate_report()` と `:1260` `_generate_section_react()` が、Zep検索と模擬agentへのinterview等のtoolを使い文章化する。

[固定ソース: prepare_simulation](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/simulation_manager.py#L244)

**採用する考え方:** prepare/run/reportの責務分割、artifact・run status・取り込み完了の明示。**初期に移植しない:** 文書から作った関係を実測の因果グラフと扱うこと、SNS投稿数を健康・所得改善の代理にすること、LLMレポートを効果の検証にすること。

### Concordia: 観測 → component context → 行動案 → GM解決

`concordia/prefabs/simulation/generic.py:235` `Simulation.play()` と `concordia/environment/engines/sequential.py:223` `Sequential.run_loop()` が実行の入口。GMの `act(MAKE_OBSERVATION)` (`:93`) → 各entityの `observe()` → GMがnext entity/action specを決める (`:106`) → entity `act()` → `resolve()` (`:148`) でGMにputative eventを観測させ、GM `act(RESOLVE)` の結果を再度記憶する。

`concordia/agents/entity_agent.py:152` は `PRE_ACT` → context componentsの `pre_act` → acting componentの `get_action_attempt(contexts, action_spec)` → `POST_ACT` → `UPDATE` → `READY`。`:188` の `observe` にもphase分離がある。

[固定ソース: Sequential](https://github.com/google-deepmind/concordia/blob/b71d202750e23444ce1bf28d9f114bcd88aa41db/concordia/environment/engines/sequential.py#L223)

**adapt:** 観測・意思決定context・行動・結果記録を分ける境界、agent checkpoint。**reject:** GMが自然言語で解決した結果をそのまま会計残高・診療容量・健康状態の正解にする。Managerでは行動案をtyped commandに変換し、数値環境が容量制約と結果を確定する。

### AgentSociety: 同期clock → agent batch → env tick → checkpoint

今回のactive版はAS2。`packages/agentsociety2/agentsociety2/society/cli.py:322` `ExperimentRunner.run()` がconfig/stepsを読み実験を実行。`society/society.py:768` `AgentSociety.step(tick)` はrouter clockを同期 → `step_agent_batch.remote(...)` をRayに投入 → batch結果とtoken差分を集計・failure検出 → `env_router.step(tick,t)` → clock進行 → `to_workspace()`。`:841` `run()` がこのtickを繰り返す。

`agent/person.py:489` `PersonAgent.step()` は初期化 → skill hooks → readonlyな環境観測 → 基底 `AgentBase` のReAct loop → memory更新という構成。`person.py:302` 付近でstep用finish toolを差し替え、終了時にmemoriesも回収する。環境の具体的な状態遷移はmodule/router側に置く構造であり、PersonAgent自体から健康・所得の正確さは生まれない。

[固定ソース: society.step](https://github.com/tsinghua-fib-lab/agentsociety/blob/8cc5bb9a9c27d039ec5519375db9d73ccf508cba/packages/agentsociety2/agentsociety2/society/society.py#L768)

**adapt:** 全agentが同じtickを観測してから環境を進める順序、failure伝播、run単位のtoken集計、永続checkpoint。**defer:** Ray、skill/ReAct、地図、memory serviceの一括導入。少数agentなら逐次実行で仕様を検証する。旧v1の都市実装を現行AS2の機能保証として引用しない。

### OASIS: 推薦表更新 → manual/LLM action → SNS状態

`oasis/environment/env.py:136` `OasisEnv.step(actions)` → `platform.update_rec_table()` → `ManualAction` は `agent.perform_action_by_data()`、`LLMAction` は `_perform_llm_action()` (`:124`) → `asyncio.gather()` → Twitterの場合clockを進める。DB・投稿・フォロー・推薦が環境の中心。

[固定ソース: env.step](https://github.com/camel-ai/oasis/blob/affe52e8dcbc70bba0a4162bfea1057aa5df9316/oasis/environment/env.py#L136)

**adapt:** manual policyとLLM policyを同じaction境界から投入できる考え方。**reject:** 投稿の多寡を制度の成果に読み替える。並行SNS actionをそのまま希少な診療枠の同時予約に使わず、環境の予約処理でatomicな容量管理をする。

### AI Economist: agent/planner action → 数値component → scenario → observation/reward

`ai_economist/foundation/base/base_env.py:929` `BaseEnvironment.step(actions, seed_state)` → `parse_actions()` → RNG state/replay記録 → timestep進行 → 各component `component_step()` → `scenario_step()` → observations/masks → rewards → done → action reset。

`foundation/components/redistribution.py:79` `PeriodicBracketTax` はplannerの税率制御を持つ。`:945` `component_step()` → 課税周期に `:853` `enact_taxes()`。同ファイル `:46` `WealthRedistribution.component_step()` はcoinを再分配し総量保存をassertする。

[固定ソース: numerical step](https://github.com/salesforce/ai-economist/blob/a84d5f3fdcabb207d9fde7754d34906903b3e184/ai_economist/foundation/base/base_env.py#L929)

**最も重要なadapt:** 人の行動policyとplannerの制度policyを分離し、結果を実行コードで数値化する。容量・時間・金銭の保存則とreplayを残す。**reject:** 既存toy economyの報酬がそのまま現実の厚生を表すとすること、最初から二段階RL訓練を必要条件にすること。有限候補探索でまず透明なbaselineを作る。

### DoWhy: DAG → 識別 → 推定 → 反証 / SCM介入

`dowhy/causal_model.py:234` `identify_effect()` → AutoIdentifier/IDIdentifierがDAGからestimandを作る → `:271` `estimate_effect()` で指定推定法 → `:462` `refute_estimate()` で反証手法を適用する。これは数値環境やplannerではなく評価層。

`dowhy/gcm/whatif.py:27` `interventional_samples()` はDAGを検証してモデル内の介入分布を生成する。`:105` `counterfactual_samples()` は観測またはnoiseを要求し、観測からnoiseを復元する場合は `InvertibleStructuralCausalModel` を要求する。単に「同じseedで2回simulation」しただけで、個人の現実の反実仮想が識別されたことにはならない。

[固定ソース: identify_effect](https://github.com/py-why/dowhy/blob/cc23521127ba21ade40514539ae7b91db27ca54a/dowhy/causal_model.py#L234)

**reuse候補:** 観測データがある段階でCausalModelの4段階API。**reject:** 自動生成DAGを正しいと決める、refutation通過を因果証明と呼ぶ、simulation内の効果を現実への外挿保証とする。時系列feedbackは時間添字つきDAG等で表す。定常DAGをfeedback loopに直接当てない。

## 3. MiroFishのZep依存と事実上の限界

`backend/app/config.py:33` に `ZEP_API_KEY`。`:67` 以降のvalidateでLLM/Zep key未設定をerrorにし、`:71` では **`ZEP_API_URL` は非対応、MiroFishはZep Cloudのみに接続** と明示している。`GraphBuilderService.__init__` と `ZepEntityReader.__init__` もkeyなしでValueError。requirementsの `zep-cloud` はSDKであり、Zep Cloudの運用サービスがrepoに含まれるという意味ではない。

従って、この固定版をそのまま「完全ローカル・無料で動く世界モデル」と紹介できない。ZepをSQLiteへ置換する場合は、node/edge取得、ontology、文書取り込みの非同期完了、search、report tool、simulation memory更新を置換・再検証する設計作業になる。環境変数でlocal Zepに切り替えるだけの経路は、この固定版のconfigが拒否する。

文書グラフは出典中の関係を検索する記憶構造であり、医学・経済の構造方程式ではない。profiles/config/投稿/interview/reportには生成内容が入り、元資料にない属性・反応を仮定しうる。取り込み完了のbarrierやログは追跡性を改善するが、実世界での代表性・校正・介入効果を証明しない。今回のsource readだけではbenchmarkの再現、実データとの一致、運用料金・free tier、サービスSLAは検証できていない。

## 4. 独立Managerの最小構成

### 状態と責任の境界

| module | 入出力と責任 | 初期実装 |
|---|---|---|
| `observations` / `belief` | 観測 `value, unit, observed_at, source, quality` → 状態分布 `b_t`。未観測・期限切れ・仮定を区別 | dataclass、SQLite、未知のattendance係数は区間/複数仮説。単一のLLM要約をbeliefとしない |
| `behavior` | agentの情報・時間・価格・制度変更 → 応答/選択 `a_t` | explicitな確率・rule baseline。実測で校正後にLLM/Concordia/AS2 adapterを比較 |
| `environment` | 潜在状態 `x_t`、policy `u_t`、行動 `a_t`、外乱 `epsilon_t` → `x_(t+1), events` | 純粋な数値関数。診療枠、予約、移動、労働時間、費用、台帳を更新 |
| `candidates` / `controller` | 権限・予算内の候補 → 複数belief/外乱でrollout → 選択理由と実行案 | 固定候補列挙、Pareto比較、制約付き短期探索。初期にRLは不要 |
| `evaluation` | baselineとの比較、仮定、観測実験 → simulator差分/識別可能な効果推定 | 同じ外乱のpaired rolloutと感度分析。DoWhyは実データ評価に分離 |
| `adapter` | 承認済みtyped command → 運営システムの実行 → acknowledgement/観測 | まずCSV intakeとローカル予約台帳へのcapacity update。後に実事業者APIを追加 |
| `budget` / `audit` | 計算量・token・API費・介入予算・時間上限 → reserve/commit/stop | 上限超過前に停止し、最良のfeasible候補または何もしない案を返す |

beliefは `P(x_t, theta | observed events)` の近似。environmentは `x_(t+1)=F_theta(x_t,u_t,a_t,epsilon_t)`。observationsは `y_t=G(x_t,noise)`。シミュレータ内のlatent stateと、現実にManagerが観測できるstateを別にする。健康など未観測量のposteriorを確定値としてUIに出さない。

親タスクで選定された実装先は `apps/manager`、Python 3.12標準ライブラリのtyped core。旧runtimeを依存に持たず、同じinterfaceでservice-accessとcommonsのscenarioを差し替える構成。本稿の診療所例はservice-accessの具体化であり、以下のファイル名は責務を示す設計案である。

最小の閉ループ:

```text
CSV/実観測 → unit/time/source検証 → belief更新
→ baseline込みpolicy候補 → 権限・予算・容量チェック
→ belief仮説×外乱を固定し、behavior→environmentを反復
→ 平均/不確実性/悪化する群/実行費を比較 → typed変更案
→ approval済み範囲をadapterで実行 → ackと観測event
→ 予測誤差・欠測・実施差分を更新し、次の候補へ
```

責務の参考構成は `manager/{belief,behavior,environment,controller,evaluation,adapters,budget}.py`、`scenarios/clinic_access.json`、`data/{agents,capacity,observations}.csv`、`runs/<run_id>/{manifest,events,metrics,decision}.json*`。独立package/entrypoint/schemaをcanonical repo内のapps/managerに作る。既存Life Managerへhookを追加する形を必須にしない。

### 数値遷移が担う具体的な処理

例: agentごとに勤務可能時間帯、賃金、交通時間、移動費、受診希望、予約情報を保持。policyは開院時間帯・提供枠・交通支援・総運営費を保持する。

1. 公開された枠と費用を見たbehaviorが予約希望/拒否を返す。
2. environmentが先着/抽選等の明記したallocation ruleで枠を割り当てる。`bookings <= slots`。behaviorが「予約できた」と書いても枠は生成されない。
3. 外乱とresponseから欠席/来院を決め、未利用枠を処理する。通院・待機・就労の時間を二重計上しない。
4. `net_income = earned_wage - travel_cost - service_fee + allowed_transfer`、支援額は運営budgetから引く。開院延長は職員の労働/費用/上限も更新する。
5. access成功、待ち時間、lost work income、運営費、群別未充足率を計算。健康は初期では「受診機会」という結果まで。臨床的health transitionは別の根拠と校正が得られてから追加する。

制御は平均だけで選ばない。費用上限、職員負荷、最も不利な群の未充足率、群ごとの所得悪化を制約・Pareto表で示す。重みは利用者がレビューできる設定値。情報が不足すれば追加観測または現状維持を候補に残す。

adapter commandには `command_id, policy_version, target, expected_previous_version, effective_at, estimated_cost` を持たせる。実行済みcommandの重複適用を防ぎ、ackがない場合に成功扱いしない。real adapterが未接続の段階は「運営への実施はローカル台帳デモ」と表示する。コネクタが存在するだけでは変更権限もデータ取得権限も得たことにならない。

## 5. 実行可能なデモの候補

ここに示すentrypoint/commandは **実装時の仕様案** であり、今回生成・動作確認したプログラムではない。どの案もAPI key不要の数値baselineから始められる。

| 案 | 変えられる構造 | 取り込む入力 / 数値遷移 | 観測する成果 / 限界 | 適性 |
|---|---|---|---|---|
| A: 診療所アクセス | 夜間枠、総枠配分、交通支援、予約配分 | 勤務時間帯・移動時間・費用・枠CSV → 予約/来院/容量/欠勤損失 | アクセス、待ち時間、所得損失、群別未充足。疾病改善は未検証 | 第一推奨。health/access/incomeが同じ構造でつながる |
| B: 保育と就労アクセス | 保育枠、開所時間、所得別支援、通勤/研修枠 | 世帯・勤務・保育枠・交通・賃金 → 割当/勤務可能時間/手取り | 就労可能時間、保育未充足、可処分所得。雇用が自動発生する仮定は避ける | health proxyは時間負担まで。制度の構造的意味が明瞭 |
| C: 食事サービス | 安価な食事枠、pickup場所/時間、交通支援 | 予算・移動・勤務・供給量 → allocation/利用/家計 | 食事アクセス、自己負担、移動時間。栄養・健康効果の係数には外部根拠が必要 | 小さく実装可能。供給上限と予算の説明が容易 |

Aの想定CLIは `python -m manager.demo --scenario clinic_access --seed 42 --agents 100 --days 14 --policies 6 --output runs/demo`。6候補には必ず現状維持を入れ、同一の初期集団・外乱で比較する。agent数・日数・候補数は計画値で、所要時間のbenchmarkではない。

デモで見せる4場面: (1) どの群が勤務/交通の制約で受診できないか、(2) policy候補のfeasible領域とtradeoff、(3) 選択案をローカル運営台帳へ一度だけ適用して新しい枠を表示、(4) 観測を再取り込みして予測誤差を表示。夜間延長が職員コストを超える場合など、採用されない候補も説明する。LLM説明文は任意の最後の薄い層にし、数値結果を変更させない。

**synthetic実験の注意:** policy effectを正に埋め込んだ生成器を使うと「改善」は仮定の再表示になる。attendance効果を0/負にもする、需要が少ない/過多、支援利用なし、交通の改善がない等の別シナリオで順位の安定性を示す。別behavior baselineを比較し、選択した候補だけを報告しない。

## 6. 証拠の段階と期限向けの範囲

| 段階 | 必要な証拠 | 許される主張 |
|---|---|---|
| E0: 機械的整合 | 容量・予算・時間の不変条件、seed/replay、command重複防止、失敗ログ | 実装が明記した規則を守る |
| E1: 仮定内の比較 | 全候補のpaired rollout、効果0/負を含む感度分析、群別tradeoff | この仮定・外乱集合で候補が優位 |
| E2: 観測に対する予測検証 | 時間を分けたholdout、欠測・選択biasの確認、naive baselineとの比較、uncertainty校正 | 対象・期間を限定した予測能力 |
| E3: 現場介入評価 | 明記したDAG/estimand、無作為化または識別可能な設計、実施率、費用/群別悪影響 | 条件を明記した実介入の効果推定 |
| E4: 運用generalization | 新しい場所・期間・制度での再評価、drift検出、停止/復旧 | 検証済み範囲の継続運用能力 |

DoWhyはE3の仮定・識別・推定・反証を整理する道具。E1のsimulation差分をDoWhyへ通してもE3へ昇格しない。対照との差のMonte Carloばらつき、未知パラメータの感度、現実の因果識別の不確実性を混ぜて単一の「95%信頼」にしない。

親タスクで確認された締切はYCの2026-11-02 PT。10月8日から約25日ある。正確な時刻・提出要件は親タスクの公式情報確認を参照し、このソース調査から独立に検証した情報とは扱わない。以下は最初のデモを短期間で固定する範囲提案であり、新たなtask trackerではない。残期間は実観測によるE2、権限と協力先が揃えばE3へ回す。

- **最初の1–2日相当:** Aの数値環境、rule behavior、6候補、SQLite/JSONL、CSV intake、ローカル台帳への実行、E0/E1のチェックを作る。E0の破綻が残るなら候補探索やLLMを増やさない。
- **余裕がある次の1–2日相当:** 入力/仮定を編集できる比較画面、群別tradeoff、感度表、実行ackと再観測を統合。許可済み実データがある場合だけ小さなholdout評価を追加する。
- **締切前の固定:** 結果とmanifestを保存し、networkなしでもreplay可能にする。デモを3–5分にまとめ、synthetic/実観測・未接続adapter・未検証の健康効果を明記する。E2/E3が揃わなければE1の主張で提出する。

Concordia/AS2で多数LLM agentを動かすこと、Zep置換、大規模都市地図、planner RL、外部provider連携は期限のcritical pathへ入れない。Managerらしさはagent数ではなく、状態の不確実性、構造的に変えられるpolicy、数値制約、現実への実施と結果学習の閉ループで示す。

## 7. 次にレビューすべき設計判断

推奨の独立MVPはA。レビュー対象は「誰が診療枠・運営時間・支援budgetを変更できるか」「第一成果を受診アクセス/所得損失とするか」「勤務・交通・枠の実観測がどこから得られるか」の3点。回答が未確定でもsynthetic E0/E1とローカル台帳デモの設計は進められる。実運営APIへの接続や実際の健康効果の説明には、その対象・権限・データ・根拠を確定させる。

このレポートで作成したものはscratch内の設計文書とHEAD確認用のソース抽出のみ。canonicalの仕様・既存Manager・trackerは変更していない。OSSのruntime、API、依存install、外部benchmarkの再現は行っていない。


## 親タスクでの採用範囲

本稿の診療所はservice-access scenarioの具体例。最初のlive事業を診療所へ固定する決定ではない。親仕様ではservice-accessとcommonsを同一interfaceのreferenceとして選定。実装path・CLI・型は [greenfield設計](../../superpowers/specs/2026-10-08-manager-greenfield-design.md)、作業順は [統合SSOT](../../superpowers/specs/2026-09-25-life-manager-unified-ssot.md#manager-20261008) を優先する。
