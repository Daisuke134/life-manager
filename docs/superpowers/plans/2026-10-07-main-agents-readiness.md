# 主要15エージェントの復旧前検証計画

> 実行者は `superpowers:executing-plans` を使い、各atomの入力・出力・完了条件を満たしてから次へ進む。

**Goal:** 現在の15能力を保持し、復旧に必要な実変更を実測原因から確定する。
**Architecture:** 現行entrypoint/state/receipt経路を維持する。まず観測atomを実行し、原因が再現できたものだけ別の修正atomへ昇格する。
**Tech Stack:** Python、既存launchctl-safe、read-only SQLite、各既存provider reader。
**Spec:** `docs/superpowers/specs/2026-10-07-main-agents-readiness.md`

これは検証の実行計画。未確定原因を仮の実装タスクで埋めない。修正実装計画の確定は未完了。

## 制約

- 本番コード・設定・stateの変更、開始/停止、再送、effect fence解除は行わない。
- credential値と業務payloadを成果物に保存しない。source/provider readを同一owner/occurrence/releaseで照合する。
- provider readerがstate/evidenceを暗黙に書く場合は、pure read関数とprivate出力を使う。`--resolve`は付けない。
- 各観測は自然runの完了を待つ。進行中ownerのlease、profileを奪わない。
- 修正atomは既存のファイル・関数、再現入力、失敗するassert、最小修正、既存testコマンドを確定した時だけ追加する。

## 重点確認

capacity待ちと故障の混同、exit0と業務成果の混同、古いreleaseのreceiptの流用、official readback前の再送、共有ログを別owner/runへ誤帰属。

## 現在cursor: MA-01

### MA-01 — capacity待ちの条件を1件確定する

- [ ] `docs/evidence/main-agents/admission-capacity.json` を作る。
- 入力: `life-manager-cfo-hourly:18dc1958f6515e98-18701`、loaded serviceのcapacity envの許可キーだけ、read-only admission DBの同時刻claim/reservation/queue。
- 参照関数: `runtime/host/resource_admission.py::_limits/_capacity_available/_durable_capacity`。
- 出力: total/class/revenue-floor/legacy fenceそれぞれの実値と、通らない比較式を1つ確定。DB読み取りはmode=ro、現行writerを呼ばない。
- 完了: capacityを変える必要の有無を数値で判定。値の増加を先に決めない。

### MA-02 — control待ちのlock保持主体を確定する

- [ ] `docs/evidence/main-agents/admission-control.json` を作る。
- 入力: hf-gig-paid-direct、hf-gig-reply-detector、capafy-ig-account-managerの最新natural occurrenceとcontrol/owner deploy lockの保持PID・process start。
- 参照: `runtime/host/resource_admission.py::_defer_during_owner_deploy/enqueue_durable/claim_durable`、`runtime/loop/lm_loop_run.py::_admission_with_retry`。
- 出力: owner-deploy/global-lock/claim-flock/database-busyのどの境界か、保持時間とcode path。lock取得/解除やprocess killはしない。
- 完了:一時的待機と継続不具合を分離。索引不足仮説は既存索引実在のため採用しない。

### MA-03 — Lancers work-syncの実行エラーを相関する

- [ ] `docs/evidence/main-agents/lancers-work-sync.json` を作る。
- 入力: run `18dc1b6aee07d1e0-39467`、occurrence `lancers-revenue-work-sync:18dbf39232d477c0-73625`。
- 参照: `skills/earn/lancers/scripts/work_sync.py::run_tick/_production_account_diagnostic`呼出、`_worker_exit_code`。account診断本体はapplication_tickにある。
- 出力:同一runのaccount_diagnostic ready/reason、HTTP errorの分類、ログ相関がない場合はmissing_correlationを残す。
- 完了:source/認証/remote HTTP/観測欠落の一つを証拠で選ぶ。空のwork-sync.jsonだけを原因にしない。

### MA-04 — Investment liveの不在が意図通りか確定する

