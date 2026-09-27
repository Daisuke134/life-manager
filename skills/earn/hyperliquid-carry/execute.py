"""The only module that sends signed Hyperliquid actions.

Every mutating call is followed by a state readback (spot balance, perp szi)
rather than trust in the order response, because the SDK returns
status="ok" envelopes even for rejected/unfilled orders and raises
ClientError/ServerError on transport failures. Nothing here ever reports
"flat" or "entered" without checking the account state that would prove it.
"""
from __future__ import annotations

import math
import uuid

MIN_NOTIONAL_USD = 11.0


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


def _floor(x: float, d: int) -> float:
    return math.floor(x * 10**d) / 10**d


def _spot_balance(info, address, coin) -> float:
    for b in info.spot_user_state(address)["balances"]:
        if b["coin"] == coin:
            return float(b["total"])
    return 0.0


def _perp_szi(info, address, perp) -> float:
    for p in info.user_state(address).get("assetPositions", []):
        pos = p.get("position", {})
        if pos.get("coin") == perp:
            return float(pos.get("szi", 0.0))
    return 0.0


def enter(ex, info, address, pair, leg_usd, lg) -> dict:
    iid = uuid.uuid4().hex
    lg.append("intent", intent_id=iid, action="enter", perp=pair.perp, spot=pair.spot, leg_usd=leg_usd)
    coin = pair.spot_token or pair.spot.split("/")[0]

    xfer = ex.usd_class_transfer(leg_usd + 1.0, True)
    if xfer.get("status") != "ok":
        return lg.append("receipt", intent_id=iid, result="failed", perp=pair.perp, reason="transfer_failed")
    lev = ex.update_leverage(1, pair.perp, True)
    if lev.get("status") != "ok":
        return lg.append("receipt", intent_id=iid, result="failed", perp=pair.perp, reason="leverage_failed")

    px = float(info.all_mids()[pair.spot])
    d = min(_sz_decimals(info, pair.spot), _sz_decimals(info, pair.perp))
    order_sz = _floor(leg_usd / px, d)
    if order_sz * px < MIN_NOTIONAL_USD:
        return lg.append("receipt", intent_id=iid, result="failed", perp=pair.perp, reason="below_min_notional")

    spot_sz = _filled(ex.market_open(pair.spot, True, order_sz))
    if spot_sz <= 0:
        return lg.append("receipt", intent_id=iid, result="failed", perp=pair.perp, reason="spot_not_filled")

    exc_name = None
    entered, szi, bal = False, 0.0, 0.0
    try:
        # Hedge off the balance actually received (buy fees are taken in the
        # base asset), never off the order size we asked for. (C1)
        hedge_sz = _floor(_spot_balance(info, address, coin), d)
        ex.market_open(pair.perp, False, hedge_sz)
        szi = _perp_szi(info, address, pair.perp)
        bal = _spot_balance(info, address, coin)
        floored_bal = _floor(bal, d)
        entered = szi < 0 and abs(-szi - floored_bal) < 10**-d + 1e-9
    except Exception as e:  # SDK ClientError/ServerError/network — never trust an unread state (C2)
        exc_name = type(e).__name__

    if entered:
        return lg.append("receipt", intent_id=iid, result="entered", perp=pair.perp, spot=pair.spot,
                         spot_sz=bal, perp_szi=szi, entry_px=px)

    # Not hedged (mismatch or exception): unwind, then prove flat before saying so.
    try:
        szi = _perp_szi(info, address, pair.perp)
        if szi != 0:
            ex.market_close(pair.perp)
        sell_sz = _floor(_spot_balance(info, address, coin), d)
        if sell_sz > 0:
            ex.market_open(pair.spot, False, sell_sz)
    except Exception as e:
        exc_name = exc_name or type(e).__name__

    szi = _perp_szi(info, address, pair.perp)
    bal = _spot_balance(info, address, coin)
    if szi == 0 and _floor(bal, d) * px < 1.0:
        return lg.append("receipt", intent_id=iid, result="partial", perp=pair.perp, reason="flat", exc=exc_name)
    return lg.append("receipt", intent_id=iid, result="unhedged", perp=pair.perp,
                     spot_sz=bal, perp_szi=szi, exc=exc_name)


def exit(ex, info, address, pair, lg) -> dict:
    iid = uuid.uuid4().hex
    lg.append("intent", intent_id=iid, action="exit", perp=pair.perp, spot=pair.spot)
    coin = pair.spot_token or pair.spot.split("/")[0]

    ex.market_close(pair.perp)  # may return None (SDK: no open position) — readback decides, not the response (C3/I3)
    szi = _perp_szi(info, address, pair.perp)
    if szi != 0:
        return lg.append("receipt", intent_id=iid, result="partial", perp=pair.perp, reason="perp_not_flat")

    d = _sz_decimals(info, pair.spot)
    sell_sz = _floor(_spot_balance(info, address, coin), d)  # floored, never raw fee-dust balance (C4)
    if sell_sz > 0:
        ex.market_open(pair.spot, False, sell_sz)

    withdrawable = float(info.user_state(address).get("withdrawable", 0.0))
    if withdrawable > 0:
        ex.usd_class_transfer(withdrawable, False)

    remaining = _floor(_spot_balance(info, address, coin), d)
    result = "exited" if remaining == 0 else "partial"
    return lg.append("receipt", intent_id=iid, result=result, perp=pair.perp)
