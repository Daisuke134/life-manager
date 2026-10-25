# 追加調査: Railway以外の実行先を一次資料で比較

2026-10-22 UTC。範囲は開発/実行host、永続状態、復旧。既存Railway選定を新発見として数えない。Firecrawl web検索と別のweb検索系統で候補を発見し、公式本文をmaxAge0で取得。実配備・課金・性能比較は実施していない。source metadataは[HOSTS_SOURCES.json](HOSTS_SOURCES.json)。

## 判定と反証

| 追加候補 | 確認できた公式契約 | Managerへの判断 |
|---|---|---|
| Render Background Worker + Persistent Disk | workerは常駐しincoming trafficなし。paid workerにdiskをmount可能。diskは単一instance/runtimeのみ、zero-downtime deploy不可、24時間snapshot/少なくとも7日保持 | 現行Python/SQLiteとの構成上の適合がある有力な代替。Railwayより可用性が高いとは示されていない。account接続/実機lock/復元/費用は未検証 |
| Fly Machines + Volumes | volumeは一つのserver/region、一対一mount、volume間自動replicationなし。daily snapshotsはdefault5日、primary backupにすべきでないと公式記載 | native Python/SQLiteを動かせる候補だが、単一volumeの障害を自動で解消しない。複数Machineを足すだけではlocal flockの代替にならない |
| Modal Functions/Sandboxes + Volumes | commit/reloadで他containerへの可視化を制御。同一fileへの並行変更はlast-write-wins、distributed file lockingなし。v2はBeta | isolated inference/render/readonly research向け候補。現行SQLite/flock stateを複数container共有volumeへそのまま載せる判断はしない。single writerでも実動検証なしにPOSIX互換を仮定しない |
| Cloudflare Workflows / Durable Objects | step.doの結果を保存、durable sleep/retry。公式は外部APIのidempotencyを要求。Python WorkersはPyodide/WebAssembly/V8 isolate | workflowやedge stateを既成serviceへ委譲できる候補。ただし現coreのfcntl/subprocess/git/local SQLiteと同一host契約ではない。Pythonの名前だけで無変更移植可能としない |
| Render Workflows | TS/Python task、managed queue/retry、on-demand workers。現docsはpreview environment/Blueprint replication未対応 | 新しいdurable-task選択肢として記録。現worker+file DBのdrop-inではない。external effect receiptは別。SDK/実行backend全体のcode監査は今回未実施 |

**選択:** 現行の初期Railway構成は維持するが、「最良のplatformと証明済み」から「既存接続＋現在の単一Python/SQLite契約に合う初期選択」へ表現を限定する。Renderは実質的なfallback。新アカウント/課金/移行をこの調査で発生させない。platform比較に独立したSLA実測や実請求がなく、未確認値はunknown。

**変更条件:** persistent volumeでflock/SQLite durability/backup restoreを満たせない、停止許容や予算を満たせない時は実host比較で再選定する。複数worker/長期durable waitsが必要ならDBOS等のruntime比較と状態DB設計を先に行い、単にVMを増やさない。

## 再利用するbackup API

Python公式 `sqlite3.Connection.backup(target, *, pages=-1, progress=None, name='main', sleep=0.250)` は、他clientや同一connectionがDBへアクセスしていてもbackupできると説明する。DB fileを単純copyしてWAL/未checkpointの状態を取り落とす独自手法を作らない。取得は最新3.15 docsのAPI節だけであり、実装時に対象3.11の同じAPIを確認する。バックアップの成功は、古い状態から外部作用を安全に再開できる証明ではない。restore後は外部target/未解決effectを照合するまで新dispatchを禁止する。

## コードに落とす場所

- `manager_core/owned_cycle.py::CycleStore`: 現行のlocal flockをdistributed lockと扱わない。owner/volume起動検査とslot状態を明示。
- `manager_core/outbox.py::OwnedEffectJournal`: pendingは現在candidateに依存せず回収。backupから欠けた予約を不存在と推定しない。
- `manager_core/reconcile.py::reconcile_owned`: platformのcommit/parent/全bundleを先に照合。readback lagは再送理由にしない。
- 新 `scripts/backup_owned_cycle.py`: stdlib backupを利用。hash/integrity/restore検査、private state外のsource/Gitへ個人データを出さない。
- 新 `deploy/owned-digital/` のcontainer/configと既存 `scripts/run_owned_digital_cycle.py`: admitted immutable releaseだけを起動。host選定や環境変数だけでpublisher権限を作らない。

