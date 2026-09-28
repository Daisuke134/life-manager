# Alpaca ETF Runtime Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the research-only `alpaca-etf-126d-momentum-v1` result into a deterministic, paper-only Alpaca ETF execution boundary that can produce one official paper receipt without permitting live stock orders.

**Architecture:** Keep signal calculation pure and separate from Alpaca I/O. The policy consumes a release-pinned `StrategyCard`, completed daily bars, explicit position ownership, and effect-fence state; it returns a JSON-safe decision. The broker adapter later supplies bars and paper orders, while the live boundary rejects this ETF asset class until a separate promotion gate is passed.

**Tech Stack:** Python 3 standard library, `Decimal`, existing `StrategyCard`, `unittest`, existing Alpaca CLI adapter, Life Manager immutable release workflow.

## Global Constraints

- Fixed ETF universe: `SPY`, `QQQ`, `IWM`, `DIA`, `EFA`, `EEM`, `TLT`, `GLD`.
- Fixed policy parameters: 126 completed sessions for ranking, top momentum symbol only, 21 completed holding sessions.
- Fixed sizing: `$10.00` notional; expected round-trip slippage is 20 bps and expected cost is `$0.02` before any provider-reported difference.
- The policy must reject missing, duplicate, unsorted, future, or in-progress daily bars; it never fills missing values with zero.
- A position or order may be acted on only when `owner_id=alpaca-investment-live` and `strategy_id=alpaca-etf-126d-momentum-v1` match exactly.
- Paper ETF orders are allowed only after deterministic selection and effect-fence checks; live ETF orders remain rejected.
- No Binance transfer, wallet creation, cap increase, live canary, scheduler restart, queue mutation, or registry/runtime-host edit is part of this plan.
- Every production-code change follows RED → GREEN → focused regression tests before commit.
- Historical holdout profit and paper P&L are evidence, not settled live revenue and not permission to increase capital.

---

### Task 1: Pure completed-session ETF policy

**Files:**

- Create: `skills/alpaca-investment/etf_policy.py`
- Create: `skills/alpaca-investment/test_etf_policy.py`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` after the focused test and implementation are verified

**Interfaces:**

- `evaluate(snapshot: Mapping[str, Any], card: StrategyCard | None = None, *, owner_id: str = "alpaca-investment-live") -> dict[str, Any]`
- Required snapshot fields: `daily_bars` (symbol → ordered rows), `completed_through_session` (`YYYY-MM-DD`), `position` (`None` or owned position mapping), `open_orders`, `unresolved_intents`, and `last_decision_session` (`None` or `YYYY-MM-DD`).
- A bar accepts `t`/`timestamp`, `o`/`open`, and `c`/`close`; output contains `action`, `strategy_id`, `symbol`, `decision_session`, `entry_after_session`, `signal_inputs`, `reason`, and `expected_cost_usd`.
- Signal rule: compare each symbol’s latest completed close with its close 126 common sessions earlier; rank by highest Decimal return and break ties by symbol ascending.
- Entry rule: with no owned position, no pending effect, and a new decision session, return `ENTER` for the selected symbol with `entry_after_session` equal to the completed decision session; the order layer must submit no same-session duplicate.
- Position rule: return `EXIT` after 21 completed sessions or when the selected symbol changes; otherwise return `HOLD`. A foreign, malformed, or ambiguous position returns `NO_TRADE`.

- [x] **Step 1: Write failing tests.** Added 127-session fixtures across all eight ETFs and tests for deterministic top-symbol selection; future-bar rejection; missing-symbol rejection; duplicate/unsorted session rejection; same-session re-entry rejection; pending-order fence; foreign-position rejection; 21-session exit; and symbol-change exit.
- [x] **Step 2: Run the focused tests and observe RED.** `python3 -m unittest test_etf_policy` failed as expected with `ModuleNotFoundError: No module named 'etf_policy'` before production code existed.
- [x] **Step 3: Implement the minimum pure policy.** `etf_policy.py` now normalizes sessions and Decimal prices, requires the common latest session to equal `completed_through_session`, computes the ranking with a complete symbol tie-break, and returns fail-closed decisions without broker, subprocess, filesystem-write, scheduler, or credential imports.
- [x] **Step 4: Run focused and regression tests.** `test_etf_policy` and `test_strategy_policy` pass `24/24`; the complete `skills/alpaca-investment` discovery suite passes `175/175`.
- [x] **Step 5: Record evidence and commit.** The SSOT and this plan record that the policy is code-tested only and produced no order or P&L. The implementation is committed and pushed as `feat(investment): add fail-closed ETF daily policy`.

**Task 1 result:** This closes only the pure policy boundary. It does not create a selected runtime state, ingest broker bars, submit a paper order, produce a provider receipt, or authorize live capital.

### Task 2: Release-pinned selection and allocator dispatch

**Files:**

- Modify: `skills/alpaca-investment/strategy_policy.py`
- Modify: `skills/alpaca-investment/allocator.py`
- Modify: `skills/alpaca-investment/test_strategy_policy.py`
- Create: `skills/alpaca-investment/test_etf_allocator.py`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` after verification