- [ ] `docs/evidence/main-agents/investment-mode.json` を作る。
- 入力: alpaca-investment-liveのservice absent rc113、paper/shadow/live設定のmodeのみ。
- 参照: `config/loop-registry.json` のpaper/live行、`skills/alpaca-investment/run.py`のmode分岐。
- 出力:desired modeとinstalled/loaded modeの一致。実口座注文・live enableをしない。
- 完了:live absentを意図的無効か欠落のいずれかへ分類。

### MA-05 — eBook JAの公開結果を確定する

- [ ] `docs/evidence/main-agents/ebook-ja-readback.json` を作る。
- 入力: tiktok occurrence `ebook-ja-tiktok-daily:18dbed383f505970-22876` とinstagramのsnapshot occurrence。
- 参照: `apps/life-manager/scripts/mobile-postiz-provider-reconcile.py::build_official_proof/_provider_readback`、既存distribution ledger。
- 出力:既存post/provider id、公式GET readback、account一致、effected/no-effect/inconclusive。本文は保存しない。
- 完了:同occurrenceの結合を証明。再投稿や`reconcile_pending_owner`の書き込み経路を呼ばない。

### MA-06 — Capafy dailyの公開結果を確定する

- [ ] `docs/evidence/main-agents/capafy-readback.json` を作る。
- 入力: `capafy-loop-daily:18dc19fd7f54d8b0-43114` と既存pre-dispatch snapshot。
- 参照: `skills/self/capafy-loop/capafy_factory_fence_reconcile.py::read_publish_list/read_remote_status/load_snapshot/find_hit`。
- 出力:agent/version receiptと公式status、同run結合の強さ。read関数のみ、reconcile/resolveを実行しない。
- 完了:exit0を独立した公開成果で検証。並行publishと区別できなければinconclusive。

## 能力別の自然run・成果確認atom

各atomは下記の出力ファイルを1つ作る。入力はsource-runtime-mapの当該group全jobと最新natural run。出力はowner/run/occurrence/release、次に達成すべき業務段階、official receipt、net/costの確認範囲、source修正の必要性。売上がないだけで故障としない。provider問い合わせ前に既存receiptを読み、複数ownerの共有ログは根拠にしない。

### MA-07 — Gig — Coconala

- [ ] `docs/evidence/main-agents/gig-coconala-outcome.json` を作る。
- 読む実行入口: `runtime/loop/entry_dispatch.py`, `skills/earn/gig/gig_daily_report.sh`, `skills/earn/gig/scripts/coconala-reply-owner`, `skills/earn/gig/scripts/evidence_gc.py`, `skills/earn/gig/scripts/launch_gig_browser.sh`, `skills/earn/gig/scripts/paid-direct-owner`.
- 完了: 実行・成果・入金を別判定し、未確認の必須条件をfile/owner/providerに固定する。正常能力は修正なし。

### MA-08 — Gig — Lancers

- [ ] `docs/evidence/main-agents/gig-lancers-outcome.json` を作る。
- 読む実行入口: `skills/earn/lancers/scripts/application-owner`, `skills/earn/lancers/scripts/browser-owner`, `skills/earn/lancers/scripts/negotiate-owner`, `skills/earn/lancers/scripts/paid-owner`, `skills/earn/lancers/scripts/storefront-owner`, `skills/earn/lancers/scripts/telegram-report-owner`, `skills/earn/lancers/scripts/work-sync-owner`.
- 完了: 実行・成果・入金を別判定し、未確認の必須条件をfile/owner/providerに固定する。正常能力は修正なし。

### MA-09 — Gig — CrowdWorks

- [ ] `docs/evidence/main-agents/gig-crowdworks-outcome.json` を作る。
- 読む実行入口: `skills/earn/crowdworks/scripts/application-owner`, `skills/earn/crowdworks/scripts/browser-owner`, `skills/earn/crowdworks/scripts/paid-owner`, `skills/earn/crowdworks/scripts/reply-owner`, `skills/earn/crowdworks/scripts/report-owner`.
- 完了: 実行・成果・入金を別判定し、未確認の必須条件をfile/owner/providerに固定する。正常能力は修正なし。

