# Andon Labsと「マクロな社会変化」を測る評価設計

確認日: 2026-10-10 UTC。一次資料の公開ページと公開GitHubソースのみ。scratchに資料スナップショットを保存。インストール、モデル実行、認証情報操作、外部送信はしていない。以下の事業案・評価プロトコルは提案であり、既存製品の性能や顧客の購入意思を示す事実ではない。

## 結論

Andonから借りるべきものは「社会のデジタルコピーを一気に作ること」ではなく、長期間・資源制約・部分観測・検証可能な結果を持つ小さな環境を公開して、シミュレーションの失敗と現実の失敗を往復させる研究方法である。ただしVending-Benchの利益は単一事業の資源獲得能力であって、社会全体の福祉・雇用・公平性・環境改善の証拠ではない。社会変化を目的にするなら、モデルが住民の需要を予測できるか、介入を選べるか、実行できるか、現実の結果が改善したかを別々に測る必要がある。

「ベンチマークを作ったからYCへ入れた」は公開時系列と合わない。YCはWinter 2024。Andon本人の記事によるVending-Bench着手はlate 2024、公表は2025-02-20。一方、シミュレーションからAnthropicの現実実験へ進んだ経路は両社の一次記事に記載がある。ラボとの共同研究、特別な事前モデルアクセス、顧客契約、データ購入の因果はそれぞれ別問題で、公開記事から自動的に導けない。

## 一次資料による時系列と確度

| 時期 | 確認事実 | 解釈の限界 |
|---|---|---|
| 2023 | YC公式にFounded: 2023 | 設立日は不明 |
| Winter 2024 | YC公式にBatch: Winter 2024、Primary Partner: Diana Hu | 採択理由は記されていない |
| late 2024 | Andon『Why we built Pion』がVending-Benchの開発開始を明記 | この前に他の評価活動があった可能性を否定するものではない |
| 2025-02-20 | Vending-Bench論文v1、Axel Backlund / Lukas Petersson | 論文著者だけで現在の全創業者を断定しない。YC現行ページのActive FoundersはLukas Peterssonのみ、重複表示 |
| 2025-06-27 | Anthropic『Project Vend: Can Claude run a small shop? (And why does that matter?)』公表 | 実験開始日ではない。Sonnet 3.7使用、収益は失敗 |
| 2025-11-18 | Vending-Bench公式ページにVB2 released / VB1 deprecated | VB1とVB2は期間と採点が異なるため直接のスコア比較不可 |
| 2025-12-18 | Anthropic Project Vend phase two公表、Sonnet 4.0→4.5、ツール改良、複数拠点 | モデルと足場と手順が同時に変わっている。改善を一変数に帰属できない |
| 2026-09-14 | Pion研究プレビュー公開告知。既存ビジネスを持つ人のwaitlist募集 | 公開価格、売上、契約、購入意思はここから分からない |

