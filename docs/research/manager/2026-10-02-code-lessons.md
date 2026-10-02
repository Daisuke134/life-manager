# 社会・経済・物理環境の構造変更に向けたコード調査

2026-10-02。対象はLife-Managerを「価格、供給、利用可能性、ルール、共同インフラを変え、生活可能性を改善する一つの主体」へ進化させるための外部実装調査。室温・建物省エネを製品の主題にはしない。旧repo調査のBOPTEST優先という推奨はこの新しい目的では置き換える。

今回読んだのは`/workspace/scratch/manager-upstreams/`の5 cloneと既取得の一次論文cacheのみ。canonical Life-Managerコードは読んでいないため、以下は外部実装から得られる設計条件・接続案であって、既存Life-Managerの実装済み機能を主張するものではない。依存install、LLM/API実行、テスト実行、外部clone変更は行っていない。

## 結論

**学ぶべき中心は架空の住民の会話ではなく、共通の環境状態、介入の適用点、要求と実現の差、ルールの版、資源制約、観測可能な結果である。**

- Concordia: 誰が何を試みたかと、環境がどう解決したかを分ける。Inventoryの構造化状態を参考にするが、自然言語からのLLM数量更新は現実台帳に使わない。
- AgentSociety: `EnvBase`の観測/変更tool分離、共有資源の一括決済、state/replayを参考にする。経済moduleを完成した価格・需給モデルとは扱わない。
- OASIS: 推薦・到達可能性・見える情報を環境側で変える構造を学ぶ。商品購入methodは市場決済ではない。
- MiroFish: ingest→prepare→run→reportの運用状態とエビデンス照会を学ぶ。graph、生成persona、agent interviewを実住民の観測と混ぜない。
- DoWhy: 効果を推定できない条件と反証を表明する。シミュレーションを作ったモデル自身の結論を現実の因果証拠にしない。

価格・供給・ルール変更を最初に実験するなら、**small deterministic resource/market environmentに単一Managerを接続し、必要な行動異質性だけをConcordia/AgentSocietyから借りる**。5製品の全面導入は必要ない。

## cloneの固定版

|clone|HEAD SHA|原license|
|---|---|---|
|concordia|`b71d202750e23444ce1bf28d9f114bcd88aa41db`|Apache-2.0|
|AgentSociety|`8cc5bb9a9c27d039ec5519375db9d73ccf508cba`|Apache-2.0。ただしAS1 `commercial`領域は別の商用license|
|oasis|`affe52e8dcbc70bba0a4162bfea1057aa5df9316`|Apache-2.0|
|MiroFish|`7657031ac01184afe2cb220f5ee3545573b5e843`|AGPL-3.0|
|dowhy（py-why）|`cc23521127ba21ade40514539ae7b91db27ca54a`|MIT|

SHAは各cloneの`git rev-parse HEAD`で確認。AgentSociety/AGENTS.mdによるとGitHubはpublic mirror、primary remoteはGitLabであり、現行CI対象はAS2、extension、frontend。AS1とbenchmarkはreference-only。最新mainにあることと、現行CIの対象であることは異なる。

## 1. Concordia: 環境の裁定を独立した契約にする

### 実コードの制御フロー

`concordia/environment/engines/sequential.py`:

- L93 `make_observation(self, game_master, entity) -> str`: GMの`act(ActionSpec(..., output_type=MAKE_OBSERVATION))`で観測を作る。
- L148 `resolve(self, game_master, putative_event: str, verbose=False) -> None`: 提案eventをGMにobserveさせ、`RESOLVE`を要求し、その結果をGMのmemoryへobserveする。
- L223 `run_loop(..., max_steps=100, checkpoint_callback=None, step_controller=None, step_callback=None)`: 終了確認→GM選択→各entity観測→次entity/action spec選択→entity.act→resolve→log/checkpoint。

原コードの核:

```python
raw_action = next_entity.act(entity_spec_to_use)
self.resolve(game_master=game_master, putative_event=action, verbose=verbose)
```