### MA-10 — Writer

- [ ] `docs/evidence/main-agents/writer-outcome.json` を作る。
- 読む実行入口: `skills/writer-agent/scripts/claim-loop-owner`, `skills/writer-agent/scripts/craft-train-owner`, `skills/writer-agent/scripts/money-sync-owner`, `skills/writer-agent/scripts/opportunity-discovery-owner`, `skills/writer-agent/scripts/opportunity-response-owner`, `skills/writer-agent/scripts/writer-report-owner`, `skills/writer-agent/scripts/writer-sales-measure-worker.sh`.
- 完了: 実行・成果・入金を別判定し、未確認の必須条件をfile/owner/providerに固定する。正常能力は修正なし。

### MA-11 — Affiliate

- [ ] `docs/evidence/main-agents/affiliate-outcome.json` を作る。
- 読む実行入口: `skills/affiliate/affiliate`, `skills/affiliate/scripts/local-browser`.
- 完了: 実行・成果・入金を別判定し、未確認の必須条件をfile/owner/providerに固定する。正常能力は修正なし。

### MA-12 — Investment

- [ ] `docs/evidence/main-agents/investment-outcome.json` を作る。
- 読む実行入口: `apps/life-manager/investment-core/cross_venue_run.py`, `skills/alpaca-investment/run.py`, `skills/alpaca-investment/validation_runner.py`.
- 完了: 実行・成果・入金を別判定し、未確認の必須条件をfile/owner/providerに固定する。正常能力は修正なし。

### MA-13 — Agent Economy

- [ ] `docs/evidence/main-agents/agent-economy-outcome.json` を作る。
- 読む実行入口: `apps/life-manager/scripts/x402-sale-ledger-boot.sh`, `bin/citizen-refill-launchd`, `skills/agent-economy/launch.sh`, `skills/earn/sol-funding-owner`, `skills/earn/x402-sell/acquisition-controller-boot.sh`, `skills/earn/x402-sell/experiment-tick.mjs`, `skills/earn/x402-sell/sale-observer-boot.sh`, `skills/earn/x402-sell/seller-boot-v2.sh`, `skills/earn/x402-sell/serve-claude-p-boot.sh`, `skills/earn/x402-sell/serve-franklin1-boot.sh`, `skills/earn/x402-sell/serve-franklin2-boot.sh`, `skills/earn/x402-sell/serve-mainnet-boot.sh`, `skills/earn/x402-sell/settlement-recorder-boot.sh`, `skills/earn/x402-sell/the402-boot.sh`, `skills/earn/x402-sell/the402-worker-boot.sh`, `skills/earn/x402-sell/watch-inflow.sh`.
- 完了: 実行・成果・入金を別判定し、未確認の必須条件をfile/owner/providerに固定する。正常能力は修正なし。

### MA-14 — Job Hunter

- [ ] `docs/evidence/main-agents/job-hunter-outcome.json` を作る。
- 読む実行入口: `apps/job-search-loop/scripts/run-daily.sh`, `apps/job-search-loop/scripts/run-health.sh`, `apps/job-search-loop/scripts/run-inbox.sh`, `apps/job-search-loop/scripts/run-learning.sh`, `skills/earn/mercor/scripts/application-owner`, `skills/earn/mercor/scripts/paid-owner`, `skills/earn/mercor/scripts/reply-owner`.
- 完了: 実行・成果・入金を別判定し、未確認の必須条件をfile/owner/providerに固定する。正常能力は修正なし。

### MA-15 — Fundraiser

- [ ] `docs/evidence/main-agents/fundraiser-outcome.json` を作る。
- 読む実行入口: `skills/fundraiser-agent/runtime/run.sh`.
- 完了: 実行・成果・入金を別判定し、未確認の必須条件をfile/owner/providerに固定する。正常能力は修正なし。

