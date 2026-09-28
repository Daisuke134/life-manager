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

The canonical `VenueSnapshot` is in `portfolio_receipts.py`. `venue_receipts.py` normalizes receipt rows; `net_pnl.py` aggregates Decimal-safe totals; `cross_venue_allocator.py` ranks only measured, positive-net, sample-qualified, drawdown-safe candidates. The allocator always keeps the existing `$100` cap and reserve and returns `capital_expansion_allowed: false`.

## Daily wake and state

`cross_venue_reporter.wake(...)` is a finite read-only wake. It writes one `cross-venue-YYYY-MM-DD.json` receipt and uses `telegram_outbox.sqlite3` for idempotent delivery. A provider message ID is recorded only after the sender acknowledges it. Missing provider acknowledgement is `delivery_uncertain` and is not blindly resent. State roots must be owner-only (`0700` directory, `0600` files).

Current source boundaries:

- Alpaca performance receipts: existing `skills/alpaca-investment` readback and `investment-core` adapters.
- Hyperliquid carry: its local journal and official account/funding readbacks; currently unfunded with no journal receipt.
- Solana copy-trade: `skills/earn/solana-memecoin-copytrade` journal; the staged read-only scout evidence is outside the repo under `~/.local/state/anicca/solana-memecoin-copytrade/`.
- Owner cash flow and model/API cost: an explicit reader must provide these receipts. Absent input is `不明`/blocked, not zero.

## $10k/month scoreboard

The `$10,000/month` target is a measurement target, not a forecast. It is achieved only when a rolling monthly official receipt reports `net_pnl_usd >= 10000` after all listed costs. Until then, `target_gap_usd` is `不明` unless a measured rolling-30-day receipt is supplied. Treasury cash surplus and customer revenue remain separate from investment P&L.

## lm-lead boundary

The allocator may report a recommendation, but it must not edit `config/loop-registry.json`, `runtime/loop`, `runtime/host`, `bin/`, or any provider wallet. lm-lead owns cadence, registry admission, release, external funding, and live enablement. A missing owner/runtime receipt keeps the relevant venue visible as partial/unknown.

