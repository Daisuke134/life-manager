# 投資注文reconciliation状態遷移修正 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alpacaの`accepted`/未約定注文を約定済みとして閉じず、公式のfilled orderと口座・保有readbackが揃った時だけETF保有と損益測定へ進める。

**Architecture:** append-only effect ledgerにbroker注文のpending状態を記録し、非終端statusではeffectを未解決のまま保持する。`filled`だけをETF ownership callbackへ渡し、`canceled`/`expired`/`rejected`のゼロfillだけを終端失敗として閉じる。既存の誤った非終端outcomeは、最新公式statusを優先するreadbackで次のwakeから再開できるようにする。

**Tech Stack:** Python 3.14、stdlib `json`/`decimal`/`unittest`、Alpaca公式CLI readback、既存のappend-only receipt ledger。

**Spec:** `docs/superpowers/plans/2026-09-28-investment-unattended-revenue-loop.md`、`docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` §8-4。

## Global Constraints

- paper注文は再送しない。既存のclient order IDを公式readbackで追跡し、同じeffectを二重実行しない。
- `accepted`、`new`、`pending_new`、`partially_filled`、その他未認識statusはfilledとして扱わず、effectを未解決で保持する。
- `filled`でも公式account/position readbackが不完全ならownershipを作らず、次のnatural wakeで再試行する。
- partial fillをゼロ損益・完全約定に変換しない。残数量の扱いが未確定なら未解決のまま保持する。
- paper結果はlive資金、Binance送金、live注文、資本増額、$10,000/月の収益証明ではない。
- Capafy、PromptBase、共有runtimeの無関係なファイルは変更しない。

## Review Focus

- premarket `accepted` order: `outcome`を書かず、`reconciliation_pending`と公式client order IDを保持する。
- `filled` order: callbackが先にaccount/positionを検証し、strategy receipt付きoutcomeを一度だけ書く。
- `canceled`/`expired`/`rejected` with zero fill: terminal failureとして閉じ、paper P&Lに数えない。
- terminal status with positive `filled_qty`: partial fillを閉じず、追加readback待ちにする。
- 既存ledgerの誤った`broker_reconciled(status=accepted)`：次wakeで再度公式statusを読み、filledなら正しいstrategy receiptへ収束する。

### Task 1: Effect ledgerのbroker status境界を固定する

**Files:**
- Modify: `skills/alpaca-investment/effect_store.py`
- Test: `skills/alpaca-investment/test_etf_execution.py`

**Interfaces:**
- `reconcile_started(...) -> dict[str, int]`は従来の`pending/reconciled/unresolved`を維持し、非終端orderを処理した場合だけ`deferred`を追加する。
- `_unresolved()`は`reconciliation_pending`を未解決として扱い、非終端の古い`broker_reconciled` outcomeを閉じたeffectとして数えない。

- [x] **Step 1: Write failing tests.** `accepted`は`reconciled=0`・`unresolved=1`・`deferred=1`でoutcomeなし、filledはstrategy callbackを実行、zero-fill terminal failureはP&L対象外になるfixtureを追加する。
- [x] **Step 2: Run focused tests to verify RED.** `python3 -m unittest skills.alpaca-investment.test_etf_execution -q`を実行し、現在の実装が`accepted`を閉じる失敗を確認する。
- [x] **Step 3: Implement minimal status handling.** `filled`とzero-fill terminal failureだけをcloseし、その他は`reconciliation_pending`をappendする。outcome履歴は最新broker statusを正本にし、同一statusを重複appendしない。
- [x] **Step 4: Run focused tests to verify GREEN.** 同じfocused suiteを再実行し、追加fixtureを含めてPASSにする。
- [x] **Step 5: Commit.** 実装をこのinvestment専用branchへcommitする。

### Task 2: ETF paper performanceがpending/terminal failureを利益に変換しないことを固定する

**Files:**
- Modify: `skills/alpaca-investment/paper_performance.py`
- Test: `skills/alpaca-investment/test_paper_performance.py`

**Interfaces:**
- `build_paper_performance(...)`は未約定effectに対してnumeric P&Lを返さず、zero-fill terminal failureは閉じた往復数から除外する。

- [x] **Step 1: Write failing tests.** accepted legacy outcomeとzero-fill terminal failureを含むledgerで、pendingは`paper_effect_unresolved`、terminal failureは他のclosed round tripを壊さないことを固定する。
- [x] **Step 2: Run focused tests to verify RED.** `python3 -m unittest skills.alpaca-investment.test_paper_performance -q`を実行する。
- [x] **Step 3: Implement latest-outcome selection.** 同一effectのappend-only履歴から最新の公式statusを選び、filled strategy receiptだけをround tripへ渡す。
- [x] **Step 4: Run focused tests to verify GREEN.** `python3 -m unittest skills.alpaca-investment.test_paper_performance -q`をPASSさせる。
- [x] **Step 5: Commit.** 実装をこのinvestment専用branchへcommitする。

### Task 3: runnerがpending effectをtyped holdとして自然wakeへ返すことを確認する

**Files:**
- Modify: `skills/alpaca-investment/run.py`
- Test: `skills/alpaca-investment/test_run.py`

**Interfaces:**
- pending reconciliationは`investment_unresolved_intent`の一般失敗にせず、既存の`unresolved_intents` gateで新規注文を抑止する。filled後のwakeだけがownershipへ進む。

- [x] **Step 1: Write failing test.** `reconcile_started`が`deferred=1`を返したrunが新規submitを行わず、次回wakeへ継続可能なtyped holdになるfixtureを追加する。
- [x] **Step 2: Run focused test to verify RED.** `python3 -m unittest skills.alpaca-investment.test_run.DeploymentProfileTest.test_reconciliation_pending_is_a_hold_not_a_generic_failure -q`を実行する。
- [x] **Step 3: Implement the narrow guard.** `deferred`を既知のpendingとして許可し、`reconciliation_blocked`やreadback failureは従来通りfail closedする。
- [x] **Step 4: Run focused and full verification.** focused `68/68`、Alpaca全体`243/243`、`./bin/lm-loop-contract`、`git diff --check`をPASSさせた。
- [x] **Step 5: Commit and push.** 実装をcommitしてinvestment branchへpushする。

### Task 4: immutable releaseと既存paper注文の公式readbackを行う

**Files:**
- Modify: `docs/superpowers/plans/2026-09-28-investment-unattended-revenue-loop.md`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

- [ ] **Step 1:** source verificationとPR/main merge後、`origin/main` ancestorのimmutable releaseを作る。
- [ ] **Step 2:** `alpaca-investment-paper` ownerへapplyし、loaded argv/env/release SHAをreadbackする。
- [ ] **Step 3:** 既存client order `lm-ai-d3935170807d46a7a5cde38e`を再送せず、公式order/account/position/fillをreadbackする。
- [ ] **Step 4:** filledならdurable ETF ownership + strategy receiptを確認し、未約定ならpending、zero-fill terminalならfailed/no-P&Lとして記録する。
- [ ] **Step 5:** paper P&Lはcost-completeになるまでpromotion/sampleに数えず、残りのTODOと事実をplan/SSOTへ追記する。

## Completion Evidence

- 最新broker statusが`accepted`のままなら「paper注文受理、未約定、利益$0」と報告する。
- `filled`でもclose orderなしなら「保有中、実現損益未確定」と報告する。
- entry/exitの公式fill、account/position readback、fee/slippage/model costが揃うまで、completed round tripや収益を増やさない。