一次URL: [YC company](https://www.ycombinator.com/companies/andon-labs)、[論文v1](https://arxiv.org/html/2502.15840v1)、[Pionの起源](https://www.andonlabs.com/blog/why-we-built-pion)、[Vend 1](https://www.anthropic.com/research/project-vend-1)、[Vend 2](https://www.anthropic.com/research/project-vend-2)、[VB1](https://www.andonlabs.com/evals/vending-bench)、[VB2](https://www.andonlabs.com/evals/vending-bench-2)。

Pion記事は「To answer these questions, we asked Anthropic if we could put a real vending machine in their office ... they agreed」と説明する。AnthropicもVBを現実へ移すlogical next stepと記載する。これは提案→共同実験の証拠であり、「ベンチマークだけを売ればフロンティアモデル会社が必ず買う」「同じ経路でYCに入れる」という保証ではない。

## Vending-Benchの機構: 社会シミュレーションに転用できる部分とできない部分

### VB1 (論文セクション2、2025年仕様)

- 30,000 tokenの直近履歴。scratchpad / key-value store / vector databaseの読み書き削除による外部記憶。vector検索はtext-embedding-3-smallとcosine similarity。履歴切断と破綻の明白な相関は見つからないという著者の結果。
- 初期現金$500、機械の毎日費用$2。工具呼び出しに応じて5分/25分/75分/5時間進む。`wait_for_next_day`もある。2000 messagesで終了、毎日費用を10日連続払えなければ早期終了。通常約25M token、5–10実時間、条件ごと5反復。
- メール、実際のウェブ検索、在庫、銀行残高。物理作業はsub-agentが担当し、stock / collect cash / set prices / machine inventoryを扱う。主エージェントには`sub_agent_specs`, `run_sub_agent`, `chat_with_sub_agent`。委任先が何をしたかは自動で全部知らされず、問い合わせが必要。
- 供給者返信はPerplexityで実世界情報を取ってGPT-4oが生成。商品購入には品名・数量・住所・口座番号等の注文条件が必要、配送遅延がある。
- **顧客は「何万人ものLLM人格が自由に買う」仕組みではない。** GPT-4oが商品ごとの価格弾力性、基準価格、基礎販売量を生成・cacheし、その後は価格差・曜日/月/天気・品揃え効果・ノイズ・在庫上限で数値計算。反復できる数値ルールとモデル由来パラメータが混在する。実在人口から同定されたマクロ需要とは限らない。
- terminal scoreは純資産 = 銀行等のcash + 未回収の機械cash + 未販売商品の仕入値。商品が高く評価される構造、比較期間がmessage上限のため異なる構造がある。これは実際の利益と同一ではない。

### VB2 (現行公式の説明)

365日相当の一年、終端銀行残高で採点。初期$500、日費用$2、10日超払えなければ打切り。平均3000–6000 messages。公式は60–100M tokens in outputと書くが、本文の表現を総API token/費用へ独自に置換しない。供給者の値上げ、品切れ、倒産、返金要求を導入。note/reminderを改善、最適化対象を明確化。[VB Arena](https://www.andonlabs.com/evals/vending-bench-arena)は同じ場所で競争・価格戦争・取引を追加するがindividual scoring。協調や競争を測る方向へ拡張しても社会福祉の採点にはならない。

VB1・VB2の全シミュレータの公開ソースと再利用ライセンスは今回確認できていない。VB1公式は研究者へcontactを案内する。論文HTMLはCC BY 4.0だが、**論文ライセンスをシミュレータの商用利用許可と取り違えない**。公開されているのは少なくともInspect拡張`multiagent-inspect`で、Apache-2.0。

### 実Project Vend

VBはシミュレーション、Vendは物理商品と実際の従業員購買。phase 1ではweb search、試作用メール（実メールを送れない）、メモ、Slack対話、価格変更。Andonは実験の卸業者役・補充担当でもある。単独AIで人間の物理作業が完全に消えた実験ではない。phase 2でも購入決済インターフェースを与えず人間確認を要した。phase 2の改善には新モデル、CRM、仕入価格を見せるinventory、browser、事前payment link、reminder、手順強制等が同時に存在。人間の手間や監督費用込みの完全自律企業の経済性は別に測る必要がある。

### 他のAndon eval

「Bun-Bench」は一次資料で確認できない。公式の実在名は[Butter-Bench](https://www.andonlabs.com/evals/butter-bench): household delivery / butter passingをロボットで行い、公開紹介は最上位LLM40%、human95%。[Drone-Bench](https://www.andonlabs.com/evals/drone-bench)、[Blueprint-Bench 2](https://www.andonlabs.com/evals/blueprint-bench-2)も公式ナビゲーションにある。Butterは物理環境でのエラー・介入を扱える参考だが、人口モデルや社会政策評価の代替ではない。今回はButter紹介の数値に限り確認、Drone/Blueprintの全プロトコルまでは未調査。

## 移植価値がある隣接5件 (巨大スタックを全導入する必要はない)

| プロジェクト | 使うべき部分 | 使わない推論 | ライセンスと一次出典 |
|---|---|---|---|
| METR | 人間時間でtask horizonを測る、固定予算・実行環境・隠れた採点。タスク成功率をdurationに対して見る | ソフトウェアtask horizonがそのまま社会全体の変化速度という推論 | task-standard MIT。[時間測定研究](https://metr.org/blog/2025-03-19-measuring-ai-ability-to-complete-long-tasks/)、[standard](https://github.com/METR/task-standard) |
| Inspect AI (UK AISI) | dataset / solver / scorerを分離、message/token/time/cost limit、sandbox、epochs、replayable logs | frameworkを使っただけでシミュレーションが現実妥当になる推論 | MIT。[Task docs](https://inspect.aisi.org.uk/tasks.html)、[source](https://github.com/UKGovernmentBEIS/inspect_ai) |
| Melting Pot (DeepMind) | 未見の社会場面・background populationでgeneralization評価。focal vs background returnsを別保存。共有資源・協力・欺瞞の実験設計 | ゲームの報酬から現実の社会厚生を保証する推論 | Apache-2.0。[README](https://github.com/google-deepmind/meltingpot)、[report](https://arxiv.org/abs/2211.13746) |
| AI Economist / Foundation (Salesforce) | household/workersと政府planner、資源・税・労働・成分モジュール、シナリオ独立のreward、simulation card | 内部経済モデルで最適な税が実際にも最適という推論 | BSD-3-Clause。[repo](https://github.com/salesforce/ai-economist)、[paper](https://arxiv.org/abs/2108.02755) |
| AgentSociety (Tsinghua FIB Lab) | populationプロフィール、移動/経済/社会ネットワーク、intervene / questionnaire / trace・replay、Rayによる必要に応じた拡張 | LLM人口が実人口の代表サンプルだという推論、口頭賛成を実行動と同視 | 基本Apache-2.0だがREADMEは`packages/agentsociety/commercial`を除外。[repo](https://github.com/tsinghua-fib-lab/AgentSociety)、[v1 paper](https://arxiv.org/abs/2502.08691)、[v2](https://arxiv.org/abs/2607.11895) |

PettingZooはmulti-agent環境API標準として選択肢だが、上表の社会scenario・人口妥当性・因果同定を足すものではない。EconGymという名称は今回一次ソースを確認していないので特定製品を推薦しない。企業の「データ購入」を確約する一次資料も未確認。

因果推定の補助には[PyWhy EconML](https://github.com/py-why/EconML)を参照できる。`DML`等は処置効果を推定する道具であって、交絡なし/positivity等の識別仮定や外的妥当性を自動的に満たさない。LICENSEは主にMIT、一部tree/grfのscikit-learn派生がBSD-3。評価設計はcluster randomizationを優先し、無作為化できない場合は識別仮定、negative controls、感度解析、観測不能交絡を明示する。

## ソース固定と確認したコード署名

今回GitHub APIで取得したsnapshot commit SHA。branch headを今後使い続ける指定ではない。全依存ツリーのインストールは不要。

- `AndonLabs/multiagent-inspect`: `e3ad26b91b136d591f9fceab829262842faf08b2`
- `UKGovernmentBEIS/inspect_ai`: `697fde94e2bb08fcba1b3bad65d8c752e1812111`
- `METR/task-standard`: `83ad6fd1e9d9cba9885341d1efd23a0aff472fe1`
- `google-deepmind/meltingpot`: `0e94a94c834048b836b64d8224b7ff42f4c37250`
- `salesforce/ai-economist`: `a84d5f3fdcabb207d9fde7754d34906903b3e184`
- `tsinghua-fib-lab/AgentSociety`: `8cc5bb9a9c27d039ec5519375db9d73ccf508cba`
- `py-why/EconML`: `d625dd696ea28c62e6e4d8baea6e4154b98c30b4`

[Andon core.py固定URL](https://github.com/AndonLabs/multiagent-inspect/blob/e3ad26b91b136d591f9fceab829262842faf08b2/src/multiagent_inspect/core.py):

```python
init_sub_agents(sub_agent_configs: list[SubAgentConfig])
sub_agent_specs(single_sub_agent: bool = False) -> Tool
run_sub_agent(single_sub_agent: bool = False) -> Tool
# tool execute_single(instructions: str)
# tool execute_multi(sub_agent_id: str, instructions: str)
chat_with_sub_agent(single_sub_agent: bool = False) -> Tool
# execute_single(question: str)
```

[Inspect Task固定URL](https://github.com/UKGovernmentBEIS/inspect_ai/blob/697fde94e2bb08fcba1b3bad65d8c752e1812111/src/inspect_ai/_eval/task/task.py)のconstructorには`dataset`, `setup`, `solver`, `scorer`, `metrics`, `sandbox`, `epochs`, `message_limit`, `token_limit`, `time_limit`, `cost_limit`, `checkpoint`等が存在。新しい社会評価にもこの分離を借りる。

[AI Economist固定source](https://github.com/salesforce/ai-economist/blob/a84d5f3fdcabb207d9fde7754d34906903b3e184/ai_economist/foundation/base/base_env.py):

```python
BaseEnvironment.reset(self, seed_state=None, force_dense_logging=False)
BaseEnvironment.step(self, actions=None, seed_state=None)
BaseEnvironment.generate_observations(self)
BaseEnvironment.compute_reward(self)
BaseEnvironment.scenario_metrics(self)
```

[Melting Pot固定source](https://github.com/google-deepmind/meltingpot/blob/0e94a94c834048b836b64d8224b7ff42f4c37250/meltingpot/utils/evaluation/evaluation.py):

```python
evaluate_population_on_scenario(
    population: Mapping[str, policy_lib.Policy],
    names_by_role: Mapping[str, Collection[str]],
    scenario: str,
    num_episodes: int = 100,
    video_root: Optional[str] = None,
) -> pd.DataFrame
```

returnsの列にはbackground_player_names/returns、focal_player_names/returnsがある。地域介入で受益対象と周辺集団の影響を分ける設計に適する。

[AgentSociety v2固定source](https://github.com/tsinghua-fib-lab/AgentSociety/blob/8cc5bb9a9c27d039ec5519375db9d73ccf508cba/packages/agentsociety2/agentsociety2/society/society.py):

```python
async def init(self)
async def step(self, tick: int)
async def run(self, num_steps: int, tick: int)
async def ask(self, question: str) -> str
async def intervene(self, instruction: str) -> str
```

## 提案: マクロ社会変化を測る最小ベンチマーク

例は「複数自治体の暑熱対策・冷房支援・公共施設の資源配分」。対象の規模は数万人〜地域人口をsample weightsで代表するsynthetic population。すべての人を毎tick LLMとして呼ぶ必要はない。世帯属性、所得、就労時間、健康脆弱性、移動可能性、家族関係、住宅、地域資源からなる人口層の数値モデルを主体とし、LLMは連絡文解釈、意思決定、例外処理のような必要部分のみ。目的は単発のアシスタント満足度でなく、期間内の熱リスク、利用格差、行政負荷、電力/排出、持続費用の変化。

**数値モデルとLLM需要モデルを明確に分ける。** 人口分布を公的統計/実測から重み付けし、行動応答は実際の申込・利用・離脱・移動のデータで校正する。LLMが生成する嗜好や口頭反応を観測真実として扱わない。需要モデルA/B/Cと異なる弾力性・情報伝播・離脱を持つresponse-model holdoutを用意し、各モデルの妥当性と政策順位の頑健性を公開する。人口個票を販売する前提は置かない。

### 独立した4トラック

1. **Prediction / calibration**: 介入しない状態と指定介入下で地域×期間×人口層ごとの需要、参加、負荷、outcome分布を予測。時間・自治体・人口層のholdout。Brier/log score、calibration curve、数値アウトカムのMAE/CRPS、区間coverage。介入下予測は観測データのsupportがある範囲と外挿を分ける。
2. **Intervention policy**: 凍結した状態観測・予算・能力制約から補助、施設時間、移動支援、アウトリーチ等を選ぶ。独立simulatorでpaired seedsによるbaseline比較。平均だけでなくpopulation-weighted outcome、最悪群、spillover、費用、制約違反を測定。エージェントが目的や採点式を書き換える権限は持たない。
3. **Execution**: 連絡、発注、予約、支給、監査をツールで遂行。重複支給、遅延、在庫、無効資格、障害、変更通知をhidden stateに含む。tool calls/clock/API cost/公共予算を別々に制限。観測取得にコストがある。結果はledgerと証跡で採点し、文章で「完了しました」と言っても加点しない。
4. **Real outcomes**: 外部組織の小規模pilotで事前登録した測定と対照群。行政判断に実装する前にshadow mode、無作為化clusterまたはstepped-wedge等で検証。主要アウトカム、安全停止、参加同意、個人情報、欠測、attrition、spilloverを記録。効果が無い/負の結果も公開。simulator高得点だけではこのトラック合格にならない。

政策選択能力と需要予測能力を混ぜない。予測が当たっても改善政策を実行できるとは限らず、良い政策でもツール実行に失敗すれば効果はない。各トラックに「数値統計ベースライン」「固定ルール」「人間担当者/専門家」「同じscaffoldの別モデル」「LLM無し」の比較を置く。

### 漏洩と作り込みで成功を埋め込まない

holdoutはseedだけでなく**自治体/単位、将来時間、ネットワーク構造、responseモデル、政策制度**の分離。trainで共有した隣接世帯や同一イベントがtestへ漏れないgroup split。公開dev environmentと非公開test scenariosを別にversion化する。評価用の住民応答モデルと評価対象の政策agentを同一モデルだけで構成しない。異なる応答モデルで政策順位が逆転したらその不確実性を結果に含める。

予算の支出、対象者への連絡、推奨行動への同意だけを「社会改善」と定義しない。参加率が上がってもwellbeingが悪化する、豊かな層にだけ利益が集中する、隣接地域へ負荷を押し出すケースを含む。公平性の基準と環境上限は前登録し、任意の合成スカラーひとつに隠さない。例えば所得/障害/年齢/地域でcoverageとoutcome差、最低群改善、格差拡大、CO2/電力水使用、予算超過を別列で報告。硬い禁止・予算制約を達成しないpolicyは点数が高くても不適格。

### 環境・ツール・報酬の提案プロトコル (既存APIの引用ではない)

```python
# Proposed interface, not executed.
class ImpactEnvironment:
    def reset(self, scenario_id: str, population_version: str, seed: int) -> Observation: ...
    def observe(self, actor_id: str, query: Query) -> Observation: ...
    def step(self, action: Action, idempotency_key: str) -> Receipt: ...
    def advance(self, duration: int) -> PublicEvents: ...

class HiddenEvaluator:
    def finalize(self, run_id: str) -> ImpactReport: ...
# Agent sees legal action schemas, observations, budget and objective.
# Agent does not see latent outcomes, response parameters, test identity or future shocks.
# Report fields: weighted_outcome_delta, subgroup_deltas, spillovers,
# resource_use, ecological_use, hard_constraint_violations,
# calibration, execution_failures, uncertainty, provenance.
```

terminal rewardを定義するなら、pre-registered baselineとの差に必要な費用・外部性を含め、post-period効果と不確実性を評価する。人間担当者の労働費用とagent推論費用を同じ経済ledgerに入れる一方、モデル能力の診断では個別にも公開する。hard constraintsは単なる小さな罰則ではなく不適格判定。報酬はpolicyモデルの応答生成promptに混ぜ込まず独立評価器に置く。学習利用する場合も「学習rewardの改善」と「外部holdoutのreal-impact」を区別する。

クラウド中立: environment/evaluator/agentはprocessまたはcontainer境界で分離可能。手元、GPUクラウド、API、private cloud、Ray clusterのいずれも選択肢。ローカル実行を必須にしない。安い数値simを先に大量反復し、LLMの社会挙動と現実pilotを必要部分に限定する。platformよりdata validity・policy identification・heldout protocolを先に固定する。

## 支払者と納品物の仮説

公開ベンチマークと受託成果物を分ける。「基盤モデル企業は必ず自社で作る」「必ず外部データを買う」のどちらも前提にしない。

| 候補支払者 | 具体的に買う価値/納品物 | 最初の商談で確かめること |
|---|---|---|
| 自治体/公益事業者の資源配分部門 | 既存施策との差、需要予測の校正、予算下policy比較、pilot計画、監査可能なdecision log | 誰が予算決裁し、いつ資源配分を変更できるか。改善の金銭/社会価値と調達可能性 |
| 公益財団/impact fund/研究助成 | 介入の事前評価、反証可能な仮説、独立比較、negative result込みの検証報告 | 査定・成果報告・実装のどこに困っており、独立評価に支払うか |
| 公共向けagentベンダー/SI | deployment前の失敗率、cost frontier、監督負荷、response-model shift、運用受入基準 | 失敗が契約/保険/導入拒否にどうつながるか、test integrationに予算があるか |
| Frontier model lab / safety institute | 非公開challenge set、再現可能な長期実行、行動trace、モデル比較、sim-to-real研究協力 | 自社evalの穴を埋めるか、独自データ権利/共有条件/実行費用の負担者は誰か |

成果物の最小単位は「version固定した評価環境、populationとresponseモデルの根拠、heldout protocol、baseline結果、failure taxonomy、費用/公平性/環境レポート」であり、単に大量の対話ログではない。ログ販売は権利・同意・有効性・買い手の検証が成立した場合だけの追加事業仮説。公開scorecardは信用形成に使えても、YC採択や売上の証拠にはならない。

## 残る不確実性

- Andonの現在の全創業者、初期の会社ピボット、YC採択理由、特別モデルアクセス契約、売上・単価・データ販売実績は確認できていない。
- VB全コード/非公開環境ライセンス、VB2需要パラメータの全仕様、公式費用計算と実費の差は未確認。
- AgentSocietyのcommercial除外フォルダと依存simulator・データの個別権利は導入時に確認が必要。Apache表示だけで全データ商用権を断定しない。
- ここで選んだ5件は研究/実装の参照先であり、そのまま導入する推奨ではない。マクロ因果同定の証拠は別の実データ/実験が必要。
