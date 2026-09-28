# Cross-Venue Capital Allocator and Fee/Model-Cost-Net P&L Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Life Manager one local-first, read-only allocator and daily report that compares Alpaca, Hyperliquid carry, Solana copy-trading, and other registered investment receipts by verified fee- and model-cost-net P&L.

**Architecture:** Keep venue execution owners unchanged. New pure aggregation code reads their official receipts into a common `VenueSnapshot`, subtracts explicit trading fees, funding/borrow costs, slippage, gas, and model-call cost exactly once, then ranks only capital that is free and risk-eligible. A finite report wake persists an aggregate receipt and uses the existing Telegram outbox for one idempotent UTC-daily message; it never submits venue orders or edits loop admission.

**Tech Stack:** Python 3.14, stdlib `dataclasses`/`decimal`/`json`, existing `investment-core` modules and Telegram outbox, `unittest`.

**Spec:** Dais directive 2026-09-27 (cross-venue capital allocator + daily fee/model-cost-net P&L), `apps/life-manager/investment-core/allocator.py`, `performance.py`, `reporter.py`, and `docs/superpowers/specs/2026-09-15-life-manager-agent-architecture-refinement.md` portfolio allocator section.

## Global Constraints

- The allocator is read-only: it returns allocation decisions and evidence but never imports or calls a venue submit/signing function.
- A venue contributes only official, wallet/provider-reconciled receipts; missing or ambiguous fields remain `unknown` and are never converted to zero.
- Net P&L is explicit: `gross_pnl - trading_fees - funding_or_borrow_cost - slippage - gas - model_cost`; each component carries source receipt IDs and cannot be subtracted twice.
- Model cost is a measured provider/x402 or local usage receipt; deterministic zero is allowed only when the venue declares `model_cost_source: deterministic_no_model`, not when the field is absent.
- Capital expansion is disabled until measured aggregate net P&L is positive after all costs and the sample/risk gates pass; the existing `$100` investment cap and cash reserve remain hard limits.
- Allocator candidates are ranked by verified marginal net return per dollar at risk, confidence, liquidity, and drawdown; a high gross return with unknown fees is ineligible.
- A daily report must show venue-by-venue gross, every cost component, net, receipt count, unknown state, and provider message ID; “unknown” is a valid terminal report value.
- No file under `runtime/loop`, `runtime/host`, `bin/`, or `config/loop-registry.json` is modified; lm-lead owns registry rows, cadence, release, and apply.

## Review Focus

- One venue has a missing fee or model-cost receipt: aggregate status is `partial`/`unknown`, and the allocator refuses to rank it; test no-zero substitution.
- A cash deposit or withdrawal occurs during the period: net P&L adjusts for owner cash flow and does not mislabel funding as profit; test both signs.
- A receipt is included twice or two venues reuse the same receipt ID: reject the aggregate before ranking; test duplicate identity.
- A stale or risk-breaching venue looks profitable: it is excluded from allocation while remaining visible in the report; test stale and drawdown gates.
- Telegram delivery is uncertain or repeated on the same UTC day: outbox idempotency prevents duplicate sends and preserves the provider message ID; test replay and delivery uncertainty.

---

### Task 1: Common venue snapshot and receipt adapters

**Files:**
- Create: `apps/life-manager/investment-core/venue_snapshot.py`
- Create: `apps/life-manager/investment-core/venue_receipts.py`
- Create: `apps/life-manager/investment-core/test_venue_snapshot.py`

**Interfaces:**
- Produces `VenueSnapshot` with exact fields `venue`, `observed_at`, `equity_usd`, `free_cash_usd`, `gross_pnl_usd`, `trading_fees_usd`, `funding_or_borrow_usd`, `slippage_usd`, `gas_usd`, `model_cost_usd`, `source_receipt_ids`, `risk`, and `cost_evidence`.
- Produces `normalize_receipts(venue, rows) -> VenueSnapshot | dict(status="unknown", reason=...)` and venue readers for Alpaca performance receipts, Hyperliquid carry JSONL, and the planned Solana copy-trade journal; readers accept paths/injected text and never credentials.

- [x] **Step 1: Write failing tests** for valid receipts, absent model cost, duplicate IDs, malformed numbers, and an effect-unknown row.
- [x] **Step 2: Run `cd apps/life-manager/investment-core && python3 -m unittest test_venue_snapshot` and verify failure.** RED observed with missing `venue_receipts.py`.
- [x] **Step 3: Implement decimal-safe normalization** while preserving `unknown` boundaries and the source receipt IDs. The existing canonical `portfolio_receipts.VenueSnapshot` is extended with per-cost evidence, and the compatibility adapter keeps latest equity/free cash while summing period P&L/cost rows.
- [x] **Step 4: Run the focused test and verify pass.** `test_venue_snapshot` passes `5/5`; existing portfolio performance tests remain green.
- [x] **Step 5: Commit** `82fdbc5f44` (`feat(investment): normalize cross-venue receipts`).

