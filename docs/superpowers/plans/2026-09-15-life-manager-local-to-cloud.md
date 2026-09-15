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
TODO worktree. The current cursor is `GRAPH-01`.

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
- [x] `FND-02` — Added explicit `job_ids` to all fourteen rows in
  `apps/life-manager/config/product-loop-catalog.json`. The catalog now points at existing
  `config/loop-registry.json` keys without copying effect/cadence data; the contract test rejects
  missing, unknown, duplicate, or malformed job identities and requires the exact fourteen product
  loop IDs. Focused proof: `python3 -m pytest
  skills/agent-engineering/tests/test_skill_contract.py::test_registry_product_and_job_identity -q`
  and `node --test apps/life-manager/lib/product-onboarding.test.js` (all passed), followed by the
  full skill contract, startup-context, repository URL, and diff checks. The overlap check read back
  latest `origin/main=005fbd9d336702814b8887ddd282c2d262a5bcbe`, a clean marketplace TODO worktree,
  and no target-file change in canonical main. Next active ID: `FND-03`.
- [x] `FND-03` — Added `RunState` and `RetryEntry` to
  `runtime/contracts/common-record.schema.json` and documented them in
  `runtime/contracts/README.md`. Lifecycle truth (`queued`, `running`, `retry_scheduled`, `deferred`,
  `human_wait`, terminal) is now separate from effect/readback truth; deferred, human-wait, and failed
  states require their resume/error metadata. Focused proof:
  `python3 -m pytest runtime/contracts/test_common_contracts.py -q` (16 passed) and the related
  contract suite for runtime events, admission, and memory (78 passed). Next active ID: `FND-04`.
- [x] `FND-04` — Extended the runtime event builders and common schema with the stable join fields
  `product_loop_id`, `job_id`, `owner_id`, `wake_id`, `attempt`, `effect_key`, `failure_layer`,
  `official_readback_ref`, and `next_eligible_at`. Builders derive backward-compatible identities for
  legacy callers while new callers can bind the full tuple; event IDs exclude timestamps and remain
  deterministic on replay. Focused proof: `python3 -m pytest
  runtime/loop/tests/test_runtime_event.py runtime/contracts/test_common_contracts.py -q` (16 passed),
  plus schema/diff checks. The overlap readback found latest `origin/main=39279e660ef95ace8c7d17f8de1129d44419ef61`,
  a clean marketplace TODO worktree, and no target-file change in canonical main. Next active ID: `FND-05`.
- [x] `FND-05` — Added the pure `apps/life-manager/lib/notification-policy.js` decision seam.
  Known routine events return `internal_only`; only `human_action_required`, `urgent_safety`,
  `material_outcome`, and `persistent_blocker` return `user_visible`; unknown kinds fail closed.
  Focused proof: `node --test apps/life-manager/lib/notification-policy.test.js` (3 passed).
  No Telegram sender or existing outbox was changed. Next active ID: `FND-06`.
- [x] `FND-06` — Applied the notification decision at the existing shared marketplace outbox via
  `skills/_shared/marketplace-core/scripts/effect_notification.py`. Routine event kinds short-circuit
  before database creation or sender invocation; user-visible kinds retain the receipt-backed delivery
  path. Focused proof sent 100 routine events with zero outbox/sender calls, delivered one material
  event, and the shared marketplace suite passed 259 tests. No live Telegram send was performed.
  Next active ID: `FND-07`.
- [x] `FND-07` — Added the redacted `HostPressure` record and builder in
  `runtime/host/memory_admission.py`, with shared-schema coverage. It records bounded memory, swap,
  load, finite-wake, browser-session/process/endpoint counts and a `metrics_only` marker; it rejects
  invalid values and never stores PIDs, URLs, or credentials. Focused proof: memory-admission and
  common-contract tests (8 passed). Next active ID: `FND-08`.
- [x] `FND-08` — Extended durable admission with a private `deferred` table carrying owner,
  resource class, original FIFO sequence, reason code, and `next_eligible_at`. A deferred owner
  releases only its reservation; before eligibility it returns `deferred`, and after eligibility it
  resumes from the same queue position. Future deferred owners are excluded from new reservations,
  while unrelated classes/owners continue. Focused proof: the durable defer/resume fixture passed and
  resource-admission plus loop-boundary tests passed 76 tests. The overlap readback found latest
  `origin/main=1f8d25eb4f12e3024e011b2fc5017443dc75c50d`, a clean marketplace TODO worktree, and no
  target-file change in canonical main. Next active ID: `FND-09`.
