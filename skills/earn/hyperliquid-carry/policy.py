"""Pure, bounded carry decisions: no I/O, no clock, no keys."""
from __future__ import annotations

from dataclasses import dataclass
import math
from collections.abc import Mapping


HARD_MAX_LEG_USD = 25.0
ALLOWED_PERPS = frozenset({"BTC", "ETH"})
ALLOWED_SPOT_SUFFIX = "/USDC"


@dataclass(frozen=True)
class Pair:
    perp: str
    spot: str
    spot_vol_usd: float
    funding_apr_24h: float
    spot_token: str = ""  # spot balance coin name, e.g. "UZEC" for pair "@272"


@dataclass(frozen=True)
class Caps:
    max_leg_usd: float = 25.0
    day_loss: float = 0.05
    drawdown: float = 0.20
    min_leg_usd: float = 11.0
    enter_hold_days: float = 14.0
    exit_apr: float = 0.05
    # Measured entry/exit fee plus slippage fraction for one complete carry.
    round_trip_cost: float | None = 0.0023
    # A bridge is not needed on every rebalance.  ``None`` means no measured
    # value exists and therefore blocks a new position.
    bridge_cost_usd: float | None = 0.0
    # Production leaves this unset until model billing is joined to the run.
    model_cost_usd: float | None = None
    net_buffer_usd: float = 0.05
    min_spot_vol_usd: float = 150_000.0

    def __post_init__(self):
        if not math.isfinite(self.max_leg_usd) or not 0 < self.max_leg_usd <= HARD_MAX_LEG_USD:
            raise ValueError(f"max_leg_usd must be finite and within (0, {HARD_MAX_LEG_USD}]")
        for name in ("day_loss", "drawdown", "min_leg_usd", "enter_hold_days", "exit_apr",
                     "net_buffer_usd", "min_spot_vol_usd"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        for name in ("round_trip_cost", "bridge_cost_usd", "model_cost_usd"):
            value = getattr(self, name)
            if value is not None and (not math.isfinite(value) or value < 0):
                raise ValueError(f"{name} must be finite and non-negative or None")


def decide(pairs, position, equity, day_start_equity, peak_equity, caps: Caps) -> dict:
    if day_start_equity > 0 and equity <= day_start_equity * (1 - caps.day_loss):
        return {"action": "halt", "pair": None, "leg_usd": 0.0, "reason": "day_loss_cap"}
    if peak_equity > 0 and equity <= peak_equity * (1 - caps.drawdown):
        return {"action": "halt", "pair": None, "leg_usd": 0.0, "reason": "drawdown_cap"}
    if position:
        details = position if isinstance(position, Mapping) else {}
        position_name = details.get("perp", position) if isinstance(position, Mapping) else position
        current = next((p for p in pairs if p.perp == position_name), None)
        if current is None:
            return {"action": "exit", "pair": current, "leg_usd": 0.0, "reason": "official_state_missing"}
        if not _allowlisted(current):
            return {"action": "halt", "pair": current, "leg_usd": 0.0,
                    "reason": "position_not_allowlisted"}
        if details.get("effect_unknown") is True:
            return {"action": "halt", "pair": current, "leg_usd": 0.0, "reason": "effect_unknown"}
        if details.get("hedge_mismatch") is True or details.get("hedged") is False:
            return {"action": "exit", "pair": current, "leg_usd": 0.0, "reason": "hedge_mismatch"}
        if not _finite(current.funding_apr_24h):
            return {"action": "exit", "pair": current, "leg_usd": 0.0,
                    "reason": "official_state_missing"}
        if current.funding_apr_24h < caps.exit_apr:
            return {"action": "exit", "pair": current, "leg_usd": 0.0, "reason": "funding_decayed"}
        if not _costs_complete(caps):
            return {"action": "exit", "pair": current, "leg_usd": 0.0,
                    "reason": "cost_model_incomplete"}
        return {"action": "hold", "pair": current, "leg_usd": 0.0, "reason": "carry_positive"}
    allowlisted = [p for p in pairs if _allowlisted(p)]
    if not allowlisted:
        return {"action": "idle", "pair": None, "leg_usd": 0.0,
                "reason": "pair_not_allowlisted"}
    liquid = [p for p in allowlisted
              if _finite(p.spot_vol_usd) and p.spot_vol_usd >= caps.min_spot_vol_usd]
    if not liquid:
        return {"action": "idle", "pair": None, "leg_usd": 0.0, "reason": "no_liquid_pair"}
    if not _costs_complete(caps):
        return {"action": "idle", "pair": None, "leg_usd": 0.0,
                "reason": "cost_model_incomplete"}
    leg = min(caps.max_leg_usd, int(equity * 0.48))
    if leg < caps.min_leg_usd:
        return {"action": "idle", "pair": max(liquid, key=lambda p: p.funding_apr_24h),
                "leg_usd": 0.0, "reason": "equity_below_min_leg"}
    worth = [p for p in liquid if _net_carry_usd(p, leg, caps) > 0]
    if not worth:
        return {"action": "idle", "pair": None, "leg_usd": 0.0, "reason": "no_carry_beats_cost"}
    best = max(worth, key=lambda p: (_net_carry_usd(p, leg, caps), p.perp))
    return {"action": "enter", "pair": best, "leg_usd": float(leg), "reason": "carry_beats_cost"}


def _finite(value: float) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _allowlisted(pair: Pair) -> bool:
    if pair.perp not in ALLOWED_PERPS:
        return False
    if pair.spot == f"{pair.perp}{ALLOWED_SPOT_SUFFIX}":
        return True
    # Hyperliquid can expose the BTC/ETH spot market as an indexed name
    # (`@142`/`@151`) with a U-prefixed token in spot balances.
    indexed = {"BTC": ("@142", "UBTC"), "ETH": ("@151", "UETH")}
    indexed_spot, indexed_token = indexed[pair.perp]
    return pair.spot == indexed_spot and pair.spot_token == indexed_token


def _costs_complete(caps: Caps) -> bool:
    return all(value is not None and _finite(value)
               for value in (caps.round_trip_cost, caps.bridge_cost_usd, caps.model_cost_usd,
                             caps.net_buffer_usd))


def _net_carry_usd(pair: Pair, leg_usd: float, caps: Caps) -> float:
    gross = float(pair.funding_apr_24h) * caps.enter_hold_days / 365.0 * leg_usd
    cost = (float(caps.round_trip_cost) * leg_usd
            + float(caps.bridge_cost_usd) + float(caps.model_cost_usd)
            + caps.net_buffer_usd)
    return gross - cost
