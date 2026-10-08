# ローカルLife Managerの同時実行と容量制約

## 現在の答え

全体は8finite枠。loaded revenue floor3なのでborrowは最大5。これとは別に初期観測はrunning claim5＋reservation3＝occupied8。queue80。5は全体上限ではなく、実行中5という観測とborrow5というpolicyが偶然同じ数だった。後続snapshotは予約2へ変化。全claimのPID/start/heartbeatは妥当で、staleを消せば解決するという証拠はない。

class別はborrow agent1、browser1、borrow deterministic2、revenue deterministic3。CFOはborrow deterministicで、revenue deterministic2が走るだけでもclass判定2<2が偽。総枠だけの空きは起動許可ではない。source _capacity_availableの仕様どおりであり、故障と同一ではない。

## 構造上の問題

runtime/loop/lm_loop_run.py::_run_admittedはchild command全体が終わるまでclaimをheartbeatし、finallyでreleaseする。モデル計算だけを限定する枠ではない。paid-direct26:41、fundraiser16:24の占有、Capafy bash+sleepを確認。待機するprocessもslotを持ち続けるので、軽い確認や他の仕事が遅れる構造はある。実際のCodex/model call5同時という意味ではない。

unknown effect fenceを持つqueued ownerは後続24、eligible queue63。別のsnapshot/集合なので数を足し合わせない。全capacity待ちをエラーや重複claimと扱わない。provider leaseは同pathを直列化するが、global shared leaseの証拠はなくMercor子launcherだけ局所leaseを確認した。

## 今日の物理制約

RAM16GiB/CPU10。df availableは調査中約3GiBから1.9853GiBへ変化した。loaded3releaseのdisk floorは現在2GiBで、旧11GiBではない。後半の値はfloor未満。限定latest event集計でdisk_low29owner。memory理由0はこの範囲だけで、ホスト全体RAMに余裕がある証明ではない。slot増加、別Gateway、Temporal/Redisの新設でこのdisk gateを迂回しない。

## OpenClawだけで解決するか

公開latest tag v2026.9.8を確認。src/config/cron-limits.tsとrun-admission-capacity.tsはcron concurrent8を直接使う。長い業務commandをそのままcronへ移すと8枠問題が再現する。

一方src/config/agent-limits.tsはtop-level agentsの既定をmax(8,CPU parallelism*4)、subagent concurrency8/direct children5とする。今の端末ならtop default40になるが、cron8・host admission8・ChatGPT account quota・browser locksとは別の上限。40を安全値として推奨しない。現在のLMが40動くという意味でもない。

## 推奨アーキテクチャ

OpenClawはnative Codex agent harnessとして維持。長期workflowは「モデル判断」「browser操作」「API確認」「build/render」「外部待機」を分け、実際に処理する短いstepだけworker/slotを使う。待機は永続化してcomputeを解放するが、注文/intent/effect fenceは維持する。生きているCodex runのclaimを勝手に解放しない。

補完OSSの単一推奨はTemporal。OpenClaw/CodexはActivityの実行側、Temporalはdurable business workflow/timers/signalsとworker task queues。モデル・browser・軽いreadback・buildのqueueを分け、ChatGPT account制限/同profile排他/CPU-RAM/diskを別に管理する。model/provider I/Oはworkflow replay codeに入れずActivitiesへ置き、Activity retryでも既存official readback/idempotency guardを通す。OpenClaw cronは短いworkflow start/signalだけにして、全業務終了を待たせない。

今日は新serverを追加する段階ではない。disk headroomを回復し、capacity/running/reserved/effect-fencedの観測を分け、長時間slotの実phaseを明示してから同じ業務をstepへ移す。固定8を32へ変えるだけは推奨しない。上限が同じ8でも待機が枠を占有しなければ全商品の進行は改善し得るが、処理量/収益倍率は未測定。

## 外部比較

| 基盤 | source/docsで確認した機能 | 判断 |
|---|---|---|
| OpenClaw | native Codex/session/trace、cron8、CPU-based top agent limit | agent harnessとして採用継続。long workflowの単純command移管だけでは混雑解消しない |
| Temporal | durable timers、Workflow/Activity別slots、CPU/RAM resource-based tuner、multiworker queues、server MIT | 長期待機と別queueの補完に第一推奨。service/DB運用とdisk確保が必要 |
| BullMQ | Redis-backed queue、全workersを跨ぐqueue global concurrency、server-independent Node workers、MIT | 軽いjob queueなら有力。長期business履歴/再開はTemporalが適する |
| Restate | durable steps、workflow wait suspension、keyed state/concurrency | 軽いdurable runtimeとして有力。serverはBSL1.1でOSI OSSではない、SDKライセンスと分ける |

調査はDuckDuckGo HTML/scrapy、公式docs crwl、GitHub gh/rawで実施。商用価格やnative account quota、他hostの実性能は確認していない。

根拠: [OpenClaw cron](https://github.com/openclaw/openclaw/blob/v2026.9.8/src/config/cron-limits.ts)、[agent limits](https://github.com/openclaw/openclaw/blob/v2026.9.8/src/config/agent-limits.ts)、[Temporal worker性能](https://docs.temporal.io/develop/worker-performance)、[durable timers](https://docs.temporal.io/develop/typescript/workflows/timers)、[TS tuner source](https://github.com/temporalio/sdk-typescript/blob/main/packages/worker/src/worker-tuner.ts)、[Temporal MIT](https://github.com/temporalio/temporal/blob/main/LICENSE)、[BullMQ concurrency](https://docs.bullmq.io/guide/queues/global-concurrency)、[Restate workflows](https://docs.restate.dev/tour/workflows)、[Restate LICENSE](https://github.com/restatedev/restate/blob/main/LICENSE)。

ソース修正・上限変更・本番start/stop・外部作用0。証拠summaryはdocs/evidence/capacity-review/summary.json、raw観測は非公開ファイルへ保持。
