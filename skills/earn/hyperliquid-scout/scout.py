#!/usr/bin/env python3
"""Read-only Hyperliquid scout: ranks perp assets by 24h notional volume.

POST https://api.hyperliquid.xyz/info {"type":"metaAndAssetCtxs"} only.
No keys, no signing, no /exchange calls.
"""
import argparse
import json
import time
import urllib.error
import urllib.request

INFO_URL = "https://api.hyperliquid.xyz/info"


def post_info(body, retries=6):
    """POST /info; retries 429/5xx/network errors with exponential backoff, other 4xx fail at once."""
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        INFO_URL, data=data, headers={"Content-Type": "application/json"}
    )
    last_err = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise
            last_err = e
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = e
        time.sleep(min(2 ** attempt, 30))
    raise last_err


def rank_assets(meta, ctxs, top):
    """Pure function: rank non-delisted assets by dayNtlVlm. Testable without HTTP."""
    universe = meta["universe"]
    rows = []
    for asset, ctx in zip(universe, ctxs):
        if asset.get("isDelisted"):
            continue
        mark_px = float(ctx["markPx"]) if ctx.get("markPx") is not None else None
        mid_px = float(ctx["midPx"]) if ctx.get("midPx") is not None else None
        oi = float(ctx["openInterest"])
        day_ntl_vlm = float(ctx["dayNtlVlm"])
        funding_hourly = float(ctx["funding"])
        prev_day_px = float(ctx["prevDayPx"])
        impact_spread_bps = None
        impact_pxs = ctx.get("impactPxs")
        if impact_pxs and mid_px:
            bid, ask = float(impact_pxs[0]), float(impact_pxs[1])
            impact_spread_bps = (ask - bid) / mid_px * 1e4
        day_change_pct = None
        if mark_px is not None and prev_day_px:
            day_change_pct = (mark_px / prev_day_px - 1) * 100
        rows.append(
            {
                "coin": asset["name"],
                "mark_px": mark_px,
                "day_ntl_vlm": day_ntl_vlm,
                "open_interest_usd": oi * mark_px if mark_px is not None else None,
                "funding_hourly": funding_hourly,
                "funding_apr": funding_hourly * 24 * 365,
                "impact_spread_bps": impact_spread_bps,
                "day_change_pct": day_change_pct,
            }
        )
    rows.sort(key=lambda r: r["day_ntl_vlm"], reverse=True)
    return rows[:top]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=10)
    args = ap.parse_args()

    meta, ctxs = post_info({"type": "metaAndAssetCtxs"})
    assets = rank_assets(meta, ctxs, args.top)
    out = {
        "venue": "hyperliquid",
        "rung": "read_only_scout",
        "ts": time.time(),
        "assets": assets,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
