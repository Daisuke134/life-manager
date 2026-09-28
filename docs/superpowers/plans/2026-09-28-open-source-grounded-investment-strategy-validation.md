# Open-Source-Grounded Investment Strategy Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 公開研究・公開OSS・公式venue仕様から再現可能なstrategy候補を作り、backtest・out-of-sample・paper・natural receiptの順で検証し、根拠のないfree-form model判断と「30回やれば良い」という誤解を投資loopから除く。

**Architecture:** 研究資料は利益保証ではなく候補の出所として記録する。各venueは明示的なStrategyCard（対象、entry、exit、cost、risk、kill条件、evidence）を1つずつ持ち、pure policyがsignalを返し、effect ownerが注文を行い、Life Managerが自然wake・release・receipt・通知を所有する。証拠不足ならstrategy選択自体を`NO_STRATEGY`にし、資金を動かさない。

**Tech Stack:** 既存Python/Nodeのpure policy、stdlib `json`/`decimal`/`unittest`/`node:test`、Freqtradeのbacktest/dry-run設計、NautilusTraderの同一strategy source設計、Hummingbotのpaper/controller/executor境界、Alpaca/Hyperliquid/Solana公式readback。

**Spec:**

- `docs/superpowers/plans/2026-09-28-investment-loop-generational-wealth.md`
- `docs/superpowers/plans/2026-09-28-investment-unattended-revenue-loop.md`
- `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md` §8-4
- `docs/superpowers/plans/2026-09-27-hyperliquid-carry-live-loop.md`
- `docs/superpowers/plans/2026-09-27-solana-memecoin-copy-trading.md`
- `docs/superpowers/research/2026-09-28-open-source-investment-strategies.md`

## Global Constraints

- OSSのstar数、READMEのvolume、backtest画像、第三者のAPR表示は利益証拠とみなさない。公式receiptとcost-complete net P&Lだけを実績とする。
- Freqtrade GPL-3.0、Freqtrade strategies GPL-3.0、Hummingbot Apache-2.0、NautilusTrader LGPL-3.0のライセンスを守り、既存repoへGPLコードをコピーしない。必要なアルゴリズムは出典を記録して最小実装する。
- 研究中・StrategyCard未承認・cost未知・out-of-sample失敗・paper/live差異未解決の間は、注文、署名、送金、wallet creation、Binance transferを行わない。
- Alpaca capは`$100`、Hyperliquid leg capは`$25`、Solana canaryは`$2`・累積`$3`を超えない。strategyが良さそうという理由で上限を変えない。
- `30` Alpaca round tripsは、StrategyCardとvalidation gateを通過した後の実測sampleであり、strategyを発見する作業でも、手動wakeの回数でも、利益保証でもない。
- per-tradeの人間承認は要求しない。Life Managerは承認済みのreleaseとcap内で自律実行する。ただし所有者口座から外部へ資金を出す不可逆操作は、No-human-loopの外部承認境界を越えない。
- `unknown`、`effect_unknown`、lookahead、duplicate receipt、delivery uncertain、missing exit ruleは成功やゼロに変換せずholdする。

## Research Baseline (2026-09-28)

調査した公開資料から採用するのは、strategyの利益主張ではなく、研究と運用の境界である。

