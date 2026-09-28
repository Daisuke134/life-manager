# Alpaca ETF Momentum Evaluator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a deterministic, side-effect-free evaluator for the source-backed Alpaca ETF momentum hypothesis before any StrategyCard selection or broker effect.

**Architecture:** The evaluator accepts official daily OHLC bars as data, aligns a fixed ETF universe on common sessions, chooses the highest prior `lookback_days` close return, enters at the next session open, exits after a fixed holding period, and subtracts declared costs. It returns chronological train/validation/holdout summaries and a fixed neighboring-parameter grid; it never reads credentials, calls a broker, writes state, or places orders.

**Tech Stack:** Python 3.14, stdlib `decimal`, `datetime`, `unittest`; existing investment-core receipt and validation conventions.

**Spec:** `docs/superpowers/plans/2026-09-28-open-source-grounded-investment-strategy-validation.md`, source ledger `docs/superpowers/research/2026-09-28-open-source-investment-strategies.md`, and SSOT §8-4.

## Global Constraints

- Fixed universe: `SPY, QQQ, IWM, DIA, EFA, EEM, TLT, GLD`.
- Main hypothesis: 126 prior common sessions, top-1 winner, 21-session hold.
- Research notional: `$10`; declared stock commission `0` and entry/exit slippage `10` bps per side.
- Entry uses the next session open after the signal close; exit uses the close of the declared holding session; no future bar may affect the signal.
- Train/validation/holdout is chronological `60%/20%/20%` of completed trades; no random shuffle or post-hoc parameter selection.
- A positive holdout is insufficient: the fixed `84/126/168 × 15/21/30` grid must have at least 5 positive holdouts and a positive median before the hypothesis can be considered for a StrategyCard.
- This plan does not authorize a selected release, paper order, live order, funding, cap increase, or runtime registry change.

## Review Focus

- Duplicate or unsorted dates must fail closed instead of silently changing the ranking window.
- A missing symbol/session must remain visible in the data-quality result and cannot be treated as a profitable zero.
- The signal must use only closes at or before the decision session; entry starts on the next open.
- Invalid, negative, or unknown cost values must fail closed before net P&L is reported.
- Too few completed trades or an empty holdout must be rejected, not represented as zero-profit evidence.

---

### Task 1: Define the pure evaluator contract with failing tests

**Files:**

- Create: `apps/life-manager/investment-core/test_etf_momentum.py`
- Create later: `apps/life-manager/investment-core/etf_momentum.py`

**Interfaces:**

- `simulate(bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]], *, universe: Sequence[str], lookback_days: int, hold_days: int, notional_usd: Decimal, entry_fee_bps: Decimal, exit_fee_bps: Decimal, entry_slippage_bps: Decimal, exit_slippage_bps: Decimal) -> dict[str, Any]`
- `screen_grid(bars_by_symbol: Mapping[str, Sequence[Mapping[str, Any]]], *, universe: Sequence[str], lookbacks: Sequence[int], hold_days: Sequence[int], notional_usd: Decimal, entry_fee_bps: Decimal, exit_fee_bps: Decimal, entry_slippage_bps: Decimal, exit_slippage_bps: Decimal) -> dict[str, Any]`

- [x] **Step 1: Write failing tests** for deterministic top-1 selection, next-open/holding-close timing, cost subtraction, chronological partitions, duplicate-date rejection, missing-symbol rejection, and the 3×3 grid gate summary.
- [x] **Step 2: Run the focused test** with `cd apps/life-manager/investment-core && python3 -m unittest test_etf_momentum`; it failed at the missing `etf_momentum` import before implementation.

### Task 2: Implement the minimum pure evaluator

**Files:**

- Create: `apps/life-manager/investment-core/etf_momentum.py`
- Test: `apps/life-manager/investment-core/test_etf_momentum.py`

- [x] **Step 1: Implement strict normalization and common-session alignment** with `Decimal` prices, deterministic symbol tie-breaking, and explicit data-quality fields.
- [x] **Step 2: Implement `simulate`** with prior-close ranking, next-open entry, fixed holding-close exit, declared cost subtraction, drawdown, and chronological 60/20/20 summaries.
- [x] **Step 3: Implement `screen_grid`** by calling the same pure simulator for each predeclared neighboring pair; report positive count and median holdout net without selecting a parameter.
- [x] **Step 4: Run the focused test** and confirm all cases pass (`8/8`).
- [x] **Step 5: Run the investment-core discovery suite** and confirm no existing behavior regresses (`99/99`).

### Task 3: Re-run the official paper-data evidence through the evaluator

**Files:**

- Read-only: Alpaca paper daily bars from the official CLI and credential SSOT.
- Modify after evidence: this plan, the primary investment plan, the open-source research ledger, and the unified SSOT.

- [x] **Step 1: Fetch only the predeclared ETF universe** with split-adjusted daily bars and preserve the source/feed/date range/hash. Official IEX bars covered common sessions `2020-07-27`–`2026-09-28`; the canonical eight-symbol payload hash is `83d5ba8290d940f63880a2770f846a1addf19ea8632ce9ed626b73cf9490336a`.
- [x] **Step 2: Run `simulate` for `126/21` and `screen_grid` for `84/126/168 × 15/21/30`** with `$10`, zero commission, and 10 bps slippage per side. Main holdout net was `+$1.62` over 14 trades; all nine grid cells were positive with median `+$1.62`.
- [x] **Step 3: Record the full train/validation/holdout and data-quality result.** A positive result is evidence for a candidate only; it is not a selected card or order authorization. Cost stress remained positive at 25 bps and 50 bps slippage per side, but was negative at 100 bps per side.
- [x] **Step 4: Update all investment spec/plan files and commit/push the measured evidence.**

### Task 4: Decide the next boundary without forcing selection

- [x] The data-quality, holdout, and grid gates pass for this research candidate; the candidate is not promoted automatically.
- [x] Add the research-only `alpaca-etf-126d-momentum-v1` StrategyCard contract and tests; it remains disconnected from live execution until daily bar ingestion, position ownership, stock order constraints, paper receipt, and release selection are separately implemented and verified.
- [x] Update the canonical remaining-TODO cursor and do not count the research replay as P&L or as one of the 30 Alpaca round trips.

## Measured result and boundary

The corrected evaluator uses only the close at the decision session, enters at the next common-session open, and exits at the close after 21 sessions. It found `40/13/14` train/validation/holdout trades for the fixed `126/21` card: train net `+$2.17`, validation net `+$2.21`, holdout net `+$1.62`; holdout max drawdown was `$1.25` and cost was `$0.28`. The nine neighboring cells were all positive (`9/9`, median `+$1.62`). This is a candidate research result, not a selected release, broker receipt, realized account P&L, or authorization to fund the account.

The result was then converted to the existing validation schema with report ID `alpaca-etf-126d-momentum-v1-20260929`, evidence ID `alpaca-paper://stock-bars/iex/split/20200929-20260928`, and release SHA `afc476bcab1f7a10f5695bd4224af4242f1d8f09`. The report returned `decision=paper`, and the pure `select_strategy` function returned `selected`. This selection exists only in the read-only process output; no `selected-strategy.json`, runtime apply, paper order, live order, or capital change was performed.
