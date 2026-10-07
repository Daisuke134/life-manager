# ローカルLife ManagerのOpenClaw移行実行計画

> 実行時は superpowers:executing-plans を使用。今回の依頼は設計/TODO更新であり、本番実装・切替を実施したとは扱わない。

**Goal:** ローカル16能力を保ち、OpenClawの既製agent/session/cron/traceを最大限再利用する。
**Architecture:** Life Manager CLI・domain policy/effect/financeを保持。最初default-off、各ownerでengine→自然確認→schedule→自然確認、最後に未参照旧runtimeを退役。
**Tech Stack:** pinned OpenClaw/GatewayClient/diagnostics-otel、既存Python runtimeとlaunchctl-safe。
**Spec:** `docs/superpowers/specs/2026-10-07-main-agents-readiness.md`

TODOの本文はSpec内のOC/P/A/C/S/V/F atomのみを参照し、別の実行順を作らない。状態/cursorは統一SSOTのみ。manifestは実行interfaceの機械表現であり状態表ではない。

Global constraints: production shadow effect0、唯一scheduler、旧仕事drain、scope別fence、同model/account、caller v2 task identity、run単位claim解放、別owner不変更、公式readback。
Review focus: multi-task idempotency衝突、native tools迂回、ACK喪失、wrapper死後のrun、scheduler二重起動、Gateway timeout時の他owner停止。

Node atomsは対象既存/new test fileを`node --test`、Python atomsは対象focused pytest/unittestでRED→minimal GREEN。source acceptanceは既存loop/CLI contractsとsecret/OSS gatesを含む。自然runはsource acceptanceと分離してVへ保存する。

推論はChatGPT account接続native Codexのみ。NC-01〜04とMI-01/02を依存DAGに従って実施。現在対象は16能力/110job、全215atomはspecを参照。

Native CodexはUnix/user scopeの既存ChatGPT accountを利用。NC-04はendpoint attach-onlyを優先。MI-01画像入力、MI-02owned thread forkを必須対応に追加し、旧仕事をunsupportedのまま完了扱いしない。
