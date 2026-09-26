#!/usr/bin/env python3
"""historical_eval.py — READ-ONLY historical replay of a Polymarket strategy, net of fees.

Ladder rung: `historical_eval` (Foundation spec investment ladder: read-only scout ->
historical/replay eval -> paper -> real-account shadow -> ...). This file never places an
order: no wallet, no key, no signing, no CLOB client. It only GETs two public endpoints:
  Gamma  https://gamma-api.polymarket.com/markets        resolved markets + fee schedule
  CLOB   https://clob.polymarket.com/prices-history      historical token prices

Strategy replayed ("favorite at horizon"): H hours before a binary market's scheduled end
(markets already closed by then are skipped), if either
side's price is inside [band_lo, band_hi], buy that side as a taker and hold to resolution.
Per-trade net return per USDC spent = payout / (fill + fee) - 1, where
  fill = price + slippage            (history is last-trade/mid, not the ask we would pay)
  fee  = feeRate * fill * (1 - fill) per share, taker only
         (https://docs.polymarket.com/trading/fees: "fee = C x feeRate x p x (1 - p)")
Markets are sampled per UTC day by volume and de-duplicated to one market per event, so the
bootstrap CI is not dominated by one multi-outcome event. Statistical support = the 95%
bootstrap CI of the mean net return is entirely above zero.

Usage:
    python3 historical_eval.py [--days 60] [--per-day 20] [--horizon-hours 24]
        [--band 0.70,0.95] [--slippage 0.01] [--min-volume 5000] [--seed 7] [--out PATH]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import statistics
import sys
import time
from pathlib import Path

import requests

GAMMA = "https://gamma-api.polymarket.com/markets"
PRICES = "https://clob.polymarket.com/prices-history"
FEE_SOURCE = "https://docs.polymarket.com/trading/fees"
MAX_STALENESS_S = 6 * 3600


def _get(url: str, params: dict, attempts: int = 6):
    """GET with exponential backoff on 429/5xx/network errors; a 4xx other than 429 fails at once."""
    for attempt in range(attempts):
        try:
            r = requests.get(url, params=params, timeout=20)
            if r.status_code < 500 and r.status_code != 429:
                r.raise_for_status()
                return r.json()
        except requests.HTTPError:
            raise
        except requests.RequestException:
            if attempt == attempts - 1:
                raise
        time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"GET {url} failed after {attempts} attempts")


def parse_ts(value: str | None) -> float | None:
    if not value:
        return None
    s = value.strip().replace(" ", "T").replace("Z", "+00:00")
    if s.endswith("+00"):
        s += ":00"
    try:
        t = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return t.timestamp()


def fetch_markets(days: int, per_day: int, min_volume: float, today: dt.date,
                  offset_days: int = 0) -> list[dict]:
    out = []
    for back in range(offset_days + 1, offset_days + days + 1):
        day = today - dt.timedelta(days=back)
        out += _get(GAMMA, {
            "closed": "true", "limit": per_day, "order": "volumeNum", "ascending": "false",
            "volume_num_min": min_volume,
            "end_date_min": f"{day.isoformat()}T00:00:00Z",
            "end_date_max": f"{(day + dt.timedelta(days=1)).isoformat()}T00:00:00Z",
        })
        time.sleep(0.2)
    return out


def select_markets(raw: list[dict], horizon_h: float) -> tuple[list[dict], dict]:
    """Binary, cleanly resolved (1/0), fee schedule understood, open before entry, 1 per event."""
    funnel = {"fetched": len(raw), "not_binary_resolved": 0, "fee_unknown": 0,
              "too_young": 0, "closed_before_entry": 0, "duplicate_event": 0, "malformed": 0,
              "eligible": 0}
    seen, keep = set(), []
    for m in raw:
        try:
            _select_one(m, horizon_h, funnel, seen, keep)
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            funnel["malformed"] += 1
    funnel["eligible"] = len(keep)
    return keep, funnel


def _select_one(m: dict, horizon_h: float, funnel: dict, seen: set, keep: list) -> None:
    try:
        outcomes = json.loads(m.get("outcomes") or "[]")
        prices = json.loads(m.get("outcomePrices") or "[]")
        tokens = json.loads(m.get("clobTokenIds") or "[]")
    except (TypeError, ValueError):
        funnel["not_binary_resolved"] += 1
        return
    if len(outcomes) != 2 or len(tokens) != 2 or sorted(prices) != ["0", "1"]:
        funnel["not_binary_resolved"] += 1
        return
    sched = m.get("feeSchedule") or {}
    if m.get("feesEnabled") and (sched.get("exponent", 1) != 1 or sched.get("rate") is None):
        funnel["fee_unknown"] += 1
        return
    # Anchor entry to the SCHEDULED end, never to the actual close: a "will X happen by D"
    # market closes early exactly when X happens, so closedTime - H leaks the outcome.
    end = parse_ts(m.get("endDate"))
    closed = parse_ts(m.get("closedTime")) or end
    start = parse_ts(m.get("startDate"))
    if end is None or start is None or start > end - horizon_h * 3600 - 3600:
        funnel["too_young"] += 1
        return
    if closed < end - horizon_h * 3600:
        funnel["closed_before_entry"] += 1  # not tradeable at the scheduled entry time
        return
    close = end
    events = m.get("events") or [{}]
    key = events[0].get("id") or m.get("conditionId") or m.get("id")
    if key in seen:
        funnel["duplicate_event"] += 1
        return
    seen.add(key)
    keep.append({
        "id": m.get("id"), "question": m.get("question"), "close_ts": close,
        "yes_token": tokens[0], "yes_won": prices[0] == "1",
        "fee_rate": float(sched.get("rate") or 0) if m.get("feesEnabled") else 0.0,
    })


def price_at(history: list[dict], ts: float) -> float | None:
    """Last observed price at or before ts, if it is not staler than MAX_STALENESS_S."""
    best = None
    for pt in history:
        if pt["t"] <= ts and (best is None or pt["t"] > best["t"]):
            best = pt
    if best is None or ts - best["t"] > MAX_STALENESS_S:
        return None
    return float(best["p"])


def favorite_trade(p_yes: float, yes_won: bool, band: tuple[float, float],
                   fee_rate: float, slippage: float) -> dict | None:
    lo, hi = band
    if lo <= p_yes <= hi:
        side, p, won = "YES", p_yes, yes_won
    elif lo <= 1 - p_yes <= hi:
        side, p, won = "NO", 1 - p_yes, not yes_won
    else:
        return None
    fill = min(p + slippage, 0.999)
    fee = fee_rate * fill * (1 - fill)
    payout = 1.0 if won else 0.0
    return {"side": side, "entry_price": round(p, 4), "fill": round(fill, 4),
            "fee_per_share": round(fee, 6), "won": won,
            "gross_return": payout / p - 1, "net_return": payout / (fill + fee) - 1}


def summarize(returns: list[float], seed: int, n_boot: int = 2000,
              clusters: list | None = None) -> dict:
    """Mean, t-stat and percentile-bootstrap CI of the mean.

    With `clusters` (one key per return, e.g. the UTC close day) whole clusters are
    resampled, so same-day correlated trades do not narrow the CI.
    """
    n = len(returns)
    if n < 2:
        return {"n": n, "statistically_supported": False, "reason": "n<2"}
    mean, sd = statistics.fmean(returns), statistics.stdev(returns)
    rng = random.Random(seed)
    if clusters is None:
        groups = [[r] for r in returns]
    else:
        by_key: dict = {}
        for key, r in zip(clusters, returns):
            by_key.setdefault(key, []).append(r)
        groups = list(by_key.values())
    boots = []
    for _ in range(n_boot):
        sample = [r for g in rng.choices(groups, k=len(groups)) for r in g]
        boots.append(statistics.fmean(sample))
    boots.sort()
    lo, hi = boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1]
    return {"n": n, "clusters": len(groups), "mean": mean, "stdev": sd,
            "t_stat": mean / (sd / n ** 0.5) if sd else None,
            "win_rate": sum(r > 0 for r in returns) / n, "sum": sum(returns),
            "ci95": [lo, hi], "statistically_supported": lo > 0}


def robustness(trades: list[dict], seed: int) -> dict:
    """Day-clustered CI and leave-top-k-winners-out CIs: an edge that vanishes when
    two trades are removed is not an edge."""
    net = [t["net_return"] for t in trades]
    days = [dt.datetime.fromtimestamp(t["close_ts"], dt.timezone.utc).date().isoformat()
            for t in trades]
    order = sorted(range(len(net)), key=lambda i: net[i], reverse=True)
    out = {"day_clustered": summarize(net, seed, clusters=days)}
    for k in (1, 2, 3):
        keep = sorted(order[k:])
        out[f"drop_top_{k}"] = summarize([net[i] for i in keep], seed,
                                         clusters=[days[i] for i in keep])
    out["robustly_supported"] = all(v["statistically_supported"] for v in out.values())
    return out


def run(args) -> dict:
    band = tuple(float(x) for x in args.band.split(","))
    raw = fetch_markets(args.days, args.per_day, args.min_volume, dt.datetime.now(dt.timezone.utc).date(),
                        args.offset_days)
    markets, funnel = select_markets(raw, args.horizon_hours)
    funnel.update(no_price_at_entry=0, out_of_band=0, trades=0)
    trades = []
    for m in markets:
        entry = m["close_ts"] - args.horizon_hours * 3600
        hist = _get(PRICES, {"market": m["yes_token"], "startTs": int(entry - MAX_STALENESS_S),
                             "endTs": int(entry), "fidelity": 10}).get("history", [])
        time.sleep(0.1)
        p = price_at(hist, entry)
        if p is None:
            funnel["no_price_at_entry"] += 1
            continue
        t = favorite_trade(p, m["yes_won"], band, m["fee_rate"], args.slippage)
        if t is None:
            funnel["out_of_band"] += 1
            continue
        trades.append({"market_id": m["id"], "question": m["question"], "close_ts": m["close_ts"], "fee_rate": m["fee_rate"], **t})
    funnel["trades"] = len(trades)
    net = [t["net_return"] for t in trades]
    return {
        "venue": "polymarket", "rung": "historical_eval", "strategy": "favorite_at_horizon",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "params": {"days": args.days, "offset_days": args.offset_days, "per_day": args.per_day, "horizon_hours": args.horizon_hours,
                   "band": list(band), "slippage": args.slippage, "min_volume": args.min_volume,
                   "seed": args.seed},
        "funnel": funnel,
        "net": summarize(net, args.seed),
        "gross": summarize([t["gross_return"] for t in trades], args.seed),
        "robustness": robustness(trades, args.seed) if len(trades) > 4 else None,
        "calibration": {"mean_entry_price": statistics.fmean(t["entry_price"] for t in trades) if trades else None,
                        "realized_win_rate": sum(t["won"] for t in trades) / len(trades) if trades else None},
        "fee_source": FEE_SOURCE,
        "caveats": [
            "entry uses the last historical price <= entry time (<=6h stale), plus fixed slippage; real asks may be worse",
            "taker fee from each market's feeSchedule; model, cloud and gas costs are not included",
            "sample = top-volume markets per UTC end-date day, one per event; not the whole market",
            "resolved-market sampling can favour markets that resolved early; past results do not predict future",
            "no order was placed; this is a replay, not a paper or live fill",
        ],
        "trades": trades,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--per-day", type=int, default=20)
    ap.add_argument("--offset-days", type=int, default=0,
                    help="skip the most recent N days (held-out windows)")
    ap.add_argument("--horizon-hours", type=float, default=24)
    ap.add_argument("--band", default="0.70,0.95")
    ap.add_argument("--slippage", type=float, default=0.01)
    ap.add_argument("--min-volume", type=float, default=5000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out")
    args = ap.parse_args()
    report = run(args)
    text = json.dumps(report, indent=2)
    if args.out:
        out = Path(args.out).expanduser().resolve()
        repo = Path(__file__).resolve().parents[3]
        if out == repo or repo in out.parents:
            raise SystemExit("--out must be outside the repository")
        out.write_text(text)
    print(json.dumps({k: v for k, v in report.items() if k != "trades"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
