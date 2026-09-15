# Life Manager Local-to-Cloud Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ローカル版で14個の製品Loopを同じ実行・証拠・修復契約で受入し、その同一コードをクラウドへ昇格して、利用者がスマホだけで使える本番版を提供する。

**Architecture:** 1つの管理基盤が目標、待ち行列、資源制限、有限wake、状況まとめ、関係図、評価、通知、人間確認を管理する。各サービスは薄い接続部品だけを持ち、ブラウザはヘッドレスSteelセッションを標準にする。ローカルとクラウドは同じ実装を使い、監督方法・保存場所・秘密情報・ブラウザ接続先だけを切り替える。

**Tech Stack:** 既存Node.js/Python runtime、config/loop-registry.json、既存JSONL/SQLite/PostgreSQL台帳、Playwright/CDP、Steel Browser、Responses API、Agents API保守実験、Firecracker隔離実行。

**Spec:** docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md

## Global Constraints

- ローカル完了ゲートを通るまでクラウドへ昇格しない。
- ローカルとクラウドで業務Loopの二重実装を作らない。違いはホスト接続部品だけにする。
- 165個のjobを同時起動して検証しない。待ち行列と資源制限の試験を使う。
- ヘッドレスは画面を隠すだけで、メモリを無限に増やす機能ではない。
- ブラウザ所有権、認証状態、台帳、公式確認、重複防止はLife Manager側の正本に残す。
- 通常の起動・再試行・評価・診断は内部記録だけにし、Telegramは人間行動・重大問題・重要な公式結果に限定する。
- Responses APIを通常のLoopのモデル接続に使い、Agents API/Agents SDKは読み取り専用の評価・修復作業に限定する。
- 認証情報、ブラウザセッション、個人情報、未加工ログをGit・Telegram・評価器・Agents APIへ渡さない。
- 公式の送信結果と公式の入金結果がないものを収益として数えない。

---

## Atomic Execution Cursor

Only one unchecked atomic ID is active. The primary records the active ID, changed files, focused
test result, receipt/evidence pointer, and next ID in this plan after every commit. Before any ID that
touches a shared file, run a shared-file overlap check against the latest main and the marketplace
TODO worktree. The current cursor is `FND-02`.

### Atomic execution log

- [x] `FND-01` — Baseline recorded before touching runtime code. Architecture worktree is
  `/private/tmp/lm-agent-engineering-skills-20260915`, branch
  `docs/agent-engineering-skills-20260915`, clean at `d1c5fa8c7cc6a0538b51614da43dfeb3f3e01a1b`.
  Latest `origin/main` is `4cdfcf7879a937e0df989615583bb75e2014ef5b`; the merge-base is
  `d8c6f097401674bd85095d019f5941ea9322657d`. The marketplace TODO worktree
  `/private/tmp/lm-shared-commercial-profile-20260911` is clean on its own branch, so this
  workstream has no shared-file overlap with its active changes. The canonical main checkout has
  unrelated local changes and remains untouched. Proof: `git status --porcelain`, branch/SHA
  readback, `git worktree list`, and `git diff --name-status origin/main...HEAD`.
  Next active ID: `FND-02`.

