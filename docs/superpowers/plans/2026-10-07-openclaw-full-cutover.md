# ローカルLife ManagerのOpenClawハーネス移行実行計画

> 実行はsuperpowers:executing-plans。採用調査ではなく作成・接続・検証・切替・旧ハーネス退役の計画。

**Goal:** 全agent harnessをOpenClawへ移し、既存業務を維持する。
**Architecture:** Life Manager CLIをfacadeとして保持。OpenClawが全agent/session/schedule/recovery/trace、CodexがChatGPT accountで推論、既存workerが制作/販売/応募/収支とdomain guardを担当する。
**Tech Stack:** pinned OpenClaw/GatewayClient/native Codex plugin/diagnostics-otel、既存domain Python/Node、既存OS supervisor。
**Spec:** docs/superpowers/specs/2026-10-07-main-agents-readiness.md

1. OC/NC/MI/Cで共通接続と直接callerを実装・private fixture GREEN。
2. Pで各商品の既存worker/tool binding fileを実装。これは探索ではない。
3. Aで対象idle/pending無しのengineを一件ずつ新経路へ。
4. 次の自然仕事を確認後、Sで旧future wake停止→新cron enabledを一件ずつ実行。
5. Vで各商品すべての自然結果/公式receiptを保存。
6. Fでlocal installer/docsと旧harness参照0/final acceptanceを完了。

正確なファイル/関数/入力契約/検証/依存はspec内全223atomとmanifest。状態は統一SSOTだけ。旧harnessは未移行とrollbackの一時経路で、最終保持はしない。

共通制約:同ChatGPT native account、production shadow effect0、唯一scheduler、旧仕事drain、同task再送0、run単位claim解放、別owner/Gateway全体停止0、公式結果確認、data/auth不変更。
