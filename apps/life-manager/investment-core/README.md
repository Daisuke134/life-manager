# Cross-venue investment-core contract

This directory owns a local-first, read-only measurement boundary for Alpaca, Hyperliquid carry, Solana copy-trading, and future investment receipt sources. It does not own venue admission, funding, signing, order submission, or loop release.

## StrategyCard contract

`strategy_cards.py` is the canonical, side-effect-free declaration for a
candidate strategy. A card must declare its instrument, timeframe, entry,
exit, sizing, cost model, risk limits, kill conditions, evidence URLs, and
status (`research`, `paper`, `shadow`, `live_candidate`, or `rejected`).

```python
from strategy_cards import StrategyCard, validate_strategy_card

card = StrategyCard.from_mapping(payload)
errors = validate_strategy_card(card)
if errors:
    # Do not grant an effect permission.
    raise ValueError(errors)
```

`StrategyCard` is frozen and recursively immutable. `to_mapping()` returns a
detached JSON-like mapping, and `Decimal` inputs are preserved as strings.
Missing cost or risk data never receives a default; missing exit, cost, risk,
or evidence data must remain invalid until the source is supplied.

## Strategy validation

`strategy_validation.validate_series(card, candles, split, costs)` is a finite
read-only evaluator. It uses chronological train/validation/holdout partitions
(60/20/20 by default), rejects duplicate or future-looking candle inputs,
subtracts entry/exit fees and slippage, and reports `unknown` when required
market or cost data is absent. A card becomes `paper` only when holdout net
P&L is positive, drawdown is within the card, no lookahead is detected, and
the nine-point parameter sensitivity gate passes. The evaluator never imports
credentials or calls venue effect functions.

The evaluator requires one instrument with an explicit `/QUOTE` suffix. USD
uses identity conversion. Other quotes require `quote_to_usd` on every candle:
`{currency, rate, timestamp, evidence_ref}`, with a finite positive USD-per-quote
rate, matching quote currency and candle timestamp, and nonempty source evidence.
Signals retain native prices; USD sizing and proceeds use entry and exit FX
respectively. Missing or invalid conversion yields `unknown` / `rejected` and
null USD money fields, so it cannot become a selected strategy. These are modeled
validation costs, not evidence of actual fees or realized profit.

For the Alpaca cards, `skills/alpaca-investment/strategy_policy.py`
`build_validation_candles(...)` derives RSI/EMA/TEMA/Bollinger/ATR features
from each prefix of the official 5-minute OHLC stream and discards only the
indicator warmup rows. If the official stream has a missing five-minute bar,
the builder starts a new contiguous segment; it never fills the gap or bridges
indicators across it. It never uses a future bar. Exit expressions may use the
current position's `entry_price` and `age_bars`; those values are supplied by
the evaluator, not invented by a model.

The new BTC `*-400-v2` hypotheses use one explicit finite indicator contract:
400 completed five-minute bars, SMA-seeded EMA/TEMA, compared with an observed
800-bar reference. Recursive-price differences above one part per million of
current close, or different internal entry/exit predicates, prevent adoption.
The longer prefix is a comparison input, not a claim of a true or universally
stable EMA. Both validation and runtime signal code use the same comparison
helper; unknown inputs retain null total USD amounts. A hard-stop or time-stop
predicate that agrees on both inputs is not suppressed solely by relative
indicator variation.

Legacy BTC v1 calculations remain available for owned-position resolution, but
the allocator rejects new v1 entries. New validation reports contain only v2
BTC hypotheses. The bounded reader can fetch exactly 800 completed BTC bars
with the same closed interval at aligned and unaligned observation times; gaps,
incomplete pages and invalid prices remain errors. Dispatch of that input in
the normal owner resolves the recorded owned entry policy before selecting history;
the task branch does not claim full runtime adoption or profitability.

Strategy refresh shares the existing investment `control_fence` with submit and
planned-receipt creation. While ownership or an unsettled intent exists, it only
refreshes the same canonical card (status changes do not change the policy).
Corrupt ownership/ledger data is an error. An ETF closed marker is accepted only
with the matching reconciled intent, official filled sell, receipt envelope and
account readback showing the position absent. A legacy BTC `closed` label alone
is insufficient. The existing validation owner evaluates BTC alongside the legacy
ETF policy; a BTC history failure is reported as partial and does not manufacture
a BTC report or prevent refreshing an existing owned ETF policy.

