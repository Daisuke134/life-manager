"""The only module that sends signed Hyperliquid actions."""
from __future__ import annotations

import math
import uuid


def _filled(resp) -> float:
    try:
        st = resp["response"]["data"]["statuses"][0]
        return float(st["filled"]["totalSz"]) if "filled" in st else 0.0
    except (KeyError, IndexError, TypeError):
        return 0.0


def _sz_decimals(info, name) -> int:
    if hasattr(info, "asset_to_sz_decimals") and hasattr(info, "name_to_asset"):
        return info.asset_to_sz_decimals[info.name_to_asset(name)]
    return 2


def enter(ex, info, address, pair, leg_usd, lg) -> dict:
    iid = uuid.uuid4().hex
    lg.append("intent", intent_id=iid, action="enter", perp=pair.perp, spot=pair.spot, leg_usd=leg_usd)
    ex.usd_class_transfer(leg_usd + 1.0, True)
    ex.update_leverage(1, pair.perp, True)
    px = float(info.all_mids()[pair.spot])
    d = min(_sz_decimals(info, pair.spot), _sz_decimals(info, pair.perp))
    order_sz = math.floor(leg_usd / px * 10**d) / 10**d
    spot_sz = _filled(ex.market_open(pair.spot, True, order_sz))
    if spot_sz <= 0:
        return lg.append("receipt", intent_id=iid, result="failed", perp=pair.perp, reason="spot_not_filled")
    perp_sz = _filled(ex.market_open(pair.perp, False, spot_sz))
    if perp_sz < spot_sz:
        ex.market_open(pair.spot, False, spot_sz - perp_sz)  # never leave an unhedged long
        if perp_sz > 0:
            ex.market_close(pair.perp, perp_sz)
        return lg.append("receipt", intent_id=iid, result="partial", perp=pair.perp,
                         spot_sz=spot_sz, perp_sz=perp_sz)
    return lg.append("receipt", intent_id=iid, result="entered", perp=pair.perp, spot=pair.spot,
                     spot_sz=spot_sz, perp_sz=perp_sz, entry_px=px)


def exit(ex, info, address, pair, lg) -> dict:
    iid = uuid.uuid4().hex
    lg.append("intent", intent_id=iid, action="exit", perp=pair.perp, spot=pair.spot)
    closed = _filled(ex.market_close(pair.perp))
    base = pair.spot_token or pair.spot.split("/")[0]
    held = sum(float(b["total"]) for b in info.spot_user_state(address)["balances"] if b["coin"] == base)
    sold = _filled(ex.market_open(pair.spot, False, held)) if held > 0 else 0.0
    ex.usd_class_transfer(float(info.user_state(address)["withdrawable"]), False)
    result = "exited" if sold >= held else "partial"
    return lg.append("receipt", intent_id=iid, result=result, perp=pair.perp, perp_closed=closed, spot_sold=sold)