- [Freqtrade](https://github.com/freqtrade/freqtrade) と [Freqtrade strategy collection](https://github.com/freqtrade/freqtrade-strategies): strategy class、entry/exit、fee込みbacktest、dry-run、lookahead-analysis、recursive-analysisを参考にする。strategy collection自身が教育用・as-isであり、対象pair・期間ごとに自分で検証すべきと明記しているため、銘柄や数値をcloneしない。
- [Freqtrade Strategy Quickstart](https://www.freqtrade.io/en/stable/strategy-101/) と [Backtesting](https://docs.freqtrade.io/en/stable/backtesting/): backtest後にdry-runを行い、両者の差を調べる手順を採用する。過去結果を将来利益と呼ばない。
- [Hummingbot](https://github.com/hummingbot/hummingbot) と [official docs](https://hummingbot.org/docs/): paper trade、controller、executor、position lifecycle、market-making/arbitrageの部品分離を参考にする。公開volumeはstrategyの利益証拠にしない。
- [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) と [strategy docs](https://nautilustrader.io/docs/latest/concepts/strategies/): backtest/liveで同じstrategy sourceを使う設計と、live特有のvenue・timing・persistence・reconciliation差を採用する。
- [Jegadeesh–Titman momentum research](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x): 過去winnerのmomentumは株式の3〜12か月期間で研究された候補であり、5分足BTCやSolanaへ直接適用できる証拠ではない。候補の出所としてのみ使う。
- [Berkshire shareholder letters](https://www.berkshirehathaway.com/letters/letters.html): Buffett型の長期・理解可能な事業・価格と価値の区別をcore wealthの説明に使う。短期botの根拠に変換しない。
- [Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf): 候補を大量に試して一番良いものを選ぶだけでは採用しない。holdout、parameter sensitivity、forward evidenceを要求する。

## Strategy Scope

| Card | Instrument | Money mechanism | Research disposition |
|---|---|---|---|
| `core-global-index-v1` | eligible Japanese NISA/regulated-broker global index fund | long-run business growth, distributions, compounding | long-term core; no short-term bot claim |
| `alpaca-btc-spot-v1` | Alpaca `BTC/USDC` only | buy spot under a declared signal, sell under a declared exit | compare published-style mean-reversion and momentum candidates; no free-form model entry |
| `hyperliquid-carry-v1` | allowlisted BTC/ETH spot-long + matching perp-short | positive funding minus all costs | keep delta-neutral; no arbitrary high-APR altcoin chasing |
| `solana-copy-v1` | token mint observed in a confirmed public-wallet swap | copy entry, mirror/forced exit, net of swap and chain costs | read-only/paper only until exit and target evidence exist |

## Review Focus

- **Backtest future leakage:** an indicator or signal using future candles must fail the validation fixture; owned by Task 3.
- **OSS performance claim treated as proof:** README stars, community backtest, or volume must not produce `approved`; owned by Task 1 and Task 3.
- **Backtest/live divergence:** fill delay, order queue, spread, fee, and provider receipt differences must appear in the report; owned by Task 3 and Task 6.
- **Strategy without an exit:** a candidate missing stop, profit/close, time, and effect-unknown behavior must become `NO_STRATEGY`; owned by Task 2 and Task 5.
- **Model invents an edge:** the model may summarize evidence but cannot create an instrument, threshold, or exit outside the StrategyCard; owned by Task 4.

---

### Task 1: Record the source ledger and license/evidence boundary

**Files:**

- Create: `docs/superpowers/research/2026-09-28-open-source-investment-strategies.md`
- Modify: `docs/superpowers/plans/2026-09-28-investment-loop-generational-wealth.md`
- Modify: `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

**Interfaces:**

- The research ledger records `source_id`, URL, license, observed_at, mechanism, reproducibility status, limitations, and `adopted_as` (`reference`/`candidate`/`rejected`).
- It must explicitly record that no inspected OSS project provides audited guaranteed profit and that Freqtrade's strategy collection is not a ready-to-use performance claim.

- [x] **Step 1: Inspect primary OSS sources and official docs.** Record Freqtrade, Freqtrade strategies, Hummingbot, NautilusTrader, the published momentum paper, Buffett letters, and backtest-overfitting research without copying implementation code.
- [x] **Step 2: Inspect licenses.** Record GPL-3.0 for Freqtrade sources, Apache-2.0 for Hummingbot, and LGPL-3.0 for NautilusTrader; mark copy-in of GPL strategy files as prohibited.
- [x] **Step 3: Write the research ledger and evidence boundary.** Separate `what the source says`, `what we infer`, and `what remains unproven` in [`docs/superpowers/research/2026-09-28-open-source-investment-strategies.md`](../research/2026-09-28-open-source-investment-strategies.md).
- [x] **Step 4: Link the ledger from the primary plan and SSOT.** The primary plan points to this active plan, and the SSOT records the ledger boundary; the old free-form Alpaca decision and Solana entry-only canary remain unvalidated strategy behavior, not approved investment strategy.
- [x] **Step 5: Commit and push the documentation-only research boundary.** Commit `264751ff05` is pushed on the dedicated investment branch.

### Task 2: Add a canonical StrategyCard contract

**Files:**

- Create: `apps/life-manager/investment-core/strategy_cards.py`
- Create: `apps/life-manager/investment-core/test_strategy_cards.py`
- Modify: `apps/life-manager/investment-core/README.md`

**Interfaces:**

- `StrategyCard.from_mapping(value: Mapping[str, Any]) -> StrategyCard`
- `StrategyCard.to_mapping() -> dict[str, Any]`
- `validate_strategy_card(card: StrategyCard) -> tuple[str, ...]`
- Required fields: `strategy_id`, `venue`, `instruments`, `timeframe`, `entry_rules`, `exit_rules`, `sizing_rule`, `cost_model`, `risk_limits`, `kill_conditions`, `evidence_refs`, `status`.
- `status` is one of `research`, `paper`, `shadow`, `live_candidate`, `rejected`; missing exit/cost/evidence always rejects.

- [x] **Step 1: Write failing tests** for missing exit, missing cost, empty instruments, missing evidence URLs, unknown status, stable serialization, and a valid read-only card. RED was observed as the expected missing-module failure before implementation.
- [x] **Step 2: Run the focused test and observe RED.** `cd apps/life-manager/investment-core && python3 -m unittest test_strategy_cards -v`.
- [x] **Step 3: Implement the minimal immutable card parser and validator.** Preserve decimal values as strings; never infer defaults for cost or risk.
- [x] **Step 4: Run focused and discovery tests.** Focused `8/8` and investment-core discovery `74/74` pass.
- [x] **Step 5: Commit.** Commit `9c0e14ca84` is pushed on the dedicated investment branch.

### Task 3: Build an OSS-style, cost-complete validation harness

**Files:**

- Create: `apps/life-manager/investment-core/strategy_validation.py`
- Create: `apps/life-manager/investment-core/test_strategy_validation.py`
- Modify: `apps/life-manager/investment-core/README.md`

**Interfaces:**

- `validate_series(card: StrategyCard, candles: Sequence[Mapping[str, Any]], split: Mapping[str, str], costs: Mapping[str, str]) -> dict[str, Any]`
- `validate_series` returns `status`, `strategy_id`, `train`, `validation`, `holdout`, `trades`, `net_pnl_usd`, `fees_usd`, `slippage_usd`, `max_drawdown_usd`, `lookahead_detected`, `parameter_sensitivity`, `decision`.
- The harness is finite and read-only. It must not import credentials, submit orders, or call venue effect functions.

- [ ] **Step 1: Write failing tests** for train/holdout separation, a future-looking signal that is rejected, fee/slippage subtraction, no-trade output, duplicate candle timestamps, and a deterministic repeated run.
- [ ] **Step 2: Run the focused test and observe RED.** `cd apps/life-manager/investment-core && python3 -m unittest test_strategy_validation -v`.
- [ ] **Step 3: Implement a minimal event-driven evaluator.** Compute each signal only from candles at or before the decision timestamp; apply entry and exit costs separately; preserve `unknown` when required fields are absent.
- [ ] **Step 4: Add validation gates.** Use chronological `60% train / 20% validation / 20% holdout` with no shuffle. A candidate can become `paper` only if holdout net is positive after costs, max drawdown is within the card, no lookahead is detected, and at least 5 of 9 one-step neighboring parameter configurations retain positive net P&L with the median positive. Otherwise return `decision=rejected` with `reason=insufficient_evidence` or the specific failed gate; do not invent a new StrategyCard status.
- [ ] **Step 5: Run focused and full investment-core tests.** Store only sanitized reports under the external Life Manager state root; do not store secrets or provider credentials in the repo.
- [ ] **Step 6: Commit.** `git add apps/life-manager/investment-core && git commit -m "feat(investment): validate strategy candidates out of sample"`.

### Task 4: Replace Alpaca free-form selection with declared candidates

**Files:**

- Create: `skills/alpaca-investment/strategy_policy.py`
- Create: `skills/alpaca-investment/test_strategy_policy.py`
- Modify: `skills/alpaca-investment/allocator.py`
- Modify: `skills/alpaca-investment/position_manager.py`
- Modify: `skills/alpaca-investment/run.py`

**Interfaces:**

- `strategy_policy.evaluate(snapshot: Mapping[str, Any], card: StrategyCard) -> dict[str, Any]` returns only `ENTER`, `HOLD`, `EXIT`, or `NO_TRADE` with `strategy_id`, `signal_inputs`, `reason`, and `expected_cost_usd`.
- Initial candidate cards are `alpaca-btc-5m-reversion-v1` (Freqtrade-style RSI/TEMA/Bollinger structure, reimplemented without copying GPL code) and `alpaca-btc-5m-trend-v1` (declared EMA/breakout rules). Both are candidates until the validation harness selects one.
- The initial candidate rules are explicit hypotheses: `reversion-v1` enters only when `RSI(14) <= 30` and `TEMA(9) < BollingerMiddle(20, 2)`, and exits on `RSI(14) >= 70`, `close >= BollingerUpper(20, 2)`, `1.5 * ATR(14)` hard stop, or 12-bar time stop; `trend-v1` enters only when `EMA(20) > EMA(50)` and the close breaks the prior 20-bar high, and exits on `close < EMA(20)`, `2 * ATR(14)` hard stop, or 24-bar time stop. No shorting, averaging down, or rule changes after the holdout is frozen.
- Live order construction remains BTC/USDC only; QQQ/SPY option candidates remain paper-only until they have their own complete cards and venue acceptance.

- [ ] **Step 1: Write failing policy tests** for each candidate's exact entry, exit, stale quote, spread, missing candle, fee threshold, position ownership, and `NO_TRADE` behavior.
- [ ] **Step 2: Run the focused test and observe RED.** `cd skills/alpaca-investment && python3 -m unittest test_strategy_policy -v`.
- [ ] **Step 3: Implement pure signals and exits.** The model runner may not select an unlisted instrument or invent a threshold; it may only summarize the selected card's evidence.
- [ ] **Step 4: Wire `run.py` and `position_manager.py` to the selected card.** Record the card ID and signal inputs in every decision receipt; reject missing or stale card releases.
- [ ] **Step 5: Run the Alpaca suite.** `cd skills/alpaca-investment && python3 -m unittest discover -s . -p 'test_*.py'`.
- [ ] **Step 6: Commit.** `git add skills/alpaca-investment && git commit -m "feat(alpaca): use declared strategy cards"`.

### Task 5: Make Hyperliquid carry a bounded, declared strategy

**Files:**

- Modify: `skills/earn/hyperliquid-carry/policy.py`
- Modify: `skills/earn/hyperliquid-carry/test_hyperliquid_carry.py`
- Modify: `docs/superpowers/plans/2026-09-27-hyperliquid-carry-live-loop.md`

**Interfaces:**

- `policy.decide` keeps `enter`, `hold`, `exit`, `halt`, and `idle`, but the live-candidate universe is `BTC`/`ETH` spot-perp matches unless a later StrategyCard explicitly admits another asset.
- Entry requires trailing 24-hour funding projected across the 14-day horizon to exceed measured entry/exit fees, slippage, bridge cost, and model cost with a fixed buffer; a displayed APR alone cannot pass.
- Exit requires funding below the declared threshold, hedge mismatch, missing official state, daily loss cap, drawdown cap, or an unresolvable effect.

- [ ] **Step 1: Add failing tests** proving PURR/ZEC/high-APR-but-unallowlisted pairs are not admitted, cost-unknown funding is idle, positive funding after costs enters, and funding decay exits.
- [ ] **Step 2: Implement the allowlist and cost-complete carry gate.** Do not fund the wallet or sign an order.
- [ ] **Step 3: Run the focused Hyperliquid suite and read-only market snapshot.** No live wallet mutation.
- [ ] **Step 4: Commit.** `git add skills/earn/hyperliquid-carry docs/superpowers/plans/2026-09-27-hyperliquid-carry-live-loop.md && git commit -m "fix(hl-carry): require declared low-risk carry universe"`.

### Task 6: Complete Solana copy exits before any canary

**Files:**

- Modify: `skills/earn/solana-memecoin-copytrade/policy.mjs`
- Modify: `skills/earn/solana-memecoin-copytrade/run.mjs`
- Modify: `skills/earn/solana-memecoin-copytrade/receipt.mjs`
- Modify: `skills/earn/solana-memecoin-copytrade/test_policy_paper.mjs`
- Modify: `skills/earn/solana-memecoin-copytrade/test_live_canary.mjs`

**Interfaces:**

- Add explicit `copy_entry`, `mirror_exit`, `stop_exit`, `time_exit`, `skip`, and `halt` decisions.
- A copy entry requires a confirmed public-wallet swap, fresh Jupiter quote, both market-provider reads, minimum liquidity, price-impact limit, reserve, and duplicate fence.
- A position exits on a confirmed target-wallet sale of the same mint, a fixed hard stop, or a fixed time stop. No averaging down. Every exit must have a verified token delta and fee receipt.

- [ ] **Step 1: Write failing paper tests** for target sale, stop-loss, time-stop, stale target event, missing exit evidence, and replay-zero.
- [ ] **Step 2: Implement the pure exit policy and paper receipts.** Keep live mode closed.
- [ ] **Step 3: Run all Solana tests and a read-only scout.** `node --test skills/earn/solana-memecoin-copytrade/test_*.mjs`.
- [ ] **Step 4: Commit.** `git add skills/earn/solana-memecoin-copytrade && git commit -m "fix(sol-copy): add explicit exits before canary"`.

### Task 7: Select one strategy per venue by deterministic evidence

**Files:**

- Modify: `apps/life-manager/investment-core/strategy_cards.py`
- Modify: `apps/life-manager/investment-core/strategy_validation.py`
- Modify: `skills/alpaca-investment/allocator.py`
- Create: `apps/life-manager/investment-core/test_strategy_selection.py`
- Modify: the three investment plan/spec files after evidence

**Interfaces:**

- `select_strategy(reports: Sequence[Mapping[str, Any]]) -> dict[str, Any]` returns exactly one `strategy_id` or `NO_STRATEGY`, with report IDs, holdout metrics, cost model, and rejection reasons.
- Selection first filters the explicit gates, then ranks by holdout net P&L, lower max drawdown, lower turnover, and finally lexicographic `strategy_id`; it is deterministic and release-pinned. Model output can explain the selected report but cannot alter selection.

- [ ] **Step 1: Write failing selection tests** for two candidates, one passing holdout, all candidates rejected, stale report, cost-unknown report, and duplicate evidence IDs.
- [ ] **Step 2: Implement fail-closed selection and release pinning.** No selected card means no effect permission.
- [ ] **Step 3: Run focused selection, investment-core, and Alpaca suites.**
- [ ] **Step 4: Record the selected card or `NO_STRATEGY` in the primary plan, detailed plan, and SSOT.**
- [ ] **Step 5: Commit and push the evidence boundary.**

### Task 8: Resume Life Manager unattended runtime only after strategy selection

**Files:**

- Read-only/runtime-owned: Life Manager registry, release, state, official venue readbacks
- Modify after evidence: `docs/superpowers/plans/2026-09-28-investment-loop-generational-wealth.md`, `docs/superpowers/plans/2026-09-28-investment-unattended-revenue-loop.md`, `docs/superpowers/specs/2026-09-25-life-manager-unified-ssot.md`

**Interfaces:**

- A natural event must expose `strategy_id`, `release_sha`, loaded argv/env, `run_id`, `occurrence_id`, official provider readback, cost-complete P&L, durable receipt, Telegram provider ID, `error_class`, `retryable`, and `next_action`.

- [ ] **Step 1: Verify the selected strategy release is loaded.** A stale release or missing card is a typed hold, not a sample.
- [ ] **Step 2: Repair current `resource_capacity_busy`, duplicate-writer, stale-release, and active state blockers.** No manual wake, restart, funding, or cap increase.
- [ ] **Step 3: Verify one natural terminal wake and replay-zero delivery.**
- [ ] **Step 4: Record the exact runtime evidence in all investment specs.**

### Task 9: Measure the selected Alpaca strategy, then cross-venue evidence

**Files:**

- Existing Alpaca receipts and official account/order/fill/fee readbacks
- Existing `apps/life-manager/investment-core/{cross_venue_run.py,cross_venue_reporter.py,rolling_measurement.py}`
- Modify: investment plan/spec files after verified milestones

- [ ] **Step 1: Keep the selected strategy and cap fixed.** No mid-sample rule changes.
- [ ] **Step 2: Accumulate only natural completed round trips toward `30/30`.** A wake, hold, paper result, or fixture is not a round trip.
- [ ] **Step 3: Stop on negative, unknown, effect-unknown, or cost-incomplete evidence.** Do not force the remaining sample.
- [ ] **Step 4: Accumulate 30 delivered UTC daily receipts only after venue receipts are complete.**
- [ ] **Step 5: Promote one cap step only after the deterministic gate and a separate authorization receipt.**

### Task 10: Keep core wealth and target claims separate

**Files:**

- Modify: investment primary plan and SSOT after verified evidence
- Existing: treasury/contribution adapters under `apps/life-manager/investment-core/`

- [ ] **Step 1: Keep NISA/index contributions separate from speculative venue P&L.** Deposits and customer revenue never become trading profit.
- [ ] **Step 2: Claim `$10,000/month` only from 30-day official realized net P&L after all costs.**
- [ ] **Step 3: Route settled surplus through tax, emergency, operating, and diversified long-term buckets.**
- [ ] **Step 4: Reconcile monthly net worth and settled receipts.**

## Execution Order and Current Cursor

The corrected order is:

`① source/OSS evidence ledger → ② StrategyCard contract → ③ cost-complete out-of-sample validation → ④ Alpaca declared policy → ⑤ Hyperliquid bounded carry policy → ⑥ Solana explicit exits → ⑦ deterministic strategy selection → ⑧ Life Manager runtime health → ⑨ natural official P&L → ⑩ selected Alpaca 30-round-trip gate → ⑪ Hyperliquid shadow/14-day receipts → ⑫ Solana paper → ⑬ one-step promotion → ⑭ rolling $10,000 verification → ⑮ settled-surplus wealth ledger`.

Current cursor: **Task 3 Step 1 — write failing tests for cost-complete out-of-sample validation.** Tasks 1–2 are complete and pushed; no strategy has been approved, no additional capital is authorized, and the old `1/30` result remains historical evidence from an unvalidated Alpaca policy rather than progress toward a new 30-trade sample.

## Completion Definition

This plan is complete only when each venue has a source-backed StrategyCard, a reproducible cost-complete holdout report, paper/shadow parity, a release-pinned natural receipt, explicit exits, and an honest promotion decision. A cloned repository, backtest screenshot, 30 wake attempts, positive fixture, or model opinion does not complete the plan.
