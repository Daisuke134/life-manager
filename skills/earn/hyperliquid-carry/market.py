"""Read-only Hyperliquid market/account snapshot."""
from __future__ import annotations

import json
import statistics
import time
import urllib.error
import urllib.request

from policy import Pair

INFO_URL = "https://api.hyperliquid.xyz/info"


def post_info(body: dict, retries: int = 6):
    req = urllib.request.Request(INFO_URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    last = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code != 429 and e.code < 500:
                raise
            last = e
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
        time.sleep(min(2 ** attempt, 30))
    raise last


def _spot_marks(post) -> tuple[dict, list]:
    meta, ctxs = post({"type": "spotMetaAndAssetCtxs"})
    names = {t["index"]: t["name"] for t in meta["tokens"]}
    rows = []
    for u, c in zip(meta["universe"], ctxs):
        base, quote = names[u["tokens"][0]], names[u["tokens"][1]]
        if quote == "USDC":
            rows.append((u["name"], base, float(c.get("dayNtlVlm") or 0), float(c.get("markPx") or 0)))
    return {base: mark for _, base, _, mark in rows}, rows


def pairs(post, now_ms: int) -> list[Pair]:
    meta, _ = post({"type": "metaAndAssetCtxs"})
    perps = {u["name"] for u in meta["universe"]}
    _, rows = _spot_marks(post)
    out = []
    for spot_name, base, vol, _ in rows:
        perp = base if base in perps else (base[1:] if base.startswith("U") and base[1:] in perps else None)
        if perp is None:
            continue
        hist = post({"type": "fundingHistory", "coin": perp, "startTime": now_ms - 24 * 3600 * 1000})
        rates = [float(h["fundingRate"]) for h in hist]
        if rates:
            out.append(Pair(perp, spot_name, vol, statistics.fmean(rates) * 24 * 365, base))
    return out


def equity(post, address: str) -> float:
    perp = float(post({"type": "clearinghouseState", "user": address})["marginSummary"]["accountValue"])
    marks, _ = _spot_marks(post)
    spot = 0.0
    for b in post({"type": "spotClearinghouseState", "user": address})["balances"]:
        qty = float(b["total"])
        spot += qty if b["coin"] == "USDC" else qty * marks.get(b["coin"], 0.0)
    return perp + spot