- [x] `FND-09` — Added `runtime/agent-runner/context_capsule.schema.json` with required goal, owner,
  product/job/wake identity, source hashes, decisions, open questions, byte/token budget, freshness,
  content hash, and secret-free references-only privacy markers. The fixture rejects missing budget or
  hash and invalid budget bounds. Focused proof: context-capsule, common-contract, and runtime-event
  boundary tests (21 passed). The overlap readback found latest `origin/main=1f8d25eb4f12e3024e011b2fc5017443dc75c50d`,
  a clean marketplace TODO worktree, and no target-file change in canonical main. Next active ID:
  `FND-10`.
- [x] `FND-10` — Added the deterministic `build_context_capsule` compiler in
  `runtime/agent-runner/context_packet.py` and a pass-through `contextCapsule` field in
  `runtime/loop/context.mjs`. The compiler normalizes authoritative facts, truncates only bounded
  excerpts, counts stale sources, hashes the canonical payload, rejects secret-like values, and is
  replay-stable; the JS context never rebuilds or expands it. Focused proof: context-capsule and
  prompt/context tests passed (15 total), plus the shared contract checks. No provider, browser,
  launchd, ledger, or Telegram effect was performed. Next active ID: `GRAPH-01`.
- [x] `ALIGN-01` — Added the fail-closed startup identity gate in
  `runtime/loop/release_identity.py` and `runtime/loop/lm_loop_run.py`. A loop now checks its
  immutable release manifest, launchd-projected Loop ID/owner/resource metadata, state-root boundary,
  and current-release SHA before starting the child. A stale effect-bearing release records a
  secret-free `release_drift` event and exits without starting the effect child; the release
  reconciler remains the explicit control-plane exception. New plist metadata makes the identity
  self-describing. Focused proof: `runtime/loop/tests/test_release_identity.py` (2 passed), the
  runner/apply/event/read-only suites (35, 79, 34, and 14 passed). No provider, browser, launchd,
  ledger, or Telegram effect was performed. Next active ID remains `GRAPH-01`.
- [x] `ALIGN-02` — Extended read-only `doctor` output to report labels whose installed release SHA
  differs from the current immutable release. The check consumes the same release manifest reader as
  the startup gate and makes release drift a failing doctor result without mutating launchd. Focused
  proof: `runtime/loop/tests/test_lm_loop_readonly.py::test_doctor_reports_installed_release_drift`
  and the full read-only suite passed. No provider, browser, launchd, ledger, or Telegram effect was
  performed. Next active ID remains `GRAPH-01`.
- [x] `ALIGN-03` — Added privacy-safe launch identity fields to runtime start/terminal events:
  repository-relative `entrypoint`, `resource_class`, and a SHA-256 state-root identifier. The
  common schema validates the fields, while raw private paths remain excluded. Added a wrong-owner
  launchd fixture proving the child is not started and an event-identity fixture proving both lifecycle
  events retain the same metadata. Focused proof: `runtime/loop/tests/test_release_identity.py` (4
  passed) and runtime/contract suites. No provider, browser, launchd, ledger, or Telegram effect was
  performed. Next active ID remains `GRAPH-01`.
- [x] `ALIGN-04` — Increased the safe launchd wrapper timeout from 30 to 45 seconds so the outer
  control-plane call covers the preflight's sequential bounded probes before reconciling stale labels.
  Added a regression test for the timeout budget. The change does not bypass preflight or perform a
  launchd mutation. Focused proof: `runtime/loop/tests/test_lm_loop_readonly.py::test_safe_launchctl_timeout_covers_the_full_control_plane_preflight` (passed). No provider,
  browser, launchd, ledger, or Telegram effect was performed. Next active ID remains `GRAPH-01`.
