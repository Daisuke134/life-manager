---
name: hyperliquid-scout
description: Read-only Hyperliquid perp market scout and historical momentum backtest — no keys, no orders, no signing.
---

# hyperliquid-scout

Purpose: rank Hyperliquid perp markets by liquidity/funding, and historically
evaluate a simple time-series momentum strategy on real hourly candles —
strictly read-only research, nothing else.

Ladder rung: **read-only scout + historical eval only**. Paper trading, shadow
trading, and live trading are NOT implemented. Any later live rung needs a
signing key stored in the credential SSOT (`~/.local/share/anicca/credentials.json`)
and explicit ladder gates before it may place an order.

## Commands

```
python3 scout.py --top 10
python3 backtest.py --coins BTC,ETH,SOL,HYPE,XRP --days 180 --hold-hours 24 \
  --lookback-hours 24 --slippage-bps 1.0 --taker-fee 0.00045 --seed 7 \
  --out /tmp/hl-backtest.json
python3 backtest.py --top 5 --days 180   # auto-picks coins by volume
python3 -m unittest -v test_hyperliquid_scout
```

Only HTTP call made: `POST https://api.hyperliquid.xyz/info`. No `/exchange`
calls, no private key, no signing anywhere in this directory.

## scout.py output fields

`coin, mark_px, day_ntl_vlm, open_interest_usd, funding_hourly, funding_apr,
impact_spread_bps, day_change_pct` per asset, ranked by 24h notional volume.

## backtest.py

Strategy `tsmom_24h`: non-overlapping windows, side = sign of the lookback
return, fees + slippage + funding subtracted. Outputs `per_coin`, `pooled`,
and `baseline_long_pooled` summaries (n, mean, stdev, t_stat, win_rate, sum,
ci95 bootstrap, statistically_supported).

Fee source: https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees
(base tier: taker 0.045%, maker 0.015%).

## Measured 2026-09-26 (`--top 5 --days 180`, BTC/ETH/SOL/ZEC/HYPE)

- `tsmom_24h` pooled: n=895, mean net -0.213%/trade, ci95 [-0.482%, +0.059%],
  not statistically supported. HYPE alone is supported *negative*.
- always-long baseline: mean net +0.387%/trade, ci95 [+0.100%, +0.684%] —
  market drift over this window, not strategy skill; correlated trades.
- Next gate: a strategy whose net ci95 lower bound is > 0 out of sample
  before any paper rung. Momentum does not pass; do not promote it.

## Caveats

Close-to-close fills assumed (no orderbook simulation); slippage-bps is an
assumption, not measured; base fee tier only; pooled trades across coins are
correlated so pooled CI is optimistic; no model/cloud cost included;
past performance does not predict future returns.

## Reference, not a dependency

The `hyperliquid-trading-agent` repo (if referenced anywhere) is reference
material only — no code from it is copied here; it is unlicensed and
unaudited.