GMが世界を作り、entityが行為を提案する。Managerの政策候補と政策の適用結果を分ける設計には向く。ただし標準GMの文章が実施済み受領証になるわけではない。

### 台帳があっても数量はLLM推定

`concordia/components/game_master/inventory.py`:

- L56 `ItemTypeConfig`はitemごとのminimum/maximumを保持。
- L179 `Inventory.pre_act(self, action_spec)`はRESOLVE時にLLMへ「誰がどのitemを獲得/失ったか」を質問し、数量deltaをPython inventoryへ反映。数量は上下限へclipする。
- L378 `Inventory.apply(self, fn: Callable[[InventoryType], InventoryType]) -> None`はdeepcopyした全inventoryへfnを適用し、owner/item keysとboundsを検証して更新。

```python
new_inventories = fn(old_inventories)
config.check_valid(new_inventories[key][item_type])
self._inventories = copy.deepcopy(new_inventories)
```

`never_increase=True`の経路は、増加できない場合にGMが増えなかった理由を**invent**するようpromptしている。境界内に収まる数量と、正しい物流・会計・現実観測は別問題。owner間の二重仕訳・全体保存則を、このclipやbounds検証だけで保証できない。

### 接続案と採否

**提案adapter `ConcordiaScenarioAdapter`**: Managerは`Entity.act(ActionSpec)`互換の単一entityとして介入候補を出す。GMのRESOLVE componentを`StructuralTransition`へ置き換え、`price_rule/supply_capacity/access_rule/infrastructure_capacity`の変更をtyped commandで検証・適用する。`Inventory.apply`相当の更新は数式・実connector receiptから行う。Entityには確定eventだけ`observe(str)`で説明として渡す。

- 採用: action attempt/eventの分離、component交換、checkpoint、構造化在庫のdeepcopy/検証。
- 追加必須: 市場clearing、予算、在庫保存、提供能力、ルールeffective time、拒否理由、intervention ID。
- 避ける: 標準`Inventory.pre_act`のLLM deltaをreal ledgerへ採用、GM narrativeだけで「供給が増えた」と確定。
- 制約: Python >=3.12、entity/GM各段階のLLM呼出し。単一ManagerでもGM/住民側のLLM費用は別に発生する。