| ID | One atomic outcome | Files/owner | Proof before the next ID |
|---|---|---|---|
| FND-01 | Record worktree and latest-main baseline | docs/architecture worktree / architecture owner | clean branch and baseline SHA |
| FND-02 | Validate Product Loop/job identity rows | config/product-loop-catalog.json / architecture owner | registry fixture PASS |
| FND-03 | Define typed issue and retry states | runtime/contracts or existing schema / architecture owner | state-shape unit PASS |
| FND-04 | Emit owner/release/readback identifiers | runtime/loop/runtime_event.py / integration owner | event fixture PASS |
| FND-05 | Implement internal-first notification decision | apps/life-manager/lib/notification-policy.js / architecture owner | routine event returns internal-only |
| FND-06 | Apply notification decision at the existing outbox | existing Telegram outbox/report envelope / integration owner | 100 routine events send zero |
| FND-07 | Record host pressure and browser-session metrics | runtime/host/memory_admission.py / architecture owner | redacted metric fixture PASS |
| FND-08 | Defer and resume one saturated owner | runtime/host/resource_admission.py / integration owner | sibling progress and durable resume PASS |
| FND-09 | Validate the context capsule shape | runtime/agent-runner/context_capsule.schema.json / architecture owner | schema rejects missing hash/budget |
| FND-10 | Compile one bounded capsule from authoritative facts | runtime/loop/context.mjs; runtime/agent-runner/context_packet.py / integration owner | freshness, privacy, and resume fixture PASS |
| GRAPH-01 | Define graph node/edge/provenance schema | apps/life-manager/lib/agent-graph.js / architecture owner | unknown predicate and missing provenance rejected |
| GRAPH-02 | Project ledger facts idempotently | apps/life-manager/lib/agent-graph.js / integration owner | two rebuilds produce identical projection |
| GRAPH-03 | Answer blocker, receipt, and human-gate queries | apps/life-manager/lib/agent-graph.js / integration owner | bounded source-backed query fixture PASS |
| EVAL-01 | Define case/run/score/gate records | apps/life-manager/eval/agent-contract/ / architecture owner | schema fixture PASS |
| EVAL-02 | Add five representative failure classes | apps/life-manager/eval/agent-contract/cases.jsonl / architecture owner | Coconala/Lancers/Mercor/Connector/Fundraiser cases run |
| EVAL-03 | Gate candidate promotion on held-out and safety | apps/life-manager/eval/agent-contract/gate.js / integration owner | regression and tripwire fixture PASS |
| HUMAN-01 | Persist one typed human gate | shared marketplace human-gate contract / market+integration owners | stable gate ID and one outbox event |
| HUMAN-02 | Resume the same owner after a human answer | shared marketplace resume path / integration owner | same owner/effect namespace and replay-zero |
| BROWSER-01 | Connect one provider-neutral session to Steel | skills/browser/session lease path / architecture owner | CDP, storage, timeout, cleanup fixture PASS |
| BROWSER-02 | Run one read-only local headless canary | local Steel service / architecture owner | measured memory and official read-only result |
| BROWSER-03 | Run one local effect canary | one market owner / market+integration owners | official effect, readback, replay-zero |
| API-01 | Add the Responses API brain adapter | runtime/loop/brain.mjs; runtime/loop/responses-adapter.mjs / integration owner | capsule hash, tool limit, timeout, and cost fixture PASS |
| API-02 | Run an Agents API maintenance-only pilot | runtime/agent-maintenance/agents-api-pilot.py / architecture owner | read-only release, no credentials/effects, hashed output |
| LOCAL-01 | Produce the local completion manifest | scripts/local-completion-gate.py / integration owner | no advertised Loop remains unknown |
| LOCAL-02 | Accept all local Product Loop contracts | provider owners + local gate / market+integration owners | official evidence or explicit capability state for all 14 |
| CLOUD-01 | Provision tenant-scoped cloud state | apps/life-manager deployment / cloud owner | tenant isolation and immutable source check |
| CLOUD-02 | Run the cloud Steel canary | cloud browser adapter / cloud owner | read-only, human-gate, and effect canaries PASS |
| CLOUD-03 | Enable phone-only control and quiet reports | apps/life-manager Telegram/API / cloud owner | smartphone can create, resume, and inspect goals |
| CLOUD-04 | Promote the identical release to production | cloud promotion gate / primary owner | local gate, cloud canary, official readback, replay-zero |

### Task 1: ローカル完了台帳を作る

Files: config/product-loop-catalog.json; docs/superpowers/specs/2026-09-15-life-manager-local-completion-gate.md; skills/agent-engineering/tests/test_skill_contract.py

- [ ] 14 Product Loopと、registry内の小さな実行jobを対応付ける。
- [ ] 各Loopに owner、release、resource、official evidence、notification state、状態を記録する。
- [ ] verified、setup_required、not_applicable、blocked、unknownを混同しない試験を追加する。
- [ ] 契約テストを実行し、広告対象にunknownが残る場合は失敗させる。

### Task 2: 正本・所有者・ロード済みリリースを一本化する

