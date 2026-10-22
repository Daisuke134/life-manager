# 既存の個人・能動・長期agent製品を先に使う：新規7候補の一次調査
調査日 2026-10-22。Manager baseline: `ae06f4ccfa30b29e427f71d6413eba0858a34cf8`。読取専用。実装、account connect、trial開始、インストール、上流コード実行、送信、課金、配備は行っていない。

## 判断を変える結論

「会話を覚え、指定時刻や外部eventで動き、既存アプリを操作するpersonal agent」は既存製品で既に提供されている。最初の選択肢は **OpenClaw / Khojをそのまま使う、またはGumloop / Relevance AI / Lindyでnative agentを作る** こと。定型的な取得・通知・承認・更新なら **n8n / Activepieces** の既存workflowが代替になる。Managerが独自の一般agent、memory、scheduler、connector catalogを再実装する理由は、この調査からは出てこない。

Managerを残す仮説は「任意のagentができること」ではなく、**所有対象を限定した変更に対し、authority・予算・同一effect・独立readback・UNKNOWN隔離・rollback・実際の結果を一つの検査可能な記録に接続すると、既存製品単体より何が改善するか**。この追加価値がnative製品の比較で出なければ、Managerを外して既存製品を使う選択を維持する。これは調査からの設計判断であり、顧客需要・収益・人の便益が証明されたという意味ではない。

新規性の確認として、Managerのresearch・presentations・現行product specに `OpenClaw|Khoj|n8n|Activepieces|Lindy|RelevanceAI|Relevance AI|Gumloop|Pipedream|Trigger.dev|Inngest` をexact-name検索し、既存hitはなかった。過去にユーザーが名前を見たことがないとは主張しない。LangGraph/Temporal/Letta/OpenHands/Simile/Aaru/Radiant/Inspect/Railwayの再深掘りはしていない。

## 1. 幅を先に比較する

| 新規候補 | 既に解いている利用問題 / 実際の仕組み | Managerをどう扱うか | 今回の証拠の深さ |
|---|---|---|---|
| **OpenClaw** | 自分の環境で動くpersonal agent。現在の公式名称はAutomationsで、旧 `cron` はalias。Gatewayの永続schedule、event起動、run history/recovery、workspace memory、tool policyを持つ。 | personal assistant自体なら直接利用。Managerとの接続はnative schedule/CLI/APIを先に確認し、別の一般agent層を作らない。 | official runtime/security + immutable code 5領域、license。 |
| **Khoj** | 自分のdocuments/webを調べ、scheduled queryをメールで届けるsecond brain。DjangoJobStore/APSchedulerとuserごとのautomation。 | 定期調査・newsletters・知識assistantなら直接利用。高頻度監視・bounded publishing engineとは適合が異なる。 | official automation docs + scheduler/locks/routes/ownership/code。 |
| **n8n** | trigger→取得→判定→承認→tool実行をvisual workflow化。queue mode、DB待機、AI tool approval。current sourceにdurable schedule occurrenceとdedup key。 | 監視・既存API連携はnative workflowをbaselineに。Managerの差分が独立readback等に限られる時だけ薄く接続。 | official queue/approval + scheduler/wait/recovery/credential/memory/license。 |
| **Activepieces** | piecesによる統合、durable flow replay、waitpoint、project-bound connection。 | CE flowをnative baselineに。Managerをstep再試行の対象にする場合もeffect keyとreconcileを別管理。 | official durability + engine/checkpoint/waitpoint/connection/license。 |
| **Gumloop** | scheduled/one-shot/app/webhook trigger、agent自身のschedule管理、MCP/API channel、tool単位・条件付きapproval、task history。 | agent-builderそのものが目的なら直接利用。既存MCP/APIを接続し、同じtrigger/approval UIを自作しない。 | official agent/trigger/approvalを実読。backendコード未公開/未確認。 |
| **Relevance AI** | Workforceのintegration/webhook/recurring trigger、toolごとのAutopilot/HITL。 | business appsのagent workforceならnative利用を先に比較。全trigger停止とmanual task停止は異なる。 | official schedule/approval全文。backend recovery未確認。 |
| **Lindy** | routines、既存app/MCP接続、編集可能なfile memory、write/send approvalを掲げる業務assistant。 | email/calendar/Slack中心なら直接利用候補。marketing demoをManager実績にしない。 | 現行公式homepage feature/FAQ。runtime/rollback契約は未確認。 |