- [x] `ALIGN-05` — Ran a targeted production reconcile against the current immutable release
  `a5da9dca71bb4ac18843b3d989baa989d7487e0d` after launchd-safe preflight passed. Coconala
  `hf-gig-apply-direct` and Mercor `mercor-revenue-application` were each loaded with the exact
  current release argv and recorded install receipts; Lancers was not touched because its application
  owner was `loaded-running`. This changed launchd configuration only and performed no provider
  effect, browser action, or Telegram send. Next active action is the same targeted reconcile when
  Lancers reaches a natural loaded-idle state; `GRAPH-01` remains the architecture cursor.
- [x] `RESOURCE-01` — Reused the existing `runtime/host/disk_admission.py` with an explicit required
  byte floor and connected it to `runtime/loop/lm_loop_run.py`. The default six-GiB floor
  defers a queued owner before its child starts, records bounded free/threshold bytes, and preserves
  the existing durable resume path; control-plane cleanup/reconcile owners remain exempt. The gate
  was motivated by a measured Coconala `ENOSPC` after current-release sync, and it changes no browser,
  provider, launchd, or Telegram state by itself. Focused proof: runner suite (34 passed), memory
  admission suite (7 passed), and the disk-deferral fixture. Next active ID remains `GRAPH-01`.

## FND research gate (search complete; FND-02 implemented)

The research pass is complete for `FND-02` through `FND-10`. This section records the evidence and
the proposed contract before any runtime fix begins. It is a design checkpoint, not a claim that the
target control plane is implemented.