## Net-P&L contract

Every measured venue snapshot carries official source receipt IDs and explicit costs:

```text
net_pnl_usd = gross_pnl_usd
              - trading_fees_usd
              - funding_or_borrow_usd
              - slippage_usd
              - gas_usd
              - model_cost_usd
              - system_cost_usd
```

`system_cost_usd` is the verified tool/browser/infrastructure total, separate from model cost. A missing total remains unknown; paid subtotals cannot fill it. Slippage and funding are signed. Other costs remain nonnegative. The core gross basis is before slippage: the Alpaca paper adapter converts explicitly identified fill-based gross to `fill_gross + signed_slippage` before using this formula, preserving the original paper receipt. Unknown paper gross basis remains partial.

Deposits and withdrawals are `owner_cash_flow_usd` and remain principal/cash-flow evidence. They are never investment revenue or net P&L. Missing, stale, duplicate, malformed, or `effect_unknown` evidence remains unknown/blocked and is never replaced with zero.

The canonical `VenueSnapshot` is in `portfolio_receipts.py`. `venue_receipts.py` normalizes receipt rows; `net_pnl.py` aggregates Decimal-safe totals; `cross_venue_allocator.py` ranks only measured, positive-net, sample-qualified, drawdown-safe candidates. `rolling_measurement.py` calculates the verified UTC 30-day window from daily receipts. The allocator always keeps the existing `$100` cap and reserve and returns `capital_expansion_allowed: false`.

## Daily wake and state

`cross_venue_reporter.wake(...)` is a finite read-only wake. It writes one `cross-venue-YYYY-MM-DD.json` receipt and uses `telegram_outbox.sqlite3` for idempotent delivery. A provider message ID is recorded only after the sender acknowledges it. Missing provider acknowledgement is `delivery_uncertain` and is not blindly resent. State roots must be owner-only (`0700` directory, `0600` files).

When `wake(...)` receives `readers["__daily_receipts__"]`, it calls
`rolling_measurement.rolling_30d(...)` and reports the result only when all 30
UTC days are present, delivered, measured, and source-receipt IDs are unique.
Missing/partial/undelivered days return `unknown`; malformed or duplicate
evidence returns `blocked`. Owner cash flow is summed as a separate field and
never added to rolling net P&L. A numeric target gap is never zero-filled.
When that reader is not supplied, `wake(...)` replays the persisted
`cross-venue-YYYY-MM-DD.json` files for the last 30 *completed* UTC days. The
current day is intentionally excluded until its delivery receipt is durable;
the result records `rolling_period_end` so the measured window is explicit.

## Owner-run entrypoint

`cross_venue_run.py` is a finite owner-runtime entrypoint. It accepts canonical
snapshot files with repeated `--snapshot venue=/path/to/snapshot.json` options,
an optional owner cash-flow receipt via `--owner-cash-flow-file`, and an
explicit `--available-capital-usd` value. It defaults to the standard venues
`alpaca`, `hyperliquid`, and `solana`; an unconfigured or malformed source is
reported as `unknown`, never as zero. The owner cash-flow file must include a
numeric `owner_cash_flow_usd` and non-empty `source_receipt_ids`.

Example owner invocation:

```text
python3 apps/life-manager/investment-core/cross_venue_run.py \
  --state-dir "$INVESTMENT_CROSS_VENUE_STATE_DIR" \
  --snapshot alpaca=/path/to/alpaca-snapshot.json \
  --snapshot hyperliquid=/path/to/hyperliquid-snapshot.json \
  --snapshot solana=/path/to/solana-snapshot.json \
  --owner-cash-flow-file /path/to/owner-cash-flow.json \
  --available-capital-usd 0
```

The entrypoint does not read credentials, sign, submit orders, fund wallets,
or edit loop admission. The Life Manager runtime owns the fixed argv/env,
cadence, release, and live provider acknowledgement.

### Life Manager To-Be connection

The canonical Life Manager job ID is `investment-cross-venue-report`. Its
registry entry runs this finite entrypoint once per UTC day with state root
`~/.local/state/life-manager/investment-cross-venue` and manifest
`inputs.json`. The investment product catalog maps this reporting job beside
`alpaca-investment-live`; it is one owner-controlled receipt path, not a
second ad-hoc scheduler.