一次出典: [OpenClaw runtime](https://docs.openclaw.ai/automation/cron-jobs/how-it-works)、[Khoj automations](https://docs.khoj.dev/features/automations/)、[n8n queue](https://docs.n8n.io/hosting/scaling/queue-mode/)、[n8n tool review](https://docs.n8n.io/build/integrate-ai/ai-examples/human-in-the-loop-for-tools)、[Activepieces durability](https://www.activepieces.com/docs/install/architecture/durable-execution)、[Gumloop triggers](https://docs.gumloop.com/core-concepts/agent_triggers)、[Relevance AI triggers](https://relevanceai.com/docs/build/workforces/build-an-ai-workforce/add-triggers)、[Lindy](https://www.lindy.ai/)。

「提供されている」は公式契約と公開実装に基づく。稼働率、retention、売上、ユーザー便益を独立測定したものではない。star数、会社logo、vendor comparison、marketing画面の成功率を採否の根拠にしていない。

## 2. Deep inspection A — OpenClaw：personal agentの直接代替

**読んだ版:** [`fe2aa4a6c4443545b14a53c17c0b7e038d6111d5`](https://github.com/openclaw/openclaw/tree/fe2aa4a6c4443545b14a53c17c0b7e038d6111d5)、commit 2026-10-22。package.jsonは2026.10.5。GitHub公開metadataではarchived=false、latest releaseは別の `v2026.10.6`（2026-10-22 12:53 UTC）。したがって、default branchの静的読取と特定releaseの本番動作を同一視しない。[MIT](https://github.com/openclaw/openclaw/blob/fe2aa4a6c4443545b14a53c17c0b7e038d6111d5/LICENSE)。

公式runtimeはGateway内scheduler、job/runtime/historyの共有SQLite永続を明記する。restartでterminal resultが残っていれば**同じrun identity**に照合して復元し、payloadやdeliveryを再実行しない。terminal記録がなければinterrupted+delivery Unknown。限定されたtime-scheduled agent-turnは一回のfresh retryがあり、その際に以前の作業を照合させる。**任意の途中tool副作用がexactly-onceになる保証はない** と明記されている。command/script、delivery開始の可能性、失われたmanual/event payloadは同じ再試行条件ではない。[runtime/reconciliation](https://docs.openclaw.ai/automation/cron-jobs/how-it-works)。

コードもその区別を持つ。`recoverCronRuns` はstate workerで復旧を行い、job stateを反映した後にnotificationを分離する。`recoverCronJobInDatabase` はreceipt/run identityで既存terminalを探し、復元不能ならfailed+unknownを記録する。再試行候補はscheduled receiptで、`deliveryNotStarted === true`、現在の `configRevision` 一致、schedule変更なし等を要求する。これは単なるcronを付けただけの実装よりManagerの問題に近い。[run-recovery.ts](https://github.com/openclaw/openclaw/blob/fe2aa4a6c4443545b14a53c17c0b7e038d6111d5/src/cron/service/run-recovery.ts)、[run-recovery.kernel.ts](https://github.com/openclaw/openclaw/blob/fe2aa4a6c4443545b14a53c17c0b7e038d6111d5/src/cron/store/run-recovery.kernel.ts)。

権限もpayloadと別に扱う。`resolveCronRequesterExecutionRevision` と `reconcileCronOperatorSource` は実行対象が変わったjobに前のcreator authorityを無条件で借用させない。[jobs-tool-policy.ts](https://github.com/openclaw/openclaw/blob/fe2aa4a6c4443545b14a53c17c0b7e038d6111d5/src/cron/service/jobs-tool-policy.ts)。ただし、**one Gateway = one operator trust boundary**。互いに信用しないtenantの分離用製品ではない。公式trust modelはunsandboxed agentのGateway-wide session visibility、既定agent-to-agent access、trusted operatorのhost exec `full / ask off` を説明し、敵対tenantには別gateway/OS user/hostを求める。[trust model](https://docs.openclaw.ai/gateway/security/trust-model)。単に「memory分離があるからmulti-tenant安全」と説明してはいけない。

memoryはworkspaceのdaily notes/curated MEMORY.md等とper-agent runtime DB。公式workspace guideはMEMORY.mdをprivate main sessionでのみloadする指針を持つ。これはprovenance/rightsを検証するManagerのworld stateと同一ではない。[workspace guide](https://github.com/openclaw/openclaw/blob/fe2aa4a6c4443545b14a53c17c0b7e038d6111d5/docs/concepts/agent-workspace.md)。

**採否:** 個人のassistant・reminder・定期調査・既存tool操作を求める部分は最も直接的な既存代替。Managerへscheduler/memoryを移植するより、OpenClawをそのまま選ぶ比較が先。Managerが必要なら、公開情報の観測/提案だけを受け、scope発行・publisher・予算・receipt readbackを既存の特権境界に残す。

**限界:** 上流regressionのidentity test setupも読んだが実行していない。公式が「terminalを復元」と書くことと、選んだdeploymentが実障害時に成功したことは別。OpenClaw単体でManagerの7-path publication、P3/P4人の便益評価まで済むと認定しない。

## 3. Deep inspection B — Khoj：定期researchは既存productで済む

**読んだ版:** [`ae229ca894c0b80ad84664afcfdde523b5e87057`](https://github.com/khoj-ai/khoj/tree/ae229ca894c0b80ad84664afcfdde523b5e87057)、commit 2026-08-02 UTC。archived=falseだが最後のpushも8月2日で、他候補ほど直近の保守ではない。latest published release tagは `2.0.0-beta.28`（2026-03-26）。[AGPL-3.0](https://github.com/khoj-ai/khoj/blob/ae229ca894c0b80ad84664afcfdde523b5e87057/LICENSE)。network提供の改変版へ組み込む場合の義務を別途確認する。

公式automationは「指定時刻・頻度でquery実行→researchをemailで届ける」と具体的。self-hostではResendとauthentication setupが必要。local LLMで動かせることと、automation配信までexternal accountなしで完結することを混同しない。[official automations](https://docs.khoj.dev/features/automations/)。

実装は `main.py` のBackgroundScheduler+DjangoJobStore、misfire_grace_time=60秒、coalesce=true。schedule leaderはDB process lockで一つを選び、別workerはpausedで起動する。`max_duration_in_seconds=43200` が設定される。followupで `configure.py:wakeup_scheduler` も読み、17分ごとにlock有効性を調べ、期限切れなら再選出/resumeすることを確認した。killされたleaderの有効lockが残ると、期限までtakeoverが遅れ得る。迅速なfailoverを仮定しない。[wakeup_scheduler](https://github.com/khoj-ai/khoj/blob/ae229ca894c0b80ad84664afcfdde523b5e87057/src/khoj/configure.py)。[main.py](https://github.com/khoj-ai/khoj/blob/ae229ca894c0b80ad84664afcfdde523b5e87057/src/khoj/main.py)。

`schedule_automation` はquery+cron由来のid、user UUID prefix、CronTrigger、jitter=60秒、process lock付きjobを登録。`scheduled_chat` は直近6時間のrunを抑制し、userのBearer tokenでchat endpointをPOSTする。非200ではerror log後returnする。**lock成功/関数return/HTTP受付と、メール到達や外部副作用成功を同じsuccessにしてはいけない**。今回の範囲には外部操作のstable occurrence receiptやunknown送信のreconcile契約は見当たらない。[helpers.py](https://github.com/khoj-ai/khoj/blob/ae229ca894c0b80ad84664afcfdde523b5e87057/src/khoj/routers/helpers.py)、[locks/automation adapters](https://github.com/khoj-ai/khoj/blob/ae229ca894c0b80ad84664afcfdde523b5e87057/src/khoj/database/adapters/__init__.py)。

routesはauthenticated scope、adaptersはautomation idのuser prefixを検査する。API createはminute-level recurrenceを拒否するため、毎分監視の代替としてそのまま選べない。Conversation/Entryにはuser外部キーがあるが、全credential encryptionや全queryのtenant隔離を監査したわけではない。[api_automation.py](https://github.com/khoj-ai/khoj/blob/ae229ca894c0b80ad84664afcfdde523b5e87057/src/khoj/routers/api_automation.py)、[models](https://github.com/khoj-ai/khoj/blob/ae229ca894c0b80ad84664afcfdde523b5e87057/src/khoj/database/models/__init__.py)。

**採否:** 自分用の文書知識・news research・定期mailが欲しいならManagerを作る必要がない候補。厳密なpublish復旧を必要とする場合も、Khoj schedulerを汎用engineとして改造するより、その用途に合う既成workflowを比較する。

## 4. Deep inspection C — n8n：一般workflowを作り直さない

**読んだ版:** [`0bfa56336e0676655f4a34d11285752c22022ab2`](https://github.com/n8n-io/n8n/tree/0bfa56336e0676655f4a34d11285752c22022ab2)、2026-10-22。checkout packageは2.45.0、latest release metadataは `n8n@2.44.6`（同日09:21 UTC）。archived=false。**Sustainable Use License** はpersonal/noncommercial/internal businessに許諾範囲を限定し、EE部分を除外する。MIT/制約なしOSSとして再販・embedded SaaSに組み込む判断をしない。[LICENSE.md](https://github.com/n8n-io/n8n/blob/0bfa56336e0676655f4a34d11285752c22022ab2/LICENSE.md)。

official queue modeはmainがtimer/webhookを受け、Redisをbroker、DBを永続化、workerが実行する構造。distributed SQLiteは非対応、複数processで同じencryption keyを用いる。multi-main等はEnterpriseの境界がある。これをManagerの単一SQLite workerへ導入するだけで運用が軽くなるとは限らない。[queue docs](https://docs.n8n.io/hosting/scaling/queue-mode/)。

current codeでは `ScheduleTriggerJobRegistrar` が同一definitionのjob rowを保ち、`(jobId, scheduledFor)` でoccurrence identityを安定化。`ScheduleTriggerTaskHandler` はdeduplicationKeyを実行へ渡す。durable schedulerはcurrent configでenabled=trueだが、workflow publication serviceも有効な時にSchedule Triggerをtake overする。したがって「どのn8n版/設定でも永続schedule」とは書かない。[registrar](https://github.com/n8n-io/n8n/blob/0bfa56336e0676655f4a34d11285752c22022ab2/packages/cli/src/scheduling/schedule-trigger-node/schedule-trigger-job-registrar.ts)、[handler](https://github.com/n8n-io/n8n/blob/0bfa56336e0676655f4a34d11285752c22022ab2/packages/cli/src/scheduling/schedule-trigger-node/schedule-trigger-task-handler.ts)、[scheduler config](https://github.com/n8n-io/n8n/blob/0bfa56336e0676655f4a34d11285752c22022ab2/packages/@n8n/config/src/configs/scheduler.config.ts)。

`WaitTracker` はDBから待機実行を拾い、再開時に `status === waiting`、`expectedStatus: waiting`、publisher acting user再構成を使う。`ExecutionRecoveryService` はevent logsからcrashed stateを修復し、既にterminalのrecordを上書きしない。**crashed stateの正確な再構成は、外部APIが一度だけ実行されたという証明ではない**。[wait-tracker](https://github.com/n8n-io/n8n/blob/0bfa56336e0676655f4a34d11285752c22022ab2/packages/cli/src/wait-tracker.ts)、[recovery](https://github.com/n8n-io/n8n/blob/0bfa56336e0676655f4a34d11285752c22022ab2/packages/cli/src/executions/execution-recovery.service.ts)。

tool approvalは既存featureであり、正確なtool名/parametersを人に見せpauseする。Managerが同様のapproval builderを作る根拠にはならない。[approval docs](https://docs.n8n.io/build/integrate-ai/ai-examples/human-in-the-loop-for-tools)。credential serviceはworkflow/projectで利用可能なcredentialを絞る。AI Simple Memory nodeはinstance-localでqueue/multi-main非互換と明記するので、分散後もそのmemoryが残ると想定しない。[credential service](https://github.com/n8n-io/n8n/blob/0bfa56336e0676655f4a34d11285752c22022ab2/packages/cli/src/credentials/credentials.service.ts)、[Simple Memory](https://github.com/n8n-io/n8n/blob/0bfa56336e0676655f4a34d11285752c22022ab2/packages/@n8n/nodes-langchain/nodes/memory/MemoryBufferWindow/MemoryBufferWindow.node.ts)。

**採否:** source取得、link/情報差分、定型API、notify/approvalのbaselineとして強い。AIが不要な部分はnative deterministic nodesで足りる。scheduler刷新そのものをManager進捗にしない。使う場合はreleaseを固定し、external effect idempotency/UNKNOWN/readbackを別検証する。

## 5. Deep inspection D — Activepieces：durabilityの限界まで読む

**読んだ版:** [`635e1661a2ff9ccde3a3496de51ef459dfe098e0`](https://github.com/activepieces/activepieces/tree/635e1661a2ff9ccde3a3496de51ef459dfe098e0)、2026-10-22。checkout packageは0.92.2、latest release metadataは0.92.3（10月12日）。archived=false。root LICENSEはMIT本体と `packages/ee` / `packages/server/api/src/app/ee` 等の商用除外を分ける。agent製品全体/全依存を一括MITと扱わない。worker内の `ee` という文字だけでもlicenseを決めず、root条文と個別依存を照合する。[root license](https://github.com/activepieces/activepieces/blob/635e1661a2ff9ccde3a3496de51ef459dfe098e0/LICENSE)、[Enterprise license](https://github.com/activepieces/activepieces/blob/635e1661a2ff9ccde3a3496de51ef459dfe098e0/packages/ee/LICENSE)。

公式のdurable executionはrun log、15秒ごとのsnapshot、terminal/pause時flush、saved completed stepをskipするreplay。waitpointがresumeをqueueする。[official](https://www.activepieces.com/docs/install/architecture/durable-execution)。実装の `waitpointService.createForPause` はDB insertをorIgnoreし、**生成し直したidではなくpersist済waitpoint.id** を使ってdelay jobを再scheduleする。`handleResumeSignal` はproject/run/waitpointを束縛し、pessimistic lockとterminal/stale排除を持つ。callback-before-workerのraceを含む既存回帰テストも公開されている。[waitpoint service](https://github.com/activepieces/activepieces/blob/635e1661a2ff9ccde3a3496de51ef459dfe098e0/packages/server/api/src/app/waitpoints/waitpoint-service.ts)、[tests](https://github.com/activepieces/activepieces/blob/635e1661a2ff9ccde3a3496de51ef459dfe098e0/packages/server/api/test/integration/ce/flows/flow-run/waitpoint.test.ts)。

**採否を変える注意:** 公式は「crashで失うのはその時runningだった単一step」と書くが、今回のstatic codeではその強さを確認できない。`flowRunProgressReporter.sendUpdate` はlive runでRAMのlatestUpdateParamsを更新するだけで、`backup` が15秒loopでZSTD fileをuploadする。`flow-executor` は各step後の永続backupをawaitせず、`pieceAction.run` の実効果の後でSUCCEEDEDをRAMに記録する。terminal/exceptionでは `flow.operation` がbackupする。**hard killがperiodic flush前なら、複数の完了済みだが未persistのstepがreplay対象になり得る** という静的推論が残る。これは再現試験済みbugではない。少なくとも「外部副作用はsingle-step以外絶対重複しない」を採用根拠にしない。[progress reporter](https://github.com/activepieces/activepieces/blob/635e1661a2ff9ccde3a3496de51ef459dfe098e0/packages/server/engine/src/lib/helper/flow-run-progress-reporter.ts)、[flow executor](https://github.com/activepieces/activepieces/blob/635e1661a2ff9ccde3a3496de51ef459dfe098e0/packages/server/engine/src/lib/handler/flow-executor.ts)、[piece executor](https://github.com/activepieces/activepieces/blob/635e1661a2ff9ccde3a3496de51ef459dfe098e0/packages/server/engine/src/lib/handler/piece-executor.ts)、[final flush](https://github.com/activepieces/activepieces/blob/635e1661a2ff9ccde3a3496de51ef459dfe098e0/packages/server/engine/src/lib/operations/flow.operation.ts)。

credential helperにAES-256-CBC、worker connection routeにengine principalのprojectId/platform bindingがある。ただしworkerは実行時に解決済secretを受け取る。保存暗号化、step再試行、tool権限、external actionの同一性は別のboundary。[encryption](https://github.com/activepieces/activepieces/blob/635e1661a2ff9ccde3a3496de51ef459dfe098e0/packages/server/api/src/app/helper/encryption.ts)、[worker connection](https://github.com/activepieces/activepieces/blob/635e1661a2ff9ccde3a3496de51ef459dfe098e0/packages/server/api/src/app/app-connection/app-connection-worker-controller.ts)。

**採否:** MIT CEのconnector/flowを使う候補として有用。retryされても安全なreads、provider-supported idempotency、別のexact effect journal/readbackがあるstepから使う。Agent run codeにapproval heartbeat/retryがあることだけで、flowとagent全体が同じdurability契約とは認定しない。

## 6. SaaSの具体的な代替と接続境界

**Gumloop:** 今回最もManagerの「薄い既存tool接続」を具体化できる新候補。agentにAPI/SDKと**MCP server channel**が既にあり、native triggersとtask historyもある。作るならそれを使う。agent自身のschedule管理、one-shot、app trigger、source account selection、Brain knowledge、subagentも既存機能。tool approvalにはAsk each time/Write-delete等と条件付きCELがあり、approval cardは実argumentsを示す。[agents](https://docs.gumloop.com/core-concepts/agents)、[HITL](https://docs.gumloop.com/core-concepts/human_in_the_loop)。

Gumloop webhook URLは**URL自体がcredential**で、header/API key不要。知っている人は起動できる。100req/min per trigger、rejected callsも計上する。agentがwebhookを作成/変更する時はapproval、AI Managedは無効化できる。これを一般公開の無認証Manager endpointと誤認しない。trigger deactivateは自主起動を止めるが、agent retire用 `is_active:false` と同じではない。[triggers](https://docs.gumloop.com/core-concepts/agent_triggers)。incognitoも全データ消去ではなく、creator/usage/operational records等が残ると公式が区別する。[agents privacy section](https://docs.gumloop.com/core-concepts/agents)。

**Relevance AI:** scheduled Workforce、integration/webhook trigger、toolごとのAutopilot/HITLを既に提供。cronはUnix5-fieldではなく**AWS EventBridge6-field**。pause all integrated triggersでもmanual user messageは生きる。この停止意味をManagerのglobal stop/revocationと同じにしない。[triggers](https://relevanceai.com/docs/build/workforces/build-an-ai-workforce/add-triggers)、[approval](https://relevanceai.com/docs/build/agents/give-your-agent-tasks/approval-mode)。

**Lindy:** 現行公式page/FAQはroutine、編集可能file memory、MCP、write/send approval、usage capsを示す。定期assistant需要ならnative製品で満たし得る。ただし「Nothing irreversible happens without your approval」というvendor表現は、backend idempotency/kill後recovery/外部receipt契約の証明ではない。掲載のCAC低下例、ticket成功例、customer logoはUI例/marketingとして読み、独立した効果・売上に数えない。[Lindy](https://www.lindy.ai/)。

3社とも今回の範囲でbackendのcrash/effect reconciliation、全credential境界、公式billingと実費の一致を実験していない。利用料・account接続・契約条件を必要とするため、read-only比較以上に進めていない。

## 7. Managerの実ファイルに戻した最小patch判断

以下は**提案**で、変更済みではない。現行interfaceを読み、存在しないAPIを接続済みと書かない。

| 現行の実装点 | 新しい先例から具体的に変える/守ること | 次の実証 |
|---|---|---|
| `manager_core/owned_cycle.py: CycleStore.due / owner_lock / run_owned_cycle` | 既存のsingle-host flock、current-slot catch-up once、journalは再実装しない。`run_owned_cycle` はexact `LocalGitCycleSandbox` 以外を `DEPLOYMENT_HOST_REQUIRED` にする。n8n/OpenClawのscheduleを付けてもproductionにならない。live host adapterを別工程で実装する場合だけ、このguardと元publisher境界を保った設計を作る。 | natural restart、missed slots、concurrent owner、stop、unknown effectの実ホストcanary。外部schedulerと既存ownerの二重起動をしない。 |
| `scripts/run_owned_digital_cycle.py: main` | 現在はread-only deployment preflight。n8n/ActivepiecesへこのCLIを登録して「継続運用済み」にしない。native製品で問題が済むならManager CLI自体を使わない。 | 選んだnative workflowと手作業baselineで同じ監視タスクを比較。 |
| `manager_core/outbox.py: OwnedEffectJournal.reserve` / `reconcile.reconcile_owned` | provider/schedulerのtask successをeffect successに代入しない。stable effect_key、packet bytes、expected_parent、DISPATCHING→exact reconcileを保持する。Activepiecesのreplay/step retryでもsame effect_keyはsendを再発行せずreconcileする。 | kill-before-send / accepted-but-response-lost / failed checkpoint / stale callback / duplicate tickでofficial occurrenceとreplay-zero。 |
| `digital_handoff.prepare_owned_change`、`scripts/phase06_kernel_release.admit_owned/admit` | OpenClawのexecutable revision bindingを先例に、scheduled proposalのsource/context/scope/artifactは実行直前に再検証。Gumloop approvalやn8n tool approvalをGitHub workflow identity/standing scopeの代用にしない。 | payload変更、scope expiry/revoke、source freshness、target-parent移動で送信ゼロ。 |
| `public_observer.fetch_snapshot` | 外部productは「再観測するwake/候補」を渡すだけ。managerは既存のallowlisted public URLから独立にbytes/hash/freshnessを取得する。webhook本文・agent要約をofficial sourceとして格上げしない。 | altered summary、wrong URL、private destination、missing source bytesでNO_ACTION。 |
| `kernel.review_public_advice` / `prepare_owned_change` | 既存toolのmodel出力は既存P0提案の入口だけ。別framework向けの新しいauthority issuerやmemory engineは作らない。Gumloop MCPを選んでも、既存typed context/verificationを満たさなければ観測用adapterまで。 | 同じinputのrule/manual/native workflowとの差、false positives/実手戻り/費用。 |

コード参照: [owned_cycle](https://github.com/Daisuke134/life-manager/blob/ae06f4ccfa30b29e427f71d6413eba0858a34cf8/products/manager/manager_core/owned_cycle.py)、[preflight CLI](https://github.com/Daisuke134/life-manager/blob/ae06f4ccfa30b29e427f71d6413eba0858a34cf8/products/manager/scripts/run_owned_digital_cycle.py)、[outbox](https://github.com/Daisuke134/life-manager/blob/ae06f4ccfa30b29e427f71d6413eba0858a34cf8/products/manager/manager_core/outbox.py)、[handoff](https://github.com/Daisuke134/life-manager/blob/ae06f4ccfa30b29e427f71d6413eba0858a34cf8/products/manager/manager_core/digital_handoff.py)、[publisher](https://github.com/Daisuke134/life-manager/blob/ae06f4ccfa30b29e427f71d6413eba0858a34cf8/products/manager/scripts/phase06_kernel_release.py)、[observer](https://github.com/Daisuke134/life-manager/blob/ae06f4ccfa30b29e427f71d6413eba0858a34cf8/products/manager/manager_core/public_observer.py)、[kernel](https://github.com/Daisuke134/life-manager/blob/ae06f4ccfa30b29e427f71d6413eba0858a34cf8/products/manager/manager_core/kernel.py)。

## 8. 次に選ぶ有限の比較

1. **personal assistantが最優先なら** OpenClaw/Khojのnative設定で同じ定期researchを評価する。Managerの新memory/scheduler実装はしない。
2. **チームのapps作業なら** Gumloop/RelevanceAI/Lindyのnative agentが代替。まずnative task/history/approvalで満たせるかを判定し、不足した証拠境界だけをManagerへ接続する。今回account接続/paid trialは行っていない。
3. **owned public page監視なら** deterministicなn8n/Activepieces flowと既存手作業/link-check baselineを先に置く。Agentを使わなくても同等ならそれを採る。
4. **Managerを続けるなら** 実装順序を崩さず、実ホストで同一bounded changeのcanary、official commit occurrence、独立GET、restart/replay-zero/rollback、通常人手と費用を記録する。「新しいengine採用」を成果に数えない。

この調査で分かったのは、既存の動く製品と読み取れる実装上の違い。まだ分からないのは本人の実workflowでの継続利用、比較対象より減る作業/失敗、実支払意思/純利益、人への効果。これらにGitHub活動やvendor宣伝の数値を代入しない。

## 証拠・読取限界

全53 source record、read_depth、support、limits、immutable file URLは[AGENT_PRODUCTS_SOURCES.json](AGENT_PRODUCTS_SOURCES.json)に保存。official page captureは `/workspace/scratch/new-agent-products-captures/`。GitHub metadataは `/workspace/scratch/new-agent-products-github-metadata.json`。公開APIの取得時刻は2026-10-22 13:51 UTC頃。web pageはpublication dateが明記されない場合nullにし、取得日を発表日として扱わない。

四つのcloneは `/workspace/scratch/new-agent-products-{openclaw,khoj-ai,n8n-io,activepieces}`。参照と静的検索のみ。upstream testsは読取に留め、実行/合格を主張しない。今回の証拠はprimary vendor docs/codeであり、独立した稼働率・売上・便益のstudyを得たという報告ではない。



---
統合注記: このlaneは読取調査。repoへ収録した統合担当の文書変更と、未実施の実装/外部操作は別。[追加調査の判断](REPORT_JA.md)と[atomic patch plan](../../plans/2026-10-22-manager-e16-atomic-patches.md)を参照。