Files: config/loop-registry.json; runtime/loop/lm_loop_run.py; runtime/loop/runtime_event.py; runtime/host/tests/

- [ ] 起動時にjob ID、entrypoint、release SHA、state root、resource classを内部イベントへ保存する。
- [ ] ロード済み定義と現在のソースが異なる場合は業務処理をせず停止する。
- [ ] 古いlaunchd labelが新しい所有者を起動しないことを確認する。
- [ ] launchdを変更しないfixtureで、正しい所有者だけが実行されることを確認する。

### Task 3: 資源の待ち行列と自動再開を完成させる

Files: runtime/host/resource_admission.py; runtime/host/memory_admission.py; runtime/loop/lm_loop_run.py; runtime/host/tests/

- [ ] agent、deterministic、browser、provider/accountごとの同時実行上限を一つの境界へ集める。
- [ ] 空きがないjobはresource_admission_deferredとnext_eligible_atを保存して終了する。
- [ ] 同じownerの重複実行を拒否し、別ownerは進行できることを試験する。
- [ ] メモリ、交換領域、load、実行中セッション数を記録する。
- [ ] 165job相当の合成fixtureで、上限超過なしと保留後の自然再開を確認する。

### Task 4: ブラウザ接続をSteel互換の共通契約へ移す

Files: skills/browser/scripts/cdp_context_lease.py; skills/browser/scripts/session_vault.py; runtime/browser/target-lease.cjs; config/loop-registry.json

- [ ] 既存CDP/Playwright接続の接続先を設定可能にし、Steel Cloudと自己運用Steelへ同じ契約で接続する。
- [ ] Cookie、localStorage、sessionStorageをprovider宣言の範囲だけ保存・復元する。
- [ ] 作成、利用、park、release、stale cleanupをowner単位で記録する。
- [ ] 自動処理はヘッドレス、画面表示は人間確認と診断だけにする。
- [ ] 読み取り専用providerで起動時間、1セッションの最大メモリ、再利用率を測定する。

### Task 5: 内部記録とTelegram通知を分離する

Files: apps/life-manager/lib/notification-policy.js; apps/life-manager/lib/notify.js; skills/earn/gig/scripts/telegram_outbox.py; skills/earn/gig/scripts/report_envelope.py

- [ ] wake、正常終了、通常再試行、評価、内部診断は内部記録だけにする。
- [ ] human_action_required、urgent_safety、material_outcome、persistent_blockerだけをTelegram対象にする。
- [ ] 同じevent keyの重複送信を防ぎ、persistent blockerは24時間に1回までにする。
- [ ] 100回の通常wakeでTelegram 0件、1つのhuman gateで1件になるfixtureを追加する。

### Task 6: 次のwakeへ渡す状況まとめを固定する

Files: runtime/loop/context.mjs; runtime/loop/prompt.mjs; runtime/agent-runner/context_packet.py; runtime/agent-runner/context_capsule.schema.json

- [ ] goal、owner、sources、decisions、open_questions、budget、hashを必須にする。
- [ ] 大きなログと画像は外部保存し、hashと短い抜粋だけを渡す。
- [ ] 外部作用の直前にprovider状態を再確認する。
- [ ] 人間確認、effect key、最後の公式結果が圧縮で失われないことを確認する。

### Task 7: 全Loopを横断する関係図を作る

Files: apps/life-manager/lib/agent-graph.js; apps/life-manager/lib/agent-graph.test.js; apps/life-manager/lib/context-graph.js; apps/life-manager/lib/intent-graph.js

- [ ] goal、capability、opportunity、artifact、effect、receipt、human_gate、revenue、resourceを投影する。
- [ ] requires、produced_by、sent_to、proved_by、blocked_by、earned、supersedesだけを許可する。
- [ ] 共通故障、公式証拠、人間確認の期限を質問できるようにする。
- [ ] 同じ台帳を2回投影して同じ結果になり、古い関係にstale印が付くことを確認する。

### Task 8: 共通評価試験と昇格判定を作る

Files: apps/life-manager/eval/agent-contract/cases.jsonl; apps/life-manager/eval/agent-contract/run.js; apps/life-manager/eval/agent-contract/gate.js; skills/earn/self-improve/lib/promote_gate.py

