#!/usr/bin/env python3
"""Read-only historical backtest of a time-series momentum strategy on Hyperliquid
hourly candles. Uses only POST https://api.hyperliquid.xyz/info. No keys, no
signing, no /exchange calls.
"""
import argparse
import json
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from scout import post_info, rank_assets

FEE_SOURCE = "https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees"


def fetch_candles(coin, start_ms, end_ms):
    """Page candleSnapshot (max ~5000 rows/response) until end_ms is covered."""
    out = []
    cursor = start_ms
    while cursor < end_ms:
        body = {
            "type": "candleSnapshot",
            "req": {"coin": coin, "interval": "1h", "startTime": cursor, "endTime": end_ms},
        }
        rows = post_info(body)
        time.sleep(0.2)
        if not rows:
            break
        out.extend(rows)
        last_t = rows[-1]["t"]
        if last_t <= cursor or len(rows) < 5000:
            break
        cursor = last_t + 1
    # dedupe by open time, keep sorted
    seen = {}
    for r in out:
        seen[r["t"]] = r
    return [seen[k] for k in sorted(seen)]


def fetch_funding(coin, start_ms, end_ms):
    """Page fundingHistory (max 500 rows/response)."""
    out = []
    cursor = start_ms
    while cursor <= end_ms:
        body = {"type": "fundingHistory", "coin": coin, "startTime": cursor, "endTime": end_ms}
        rows = post_info(body)
        time.sleep(0.2)
        if not rows:
            break
        out.extend(rows)
        last_t = rows[-1]["time"]
        if last_t <= cursor or len(rows) < 500:
            break
        cursor = last_t + 1
    seen = {}
    for r in out:
        seen[r["time"]] = r
    return [seen[k] for k in sorted(seen)]


def momentum_trades(candles, funding, lookback, hold, taker_fee, slippage_bps, force_side=None):
    """Non-overlapping time-series momentum trades. Pure function, no HTTP.

    candles: list of {"t": openMs, "c": "closeStr", ...} sorted by t ascending.
    funding: list of {"time": ms, "fundingRate": str|float}.
    force_side: if set (e.g. +1), always trade that side (used for the
      always-long baseline) instead of the momentum signal.
    Returns list of trade dicts with side/gross/costs/funding_cost/net.
    """
    closes = [float(c["c"]) for c in candles]
    times = [c["t"] for c in candles]
    n = len(closes)
    funding_pts = [(f["time"], float(f["fundingRate"])) for f in funding]
    costs = 2 * (taker_fee + slippage_bps / 1e4)
    trades = []
    i = lookback
    while i + hold < n:
        base_ret = closes[i] / closes[i - lookback] - 1
        if base_ret == 0:
            i += hold
            continue
        signal_side = 1 if base_ret > 0 else -1
        side = force_side if force_side is not None else signal_side
        gross = side * (closes[i + hold] / closes[i] - 1)
        t_entry = times[i]
        t_exit = times[i + hold]
        funding_sum = sum(rate for (t, rate) in funding_pts if t_entry < t <= t_exit)
        funding_cost = side * funding_sum
        net = gross - costs - funding_cost
        trades.append(
            {
                "t_entry": t_entry,
                "t_exit": t_exit,
                "side": side,
                "gross": gross,
                "costs": costs,
                "funding_cost": funding_cost,
                "net": net,
            }
        )
        i += hold
    return trades


def summarize(returns, seed, n_boot=2000):
    """Bootstrap summary of a list of trade net returns."""
    n = len(returns)
    if n == 0:
        return {
            "n": 0,
            "mean": None,
            "stdev": None,
            "t_stat": None,
            "win_rate": None,
            "sum": 0.0,
            "ci95": [None, None],
            "statistically_supported": False,
        }
    mean = statistics.mean(returns)
    stdev = statistics.stdev(returns) if n > 1 else 0.0
    if stdev > 0:
        t_stat = mean / (stdev / (n ** 0.5))
    else:
        t_stat = 0.0 if mean == 0 else (float("inf") if mean > 0 else float("-inf"))
    win_rate = sum(1 for r in returns if r > 0) / n
    total = sum(returns)

    rng = random.Random(seed)
    boot_means = []
    for _ in range(n_boot):
        sample = [returns[rng.randrange(n)] for _ in range(n)]
        boot_means.append(statistics.mean(sample))
    boot_means.sort()
    lo_idx = int(0.025 * n_boot)
    hi_idx = min(int(0.975 * n_boot), n_boot - 1)
    lo, hi = boot_means[lo_idx], boot_means[hi_idx]

    return {
        "n": n,
        "mean": mean,
        "stdev": stdev,
        "t_stat": t_stat,
        "win_rate": win_rate,
        "sum": total,
        "ci95": [lo, hi],
        "statistically_supported": lo > 0,
    }


