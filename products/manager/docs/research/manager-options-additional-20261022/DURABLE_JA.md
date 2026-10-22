# 新しい永続実行候補 — 2026-10-22

調査対象は Manager の既存 Python/SQLite worker を置換・補完し得る **DBOS、Restate、Inngest、Hatchet**。4件は公式文書と固定 SHA の実コードまで確認した。Windmill/Kestra は公式文書・license・release の浅い比較。LangGraph/Temporal/Railway 等は既調査のため新規件数に含めない。

**結論：DBOS＋SQLite を最初の比較対象にする。ただし E16 の前に cadence/lock だけを置換する根拠はまだない。** 現在の `run_owned_cycle()` は exact `LocalGitCycleSandbox` のみ許可し、production adapter は未実装。この権限境界を新 runtime が作ってくれるわけではない。今回 dependency・infra・実装は追加していない。

## 調査の新規性と限界

canonical checkout は `/workspace/manager-execution`、remote は `Daisuke134/life-manager`、読取基準 commit は `ae06f4ccfa30b29e427f71d6413eba0858a34cf8`。AGENTS.md/REVIEW.md、既存 dated reports/source registries、`owned_cycle.py`/`outbox.py`/`reconcile.py` と関連試験を読んだ。

開始時に `products/manager/docs/research` と `products/manager/research/imozuru` を `DBOS|Restate|Inngest|Hatchet|Windmill|Kestra` で検索し該当なし。**この inspected corpus に対して新規**であり、過去の全調査履歴や世間で初という主張ではない。

取得日 **2026-10-22 UTC**。公式文書は Firecrawl search → scrape（`maxAge:0`）、developer_search も使用。コードは独立 scratch clone で読取のみ。release の公開日、source commit 日、取得日は区別した。全14文書の短い引用・URL・scrape ID と全 selected code file の SHA-256 は同名 JSON に記録。第三者コードを実行・install していないため、以下の「確認」は source inspection であり crash test の実証ではない。

## 4候補の比較