The manifest is the owner-to-reader boundary:

```json
{
  "snapshot_specs": ["alpaca=/path/to/alpaca-snapshot.json"],
  "alpaca_state_dir": "~/.local/state/life-manager/alpaca-investment-live",
  "owner_cash_flow_path": "/path/to/owner-cash-flow.json",
  "available_capital_usd": "0"
}
```

When no explicit `--snapshot alpaca=...` is supplied, `alpaca_state_dir` lets
the reader consume the prior completed UTC day's
`performance-daily-YYYY-MM-DD.json` plus the latest observation and risk
readbacks, without credentials or provider calls. The live performance gate
and the paper performance producer both write this day-keyed receipt. During
migration, a legacy `performance-latest.json` is accepted only when its own
observation day exactly matches the requested completed day; a new-day latest
record is never used as the prior day. If the completed-day receipt is
missing or mismatched, Alpaca remains `unknown`. An explicit snapshot file
wins over the state directory. If the manifest is absent, invalid, or a source
file is missing, the daily receipt records
`input_manifest_status` as `missing` or `invalid`, keeps unavailable venues
`unknown`, and uses no available capital. It never turns a missing input into
`$0` profit. `configured` means only that the manifest was validly read; it
does not mean a venue made money. Missing funding, gas, or model-cost fields
remain partial/unknown rather than zero.

During a complete Life Manager release handoff, `bin/reconcile-agent-runner-release.sh`
invokes `provision_manifest.py` before owner reconciliation when that provisioner is
present in the release. If the owner manifest is absent, it creates only the safe
zero-capital default (`snapshot_specs=[]`, the durable Alpaca state directory, and
`available_capital_usd="0"`). A valid existing manifest is preserved; an invalid
existing manifest is not overwritten and fails the handoff. The daily wake never
creates or repairs this file.

Current source boundaries:

- Alpaca performance receipts: existing `skills/alpaca-investment` readback and `investment-core` adapters.
- Hyperliquid carry: its local journal and official account/funding readbacks; currently unfunded with no journal receipt.
- Solana copy-trade: `skills/earn/solana-memecoin-copytrade` journal; the staged read-only scout evidence is outside the repo under `~/.local/state/anicca/solana-memecoin-copytrade/`.
- Owner cash flow and model/API cost: an explicit reader must provide these receipts. Absent input is `不明`/blocked, not zero.

## $10k/month scoreboard

The `$10,000/month` target is a measurement target, not a forecast. It is achieved only when a rolling monthly official receipt reports `net_pnl_usd >= 10000` after all listed costs. Until then, `target_gap_usd` is `不明` unless `rolling_30d(...)` returns a measured 30-day receipt. Treasury cash surplus and customer revenue remain separate from investment P&L.

## Treasury cash contract

`treasury.treasury_snapshot(period, receipts, reserve_policy)` is a read-only
rollup. It keeps `customer_revenue`, `investment_net_pnl`, `owner_cash_flow`,
and `model_cost` as separate receipt categories. Owner cash flow is never
added to profit. A model cost is deducted from treasury only when its receipt
explicitly says it was not already included in investment net P&L; missing
scope, cost, duplicate, or unverified receipts produce `partial`/`blocked`
evidence rather than zero.

The result exposes two independent gaps: `investment_net_pnl_target_gap_usd`
against the `$10,000/month` trading target, and the optional
`treasury_surplus_target_gap_usd` after tax and cash reserves. Neither target
authorizes a transfer, a capital increase, or a live venue action.

`cfo_receipts.cfo_table_to_treasury_receipts(table, period)` is the read-only
bridge from `skills/cfo/loop_pnl.py`. It maps only non-investment `USD`
`revenue`, `refund`, and `cost` cells to `customer_revenue`,
`customer_refund`, and `operating_cost`. The `investment` row remains owned by
the canonical venue P&L spine; owner cash flow and model cost require their own
receipts. `JPY`, `USDC`, and `USD_API_EQUIV` are reported as excluded rather
than converted or treated as a provider bill. Unverified or incomplete cells
remain partial, and the aggregate receipt retains the source receipt IDs.