これらは次のpatch提案であり、今回実装・配備した結果ではない。

## 2026-10-25 Railway一次資料での運用方式更新

Railway公式の[cron contract](https://docs.railway.com/cron-jobs)は、service start commandを指定時刻に起動し、短いtaskが完了後にexitする構成を要求する。UTCで動き、最低5分の間隔を要し、前runが終了していない場合は次runを積まずskipする。Managerは毎時UTCに一度だけ有限tickを行うため、常駐schedulerではなく `0 * * * *` を採る。`CycleStore.due()`は3600秒slotを確認し、同一時間の重複起動を抑え、SQLite/flockがさらに同時ownerを拒否する。実際の開始時刻は分単位で保証されないので、期限精度は約束しない。

[Railway variables reference](https://docs.railway.com/variables/reference#railway-provided-variables)にはproject/environment/service/deployment IDと、volume name/mount path、Git由来deploymentのrepository/branch/commit SHAが列挙されている。現preflightはこれらを読み、expected project/environment/service/volume IDを別の `MANAGER_EXPECTED_*` 設定と照合する。`MANAGER_WORKFLOW_DISPATCH_TOKEN`の値は期待IDやログへ混ぜず、workerだけに渡す。

[Config as Code](https://docs.railway.com/config-as-code)はdeprecatedで、2026-12-01に既存利用のhard cutoff、新しいserviceはopt-in不可と記載されている。このため`railway.json`/`railway.toml`は追加しない。専用staging serviceが用意できる段階で、Railway service settingsにproduct root、Dockerfile、hourly cronを設定し、`/data/manager`に一つのdedicated volumeをmountする。Docker imageは必要なruntime filesだけを含め、root entrypointは正確なhost/mount preflightを通した後にvolume root inodeだけをowner UIDへ渡し、workerをUID 10001で実行する。これはDockerfileとlocal testsの実装状況であり、実image build、Railway mount ownership、service cost、cron/restart実測は未実施。

## 主な一次資料

- [Render disks](https://render.com/docs/disks) / [Background workers](https://render.com/docs/background-workers) / [Workflows](https://render.com/docs/workflows)
- [Fly volume overview](https://docs.fly.io/volumes/overview) / [snapshots](https://docs.fly.io/volumes/snapshots)
- [Modal volumes](https://modal.com/docs/guide/volumes)
- [Cloudflare workflow rules](https://developers.cloudflare.com/workflows/build/rules-of-workflows/) / [sleep/retry](https://developers.cloudflare.com/workflows/build/sleeping-and-retrying/) / [scheduled triggers](https://developers.cloudflare.com/workflows/build/trigger-workflows/) / [Python runtime](https://developers.cloudflare.com/workers/languages/python/how-python-workers-work/)
- [Python SQLite backup](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup)
- [Railway Cron Jobs](https://docs.railway.com/cron-jobs) — 2026-10-25、finite task/UTC/minimum interval/non-overlap/skip contract
- [Railway variables reference](https://docs.railway.com/variables/reference#railway-provided-variables) — 2026-10-25、system/volume/Git deployment variables
- [Railway Config as Code](https://docs.railway.com/config-as-code) — 2026-10-25、deprecation/new-service restriction/2026-12-01 cutoff

確認日とrelease日は別。本文を取得したことと、全service/全SDKを監査したことは別。Fly初回URLは新docsへredirect、indexだけでは保証を読めないためoverview/snapshotsを追加取得した。Modal v1/v2とPython最新docsの世代も保持する。


---
統合注記: このlaneは読取調査。repoへ収録した統合担当の文書変更と、未実施の実装/外部操作は別。[追加調査の判断](REPORT_JA.md)と[atomic patch plan](../../plans/2026-10-22-manager-e16-atomic-patches.md)を参照。