### Task 2: Fee/model-cost-net P&L aggregation

**Files:**
- Create: `apps/life-manager/investment-core/net_pnl.py`
- Create: `apps/life-manager/investment-core/test_net_pnl.py`

**Interfaces:**
- Produces `aggregate(period_start, observed_at, snapshots, owner_cash_flow_usd) -> dict` with `gross_pnl_usd`, `trading_fees_usd`, `funding_or_borrow_usd`, `slippage_usd`, `gas_usd`, `model_cost_usd`, `owner_cash_flow_usd`, `net_pnl_usd`, `venue_rows`, `source_receipt_ids`, `measurement_status`, and `reason`.
- Produces `venue_net(snapshot) -> dict` and rejects non-finite numbers, negative cost components, duplicate source IDs, and cash-flow-adjusted NAV mismatches.

- [x] **Step 1: Write failing tests** for exact net arithmetic, cash-flow adjustment, missing-cost unknown, duplicate receipt rejection, negative net, and aggregate receipt ordering.
- [x] **Step 2: Run the focused test and verify failure.** RED observed with missing `net_pnl.py`; one fixture expectation also caught the full cost-vector arithmetic and was corrected to `-3.00`.
- [x] **Step 3: Implement the pure Decimal aggregation** and reuse the existing `performance.py` fail-closed conventions without weakening its schema. The adapter returns per-venue rows, owner cash flow separately, and never turns a deposit into P&L.
- [x] **Step 4: Run the focused test and verify pass.** `test_net_pnl`, `test_venue_snapshot`, and `test_portfolio_performance` pass `16/16`.
- [x] **Step 5: Commit** `86e39e6fcc` (`feat(investment): calculate fee and model-cost net pnl`).

### Task 3: Deterministic cross-venue capital allocator

**Files:**
- Create: `apps/life-manager/investment-core/cross_venue_allocator.py`
- Create: `apps/life-manager/investment-core/test_cross_venue_allocator.py`

**Interfaces:**
- Produces `build_candidates(snapshots, aggregate, caps) -> list[dict]` with `venue://<name>` references and only verified fields.
- Produces `rank(candidates, available_capital, caps) -> dict` returning `action="allocate"|"hold"|"halt"`, ranked candidates, excluded reasons, and a single capital amount that stays inside the existing cap/cash/drawdown rules.

- [x] **Step 1: Write failing tests** for positive net versus unknown-cost candidates, stale venue exclusion, drawdown halt, cash reserve, deterministic tie-breaks, and capital-expansion denial below the sample threshold.
- [x] **Step 2: Run the focused test and verify failure.** RED observed with missing `cross_venue_allocator.py`.
- [x] **Step 3: Implement the pure ranking/gating layer**; do not call the existing model runner or any venue execution module from this file. Allocation is capped by reserve, current `$100` cap, drawdown, and sample thresholds; expansion remains false.
- [x] **Step 4: Run the focused test and verify pass.** `test_cross_venue_allocator` passes `6/6`; the module imports only the read-only net-P&L adapter.
- [x] **Step 5: Commit** `567862f202` (`feat(investment): rank verified cross-venue capital`).

### Task 4: Daily aggregate report and finite read-only wake

**Files:**
- Create: `apps/life-manager/investment-core/cross_venue_reporter.py`
- Create: `apps/life-manager/investment-core/cross_venue_run.py`
- Create: `apps/life-manager/investment-core/test_cross_venue_reporter.py`
- Create: `apps/life-manager/investment-core/test_cross_venue_run.py`

**Interfaces:**
- Produces `render_daily_pnl(aggregate, allocation, day) -> str` including all cost components and `unknown` markers.
- Produces `wake(readers, state_dir, today, send) -> dict`; it writes one aggregate receipt per UTC day, uses the existing Telegram outbox contract, and returns the provider message ID or a typed delivery-uncertain result.

- [x] **Step 1: Write failing tests** for report content, unknown cost visibility, venue ordering, same-day replay, outbox message-ID persistence, and the assertion that no venue submit/sign function is called.
- [x] **Step 2: Run the focused test and verify failure.** RED observed with missing `cross_venue_reporter.py`.
- [x] **Step 3: Implement the read-only wake** with configurable state roots for Alpaca, Hyperliquid, and Solana; make the current branch's Hyperliquid journal and the future copy-trade journal optional readers that report missing sources explicitly. Missing owner cash-flow evidence remains `unknown`, not zero; outbox delivery uncertainty is persisted and not retried blindly.
- [x] **Step 4: Run the focused test and verify pass.** The initial reporter slice passed `4/4`; after the rolling-window additions, the current `test_cross_venue_reporter` suite passes `7/7`, including same-day replay and provider-message-ID persistence.
- [x] **Step 5: Commit** `e407769d43` (`feat(investment): report cross-venue net pnl daily`). The pure wake and reporter import shim are committed; owner-owned registry/cadence wiring and a natural owner-runtime receipt remain open.
- [x] **Step 6: Add the finite owner entrypoint** in `cross_venue_run.py`. It loads canonical snapshot files without credentials or venue-effect imports, keeps missing standard venues `unknown`, requires source IDs for owner cash-flow evidence, and delegates idempotent delivery to `wake(...)`. Focused entrypoint tests pass `4/4`; the owner runtime still has to provide the fixed argv/env and natural receipt.