`financial_record_receipts.financial_records_to_treasury_receipts(records,
subject_id, period)` consumes rows already returned by the canonical
FinancialRecord store. It requires an exact subject and `YYYY-MM` period,
maps only verified USD `business_revenue` and explicit `fee` rows, and keeps
native-asset balances, ambiguous `business_cost` rows, payouts, transfers,
taxes, stale rows, and non-USD assets outside the USD treasury. A second
subject is a blocked input, never an additional revenue source.

`x402_inflow_receipts.x402_inflows_to_cash_receipts(rows, period)` consumes the
separate finalized external-inflow ledger produced by the x402 seller. It
requires successful finalized Base USDC transfers, `external=true`, exact
pay-to binding, unique transaction/source-sale IDs, and timezone-aware
timestamps. It returns `amount_usdc` only; it never invents an FX rate or an
`amount_usd` field, and therefore cannot silently enter the USD Treasury rollup.
The current audited ledger has 18 unique Railway inflows totaling `0.180000
USDC`; September has 15 totaling `0.150000 USDC`.

The local CFO discovers `external-inflows-0x*.jsonl` under the shared
`x402-sell` state root, projects the current period through this adapter, and
renders a separate `x402外部USDC cash` briefing section. That section is
delivery/reporting evidence only; it does not create a USD FinancialRecord or
authorize a transfer.

## Life Manager runtime boundary

The allocator may report a recommendation, but it must not edit `config/loop-registry.json`, `runtime/loop`, `runtime/host`, `bin/`, or any provider wallet. Life Manager runtime owns cadence, registry admission, release, external funding, and live enablement. A missing owner/runtime receipt keeps the relevant venue visible as partial/unknown.

### Recorded BTC ownership before submission

Approved BTC entry decisions freeze the canonical card, release, owner and mode
in the existing receipts ledger. Owned HOLD/EXIT resolves that entry through
its sealed intent and consistent official filled-buy outcome; a stale or replaced
current selection cannot replace the owned policy. Missing or conflicting fill
evidence remains an error. Native fill price and `filled_at` define the entry.
Before selling, the existing control fence checks fresh account quantity and the
exact original entry effect/client/provider identity. A changed position is not
submitted. New crypto buys also revalidate the fresh selected card, release and
expiry under that fence before sealing; only a new report for the same policy
and release may replace the entry report. Paper and live share the existing
bounded BTC/USDC market/gtc transport, keeping their mode-specific contexts.
Paper uses the same recorded BTC ownership and EXIT path as live, alongside its
existing owned ETF path. Missing account positions retain open/pending entry
markers; absence alone does not prove a close. Before a new buy, fresh account
and marker observations under the submit fence prevent overwriting another
entry. Ambiguous or contradictory fill history cannot become a zero-fill close.
Paper pending BTC orders defer the legacy option campaign with unknown P&L,
while keeping the account-wide allocator, risk and unresolved-intent checks.
A managed BTC close records its sealed original entry, exact filled sell and
mode-scoped account readback in the existing outcome strategy receipt before
closing the position. The position owner and durable intent fence share one pure
recorded-close validator from `crypto_ownership_proof`, including the core
selection guard despite its other module names. Completion callers must pass
full ledger history; planned and unresolved work prevent policy replacement.
Account lag remains pending across repeated runs and
receipt recovery; complete reconciliation replays without another query/append.
Terminal no-fill requires an explicit finite zero consistent with known fills.
Missing, malformed and partial quantities remain pending, and a later official
zero can enrich unknown evidence without erasing a known positive fill.
Existing closed markers are also audited: a sell needs its recorded original-entry,
close and account proof; a no-fill needs a sealed entry, official terminal zero and
flat account receipt. Known owner/policy/status contradictions are rejected across
all fill phases. Proven closed/no-fill state permits the next policy refresh;
unproved state cannot become permission to reenter. No-fill receipts retain unknown
USD net profit and do not assert zero operating costs.
Managed filled buys now require recorded same-mode acquisition/account evidence
before opening ownership. Account lag remains durably unresolved, and malformed
completed phases cannot hide an invalid proof from the common counter.
Terminal partial recovery first reads bounded FILL/CFEE snapshots through the
existing CLI. CFEE may post at end of day without an order ID: an empty query
or an observed balance difference does not prove zero or attributed fees.
This branch is source only: partial fills, complete costs, performance, deployment
and natural outcomes remain in the SSOT.
