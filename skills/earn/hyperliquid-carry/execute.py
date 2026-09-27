"""The only module that sends signed Hyperliquid actions.

Every mutating call is followed by a state readback (spot balance, perp szi)
rather than trust in the order response, because the SDK returns
status="ok" envelopes even for rejected/unfilled orders and raises
ClientError/ServerError on transport failures. Nothing here ever reports
"flat" or "entered" without checking the account state that would prove it,
and nothing here ever assumes an unwind leg (close/sell) actually worked
without re-reading state after it.
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


def _safe_perp_szi(info, address, perp):
    try:
        return _perp_szi(info, address, perp)
    except Exception:
        return None


def _safe_spot_balance(info, address, coin):
    try:
        return _spot_balance(info, address, coin)
    except Exception:
        return None


def _xfer_back(ex, info, address) -> str:
    """Best-effort return of perp margin to spot after a failed/aborted entry (N3)."""
    try:
        withdrawable = float(info.user_state(address).get("withdrawable", 0.0))
    except Exception:
        return "readback_failed"
    if withdrawable <= 0:
        return "skipped"
    try:
        return ex.usd_class_transfer(withdrawable, False).get("status", "unknown")
    except Exception as e:
        return f"error:{type(e).__name__}"


def enter(ex, info, address, pair, leg_usd, lg) -> dict:
    iid = uuid.uuid4().hex
    lg.append("intent", intent_id=iid, action="enter", perp=pair.perp, spot=pair.spot,
              spot_token=pair.spot_token, leg_usd=leg_usd)
    coin = pair.spot_token or pair.spot.split("/")[0]

    # Size and the min-notional check run before any transfer: a rejected plan
    # should never leave margin stranded on the perp side to unwind. (N3)
    px = float(info.all_mids()[pair.spot])
    d = min(_sz_decimals(info, pair.spot), _sz_decimals(info, pair.perp))
    order_sz = _floor(leg_usd / px, d)
    if order_sz * px < MIN_NOTIONAL_USD:
        return lg.append("receipt", intent_id=iid, result="failed", perp=pair.perp, reason="below_min_notional")

    xfer = ex.usd_class_transfer(leg_usd + 1.0, True)
    if xfer.get("status") != "ok":
        return lg.append("receipt", intent_id=iid, result="failed", perp=pair.perp, reason="transfer_failed")

    lev = ex.update_leverage(1, pair.perp, True)
    if lev.get("status") != "ok":
        return lg.append("receipt", intent_id=iid, result="failed", perp=pair.perp, reason="leverage_failed",
                         xfer_back_status=_xfer_back(ex, info, address))

    try:
        spot_sz = _filled(ex.market_open(pair.spot, True, order_sz))
    except Exception as e:
        # The exchange may have accepted the order even though the call raised
        # (timeout/network drop) — never claim "failed" here, we don't know. (N2)
        return lg.append("receipt", intent_id=iid, result="unhedged", perp=pair.perp,
                         spot_sz=_safe_spot_balance(info, address, coin),
                         perp_szi=_safe_perp_szi(info, address, pair.perp), error=type(e).__name__)

    if spot_sz <= 0:
        return lg.append("receipt", intent_id=iid, result="failed", perp=pair.perp, reason="spot_not_filled",
                         xfer_back_status=_xfer_back(ex, info, address))

    error = None
    szi, bal = None, None
    try:
        # Hedge off the balance actually received (buy fees are taken in the
        # base asset), never off the order size we asked for. (C1)
        hedge_sz = _floor(_spot_balance(info, address, coin), d)
        ex.market_open(pair.perp, False, hedge_sz)
        szi = _perp_szi(info, address, pair.perp)
        bal = _spot_balance(info, address, coin)
        floored_bal = _floor(bal, d)
        if szi < 0 and abs(-szi - floored_bal) < 10**-d + 1e-9:
            return lg.append("receipt", intent_id=iid, result="entered", perp=pair.perp, spot=pair.spot,
                             spot_sz=bal, perp_szi=szi, entry_px=px)
    except Exception as e:  # SDK ClientError/ServerError/network (C2)
        error = type(e).__name__

    # Not hedged (mismatch or exception): unwind, then prove flat before saying so.
    try:
        szi = _perp_szi(info, address, pair.perp)
        if szi != 0:
            ex.market_close(pair.perp)
            szi = _perp_szi(info, address, pair.perp)  # (N1) re-read — never assume the close worked
        if szi == 0:
            sell_sz = _floor(_spot_balance(info, address, coin), d)
            if sell_sz > 0:
                ex.market_open(pair.spot, False, sell_sz)
        bal = _spot_balance(info, address, coin)
    except Exception as e:  # an unwind leg or its readback failing (C2/N2)
        error = error or type(e).__name__
        szi = _safe_perp_szi(info, address, pair.perp)
        bal = _safe_spot_balance(info, address, coin)

    if szi == 0 and bal is not None and _floor(bal, d) * px < 1.0:
        return lg.append("receipt", intent_id=iid, result="partial", perp=pair.perp, reason="flat", error=error,
                         xfer_back_status=_xfer_back(ex, info, address))
    return lg.append("receipt", intent_id=iid, result="unhedged", perp=pair.perp,
                     spot_sz=bal, perp_szi=szi, error=error)


def exit(ex, info, address, pair, lg, resolves_intent_id: str | None = None) -> dict:
    iid = uuid.uuid4().hex
    intent_fields = {"spot_token": pair.spot_token}
    if resolves_intent_id:
        intent_fields["resolves_intent_id"] = resolves_intent_id
    lg.append("intent", intent_id=iid, action="exit", perp=pair.perp, spot=pair.spot,
              **intent_fields)
    coin = pair.spot_token or pair.spot.split("/")[0]

    ex.market_close(pair.perp)  # may return None (SDK: no open position) — readback decides, not the response (C3/I3)
    szi = _perp_szi(info, address, pair.perp)
    if szi != 0:
        return lg.append("receipt", intent_id=iid, result="partial", perp=pair.perp, reason="perp_not_flat",
                         xfer_status="not_attempted")

    d = _sz_decimals(info, pair.spot)
    sell_sz = _floor(_spot_balance(info, address, coin), d)  # floored, never raw fee-dust balance (C4)
    if sell_sz > 0:
        ex.market_open(pair.spot, False, sell_sz)

    withdrawable = float(info.user_state(address).get("withdrawable", 0.0))
    xfer_status = "skipped"
    if withdrawable > 0:
        xfer_status = ex.usd_class_transfer(withdrawable, False).get("status", "unknown")

    remaining = _floor(_spot_balance(info, address, coin), d)
    result = "exited" if remaining == 0 else "partial"
    fields = {"xfer_status": xfer_status}
    if result == "exited" and resolves_intent_id:
        fields["resolves_intent_id"] = resolves_intent_id
    return lg.append("receipt", intent_id=iid, result=result, perp=pair.perp, **fields)