- [ ] Coconala情報源失敗、Lancersログイン不可、Mercor認証保存失敗、Connector登録失敗、Fundraiser締切失敗をfixture化する。
- [ ] 成功条件をプロセス終了ではなく、正しい状態、公式確認、重複なし、費用上限とする。
- [ ] 調整用データとheld-outデータを分離する。
- [ ] 安全性、費用、遅延、公式証拠のどれかが悪化した候補を昇格させない。

### Task 9: 人間確認を共通の再開可能な状態にする

Files: skills/_shared/marketplace-core/scripts/human_gate.py; skills/earn/mercor/scripts/application-owner; Connector/Fundraiser owners; existing Telegram outbox

- [ ] 面接、KYC、本人録画、本人承認だけをhuman_requiredにする。
- [ ] 人間が不要な作業は完了まで進めてから通知する。
- [ ] 返信が来るまで同じ案件を再送しない。
- [ ] 同じgateを何度wakeしてもTelegram 1件、同じowner/effect namespaceになることを確認する。

### Task 10: モデル接続をResponses API中心にする

Files: runtime/loop/brain.mjs; runtime/loop/responses-adapter.mjs; runtime/agent-maintenance/agents-api-pilot.py

- [ ] 通常のprovider/effect LoopはResponses APIを既存brain adapter経由で呼ぶ。
- [ ] 長い診断だけbackground=trueで開始し、response IDを保存して次wakeで確認する。
- [ ] background応答にはブラウザ・送信・支払いの権限を渡さない。
- [ ] Agents API pilotは読み取り専用release、fixture、出力先だけを与える。
- [ ] Agents API/SDKがscheduler、provider effect、正本台帳、秘密情報へ触れられないことを確認する。

### Task 11: ローカル版を完全受入する

Files: scripts/local-completion-gate.py; docs/superpowers/specs/2026-09-15-life-manager-local-completion-gate.md; local gate tests

- [ ] 14 Product Loopすべてにowner、release、資源制限、内部記録、評価結果を確認する。
- [ ] 収益Loopは公式作用、公式確認、replay-zeroを確認する。
- [ ] setup_requiredとnot_applicableをunknownと区別する。
- [ ] ユーザーがMac画面を見なくても、許可された処理が進むことを確認する。
- [ ] signed local completion manifestを作り、これをcloud promotionの必須入力にする。

### Task 12: クラウド版へ同じ実装を昇格する

Files: existing apps/life-manager deployment; scripts/cloud-promotion-gate.py; cloud promotion spec; cloud gate tests

- [ ] ローカルと同じimmutable release、Loop ID、receipt schema、関係図語彙、評価条件を使う。
- [ ] PostgreSQL/object storageへ利用者・owner単位の状態を作り、ローカルの可変状態をコピーしない。
- [ ] Steel Cloudまたは自己運用Steelへheadlessセッションを作る。
- [ ] 読み取りLoop、人間確認Loop、外部作用Loopを順にcanaryする。
- [ ] 公式確認とreplay-zeroが通るまで全利用者へ容量を広げない。

### Task 13: スマホだけの本番を有効化する

Files: apps/life-manager Telegram/API onboarding; cloud notification policy; tenant session provisioning

- [ ] 利用者がスマホとTelegramだけで目標登録、確認、再開、結果確認を行える。
- [ ] phone-only体験では、通常処理にMac画面を必要としない。
- [ ] 通常のLoop実行は画面に表示せず、内部管理画面で詳細を確認できる。
- [ ] 人間確認時は同じブラウザセッションを短時間だけ表示できる。
- [ ] 利用者ごとの認証、台帳、ブラウザ、関係図、評価結果が混ざらない。
- [ ] 一人の利用者の失敗が別利用者のLoopを停止しないことを確認する。

## Verification Commands

Run: python3 -m pytest skills/agent-engineering/tests/test_skill_contract.py -q
Run: for each of the seven agent-engineering skills, execute quick_validate.py
Run: git diff --check
Run: each focused runtime/browser/graph/eval/human-gate test named above

Local completion and cloud promotion never start all production jobs and never perform an unapproved external effect.
