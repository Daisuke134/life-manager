# ローカルLife ManagerとOpenClaw — コードからの判断

対象はOpenClaw公開tag v2026.9.8、commit fc23bc864e4553c2d215e479eeec47b67a0bf943。gh APIで対象sourceを取得し、現行LM sourceと比較した。速度や利益の推測をせず、分岐・保存・所有権・event recordを根拠にする。

## 結論

LM全体のharnessをOpenClaw cronへ全面置換する設計は採らない。Life Manager CLI、host admission、業務state、effect fence、公式readbackを保持し、OpenClawはエージェント実行・session管理・観測に利用する設計が適する。有限execの互換だけでは後者の全機能を活用できない。

この判断は「実測がないので何も判断できない」ではない。sourceから構造的な適合/不適合を判断した。実際の速度・RSS・task成功率だけはsourceの存在から定量値へ換算しない。

## 実読の結果

1. SQLite耐久化は双方に存在。OpenClaw `claimCronRunReceiptInDatabase` は同transactionでjob/configRevision/agentを照合し、running receiptにはstore/jobの部分UNIQUE制約がある。LM `resource_admission.py::_database`もFULL synchronousとBEGIN IMMEDIATEでqueue/reservation/occurrenceを持つ。永続化一般は新しい利点とは言えない。
2. OpenClaw `repairCronRunInDatabase` はreceipt ID/PID/process start/開始時刻を照合してから変更する。`restoreFinalizedStartupRun` は保存済みhistoryから結果・次回時刻・script stateを戻す。LMもPID/process start/claimを使う。OpenClawの完了履歴に基づくschedule状態復元は再利用できるが、「復旧が速い」は未計測。
3. OpenClaw `markInterruptedStartupRun` はstartup時だけ中断at jobを再候補化できる。`isRunnableJob`がstartupCatchupを扱う。内部historyが終わる前に外部送信が済んだ窓では、tool側のidempotencyなしに再実行安全を証明できない。LM `_durable_capacity` は未開始claimedのみqueueへ戻し、runningはeffect_unknownへ隔離、`resolve_unknown_occurrence`は同owner/occurrenceの公式receiptを要求する。この外部作用境界はLMが強い。
4. OpenClaw `trackCronRunReceiptSettlement` はtimeout/cancelが先に返ってもrunner Promiseのsettlementまでreceiptをrunningに保つ。commitが不明ならreceiptを残し復旧へ渡す。非同期実行の終結とDB terminal保存を分ける設計は明確で再利用価値がある。LMもchild PIDへのclaim移管とheartbeatを持つため、唯一の安全機構と扱わない。
5. OpenClaw cronのservice-local active/FIFO容量はこのtagで8。direct waiter優先とcatchup staggerはあるが、複数Gateway全体の共有枠ではない。LMはdurable queue、resource class、revenue floor、priority aging、owner reservationを既に持つ。収益/browser枠をOpenClaw cronへ置き換える根拠はない。
6. `createToolAndSystemRecorders` はtool.started/completed/error/blockedを扱い、run属性・親trace・duration・errorCodeをspanに記録する。`createModelRecorders` はmodel/provider/transport、duration、request/response size、time-to-first-byte等を記録する。`contextForTrustedTraceContext` はtrusted traceだけをparentへ結ぶ。LM共有runnerはattempt/summary/usageを持つが、このmodule内にはOTelのtool/model span pipelineがない。共通の内部観測を再利用できる具体的な差。
7. OpenClaw restart recoveryはsession/run一致を確認してclaim/cleanupを保存し、復旧owner leaseを扱う。LM runnerのCodex経路はresumeが指定されないとephemeral、指定されたresume経路もある。OpenClawの利点は既存providerのresumeが無かったことではなく、agent/session/recoveryを共通contractへ統一できること。業務checkpointや決済receiptの代替ではない。

## 設計への反映

CLIはLife Managerのまま。LM scheduler→host admission→OpenClaw agent/session execution→既存業務tool→LM effect/readback→収支の順。単一推奨はLife Manager専用のローカルGatewayとdiagnostics-otel。agent --localもOTel対応の候補だが、sessionを共通管理する最終接続にはGatewayを選ぶ。最初のtool-less有限execはschema等の互換検証としてのみ使う。OpenClaw cronは業務のschedule authorityにしない。

sourceで判定した設計適合はPASS（部分利用）。全面置換は不採用。実接続のcontract/claim lifetime/tool scopeは実装前acceptanceが必要。本番切替は未実施。40pair/20%閾値は性能比較の旧提案で、構造選定の前提やユーザーに要求する作業にはしない。

## 根拠

- [cron receipt claim](https://github.com/openclaw/openclaw/blob/fc23bc864e4553c2d215e479eeec47b67a0bf943/src/cron/store/run-receipt-store.ts)
- [restart recovery](https://github.com/openclaw/openclaw/blob/fc23bc864e4553c2d215e479eeec47b67a0bf943/src/cron/store/run-recovery.kernel.ts)
- [startup repair](https://github.com/openclaw/openclaw/blob/fc23bc864e4553c2d215e479eeec47b67a0bf943/src/cron/service/startup-run-repair.ts)
- [runnable jobs](https://github.com/openclaw/openclaw/blob/fc23bc864e4553c2d215e479eeec47b67a0bf943/src/cron/service/timer-runnable.ts)
- [settlement](https://github.com/openclaw/openclaw/blob/fc23bc864e4553c2d215e479eeec47b67a0bf943/src/cron/store/run-receipt-settlement.ts)
- [cron capacity](https://github.com/openclaw/openclaw/blob/fc23bc864e4553c2d215e479eeec47b67a0bf943/src/cron/service/run-admission-capacity.ts)
- [cron limits](https://github.com/openclaw/openclaw/blob/fc23bc864e4553c2d215e479eeec47b67a0bf943/src/config/cron-limits.ts)
- [tool spans](https://github.com/openclaw/openclaw/blob/fc23bc864e4553c2d215e479eeec47b67a0bf943/extensions/diagnostics-otel/src/service-recorders-tools.ts)
- [model spans](https://github.com/openclaw/openclaw/blob/fc23bc864e4553c2d215e479eeec47b67a0bf943/extensions/diagnostics-otel/src/service-recorders-model.ts)
- [trusted trace context](https://github.com/openclaw/openclaw/blob/fc23bc864e4553c2d215e479eeec47b67a0bf943/extensions/diagnostics-otel/src/service-trace-context.ts)
- [session recovery claim](https://github.com/openclaw/openclaw/blob/fc23bc864e4553c2d215e479eeec47b67a0bf943/src/agents/agent-command-restart-recovery.ts)
- [recovery owner lease](https://github.com/openclaw/openclaw/blob/fc23bc864e4553c2d215e479eeec47b67a0bf943/src/agents/agent-command-recovery-owner.ts)

LM比較: `runtime/host/resource_admission.py`、`runtime/loop/lm_loop_run.py`、`runtime/agent-runner/agent_runner.py::command_for/run_provider_process`。source/state/provider変更0。