def _check_out_path(out_arg):
    repo_root = Path(__file__).resolve().parents[3]
    resolved = Path(out_arg).resolve()
    if resolved == repo_root or repo_root in resolved.parents:
        raise SystemExit(f"refusing to write inside repository root: {resolved}")
    return resolved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coins", type=str, default=None, help="comma-separated coin list")
    ap.add_argument("--top", type=int, default=None, help="use top-N coins by volume instead of --coins")
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--hold-hours", type=int, default=24)
    ap.add_argument("--lookback-hours", type=int, default=24)
    ap.add_argument("--slippage-bps", type=float, default=1.0)
    ap.add_argument("--taker-fee", type=float, default=0.00045)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    if args.coins:
        coins = [c.strip().upper() for c in args.coins.split(",") if c.strip()]
    else:
        top_n = args.top or 5
        meta, ctxs = post_info({"type": "metaAndAssetCtxs"})
        time.sleep(0.2)
        coins = [a["coin"] for a in rank_assets(meta, ctxs, top_n)]

    end_ms = int(time.time() * 1000)
    start_ms = end_ms - args.days * 86400 * 1000

    per_coin = {}
    pooled_returns = []
    baseline_returns = []
    for coin in coins:
        candles = fetch_candles(coin, start_ms, end_ms)
        funding = fetch_funding(coin, start_ms, end_ms)
        if len(candles) < args.lookback_hours + args.hold_hours + 1:
            continue
        trades = momentum_trades(
            candles, funding, args.lookback_hours, args.hold_hours, args.taker_fee, args.slippage_bps
        )
        baseline = momentum_trades(
            candles, funding, args.lookback_hours, args.hold_hours, args.taker_fee, args.slippage_bps,
            force_side=1,
        )
        returns = [t["net"] for t in trades]
        per_coin[coin] = summarize(returns, args.seed)
        pooled_returns.extend(returns)
        baseline_returns.extend(t["net"] for t in baseline)

    pooled = summarize(pooled_returns, args.seed)
    baseline_pooled = summarize(baseline_returns, args.seed)

    out = {
        "venue": "hyperliquid",
        "rung": "historical_eval",
        "strategy": "tsmom_24h",
        "params": {
            "coins": coins,
            "days": args.days,
            "hold_hours": args.hold_hours,
            "lookback_hours": args.lookback_hours,
            "slippage_bps": args.slippage_bps,
            "taker_fee": args.taker_fee,
            "seed": args.seed,
        },
        "window": {"start": start_ms, "end": end_ms},
        "per_coin": per_coin,
        "pooled": pooled,
        "baseline_long_pooled": baseline_pooled,
        "fee_source": FEE_SOURCE,
        "caveats": [
            "Fills assumed at exact close-to-close prices; no orderbook/impact simulation of the actual fill.",
            "Slippage (slippage-bps) is an assumption, not measured from historical fills.",
            "Fees use the base (lowest volume) taker tier; real fees may be lower with higher volume/HYPE staking.",
            "Pooled trades across coins are correlated (correlated crypto markets), so the pooled CI is optimistic (narrower than true uncertainty).",
            "No model, cloud, or infrastructure cost is included in net returns.",
            "Past performance does not predict future returns; this is a historical eval, not a live-trading guarantee.",
        ],
    }

    payload = json.dumps(out, indent=2)
    if args.out:
        dest = _check_out_path(args.out)
        dest.write_text(payload)
    print(payload)


if __name__ == "__main__":
    main()
