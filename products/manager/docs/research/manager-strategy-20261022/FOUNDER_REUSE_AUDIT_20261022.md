# Manager — 既存の成功例・実装をどこまで再利用するか

**調査日:** 2026-10-22 UTC。**範囲:** 8系統の直接的な先行例、永続実行・記憶・coding・評価・人間行動シミュレーション。読み取り調査のみ。Managerの状態台帳ではない。

**結論:** 現在の単一Python worker＋永続SQLite/outboxをE16まで接続する方針を保つ。ただし「汎用agent基盤を自作して完成させる」という計画にはしない。既存の効果journal・権限・Git CAS・独立readbackはManager固有の境界として残し、複雑なgraph、分散workflow、agent memory、coding sandbox、eval runnerを必要に応じて既成品へ委譲する。

**重要な新知見:** Lettaの旧V1 API serverは現行公式READMEでretiredとされ、active sourceは `letta-ai/letta-code`。検索で返る `v1-sdk` のDB永続memory説明を、新規導入の現行architectureと混ぜない。Railwayのvolumeはreplicaと併用できず、volume付きserviceのredeployには短時間停止がある。どちらも「有名OSSだから最新仕様も同じ」という判断を避ける実例である。[Letta lifecycle](https://github.com/letta-ai/letta) · [Railway volume caveats](https://docs.railway.com/volumes/reference)

## 1. 何を成功の証拠とみなしたか

公開された製品、公式契約、実コードinterface、ライセンス、著者の実運用研究があることを先行例の根拠とした。星数、企業logo、自社benchmark、資金調達を独立した便益・売上・顧客継続の証拠にはしていない。8系統すべての売上や利益は本調査では未検証。Managerの需要・支払意思・P3/P4便益は依然未知である。

既存の [REPORT_JA](REPORT_JA.md)、[PRIMARY_SOURCES](PRIMARY_SOURCES.json)、[UPSTREAM_CODE_AUDIT](../evals/UPSTREAM_CODE_AUDIT_20261022.md) の同日証拠を再利用した。Simile/Aaru/Radiant/Inspectはこの台帳の読取深度を継承し、今回あらためて全文を読んだことにはしない。新規の公式docs・repo・metadata・selected code・論文passageは以下に分けて記録した。取得には同日cacheも含まれ、全ページをlive強制再取得したものではない。

## 2. Component → upstream → Managerが書く薄い接続

| 成分／先行例 | 読んだ版・license | 再利用するところ／薄い接続 | 判断と未確認事項 |
|---|---|---|---|
| **Agent graph: LangGraph** | 公式Python persistence/checkpointers。mainのpyprojectは1.2.16、Python>=3.10、MIT。docsはcommit `94296a63c145368eb42ddd78a36189dc1459b079`でも確認 | graph stateのcheckpointとcross-thread Storeを分離。採用時はManagerのcandidate/NO_ACTION/評価をnodeへ包み、effect boundaryは既存outbox adapterへ渡す | **今すぐ交換しない。** 単純cycleにgraph runtimeを足す利益が未実証。分岐・反復・途中再開が繰り返し必要になったら第一候補。mainのpackage版は観測値でimmutable install pin未確定。推測したrelease tagは404であり採用pinにしない |
| **Distributed durable workflow: Temporal** | 公式Python error-handlingと既存idempotency記事。sdk-python main metadata 1.34.0、Python>=3.10、MIT | durable task queue/timer/retryの必要時に採用。既存の `effect_key` とreconcileをActivityに薄く包む | **今すぐ交換しない。** 複数host・長期timer・worker failoverが要件になれば再評価。Activityはat-least-onceであり任意remote effectのexactly-onceを付与しない。server/Cloud運用・費用・Manager移行試験は未調査 |
| **Persistent agent memory: Letta / MemGPT** | 現行letta-code 0.34.20、commit `c25f091d0fce1f032e5cdf67ce131d5b474e6576`、Apache-2.0。現行memory/MemFS docs。MemGPT論文v2（2024-02-12）passages | 時間をまたぐ助言agentが必要ならmemory filesystem/context管理を再利用。Managerはsource ID・観測時点・有効範囲・失効を付けた証拠viewだけ渡す | **optional adviserに限定。** MemFSはGit-backedでlocal editはcommit/pushまで他環境へ共有されない。記憶の事実性・権限・exact external outcomeは別。旧V1 serverを新規導入せず、agentの自己編集memoryを予算/権限SSOTにしない |
| **Coding/task agent: OpenHands SDK** | v1.57.0のLICENSE/pyproject/`conversation/event_store.py`/`state.py`。MIT、Python>=3.12。SDK論文v2、MLSys 2026表示 | Agent/Tool/Workspace/Server、会話events、persist/restore、Docker等の隔離workspaceを再利用。Managerは限定作業票→隔離repo差分→検査結果を受け取り既存publisherへつなぐ | **codingが必要な時だけ隔離adapter。** Manager core>=3.11へ直入れせず別process/environmentを選ぶ。自由shellを本番owner/秘密/公開権限へ直結しない。SDK内のevent保存はprovider receiptや人の便益ではない |
| **Evaluation runner: Inspect AI** | 既存台帳: 0.3.283、commit `c2fc3d9e3ff3fdc389be2933c6e3f9824648876e`、MIT、Python>=3.11。別の既存auditはscorer/metricの固定commitを読取 | Task/Solver/Scorer/log/limitsを再利用。Managerが書くのはown task input、採点意味、P0-P5 mapping、独立holdoutと失敗分類 | **競合runnerを作らない。** Inspectのsample cost_limitはManager全体の永続予約やsettled請求の代用ではない。既存imports/実行済みと仮定しない |
| **Behavior simulation: Simile** | 公式homepageと2026-08-25 confidence記事（既存同日台帳）。hosted proprietary、公開model/code license未確認 | 自社の「自信」を出すだけでなくquestion-level errorを予測し、母集団・用途・時点・coverageごとに校正。真正な参照がある時だけ同じManager taskでprovider比較 | **任意の予測adapter候補。** weekly validation/顧客名/精度はvendor claim。自社threshold TVD 0.16をManagerの成功基準に輸入しない。商用価格、API契約、利用可能性は未確認 |
| **Behavior simulation: Aaru** | 2026-09-24技術report（既存同日台帳）。hosted proprietary、公開model/code license未確認 | observedとsampling-adjusted errorを別記録。pre-fieldwork retrieval cutoff、study単位split、univariateとjoint/individual coherenceを分ける | **任意adapter候補。** 2,993問・186 studies等はvendor報告。r=0.970を97% accuracyと呼ばない。Simileとの異なるdatasetのAUROC比較を勝敗にしない |
| **Behavior simulation: Artificial Societies / Radiant** | vendor method/eval・AS Benchmark v2・connector README/LICENSE（既存同日台帳）。connector MIT、README blob `0b6681b9593cc43395658979e79fffe1817b085d` | 公開benchmarkを評価項目の参考にし、正規の利用条件と予算が成立した場合だけ既成remote MCP/OAuth connectorをadapterとして使う | **同一企業/製品を二重計上しない。** MIT wrapperはhosted simulation/dataへの無償利用権ではない。22toolsのうち実行系は費用を発生。今回接続・認証・実行なし |

直接source: [LangGraph](https://docs.langchain.com/oss/python/langgraph/checkpointers) · [Temporal](https://docs.temporal.io/develop/python/best-practices/error-handling) · [Letta current source](https://github.com/letta-ai/letta-code) · [OpenHands SDK](https://github.com/OpenHands/software-agent-sdk/tree/v1.57.0) · [Inspect Task pin](https://raw.githubusercontent.com/UKGovernmentBEIS/inspect_ai/c2fc3d9e3ff3fdc389be2933c6e3f9824648876e/src/inspect_ai/_eval/task/task.py) · [Simile](https://www.simile.com/blog/confidence) · [Aaru](https://aaru.com/publications/population-simulation-at-the-replication-floor-research) · [Radiant](https://github.com/artificial-societies/radiant-claude-plugin)

## 3. Railway＋volume＋単一Python workerは妥当か

**v0.1の限定運用には妥当、可用性の最終設計としては未確定。** 現実のvolume・owner・publisher・readbackをつなぐことが現在の仕事であり、framework導入自体はE16の完了条件を満たさない。

| 選択肢 | 得るもの | 残る責任と選択条件 |
|---|---|---|
| 現worker＋SQLite＋Railway volume | 既存outbox/予算/packet bindingを最小変更で永続化。実際のloopをまず運用できる | local flockとSQLiteを支えるfilesystem挙動、restart、backup/restore、起動時reconcile、停止時間を実hostで検証。serviceごとvolume一つ、replica不可、redeployで短時間停止。これは許容する運用特性として記述する |
| 同worker＋外部Postgres | workerのhostから状態を切り離し、後の並列/複数hostへ備えやすい | ただDBを移してもsingle-writer/fencing/外部UNKNOWNは解けない。複数owner/可用性要件と運用費が立つまでmigrationを先行させない |
| LangGraph＋persistent checkpointer | 分岐・checkpoint・途中再開を手書きする量を減らす | checkpointerとStoreは別。採用時はdurabilityを明示し、RAM saverを本番永続化としない。`sync`はcheckpoint保存時点の保証で外部作用の一回性ではない。既存effect journalは残る |
| Temporal＋Python worker | 複数worker・durable timer・service起点の再試行/履歴を既成runtimeへ委譲 | 管理service/Cloudを加える運用・費用。Activity retry前提のidempotency/reconcileは必要。分散処理が実要件になった時の優先候補 |
| 常時VPS/既存owner host | 現contractを再利用しやすいhost adapter | host保守・復旧・監視責任は増える。既存Life Manager ownerと混同/共有しない。単にcronを置くだけではdeployment evidenceにならない |
| 一時CIだけ | reproducible build/evalに適する | 実行host/state/ownerの永続性を満たさず、現在のE16の代替にはしない |

Railway公式の短い支持箇所は `Replicas cannot be used with volumes` と `there will be a small amount of downtime when re-deploying a service that has a volume attached`。volumeはbuild/predeploy時にはmountされず、runtimeのstart時にmountされる。[volume reference](https://docs.railway.com/volumes/reference) · [using volumes](https://docs.railway.com/guides/volumes)

**現在codeの良い境界:** `OwnedEffectJournal.reserve()` はSQLite `BEGIN IMMEDIATE`でeffect key/packet/expected parentを固定して送信前commit。`reconcile_owned()`は同じoccurrenceのcommit/parent/bodyを照合し、欠測をUNKNOWNに残す。`CycleStore.owner_lock()`はcycle全体をlocal `flock`で囲み、Git CASでtargetを固定する。これをLangGraph/Temporalの採用で捨てない。[outbox.py:141](https://github.com/Daisuke134/life-manager/blob/3391f6a5237681ad1166ebaadb38597db1d0c9e6/products/manager/manager_core/outbox.py#L141) · [reconcile.py:44](https://github.com/Daisuke134/life-manager/blob/3391f6a5237681ad1166ebaadb38597db1d0c9e6/products/manager/manager_core/reconcile.py#L44) · [owned_cycle.py:34](https://github.com/Daisuke134/life-manager/blob/3391f6a5237681ad1166ebaadb38597db1d0c9e6/products/manager/manager_core/owned_cycle.py#L34)

**本番前に閉じる具体的gap:** `run_owned_cycle()` はexact `LocalGitCycleSandbox`のみ受け入れ、現時点の本番adapterではない。また `due()` はcycle開始前にschedule slotをcommitする。新prepare後の現在keyだけをreconcileする経路なので、slot予約直後crashの扱いと、候補やsource/scopeが変わった後も旧UNKNOWNを拾う独立drainの保証を確認する必要がある。コード読取所見であり、不具合を実行再現した主張ではない。少なくとも「due直後・reserve直後・send成功応答消失・readback前」のcrash-point検査と、再送しない未解決intent照合を本番接続の受入へ置く。[owned_cycle.py:56](https://github.com/Daisuke134/life-manager/blob/3391f6a5237681ad1166ebaadb38597db1d0c9e6/products/manager/manager_core/owned_cycle.py#L56) · [owned_cycle.py:152](https://github.com/Daisuke134/life-manager/blob/3391f6a5237681ad1166ebaadb38597db1d0c9e6/products/manager/manager_core/owned_cycle.py#L152)

## 4. 論文から持ち帰る実装判断

**MemGPT v2:** main context、archival/recall storage、functionによるmemory移動を扱う。会話taskではbaselineは過去5会話のlossy summary、MemGPTは完全履歴をpaginated recall検索する。document QAでは同じretrieverを比較し、archival memoryにPostgres/pgvectorを使ったと記載。この研究はcontext managementの根拠であり、永続scheduler・外部作用の一回性・福祉効果の証明ではない。現行Lettaのarchitectureを2024年論文の実装と同一視しない。[MemGPT v2](https://arxiv.org/abs/2310.08560v2)

**OpenHands SDK v2:** §4.2のimmutable events、`ConversationState`、metadata snapshot＋event log、§5.2の433会話/39,870 eventsのoverhead、Discussionのmulti-tenant security audit未実施とLLM-based security analyzerの限界を読んだ。15日比較のsystem-attributable failure 61%減は著者のproduction観測で、Managerで再現した結果でも無作為化比較でもない。v2本文の一般的な「recovery under 20ms」とtableの最大32.1msは異なる集計で、最悪値を20msと断定しない。[SDK paper v2](https://arxiv.org/html/2511.03690v2)

**シミュレーション先行研究:** 既存台帳で読んだThe Illusion of Intervention、Validating LLM simulations as behavioral evidence、AS Benchmark等の意味を維持する。人間データのないもっともらしい予測はP0。商用providerの高い分布一致も、Managerの介入効果や人の生活改善の証拠には昇格しない。[intervention paper](https://arxiv.org/html/2605.20767v1) · [validation paper](https://arxiv.org/html/2602.15785v1) · [AS benchmark](https://arxiv.org/html/2609.30030v2)

## 5. 証拠表：support、read depth、未知

全行の読取/取得日は2026-10-22。英語の引用はその資料に現れる短い文字列。既存資料行の支持は台帳の要旨であり今回の原文新規読了を意味しない。

| ID / source | 支持する短い記述・箇所 | 読んだ範囲／限界 |
|---|---|---|
| R01 [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) | “Checkpointers”はsingle threadのgraph state、“Stores”はcross-thread application data | 新規page全文取得、両者の表・RAM saver・production注記を読取。旧durable-execution URLはここへredirectした |
| R02 [LangGraph checkpointers fixed docs](https://github.com/langchain-ai/docs/blob/94296a63c145368eb42ddd78a36189dc1459b079/src/oss/langgraph/checkpointers.mdx) | “sync”は次stepの前にcheckpoint保存。“exit”はmid-execution process crashから復元不可 | 新規公式pageと固定docs sourceのdurability/pending-writes節。external exactly-onceは主張しない |
| R03 [LangGraph metadata](https://raw.githubusercontent.com/langchain-ai/langgraph/main/libs/langgraph/pyproject.toml) / [LICENSE](https://raw.githubusercontent.com/langchain-ai/langgraph/main/LICENSE) | `version = "1.2.16"`、`requires-python = ">=3.10"`、MIT | 新規metadata/license読取。main可変、immutable code pin未取得 |
| R04 [Temporal Python errors](https://docs.temporal.io/develop/python/best-practices/error-handling) / [durable timers](https://docs.temporal.io/develop/python/workflows/timers) | “Activities follow an at-least-once execution model.”、serverへ通知する前にworker crashするとretry。timerはworker/service停止をまたいで永続化 | 新規2pages取得。idempotency/error分類/retry/compensationとtimerのpersist/resume節読取。実行なし |
| R05 [Temporal metadata](https://raw.githubusercontent.com/temporalio/sdk-python/main/pyproject.toml) / [LICENSE](https://raw.githubusercontent.com/temporalio/sdk-python/main/LICENSE) | 1.34.0、Python>=3.10、MIT | 新規metadata/license読取、main可変。Temporal server/Cloud全契約の監査ではない |
| R06 [Letta historical source](https://raw.githubusercontent.com/letta-ai/letta/main/README.md) | “retired Letta V1 API server”、active projectsはcurrent sourceへ | 新規README全文。v1-sdk検索結果と現行sourceの世代差を発見 |
| R07 [Letta current metadata](https://raw.githubusercontent.com/letta-ai/letta-code/c25f091d0fce1f032e5cdf67ce131d5b474e6576/package.json) / [fixed LICENSE](https://raw.githubusercontent.com/letta-ai/letta-code/c25f091d0fce1f032e5cdf67ce131d5b474e6576/LICENSE) | `@letta-ai/letta-code` 0.34.20、Apache 2.0 | 新規repo README/package/license読取。現在表示commitを固定。runtime未実行 |
| R08 [Letta MemFS](https://docs.letta.com/concepts/memfs) / [memory](https://docs.letta.com/configuration/memory) | “Edits are local until committed and pushed” | 新規公式page取得・memory/MemFSのprojection/同期を読取。cloud plan条件はコードlicenseとは別 |
| R09 [MemGPT v2](https://arxiv.org/abs/2310.08560v2) | “main context and external context (the archival and recall storage databases)” | paper index canonical metadata＋本文4passages。§2 memory/§3会話とdocument QA条件。全論文読了ではない |
| R10 [OpenHands SDK metadata](https://raw.githubusercontent.com/OpenHands/software-agent-sdk/v1.57.0/openhands-sdk/pyproject.toml) / [LICENSE](https://raw.githubusercontent.com/OpenHands/software-agent-sdk/v1.57.0/LICENSE) | 1.57.0、Python>=3.12、MIT | 新規fixed file全文取得・metadata/license読取 |
| R11 [OpenHands event_store.py](https://github.com/OpenHands/software-agent-sdk/blob/v1.57.0/openhands-sdk/openhands/sdk/conversation/event_store.py) | `append()`: “Append an event with locking for thread/process safety.” / duplicate event IDをreject | 新規375行取得。append/write/marker更新の実コードを選択読取。FileStore各backendや全concurrency挙動は未監査 |
| R12 [OpenHands state.py](https://github.com/OpenHands/software-agent-sdk/blob/v1.57.0/openhands-sdk/openhands/sdk/conversation/state.py) | `append_event()`、`_save_base_state()`、`create()`、`__setattr__()` | 新規777行取得、event chokepoint/base snapshot/auto-persistを選択読取。全コード読了/benchmark再現ではない |
| R13 [OpenHands persistence guide](https://docs.openhands.dev/sdk/guides/convo-persistence) | `persistence_dir`＋same `conversation_id`で保存/復元 | 新規guide取得、保存/復元API例読取。会話stateとworkspace/external stateを混同しない |
| R14 [OpenHands SDK paper v2](https://arxiv.org/html/2511.03690v2) | immutable events、4-package architecture、multi-tenant security auditはfuture work | canonical metadata＋本文4passages。MLSys 2026表記。著者のproduction観測・限定taskで外的妥当性は未確認 |
| R15 [Inspect Task pin](https://raw.githubusercontent.com/UKGovernmentBEIS/inspect_ai/c2fc3d9e3ff3fdc389be2933c6e3f9824648876e/src/inspect_ai/_eval/task/task.py) | Task/Scorer/log/limits、checkpoint callback idempotency | 既存同日台帳systems-S01とupstream code auditを再利用。今回runner未実行 |
| R16 [Simile confidence](https://www.simile.com/blog/confidence) | question-level error predictor、study/sampleをまとめたfold、confidence cutoff | 既存simulation-BS06の本文method読取を継承。raw data/code未監査、vendor claim |
| R17 [Aaru research](https://aaru.com/publications/population-simulation-at-the-replication-floor-research) | univariate answer-shareを評価、observed/adjusted error、retrieval cutoff | 既存simulation-BS07のsummary/research読取を継承。joint/row-level coherence未提示、独立追試未確認 |
| R18 [Radiant connector](https://github.com/artificial-societies/radiant-claude-plugin) / [method](https://societies.ai/knowledge/what-are-artificial-societies) | remote MCP/OAuth、read-onlyとrunを区別、serviceとMIT wrapperを区別 | 既存simulation-BS01/BS04のREADME/LICENSEとmethod読取を継承。connection未実施 |
| R19 [Railway volume reference](https://docs.railway.com/volumes/reference) / [guide](https://docs.railway.com/guides/volumes) | single volume/service、replicas不可、redeploy downtime、runtime mount | 新規公式2pages全文取得。実際のManager service/plan/volume/バックアップ設定は読取確認していない |
| R20 [Manager owned cycle](https://github.com/Daisuke134/life-manager/blob/3391f6a5237681ad1166ebaadb38597db1d0c9e6/products/manager/manager_core/owned_cycle.py#L152) | exact sandbox host型、本番未接続、due slotと現在keyの処理順 | ローカルcode読取を独立subagentと本laneで照合。実行テスト/本番観測なし |

## 6. 仕様へ反映すべき3つの決定

1. **Reuse registerを設計に入れる。** 成分ごとに採用/比較/見送り、source、実版、license、既存機能、Managerで追加する薄い接続、残る未知を表にする。現kernelを完成させつつ、独自の汎用workflow/memory/coding/eval製品を増やさない。
2. **E16の主眼を「永続hostへ接続＋crash/reconcile実証」に固定する。** Railwayを使うならreplica不可と再deploy停止を受入条件に明記。slot予約前後とUNKNOWNの回収を検査する。複数host/HAが実要件になった時は既存kernelのeffect boundaryを保持してTemporal/DBへ移す。分岐graphだけが増えた場合はLangGraphが先。
3. **シミュレーションは買える/接続できる候補から比較し、真の成果と商売を先に検証する。** 独自population modelの学習やpersona factoryを先行させず、実顧客問題・運用差分・原価・独立readback・真正な利用結果を集める。YC/記事/本/キャリア資料は同じ再現可能な結果と失敗から派生させる。販売実績・便益・公開を未実施のまま「達成」にしない。

## 7. いま作らないもの／未知の閉じ方

- 独自汎用agent OS、SDK、checkpoint engine、vector DB、memory filesystem、simulation foundation model、eval runner。
- 最初の利用者がいない段階のmulti-tenant SaaS control plane・multi-region HA・多数agentのscheduler。
- シミュレーションの一致率から算出する「福祉総点」「実売上」「自律利益」。論文のhistorical rewardや仮想残高を現金収益としない。
- memory自己書換えから権限/予算を書き換える経路、任意shellから本番publisherへ直通する経路。
- Universal exactly-onceの宣言。対象APIのidempotency/CAS契約がない時はUNKNOWN隔離と独立照合を保持する。

**未解決:** 実hostのfilesystem/backup復旧、現在のstanding scopeとowner、production publisher/collector、上記crash検査、顧客需要、paid利用の単位原価、simulation API価格・契約・task適合、framework導入後の性能/保守差分。これらは文献調査で埋まらない。具体的なhost readback、限定canary、実問題インタビュー、同じtaskでの比較が必要。

**調査手続:** Firecrawl deep-research/read-docs/use-railway、公式search/developer search/scrape、paper metadata＋passage読取を使用。search feedbackは6件に送信を試み、後2件はaccepted、初期4件は120秒の受付windowを過ぎてrejected。feedback目的の再検索は行わなかった。新規package install、モデル試行、商用simulation接続、infra変更、記事公開、YC応募、連絡は実施していない。外部に対する作用は調査取得とその品質feedbackのみ。


---
統合注記: このlaneは読取調査として実施し、報告を製品repoへ収録した。現行状態・改稿結果は [統合更新](FOUNDER_EXECUTION_UPDATE_JA.md) と既存task台帳を参照。
