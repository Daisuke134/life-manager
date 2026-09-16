# 調査の出典・検証範囲

この資料は一次資料とLife Managerのread-only実測のみを使用する。外部資料の閲覧時点は2026-09-17 JST。性能値をベンチマークとして推定していない。

| 出典 | 版・調べた箇所 | 確認した内容 | 限界 |
|---|---|---|---|
| [OpenClaw公式repo](https://github.com/openclaw/openclaw/tree/6f08e4ea3c560d456f4ae1a02b0ca275bd24936e) | HEAD `6f08e4ea3c560d456f4ae1a02b0ca275bd24936e`; `src/cron/service/timer-scheduler.ts`, `run-admission-capacity.ts`, `src/config/cron-limits.ts`, `src/infra/heartbeat-runner-scheduler.ts`, `docs/cli/cron.md`, `docs/automation/cron-jobs/schedules.md`, `docs/gateway/heartbeat.md` | Gatewayのcron scheduling経路、shared SQLite state database、現行固定8 active、capacity release recheck、stagger、heartbeat busy guard | 10,000 jobのMac mini benchmarkは示されていない。主にコード／仕様であり本番負荷試験ではない。 |
| [OpenAI Symphony公式repo](https://github.com/openai/symphony/tree/e0ccc83720a42a600a53b61c5f8d3e518bebe1db) | pinned `e0ccc83720a42a600a53b61c5f8d3e518bebe1db`; `elixir/lib/symphony_elixir/orchestrator.ex` | poll・reconcile・global/state/host slot・worker-down retry | pinned snapshotでありOpenClawと同一のproduct要件ではない。 |
| [Temporal公式docs](https://docs.temporal.io/schedule), [Task Queue](https://docs.temporal.io/task-queue) | schedule overlap、jitter、catch-up、worker polling | 時刻と実行容量の分離 | 分散Temporal Serviceの設計。単一Macの性能値ではない。 |
| [Kubernetes公式CronJob docs](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/) | concurrencyPolicy、missed schedule、idempotency | cronだけではexactly-onceやhost capacityを保証しない | cluster/pod前提。 |
| [BullMQ公式docs](https://docs.bullmq.io/guide/workers/concurrency), [global concurrency](https://docs.bullmq.io/guide/queues/global-concurrency) | worker/queue concurrency | 有限枠は一般的 | Node/Redis queueの仕様、Life Manager実測ではない。 |
| [Browserless公式repo](https://github.com/browserless/browserless/tree/450ec681481a1ee7bce2a4e5fe7c2ce3f939a0d7) | pinned `450ec681481a1ee7bce2a4e5fe7c2ce3f939a0d7`; `src/config.ts`, `src/limiter.ts` | 既定10 concurrent/10 queued、timeout/health | browser session service、cronではない。 |
| [Apple launchd設定ガイド](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html)・ホストの`launchd.plist(5)` | StartInterval/StartCalendarInterval | triggerの契約と実行中miss | OS local manualの実測はこのMac上の版。 |
| Life Manager local source/state | `apps/life-manager/config/product-loop-catalog.json`, `config/loop-registry.json`, `runtime/loop/lm_loop_apply.py`, `lm_loop_run.py`, `runtime/host/resource_admission.py`; read-only `lm-loop status all`＋v2 SQLite集計 | 14 product行/96 job、registry interval分布、5 total既定、queue ageとlive status | 点時刻のsnapshot。statusのpassは公式effect proofではなく、主selectorに内側/外側report混同の既知履歴あり。 |

“Grokboard”相当の製品・repoは名前だけから公式一次資料を特定できなかったため、推測を資料へ混ぜていない。