### Task 5: Acceptance evidence and operator contract

**Files:**
- Create: `apps/life-manager/investment-core/README.md`
- Create: `apps/life-manager/investment-core/test_cross_venue_acceptance.py`

**Interfaces:**
- Documents the snapshot schema, source receipt requirements, fee/model-cost equation, unknown behavior, state paths, and the lm-lead registry request without editing registry/runtime files.

- [x] **Step 1: Add acceptance tests** for a fixture with Alpaca + Hyperliquid + Solana rows and verify the exact daily net breakdown and no execution side effect. The fixture measures aggregate net `8.70` with owner cash flow `100.00`; ranking excludes the negative-net Solana row.
- [x] **Step 2: Run the investment-core focused suite and the existing `performance.py` tests.** The current focused command (`test_venue_snapshot test_net_pnl test_cross_venue_allocator test_cross_venue_reporter test_cross_venue_acceptance test_rolling_measurement test_portfolio_performance`) passes `35/35` on the dedicated branch; this is implementation evidence, not live revenue evidence.
- [x] **Step 3: Run one local read-only wake against current state; preserve the aggregate receipt and Telegram provider ID as evidence, or report the exact missing provider receipt.** Current Hyperliquid owner/runtime receipt and external Telegram provider acknowledgement are absent; no external send was attempted, and this remains an explicit boundary in `README.md`.
- [x] **Step 4: Commit** `docs(investment): specify cross-venue net pnl contract`.

### Rolling 30-day measurement extension

**Files:**
- Create: `apps/life-manager/investment-core/rolling_measurement.py`
- Test: `apps/life-manager/investment-core/test_rolling_measurement.py`
- Modify: `apps/life-manager/investment-core/cross_venue_reporter.py`

`rolling_30d(receipts, end_day)` consumes only persisted daily report receipts.
It requires the inclusive UTC window, confirmed delivery, measured daily
aggregates, explicit owner cash flow, and unique provider receipt IDs. It sums
only `net_pnl_usd`, keeps owner cash flow separate, and returns no numeric result
for missing, partial, undelivered, malformed, or duplicate evidence.

- [x] **Step 1: Add failing tests** for exact 30-day arithmetic, owner-flow separation, missing days, partial/undelivered days, duplicate days/receipt IDs, and invalid source numbers. RED observed with the missing module.
- [x] **Step 2: Implement the Decimal-safe pure measurement function** and wire both the explicit `__daily_receipts__` reader and the persisted completed-day replay into the daily reporter; malformed state is blocked and no filesystem, network, credential, or venue-effect import was added to the pure calculator.
- [x] **Step 3: Run focused tests.** `test_rolling_measurement` passes `5/5`; `test_cross_venue_reporter` passes `7/7`, including a measured `$30.00` fixture, `$9,970.00` target gap, malformed-file handling, and a persisted 30-completed-day replay.
- [ ] **Step 4: Accumulate 30 real delivered daily receipts before reporting a numeric live rolling result.** The reporter now measures the last completed UTC window; current live venue receipts are not complete, so this data gate remains open.

## Current live boundary (2026-09-28T12:51:49Z)

- The implementation commits above are present and `cross_venue_run.py` is now an owner-ready finite executable entrypoint. The live producer is still not admitted: `config/loop-registry.json` has no cross-venue row, and no owner cadence/release receipt exists.
- A host/state read-only audit found no cross-venue/rolling launchd label or plist and `0` persisted `cross-venue-YYYY-MM-DD.json` receipts under the default Life Manager state root. `rolling_30d([], "2026-09-28")` therefore returns `measurement_status=unknown`, `reason=daily_receipt_missing`, and `capital_expansion_allowed=false`.
- The next action is an lm-lead owner/runtime admission receipt containing the loaded entrypoint, fixed argv/env, cadence, state root, release SHA, owner/occurrence, and provider acknowledgement. Do not edit registry/runtime files from this lane, fabricate a daily receipt, fund a venue, or report a numeric live rolling P&L before that boundary exists.

## Source references

- Existing Alpaca net-performance contract: `apps/life-manager/investment-core/performance.py`
- Existing allocation/risk boundary: `apps/life-manager/investment-core/allocator.py` and `risk_policy.py`
- Existing Telegram idempotent delivery: `apps/life-manager/investment-core/telegram_outbox.py`
- Hyperliquid carry journal contract: `docs/superpowers/plans/2026-09-27-hyperliquid-carry-live-loop.md`
- Solana on-chain P&L verification pattern: `skills/earn/sol-trade/lib/record-swap.mjs`
