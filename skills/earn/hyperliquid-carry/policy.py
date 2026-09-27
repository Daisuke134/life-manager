"""Pure carry decisions: no I/O, no clock, no keys."""
from __future__ import annotations

from dataclasses import dataclass
import math


HARD_MAX_LEG_USD = 25.0


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
    round_trip_cost: float = 0.0023
    min_spot_vol_usd: float = 150_000.0

    def __post_init__(self):
        if not math.isfinite(self.max_leg_usd) or not 0 < self.max_leg_usd <= HARD_MAX_LEG_USD:
            raise ValueError(f"max_leg_usd must be finite and within (0, {HARD_MAX_LEG_USD}]")


def decide(pairs, position, equity, day_start_equity, peak_equity, caps: Caps) -> dict:
    if day_start_equity > 0 and equity <= day_start_equity * (1 - caps.day_loss):
        return {"action": "halt", "pair": None, "leg_usd": 0.0, "reason": "day_loss_cap"}
    if peak_equity > 0 and equity <= peak_equity * (1 - caps.drawdown):
        return {"action": "halt", "pair": None, "leg_usd": 0.0, "reason": "drawdown_cap"}
    if position:
        current = next((p for p in pairs if p.perp == position), None)
        if current is None or current.funding_apr_24h < caps.exit_apr:
            return {"action": "exit", "pair": current, "leg_usd": 0.0, "reason": "funding_decayed"}
        return {"action": "hold", "pair": current, "leg_usd": 0.0, "reason": "carry_positive"}
    liquid = [p for p in pairs if p.spot_vol_usd >= caps.min_spot_vol_usd]
    worth = [p for p in liquid
             if p.funding_apr_24h * caps.enter_hold_days / 365 > caps.round_trip_cost]
    if not worth:
        return {"action": "idle", "pair": None, "leg_usd": 0.0, "reason": "no_carry_beats_cost"}
    best = max(worth, key=lambda p: p.funding_apr_24h)
    leg = min(caps.max_leg_usd, int(equity * 0.48))
    if leg < caps.min_leg_usd:
        return {"action": "idle", "pair": best, "leg_usd": 0.0, "reason": "equity_below_min_leg"}
    return {"action": "enter", "pair": best, "leg_usd": float(leg), "reason": "carry_beats_cost"}