[engine固定原文](https://github.com/google-deepmind/concordia/blob/b71d202750e23444ce1bf28d9f114bcd88aa41db/concordia/environment/engines/sequential.py)、[Inventory固定原文](https://github.com/google-deepmind/concordia/blob/b71d202750e23444ce1bf28d9f114bcd88aa41db/concordia/components/game_master/inventory.py)、[原論文](https://arxiv.org/abs/2312.03664)

## 2. AgentSociety: 一つの世界を明示toolで操作し、round単位で決済する

以下のpathは`packages/agentsociety2/agentsociety2/`配下。AS1の都市gRPC engineと混同しない。

### tool境界と記録

`env/base.py` L99:

```python
def tool(readonly: bool, name=None, description=None,
         kind: Literal["observe", "statistics"] | None=None)
```

observe/statisticsに`readonly=False`を指定するとValueError。method schemaとreadonly/kind metadataを登録する。async wrapper L242は成功returnまたはexceptionを`finally`でtool call historyへ記録する。`EnvBase.step(tick, t)`、`to_workspace/restore`、`_write_agent_state`/`_write_env_state`が環境時刻とstate保存の契約。

これは「見た」と「変えた」を混ぜない良い足場。ただしreadonlyというannotationは、それ自体で実設備への権限管理・二重実行防止を作らない。

### 共有資源は要求と実際配分を分ける

`contrib/env/commons_tragedy.py`:

- L186 `async submit_extraction(self, agent_name: str, requested_extraction: int) -> SubmitExtractionResponse`: lock内でpendingへ保存。同round再提出はlast wins。1～max外の入力を1に補正する。
- L227 `_calculate_actual_extractions_sync(self, requested_extractions: dict, pool_before: int) -> tuple[dict,int,int]`: 資源不足なら比例配分、整数化後の端数を配り、pool減少を計算。
- L305 `async step(self, tick: int, t: datetime)`: lock内でpendingをまとめて決済、round_historyにpool before/after、extractions、payoffsを残す。未提出者は0扱いで、全員到着を待たない。

```python
actual_extractions, _total_extracted, remaining_pool = (
    self._calculate_actual_extractions_sync(
        self._pending_extractions.copy(), pool_before_this_round))
self.current_pool_resources = remaining_pool
```

**構造再設計への直接的な教訓**: 資源プール、利用上限、配分ルールを明示状態にする。住民に「節約して」と話すことに加え、pool補充、capacity拡張、価格/割当変更、アクセス条件変更をManagerの介入toolにできる。ただし現moduleにこれらのpolicy setterはないので追加設計が必要。現在の無効要求を1に補正する挙動は実介入で採らず、明示rejectにする。非提出=0は通信故障と真の需要ゼロを区別する状態へ拡張する。

### EconomySpaceは市場ではなく台帳

`contrib/env/economy_space.py`:

- `get_person_currency(id)`, `add_person_currency(id, delta)`, `set_person_consumption(id, consumption)`, `set_person_income(id, income)`をtool公開。
- L417 `async step(self, tick: int, t: datetime)`が日単位で利子→income→tax→consumptionをcurrencyへ反映し、各人と環境stateを書き出す。

```python
person.currency += person.currency * self._bank_interest_rate / 365
person.currency += person.income
person.currency -= tax
person.currency -= person.consumption
```

bank rate/tax bracketは内部state。公開method一覧にprice/supply/inventory/rule setterは見つからない。商品の不足、価格に対する需要、競争、供給lead time、提供capacity、現実の売買決済をこのmoduleが実装しているとは言えない。税計算の仮定や単位も現実制度と同じと仮定しない。

### router/replayから学ぶこと

`env/router_codegen.py` L1793 `async ask(self, ctx: dict, instruction: str, readonly=False, template_mode=False, trace_id=None, parent_span_id=None)`。

codegen/provider/cache→AST safety validation→`_execute_code`→result/final answerのflow。L1234～1350はrestricted imports/builtinsと`exec(compile(...))`でgenerated Pythonを同process実行し、10秒timeoutを設ける。これは運用上の制限であり、real mutationの隔離sandboxやauthority boundaryと同義ではない。

`storage/replay_sink.py` L175 `async write(table, data)`/L184 `write_batch(table, rows)`はJSONLへappend。schema catalogとshard lockでstate/historyを保存する。**replayは記録を読めること**であり、同seed・model版で一字一句再現できることや因果反実仮想が正しいことではない。

**提案adapter `StructuralEnv(EnvBase)`**: readonlyの`observe_environment(region_id)`、mutationの`apply_price_rule(command)`、`reserve_supply(command)`、`change_access_rule(command)`、`allocate_shared_capacity(command)`を定義。各methodは既存Life-Managerの独立WorldState/ExecutionReceipt serviceを呼び、`step`はlead time/stock/queueを進める。Routerは観測・候補作成に利用可、実変更はallowlist command dispatcherへ明示結線。最初はAS2 runtimeを全面依存せずこのtool/stateの契約を借りる。

[tool原文](https://github.com/tsinghua-fib-lab/AgentSociety/blob/8cc5bb9a9c27d039ec5519375db9d73ccf508cba/packages/agentsociety2/agentsociety2/env/base.py)、[commons原文](https://github.com/tsinghua-fib-lab/AgentSociety/blob/8cc5bb9a9c27d039ec5519375db9d73ccf508cba/packages/agentsociety2/agentsociety2/contrib/env/commons_tragedy.py)、[economy原文](https://github.com/tsinghua-fib-lab/AgentSociety/blob/8cc5bb9a9c27d039ec5519375db9d73ccf508cba/packages/agentsociety2/agentsociety2/contrib/env/economy_space.py)、[AS2原論文](https://arxiv.org/abs/2607.11895)

## 3. OASIS: 情報へのアクセスと推薦ルールを環境の介入点として扱う

### manual actionをLLM行動と分ける

`oasis/environment/env.py` L136:

```python
async def step(self, actions: dict[SocialAgent,
               Union[ManualAction, LLMAction, List[...] ]]) -> None:
    await self.platform.update_rec_table()
    # manual: agent.perform_action_by_data(action_type, **action_args)
    # llm: self._perform_llm_action(agent)
    await asyncio.gather(*tasks)
```

推薦tableの更新が**今回のactionより先**。Twitter clockはその後に1進む。Managerの推薦policy介入をactionと同じbatchの末尾へ入れると、期待したstepから効くとは限らない。policy effective stepとrec update順序を固定する。

`env_action.py`の`ManualAction`はaction type/argsを保持するdataclass。Managerの介入主体が1つでも、内部住民にLLMActionを割当可能。これは実social platform認証や実配信APIを提供するものではない。

### 推薦という構造の変更

`oasis/social_platform/platform.py` L328 `async update_rec_table(self)`はuser/post/trace/recをDBから読み、RANDOM/TWITTER/TWHIN/REDDITの関数を選び、`DELETE FROM rec`後にnew rec matrixを再挿入する。

`oasis/social_platform/recsys.py` L168 `calculate_hot_score(num_likes, num_dislikes, created_at)`:

```python
s = num_likes - num_dislikes
order = log(max(abs(s), 1), 10)
return round(sign * order + seconds / 45000, 7)
```

推薦を環境ruleとして交換すると、個別説得をせずに情報到達・集団ダイナミクスを変えられる。学ぶのは「対象者に何と言わせたか」より「何を見られる制度にしたか」。ただしこの簡易rankingは現実サービスの推薦実装を再現した保証ではない。

### 商品purchaseは需給モデルではない

`platform.py` L208 `async sign_up_product(self, product_id, product_name)`、L220 `async purchase_product(self, agent_id, purchase_message)`。後者は商品存在を確認し、次を実行してtraceを記録する。

```python
"UPDATE product SET sales = sales + ? WHERE product_name = ?"
```

このmethodで価格×数量の支払、予算チェック、在庫減少、供給制約は確認できない。`PURCHASE_PRODUCT`というaction名だけを見て経済シミュレーションと判断しない。

**提案adapter `OasisExposureAdapter`**: exposure/recommendation実験専用。Managerの`ChangeExposureRule`をstep前の環境設定変更として受け、policy snapshotとrec matrix hashを保存。必要な住民行動だけmanual/LLMへ渡し、DB traceをOutcomeObservationへ変換する。価格・供給・共同施設のモデルは外のWorldStateへ置き、OASISは情報伝播/行動応答のみ生成する。

- 採用: manual/LLMの分離、行動trace、推薦policy交換。
- 追加: policy version/effective step、DB snapshot、seed/clock管理、変更前後の到達率と実利用の分離。
- 避ける: 善意の投稿を増やすだけの施策、like数を生活改善と同視、purchase countを物理供給と同視。
- 制約: Python/CAMEL runtime、profile/data、LLMまたはlocal inference、推薦方式によってembedding。100万user生成は経験的妥当性の増加ではない。

[env原文](https://github.com/camel-ai/oasis/blob/affe52e8dcbc70bba0a4162bfea1057aa5df9316/oasis/environment/env.py)、[platform原文](https://github.com/camel-ai/oasis/blob/affe52e8dcbc70bba0a4162bfea1057aa5df9316/oasis/social_platform/platform.py)、[recsys原文](https://github.com/camel-ai/oasis/blob/affe52e8dcbc70bba0a4162bfea1057aa5df9316/oasis/social_platform/recsys.py)、[原論文](https://arxiv.org/abs/2411.11581)

## 4. MiroFish: 実行管理と説明を、経験的証拠の種類に分けて取り込む

以下pathは`backend/app/services/`。

### 生成設定を実験仮定として固定する

`simulation_manager.py` L244:

```python
def prepare_simulation(self, simulation_id, simulation_requirement,
                       document_text, defined_entity_types=None,
                       use_llm_for_profiles=True, progress_callback=None,
                       parallel_profile_count=3) -> SimulationState
```

Zep entity読取・filter→OasisProfileGenerator→LLM simulation config→profile/config保存。LLMが時刻・活性度・発言頻度等も設定するので、入力文書に「良い結果」を匂わせるだけで実験条件へ影響する可能性がある。生成configは自然法則の発見ではなくscenario仮定として固定する。

`graph_builder.py` L75 `build_graph_async(text, ontology, graph_name, chunk_size=500, chunk_overlap=50, batch_size=350)`は文章をcloud graphへ入れる。graph relationは抽出/解釈であり、因果edge、価格弾力性、実在庫ではない。

### 実行lifecycleは流用価値がある

`simulation_runner.py` L371:

```python
def start_simulation(cls, simulation_id, platform="parallel", max_rounds=None,
                     enable_graph_memory_update=False, graph_id=None)
```

configを読んでround数を計算→simulation IDのlock内で既存active stateを検査しSTARTINGを永続化→Zep updater→platform別script/subprocess開始→monitor/action log→終了state。updater初期化失敗時はFAILEDを保存し、終了中に二重startしない設計を持つ。

これはManagerが実環境へ同じ介入を二重送信しない設計の参考。ただしsimulation ID lockは、複数process/hostから実注文を送る場合の永続idempotency ledgerの代替ではない。

### agent interviewは生成した反応

`simulation_runner.py` L1694:

```python
def interview_agent(cls, simulation_id, agent_id, prompt,
                    platform=None, timeout=60.0) -> Dict[str, Any]
```

SimulationIPCClientで生存確認→`send_interview`→completed/errorを返す。実住民へのsurveyではない。`report_agent.py` L928 `_define_tools()`は`insight_forge/panorama_search/quick_search/interview_agents`等を提供し、graphとsimulation結果へ照会して文章を作る。このreadoutは仮説の発見・説明には使えるが、同じ生成世界が「自分の介入は有効」と述べても独立validationにはならない。

**提案adapter `ScenarioArtifactAdapter`**: source document/hash、ontology、generated persona、config、action log、reportのprovenanceだけ取り込む。全recordへ`origin=real_measurement|real_record|synthetic_profile|simulation_event|llm_interpretation`を付け、Managerの学習datasetへrealとsyntheticを混在投入しない。`SimulationRunner.get_all_actions`相当のmachine eventを一次、report proseを二次artifactにする。

- 採用: 準備/実行/終了のstate machine、process receipt、失敗状態の永続化、tool readoutのtrace。
- 追加: intervention idempotency key、source/event lineage、現実観測用独立storage、report claim/evidence binding。
- 避ける: Zepのgenerated graphを現実世界modelの確定値へ昇格、generated interviewを受益者調査と表示、Reporterを唯一の効果判定器にする。
- 制約: standard構成でZep Cloud/LLM APIが必要、Python 3.11～3.12、frontend Node。AGPLを含むためコードの直接流用と設計上の学習を区別する。

[prepare原文](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/simulation_manager.py)、[runner原文](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/simulation_runner.py)、[report原文](https://github.com/666ghj/MiroFish/blob/7657031ac01184afe2cb220f5ee3545573b5e843/backend/app/services/report_agent.py)

## 5. DoWhy: 構造介入の評価契約を明示する

`dowhy/causal_model.py`:

- L234 `identify_effect(..., proceed_when_unidentifiable=None, optimize_backdoor=False)`はgraphからtreatment/outcome/observed nodesをidentifierへ渡す。
- L271 `estimate_effect(identified_estimand, method_name=None, control_value=0, treatment_value=1, confidence_intervals=False, target_units="ate", ...)`。
- L462 `refute_estimate(estimand, estimate, method_name=None, show_progress_bar=False, **kwargs)`はestimate欠落を拒否し、指定refuterを生成・実行。

```python
refuter_class = causal_refuters.get_class_object(method_name)
refuter = refuter_class(self._data, identified_estimand=estimand,
                        estimate=estimate, **kwargs)
res = refuter.refute_estimate(show_progress_bar)
```

`dowhy/causal_refuters/placebo_treatment_refuter.py` L206 `refute_placebo_treatment(...)`、`dowhy/gcm/falsify.py` L518 `falsify_graph(...)`を別に持つ。classic CausalModelとGCMは同一object APIではない。

**提案adapter `CausalEvaluationAdapter`**: intervention receiptと実観測をregion/group×time windowへ集計し、treatment=価格/供給/アクセスrule変更、outcome=必要財への到達・実負担・待ち時間・未充足需要、covariates=変更前所得/需要/供給等を設定。target estimandとDAG仮定を保存→identify→estimate→refuteを実施。干渉が強い共同インフラ・市場課題では個人独立を仮定せず、cluster/time単位の実験設計・spilloverモデルを先に定める。個人ATE用methodを無条件に選ばない。

- 採用: 識別不能を状態として出す、感度/反証、仮定保存。
- 避ける: simulator生成dataだけでreal effectをclaim、事後の都合の良いoutcome選択、LLM作成DAGを確定的truthと扱う。
- 制約: 観測だけでは交絡を除去できない場合がある。positivity、counterfactual support、効果の遅延、共同施策による干渉、対象群と市場全体の差を設計に含める。

[model原文](https://github.com/py-why/dowhy/blob/cc23521127ba21ade40514539ae7b91db27ca54a/dowhy/causal_model.py)、[placebo原文](https://github.com/py-why/dowhy/blob/cc23521127ba21ade40514539ae7b91db27ca54a/dowhy/causal_refuters/placebo_treatment_refuter.py)、[falsify原文](https://github.com/py-why/dowhy/blob/cc23521127ba21ade40514539ae7b91db27ca54a/dowhy/gcm/falsify.py)、[原論文](https://arxiv.org/abs/2011.04216)

## Life-Managerに必要な接続契約（新設案）

以下の名前は調査対象の既存APIではなく、Manager側に設ける**設計案**。

|契約|最低限のfield・意味|
|---|---|
|`EnvironmentSnapshot`|観測時刻、地理/集団scope、価格/在庫/提供capacity、queue、アクセスrule、source、欠測・不確実性|
|`StructuralIntervention`|id、種類、target resource/rule、old/new value、effective time、費用・予算、expected mechanism、rollback、authority scope|
|`ExecutionReceipt`|idempotency key、request/accept/apply/reject時刻、requested/applied delta、connector receipt、制約・拒否理由|
|`OutcomeObservation`|metric定義、対象群/期間、値・母数・欠測、real/simulated provenance、遅延とspillover、介入ID|
|`ModelUpdate`|更新対象（behavior/supply/elasticity等）、前後版、使用evidence、uncertainty、失敗/識別不能、次実験|

制御flowは`observe → identify bottleneck → propose structural alternatives → simulate/compare → validate constraints → apply → verify receipt → measure delayed outcome → update model`。simulate/reportはapply/measureの代替ではない。

候補の具体例: 必要財の共同調達で単価と欠品を下げる、販売可能なcapacity/営業時間を増やす、提供場所を追加して距離/待ちを減らす、access/eligibility ruleを変える、shared transport/storage/repair能力を整備する。変わるべきものは環境の資源とrule。受益者のアカウント登録やcredentials提供を学習前提にしない。供給側・施設側connectorの権限はManager運用側へ集約する。

## 架空人口の対話が因果証拠にならない理由

1. **仮定が結果へ循環する**: persona、初期world、rule、GM解決を同じLLMが作れば、施策の効果はpromptに埋め込んだ期待を反映しうる。
2. **stateが現実へ接続していない**: OASIS sales、Concordia inventory、AS2 currencyはそれぞれモデルのstate。現実の商品、価格、時間、会計ではない。
3. **規模と同定は異なる**: 同じ生成過程を100万回繰り返しても、欠けた供給制約・行動バイアス・交絡は修正されない。
4. **同じ世界のreadoutは独立評価ではない**: 生成agentのinterviewとReportAgentはsimulation結果の説明。実施前後のreal outcomeや対照群に置き換えられない。
5. **原論文も限界を示す**: Concordia原報告は一般化条件未確定、OASISはdownvote herdが人間と異なると報告、AS2は人間の仮説/妥当性判断を保持する。これらは有用な仮説試験基盤だが、現実の介入効用を普遍的に保証しない。

simulation用途の合格条件は「資源/予算/時間の整合」「介入parameterが別のmodel版でも動く」「未使用scenarioで機構が保たれる」。real用途ではさらに実receipt、独立outcome、変更前baselineと対照、効果/非効果の区間、弱い群への負担、spilloverを要求する。

## license・運用上の判断

Apache-2.0（Concordia/AS2/OASIS）はnotice/著作権等を維持して流用できる。AS1 commercial moduleは除外し、依存物やdata licenseを別に確認する。MIT DoWhyはlicense noticeを保持。MiroFish AGPL-3.0の改変・network提供等の条件は、ライブラリの取り込み方/派生物の提供方法に影響するので単なるMIT部品として混ぜない。設計原理を学んで独自実装することとコードをcopyすることを区別する。モデル・dataset・Zep等service利用条件はrepo licenseだけで決まらない。

今回確認したのはsource flow/signature、原license、原論文、設定・テストの内容であり、5 cloneのruntime動作やtest passではない。学習効果・費用・replay再現性の数値を今回実測したとは主張しない。

最終確認時、AgentSociety cloneの旧benchmark `DailyMobility/evaluation.py` と `HurricaneMobility/evaluation.py` に他処理によるworktree差分が見られた。このレポートはその2ファイルを根拠にしておらず、今回読んだAS2 sourceのSHAに対する変更は確認されなかった。調査者はcloneを編集していない。


## 6. AI Economist: 行動と制度を別の意思決定層にする

追加clone: [salesforce/ai-economist](https://github.com/salesforce/ai-economist)、SHA `a84d5f3fdcabb207d9fde7754d34906903b3e184`、原 `LICENSE.txt` はBSD-3-Clause。Python依存・学習・テストは今回実行していない。

`ai_economist/foundation/components/redistribution.py` の `PeriodicBracketTax.get_n_actions(agent_cls_name)` はBasicPlannerにだけ所得区分ごとの税率actionを渡す。`component_step()` は期間初日に税率を固定し、末日に `enact_taxes()` を実行。後者は前期資産との差から所得を求め、手元Coinを上限に徴収し、税収を全agentへ均等還元する。schedule、income、tax_paid、effective_rate、lump_sumを保存する。plannerの意図と実際の配分がコードでつながっている。

`ai_economist/foundation/components/continuous_double_auction.py` は売買構造の参照先。`ai_economist/foundation/scenarios/simple_wood_and_stone/layout_from_file.py` は `planner_reward_type`、`mixing_weight_gini_vs_coin` を持ち、`coin_eq_times_productivity` 等の目的を選ぶ。この選択は価値判断であり、経済シミュレータから唯一の社会目的が導かれるわけではない。

Managerへの学び: population response modelと制度・容量・アクセス・価格条件を変更するplannerを分ける。環境側が資源保存・支払・配分の実現を計算する。変更前後の同一条件比較、集団別の成果、ルールの版を残す。税制の実行はreference scenarioだけであり、現実の権限を意味しない。供給や共同調達など別の構造にもこの分離を適用できる。

コードを丸ごと採用する判断は未実施。旧依存の導入費用と互換性を確認し、必要な場合だけ固定版adapterを作る。模型内のCoinやutilityを現実の所得・健康に変換しない。