### MA-16 — Connector

- [ ] `docs/evidence/main-agents/connector-outcome.json` を作る。
- 読む実行入口: `skills/connector/run.sh`.
- 完了: 実行・成果・入金を別判定し、未確認の必須条件をfile/owner/providerに固定する。正常能力は修正なし。

### MA-17 — Self-Build / Product Improvement

- [ ] `docs/evidence/main-agents/self-build-outcome.json` を作る。
- 読む実行入口: `apps/life-manager/scripts/life-manager-dev-daily.js`, `runtime/loop/recovery-supervisor-cli.mjs`, `skills/earn/marketing-engine/report/scheduled_runner.py`, `skills/life-manager/self-build-daily.sh`.
- 完了: 実行・成果・入金を別判定し、未確認の必須条件をfile/owner/providerに固定する。正常能力は修正なし。

### MA-18 — Mobile App Loops

- [ ] `docs/evidence/main-agents/mobile-apps-outcome.json` を作る。
- 読む実行入口: `apps/life-manager/scripts/instagram-metrics-production-boot.sh`, `apps/life-manager/scripts/mobile-app`, `apps/life-manager/scripts/tiktok-metrics-production-boot.sh`, `skills/browser/owned-persistent-context`, `skills/life-manager/life-manager-daily.sh`.
- 完了: 実行・成果・入金を別判定し、未確認の必須条件をfile/owner/providerに固定する。正常能力は修正なし。

### MA-19 — eBook

- [ ] `docs/evidence/main-agents/ebook-outcome.json` を作る。
- 読む実行入口: `apps/life-manager/scripts/ebook-distribute-daily.sh`.
- 完了: 実行・成果・入金を別判定し、未確認の必須条件をfile/owner/providerに固定する。正常能力は修正なし。

### MA-20 — Capafy

- [ ] `docs/evidence/main-agents/capafy-outcome.json` を作る。
- 読む実行入口: `apps/life-manager/scripts/capafy-ig-reel`, `skills/capafy-autopublish/scripts/browser-owner`, `skills/earn/capafy-marketing/capafy-distribute-daily.sh`, `skills/earn/capafy-marketing/capafy-goal-monitor.sh`, `skills/earn/capafy-marketing/capafy-ig-account-manager.sh`, `skills/earn/capafy-marketing/capafy-ig-marketing-daily.sh`, `skills/earn/capafy-marketing/capafy-outcome-monitor.sh`, `skills/self/capafy-loop/capafy-loop-daily.sh`, `skills/self/capafy-loop/capafy-loop-healthcheck.sh`.
- 完了: 実行・成果・入金を別判定し、未確認の必須条件をfile/owner/providerに固定する。正常能力は修正なし。

### MA-21 — CFO

- [ ] `docs/evidence/main-agents/cfo-outcome.json` を作る。
- 読む実行入口: `apps/life-manager/scripts/financial-report-boot.sh`, `apps/life-manager/scripts/payout-boot.sh`, `skills/cfo/run.sh`.
- 完了: 実行・成果・入金を別判定し、未確認の必須条件をfile/owner/providerに固定する。正常能力は修正なし。

### MA-22 — 修正atomを確定する

- [ ] この計画へ、MA-01〜MA-21が特定したsource不具合だけを追記する。
- 必須欄: Modify exact file/function、Test exact file/assert、fixture input、期待output、RED command、minimal change、GREEN command、自然run受入条件。
- setup/KYC/account/login、capacity正常待機、receipt未確認はコード修正にすり替えない。
- 完了:残る修正ごとに新たな設計判断なしで実装開始できる。外部不確定性は明示的に残す。

### MA-23 — 移行の再評価

- [ ] `docs/research/2026-10-07-harness-transition-readiness.md` の復旧前提をMA証拠に合わせて更新する。
- 完了:既存正常owner、切替候補1owner、保持するstate/effect path、rollback対象が確定。MA完了前のMX実装をしない。