| 候補 | 固定 source / Python / lifecycle | 直接再利用できるもの | 現在との差・制限 |
|---|---|---|---|
| **DBOS Python** | [e63ee714e031287c9b3447a173be835d6eaf1f95](https://github.com/dbos-inc/dbos-transact-py/tree/e63ee714e031287c9b3447a173be835d6eaf1f95)、commit 10/20、MIT、>=3.10。API metadata archived=false。latest release 3.3.0 公開10/15。source版は SCM dynamic で release と同一とは未確認 | `@DBOS.workflow`、`@DBOS.step`、sleep、queue。MIT notices を保ち upstream package として使う。内部 `_core` を複製しない | **別 workflow server なし・SQLite から試せる**のが最も追加的。公式は distributed SQLite 不可・production Postgres 推奨。serialization、version replay、footprint は未測定 |
| **Restate** | [Python SDK 37953b6f6fe50554aaea98b9d72f34e4da4d6256](https://github.com/restatedev/sdk-python/tree/37953b6f6fe50554aaea98b9d72f34e4da4d6256)、1.1.0、MIT、>=3.10、CPython/Rust extension。release10/21、archived=false | `ctx.run_typed`、RunOptions、durable service calls。runtime service は別運用 | backend service/objects の durable 通信向き。SDK MIT と server BSL1.1 は別。24h default retention を lifetime の効果鍵に置換できない |
| **Inngest** | [0c53b506108a12ebf0a83044a2db8641f128ba14](https://github.com/inngest/inngest-py/tree/0c53b506108a12ebf0a83044a2db8641f128ba14)、SDK0.5.19、Apache2、>=3.10。commit10/14、release6/23、archived=false | `step.run`、sleep/event wait、event-driven ingress。SDK upstream 使用 | Python は **stepごとrequest/replay**。新しい TS v4 same-handler checkpointing mode は未対応であり、durable step result 自体が無いという意味ではない。event/function dedup は24h・例外あり。server/Cloud が別に必要 |
| **Hatchet** | [2c2f73ff8c8bce320740cfc13e1d83bbe4cab5e6](https://github.com/hatchet-dev/hatchet/tree/2c2f73ff8c8bce320740cfc13e1d83bbe4cab5e6)、SDK1.42.1、MIT、>=3.10,<4。commit10/22、archived=false。repo latest release v0.110.5公開10/6はSDKとの検証済組合せではない | durable parent/child、sleep/event waits、Postgres engine。MIT upstream API | dynamic child work、長期waitでworker slot解放に向く。通常/child tasksはat-least-once、effectはidempotency要。API/engine/Postgres＋gRPC等SDK依存が増える |

Manager は >=3.11 なので4 SDKの **declared Python bounds** とは一致する。実インストール・依存解決・OS/wheel確認はしていない。[Manager metadata](https://github.com/Daisuke134/life-manager/blob/ae06f4ccfa30b29e427f71d6413eba0858a34cf8/products/manager/pyproject.toml)

### DBOS：最小の追加性、remote write の原子性は増えない

公式は default SQLite を明記し、複数 server では使えず production Postgres を推奨する。[database connections](https://docs.dbos.dev/python/tutorials/database-connection)

実装 `invoke_step()` は既存結果があれば replay し、無ければ **`func()` → serialize → `record_operation_result()`**。つまり remote成功直後・DB保存直前のcrash gapがある。`retries_allowed=False` は例外retryを止めても recovery時の未記録step再実行を原子的に止めない。[fixed core L2289](https://github.com/dbos-inc/dbos-transact-py/blob/e63ee714e031287c9b3447a173be835d6eaf1f95/dbos/_core.py#L2289) · [replay L2322](https://github.com/dbos-inc/dbos-transact-py/blob/e63ee714e031287c9b3447a173be835d6eaf1f95/dbos/_core.py#L2322)

result tableは workflow_uuid/function_id、owner tokenを確認して別DB transactionへ保存。SQLite engineは IMMEDIATE isolation、busy_timeout30000ms、foreign_keys ON。[result transaction](https://github.com/dbos-inc/dbos-transact-py/blob/e63ee714e031287c9b3447a173be835d6eaf1f95/dbos/_sys_db.py#L2777) · [SQLite implementation](https://github.com/dbos-inc/dbos-transact-py/blob/e63ee714e031287c9b3447a173be835d6eaf1f95/dbos/_sys_db_sqlite.py#L20)

DBOSのworkflow ID dedupは有用だが、Git occurrence と expected_parent の証明の代替ではない。[workflow docs](https://docs.dbos.dev/python/tutorials/workflow-tutorial)

### Restate：run の replay と server license を分ける

SDKは action完了後に `propose_run_completion_success`、TerminalError は確定failure、普通のExceptionはtransient failure/retry設定へ渡す。`run.replayed` ならactionを再scheduleしない。remote actionと journal の一括transactionは確認できない。[actual action/result order L850](https://github.com/restatedev/sdk-python/blob/37953b6f6fe50554aaea98b9d72f34e4da4d6256/python/restate/server_context.py#L850) · [replay decision L920](https://github.com/restatedev/sdk-python/blob/37953b6f6fe50554aaea98b9d72f34e4da4d6256/python/restate/server_context.py#L920)

公式 default idempotency retention は24h。new clusterの自動random ingress keyは同じin-flight requestのretryのみをまとめ、別request横断dedupではない。長いLLM呼出しは default inactivity timeout 1分にも注意。[configuration](https://docs.restate.dev/services/configuration) · [durable steps](https://docs.restate.dev/develop/python/durable-steps)

server v1.8.1の固定 licenseは **BSL1.1、releaseの4年後Apache2**。Additional Use Grant は自組織workflowのproduction利用を明示許可し、Public Restate Platform Service を制限。MIT SDKだけを見てserverもMITとしない。[server license 20efb1b83a39b8227451e531c366e067588ae9ee](https://github.com/restatedev/restate/blob/20efb1b83a39b8227451e531c366e067588ae9ee/LICENSE)

### Inngest：event型の別案、Pythonのcheckpoint modeとserver永続性を厳密に扱う

`StepSync._run` はsaved outputを返し、なければ handler実行・serialize後、`ResponseInterrupt(StepResponse)` でserverへ返す。named step hash＋reuse index が状態鍵となる。[actual step L194](https://github.com/inngest/inngest-py/blob/0c53b506108a12ebf0a83044a2db8641f128ba14/pkg/inngest/inngest/_internal/step_lib/step_sync.py#L194) · [step ID counter L112](https://github.com/inngest/inngest-py/blob/0c53b506108a12ebf0a83044a2db8641f128ba14/pkg/inngest/inngest/_internal/step_lib/base.py#L112)

公式自身が「remote成功→step result保存前failure→request再送」を警告する。24h dedupはoutboxの永久鍵ではない。[best practices](https://www.inngest.com/docs/durable-execution/best-practices) · [Python/TS mode差](https://www.inngest.com/docs/durable-execution/durable-workflows) · [idempotency](https://www.inngest.com/docs/durable-execution/guides-and-advanced/idempotency)

self-hostはSQLite＋**in-memory Redis queue/stateのperiodic snapshot**がdefaultであり、in-flight stateが毎回SQLite transactionへ記録されるという意味ではない。default SQLiteはsingle node。metadata/history用Postgresとqueue/state用Redisを分けて読む。[self-hosting](https://www.inngest.com/docs/self-hosting)

server固定 licenseは **SSPL1.0＋availabilityの3周年からApache2追加grant**。Python SDK Apache2と別。[server license 83a17957a7808fa797cefc85a3aea01a40f76e38](https://github.com/inngest/inngest/blob/83a17957a7808fa797cefc85a3aea01a40f76e38/LICENSE.md)

### Hatchet：durable parent の「exactly-once」とchildの再送を混同しない

公式 durable-task pageはwait/child spawnごとcheckpoint、parentはdeterministic、外部callはchildへ置くと明記。architecture pageはtask deliveryがat-least-onceと明記。前者のexactly-once文言を任意remote effectへ拡張できない。[durable tasks](https://docs.hatchet.run/v1/durable-tasks) · [architecture & guarantees](https://docs.hatchet.run/v1/architecture-and-guarantees)

SDKのwaitはlistener送信→ack node/branch→callback待ち、child spawnもdurable log ackでrun IDを得る。selected engine SQLは `FOR UPDATE` とinvocation count conflict updateを使う。[Python wait L849](https://github.com/hatchet-dev/hatchet/blob/2c2f73ff8c8bce320740cfc13e1d83bbe4cab5e6/sdks/python/hatchet_sdk/context/context.py#L849) · [spawn L1037](https://github.com/hatchet-dev/hatchet/blob/2c2f73ff8c8bce320740cfc13e1d83bbe4cab5e6/sdks/python/hatchet_sdk/context/context.py#L1037) · [actual SQL](https://github.com/hatchet-dev/hatchet/blob/2c2f73ff8c8bce320740cfc13e1d83bbe4cab5e6/pkg/repository/sqlcv1/durable_event_log.sql#L1)

## 浅い比較：別問題を解く候補も捨てずに区別する

- **Windmill**：Python/TS child-job replay、approval、sleep中worker解放。script versionがcheckpointと異なればresumeを拒否してrestart要求。人の承認を含むinternal workflow全体を置換するときは別案になる。[official workflows as code](https://www.windmill.dev/docs/core_concepts/workflows_as_code)  
  v1.846.1公開10/21、固定 `01084cd405ed930b340c729a73f904287b2e353e`。backend/frontend AGPL3＋enterprise proprietary、Python client/OpenFlow Apache2、配布Community binaryには非公開proprietary componentと追加条件がある。単にAGPLだけと記載しない。[fixed license](https://github.com/windmill-labs/windmill/blob/01084cd405ed930b340c729a73f904287b2e353e/LICENSE)
- **Kestra**：declarative platformが必要なら候補。task retryとwhole flowable block retryを明確に選べる。subflow retryは新executionを作るため effect_key をrun IDにすると危険。[official retries](https://kestra.io/docs/workflow-components/retries)  
  core Apache2、v2.0.7公開10/20、固定 `49b62a2c820d37e98a1c7b63aa35fd83f960d4ec`。[license](https://github.com/kestra-io/kestra/blob/49b62a2c820d37e98a1c7b63aa35fd83f960d4ec/LICENSE)

両者 archived=false をAPI metadataで確認。ただしactual execution code、Python bounds、dedup/persistenceは未監査。直接コード採用の推薦はしない。ここで借りるのはretry scope・version guardという契約だけ。

## Managerへの正確なpatch提案（実装していない）

1. **`owned_cycle.py:run_owned_cycle` から `dispatch_owned_once(state_store, host, packet, now) -> dict` を抽出。** fresh journal lookup→admission→reserve→guarded sendを既存owner_lock内で連続実行し、外へ返すのはkey/status/receiptだけ。既存 exact sandbox type gate を維持する。  
   **reserveをcheckpointし `OwnedEffectRecord(dispatch=True)` をcached resultにして、その次のretryable sendへ渡してはいけない。** 一度だけ有効だったpermissionがreplayで再利用される。checkpoint消失後は同じhelperを呼び、existing journalならsendせずreconcileへ進む。remoteとreserveは同一transactionではないので、reserve直後crashはUNKNOWNのままになる。この安全側のliveness損失をengine retryで埋めない。[current reserve](https://github.com/Daisuke134/life-manager/blob/ae06f4ccfa30b29e427f71d6413eba0858a34cf8/products/manager/manager_core/outbox.py#L148)
2. **`outbox.py:OwnedEffectJournal` に bounded `pending_records(limit=100) -> tuple[OwnedEffectRecord,...]`。** startup/再開では新candidate生成・cadence判定より先に、保存済packet＋original expected_parentでpendingを読取回復する。候補が変わっても未確定intentを捨てない。existing rowのdispatchは常にfalseの契約を保つ。engineの24h retentionでjournalを消さない。
3. **`reconcile.py:reconcile_owned` をruntimeの成功とは独立したread-only境界のまま再利用。** UNKNOWNにbounded backoff/new observationを設ける。cached UNKNOWNを永遠に返すstepにはしない。rollback前はtargetがexact candidateのままか確認し、別の正当なtargetへ進んだ場合に古いbytesへ戻さない。engineのcompleted statusではPRESENTへ閉じない。[current exact occurrence](https://github.com/Daisuke134/life-manager/blob/ae06f4ccfa30b29e427f71d6413eba0858a34cf8/products/manager/manager_core/reconcile.py#L44)
4. **既存 `tests/test_digital_cycle_acceptance.py` と `test_owned_effect_recovery.py` を共通failure matrixにする。** `test_owned_digital_cycle.py` のscope/platform authority否認とproduction host gateは維持する。新runtime導入前に同じmatrixをcurrent kernelへ、後にisolated DBOS SQLiteへ適用する。

必須assertionsは以下。すべてactual local Git fixtureで検査し、production証明と区別する。

- reserve直後・send前crash：再開でsendしない。UNKNOWNをabsence扱いしない。
- commit後response消失、engine checkpoint保存前kill：target advanceは1回、send attempt総数<=1、再起動後は同じSHA/parent/bodiesへreconcile、次replay writes=0。
- cached `dispatch=True` を注入しても二度目のsend permissionにならない。
- 24h超でengine dedupが切れてもjournal bindingは残り、同effectを再送しない。
- **reserve後backupへrestore**：backup後に完了したeffectを保存packet/parentでread-only回収、send=0。
- **reserve前backupへrestore**：missing journalを未送信の証明にしない。restore incidentとしてdispatchを止め、original intent bindingと公式occurrenceを回収。current HEADからoriginal expected_parentを捏造しない。外部monotonic anchor等がなければ古いbackupを自動検知できるとは主張できない。DBOS等のDB restoreも同じ制約。
- wrong occurrence/parent・欠測はUNKNOWNのまま、writes=null。active owner競合拒否。old workerの遅いsendはexpected_parent CASでtargetを進められない。

## 最初の比較と切替条件

**まずDBOS＋SQLiteに絞って、current cycleと同じoffline fixtureで、多段の中断再開・長期wait・checkpoint消失・backup restoreを比較する。** 比較pinは上記audited SHAであり、今回installしない。単純に毎分起こすだけの比較ではDBOSの利点を測れない。検査項目は無重複send、UNKNOWN保持、readbackの真正性、未完stageの回収、独自state行数、メモリ/起動時間/依存量。

**現状維持への最強の反論：** DBOSはrecovery/queue/sleepを既に持ち、Managerがそれを手書きし続ける方が保守コストと失敗面を増やす。既存cadenceはslotをwork前にcommitするもので、一般的なresumable workflowではない。「今のcodeがあるから不採用」は弱い理由。

**切替trigger：** 実際のE16 workloadに複数stageのresumeや長期待機が必要となり、cadence/journal fenceの外へ独自recovery stateが増え、上のmatrixでDBOSがその実装を減らしつつ権限・no-double-send・readbackを全て保持した場合。真のmulti-host要件ならDBOS SQLiteだけでは不足し、shared DB＋target fencingを別に実証する。Restateはdurable service間通信、Inngestはevent/serverless ingress、Hatchetはdistributed child workが主要件となった場合に比較順位が上がる。Railwayは既知host選択であり新runtime発見には数えない。



---
統合注記: このlaneは読取調査。repoへ収録した統合担当の文書変更と、未実施の実装/外部操作は別。[追加調査の判断](REPORT_JA.md)と[atomic patch plan](../../plans/2026-10-22-manager-e16-atomic-patches.md)を参照。
