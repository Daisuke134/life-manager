# Cross-venue investment-core contract

This directory owns a local-first, read-only measurement boundary for Alpaca, Hyperliquid carry, Solana copy-trading, and future investment receipt sources. It does not own venue admission, funding, signing, order submission, or loop release.

## Net-P&L contract

Every measured venue snapshot carries official source receipt IDs and explicit costs:

```text
net_pnl_usd = gross_pnl_usd
              - trading_fees_usd
              - funding_or_borrow_usd
              - slippage_usd
              - gas_usd
              - model_cost_usd
```

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

## lm-lead boundary

The allocator may report a recommendation, but it must not edit `config/loop-registry.json`, `runtime/loop`, `runtime/host`, `bin/`, or any provider wallet. lm-lead owns cadence, registry admission, release, external funding, and live enablement. A missing owner/runtime receipt keeps the relevant venue visible as partial/unknown.