**Interfaces:**

- `candidate_cards()` returns the canonical ETF card in addition to the two BTC cards.
- `load_selected_card(state)` accepts the exact ETF card mapping only when the release SHA and canonical card match byte-for-byte.
- `allocator.choose()` dispatches ETF snapshots to `etf_policy.evaluate()` and keeps BTC behavior unchanged.
- `allocator.gate()` allows only paper ETF decisions; `allocator.order_for()` emits an explicit `asset_class="us_equity"` order shape.

- [x] **Step 1: Write failing regressions** for loading the selected ETF card, rejecting a stale/mutated ETF card, preserving BTC selection behavior, exposing the fixed ETF candidate universe, dispatching the pure policy, and refusing an ETF decision in live mode.
- [x] **Step 2: Run the focused tests and observe RED**; the pre-implementation run failed on the missing ETF card/candidate/order branch.
- [x] **Step 3: Implement the smallest dispatch** by importing the pure ETF card/policy, preserving the existing BTC allow-list, adding fixed ETF candidates when complete daily bars exist, and keeping live ETF orders fail-closed.
- [x] **Step 4: Run the focused allocator/selection suite.** `test_strategy_policy test_etf_allocator` passes `21/21`; the complete Alpaca discovery suite passes `183/183`. The selected-state behavior is verified in temporary test state only; no production state was written.
- [x] **Step 5: Commit and push** the release-pinned selection boundary as `c92d240299` plus the current dispatch changes; no production release was applied from this worktree.

**Task 2 result:** The code boundary is complete, but the Life Manager production release still lacks the ETF files and no production `selected-strategy.json` exists. Task 5 remains required before this becomes a runtime or paper-receipt pass.

### Task 3: Completed daily-bar ingestion

**Files:**