| FND | Measured Life Manager gap | Reusable source pattern | Proposed contract (before implementation) |
|---|---|---|---|
| FND-02 identity | The catalog has 14 product loops, while `config/loop-registry.json` has 165 jobs; zero catalog rows have `job_ids`, and zero registry rows have `product_loop_id` or `owner_id`. | [OpenAI Symphony SPEC](https://github.com/openai/symphony/blob/e0ccc83720a42a600a53b61c5f8d3e518bebe1db/SPEC.md) separates opaque issue identity, human identifier, workspace key, and run/session identity. | Keep `product_loop_id` (user capability) separate from `job_id` (registry key). Add one explicit, validated identity map; never merge job state or receipts merely because they share a product label. |
| FND-03 states | `runtime/loop/runtime_event.py` currently allows lifecycle `running/pass/fail/blocked` and effect `not_applicable/unknown/planned/started/verified/failed/reconciled`; it cannot express a durable queued/retry/deferred/human-wait state in one contract. | Symphony's orchestrator owns `running`, `claimed`, `blocked`, and `retry_attempts`; its retry entry carries `attempt`, due time, and error. | Use two typed axes: lifecycle (`queued`, `running`, `retry_scheduled`, `deferred`, `human_wait`, `completed`, `failed`, `blocked`) and effect/readback (`not_applicable`, `planned`, `started`, `verified`, `failed`, `unknown`). Never turn `unknown` into success or zero. |
| FND-04 events | Current events have `event_id`, `loop_id`, and `run_id`, but omit `product_loop_id`, `job_id`, `owner_id`, `wake_id`, `attempt`, `effect_key`, failure layer, and next eligibility. | [Symphony logging guide](https://github.com/openai/symphony/blob/e0ccc83720a42a600a53b61c5f8d3e518bebe1db/elixir/docs/logging.md) requires stable issue/session identifiers and concise outcomes. [OpenInference](https://github.com/Arize-ai/openinference/tree/812f6877d5e3e353be4ecceaf9b518963475a0) supplies typed span/agent/tool attributes instead of hand-spelled keys. | Make `(tenant, owner, product_loop, job, run, wake, attempt)` the join key; hash it into an idempotent event ID. Keep payloads redacted and evidence pointers separate. |
| FND-05/06 notification | `apps/life-manager/lib/notify.js` is a late-email helper; the existing Telegram outbox is durable and idempotent, but no shared policy decides which runtime events are user-visible. | [OpenHands telemetry rules](https://github.com/OpenHands/OpenHands/blob/23ca81c9ff6e638546f966d7f0e11a7682666179/AGENTS.md) use one telemetry owner and one canonical business event. The local outbox already suppresses unchanged messages by hash/time. | Add a pure policy before the existing outbox: routine wake/retry/eval/health stays internal; only human action, urgent safety, material outcome, or persistent blocker enters the outbox. Telegram is transitional transport, not the product boundary. |
| FND-07/08 resources | `memory_admission.py` gates on free-percent and `resource_admission.py` has durable FIFO reservations, but the shared Product Loop contract does not yet bind resource class, provider/account, browser profile, and host pressure to every job. | [Apify resource guide](https://docs.apify.com/actors/running/usage-and-resources) states that allocated memory also determines CPU/disk and that the total running allocation limits new work. [Browserless limiter](https://github.com/browserless/browserless/blob/450ec681481a1ee7bce2a4e5fe7c2ce3f939a0d7/src/limiter.ts) tracks queued/running/concurrent/timeout/health. | Admit finite wakes through one resource boundary; persist `resource_admission_deferred` with reason and `next_eligible_at`; use measured per-class/per-owner limits and fair resume. Headless removes display overhead but does not make memory unlimited. |
| FND-09/10 context | `context_packet.py` bounds bytes/depth/items and `context.mjs` passes a recent ledger slice, but there is no required hash-bound capsule containing goal, owner, sources, decisions, open questions, freshness, and budget. | [LangGraph durable execution](https://docs.langchain.com/oss/python/langgraph/durable-execution) distinguishes a thread checkpointer from a cross-thread store. [DeepAgents better harness](https://github.com/langchain-ai/deepagents/blob/1d3232c0852c47af09119edea10eeec887e4f0da/examples/better-harness/better_harness/core.py) separates train/holdout/scorecard and stores artifact/trace references. [Graphiti](https://github.com/getzep/graphiti/blob/c035afb7990b6077331a81e98b04efcfd9bf8184/graphiti_core/models/nodes.py) keeps source descriptions and temporal facts. | Compile the smallest capsule from authoritative facts; hash it; offload large artifacts; refresh mutable provider state immediately before an effect; share approved graph facts, never transcripts, credentials, or browser sessions. |

### Search evidence used

- [OpenTelemetry traces](https://opentelemetry.io/docs/concepts/signals/traces/) describes traces as the path of one request through a system; use trace/span IDs for diagnosis, not as business-effect proof.
- [Steel Browser](https://github.com/steel-dev/steel-browser/blob/2b41124d8e2953b0afe355c534e3c9aa71edae26/api/src/services/session.service.ts) exposes session identity, persistence, headless mode, CDP, and viewer handoff; Life Manager must keep provider/session ownership above that adapter.
- [Firecracker](https://github.com/firecracker-microvm/firecracker/blob/c5314e5dfc732db683115a02dee440ca06162a7c/docs/design.md) uses microVM, seccomp, cgroups, namespaces, and jailer boundaries; reserve it for untrusted repair/eval code, not every browser session.
- [Chrome headless](https://developer.chrome.com/docs/automation-and-testing/headless) confirms unattended no-UI operation, while modern headless shares Chrome's implementation; it reduces display overhead, not all browser memory.

**Alignment checkpoint:** the search and FND implementation phase is complete: `FND-02` through
`FND-10` have focused contracts and receipts. No provider effect was performed in this workstream.
The next atomic change is `GRAPH-01`'s graph node/edge/provenance schema; it begins with a focused
failing test after the FND handoff is reviewed.

| ID | One atomic outcome | Files/owner | Proof before the next ID |
|---|---|---|---|
| FND-01 | Record worktree and latest-main baseline | docs/architecture worktree / architecture owner | clean branch and baseline SHA |
| FND-02 | Validate Product Loop/job identity rows | apps/life-manager/config/product-loop-catalog.json / architecture owner | registry fixture PASS |
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

- [x] 起動時にjob ID、entrypoint、release SHA、state root（hash）、resource classを内部イベントへ保存する（`ALIGN-03`）。
- [x] ロード済み定義と現在のソースが異なる場合は業務処理をせず停止する（`ALIGN-01`）。
- [x] 古いlaunchd labelが新しい所有者を起動しないことを確認する（`ALIGN-03`のwrong-owner fixture）。
- [x] launchdを変更しないfixtureで、正しい所有者だけが実行されることを確認する（`runtime/loop/tests/test_release_identity.py`）。

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