- Modify: `skills/alpaca-investment/alpaca_cli.py`
- Create: `skills/alpaca-investment/test_alpaca_cli.py`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` after read-only command verification

**Interfaces:**

- Add a bounded stock-bars read that returns the fixed universe, sorted by session, with `completed_through_session` explicitly recorded.
- Use the Alpaca market clock to exclude the current incomplete session; a provider row after the declared completed boundary is a typed failure.
- Preserve provider response/source identifiers for later paper receipts; never convert missing bars or unavailable cost to zero.

- [x] **Step 1: Write failing adapter tests** for exact fixed symbols, bounded lookback, completed-session cutoff, duplicate rows, future rows, and provider errors.
- [x] **Step 2: Run the adapter tests RED** before changing the CLI adapter; the missing `read_etf_daily_bars` boundary and fixture setup were caught.
- [x] **Step 3: Implement the read-only stock-bars operation** with `data multi-bars`, `--feed iex`, `--adjustment split`, `--timeframe 1Day`, a bounded 260-calendar-day window, NY-session filtering, 127 common sessions, deterministic source hash, and no order calls. `run.py` now requests the same boundary for both the initial and fresh allocator snapshots.
- [x] **Step 4: Run adapter plus pure-policy regressions.** Adapter tests pass `5/5`, the combined ingestion/selection/allocator/risk/position set passes `41/41`, and the complete Alpaca discovery suite passes `188/188`. The installed CLI help confirms the `multi-bars` command contract; no live provider order or P&L receipt was created.
- [x] **Step 5: Commit and push** the ingestion boundary; the source hash is an evidence reference, not a paper trade or P&L receipt.

**Task 3 result:** The read-only ingestion code is complete in the worktree, but the loaded production release still lacks it and no provider paper receipt exists. Task 4 and the Life Manager release handoff remain open.

### Task 4: Paper order, ownership, reconciliation, and receipt

**Files:**

- Modify: `skills/alpaca-investment/alpaca_cli.py`
- Modify: `apps/life-manager/investment-core/allocator.py`
- Modify: `skills/alpaca-investment/position_manager.py` or the existing ownership module used by the run path
- Modify: `skills/alpaca-investment/run.py`
- Modify: corresponding test modules before each production change
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` after focused verification

**Interfaces:**

- Paper stock order must be `asset_class=us_equity`, symbol in the fixed universe, notional exactly `$10.00`, market/day, and carry owner/strategy/client identity.
- Live mode must return a typed refusal for every ETF order attempt.
- Ownership state must record owner, strategy, symbol, decision session, order identity, provider receipt identity, and position quantity; foreign state is never adopted.
- A receipt is complete only after provider order/fill/account readback and replay-zero identity checking.

- [ ] **Step 1: Write failing order/ownership/reconciliation tests** for paper acceptance, live refusal, wrong symbol, wrong owner, duplicate client identity, missing fill, and replay-zero.
- [ ] **Step 2: Run the focused tests RED.** Confirm each failure is at the new ETF boundary rather than a broken existing BTC test.
- [ ] **Step 3: Implement paper-only stock submission and durable ownership** using existing effect fences and official readback helpers.
- [ ] **Step 4: Run the complete Alpaca investment suite** and a read-only paper preflight; no live order is submitted.
- [ ] **Step 5: Commit and push** the paper receipt boundary and update the SSOT with the exact evidence status.

### Task 5: Life Manager release handoff and natural receipt

**Files:**

- Read-only: Life Manager registry, loaded immutable release, state receipts, and official Alpaca paper readback
- Modify only: the three investment spec/plan files after the owner release/readback exists

**Acceptance:** a Life Manager-owned immutable release contains the pure policy, selected state, completed-bar ingestion, and paper-only order boundary; one natural scheduler wake produces a typed terminal result, official paper order/fill readback, durable receipt, and replay-zero notification. A runtime `resource_capacity_busy` or `resource_fifo_wait` event remains a hold and does not count as a trade.

- [ ] **Step 1: Verify the release artifact** contains the committed investment boundary and exact loaded argv/env.
- [ ] **Step 2: Allow the Life Manager owner path to apply/reconcile** only through its normal release workflow; do not edit registry, admission DB, LaunchAgent, or production state from this lane.
- [ ] **Step 3: Observe one natural wake** and collect run ID, occurrence ID, release SHA, effect journal, provider readback, receipt ID, and Telegram message ID.
- [ ] **Step 4: Update the SSOT and primary plan** with pass/fail; only a complete receipt opens the next Alpaca sample step.

## Completion definition

This plan is complete only when Tasks 1–5 have their stated evidence. A passing unit suite, an in-memory selector, a loaded registry row, or a paper backtest does not complete the plan. Live ETF trading, Binance funding, capital expansion, and the $10,000/month claim remain closed until the separate investment SSOT gates pass.
