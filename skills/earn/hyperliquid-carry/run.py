#!/usr/bin/env python3
"""One wake of the Hyperliquid carry loop."""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import execute  # noqa: E402
import ledger  # noqa: E402
import market  # noqa: E402
import policy  # noqa: E402


def _recorded_pair(lg, perp):
    if not perp:
        return None
    for row in reversed(lg.rows()):
        if row["kind"] == "intent" and row.get("perp") == perp and row.get("spot"):
            spot_token = row.get("spot_token", "")
            if row["spot"].startswith("@") and not spot_token:
                continue
            return SimpleNamespace(perp=perp, spot=row["spot"], spot_token=spot_token)
    return None


def _exit_target(pairs, lg, perp):
    return next((p for p in pairs if p.perp == perp), None) or _recorded_pair(lg, perp)


def _decision(d):
    return {k: (v.__dict__ if hasattr(v, "__dict__") else v) for k, v in d.items()}


def _caps_from_env(environ) -> policy.Caps:
    return policy.Caps(max_leg_usd=float(environ.get("HL_CARRY_MAX_LEG_USD", "25")))


def _report_once(lg, today, text, send) -> None:
    if not any(r["kind"] == "report" and r.get("day") == today for r in lg.rows()):
        result = send(text)
        if isinstance(result, subprocess.CompletedProcess):
            result.check_returncode()
        lg.append("report", day=today)


def wake(post, make_clients, lg, address, caps, live, today, send) -> dict:
    eq = market.equity(post, address)
    lg.mark_equity(eq)
    day_start, peak = lg.risk_state(today)
    net_pnl_usd = round(eq - day_start, 6)
    pairs = market.pairs(post, int(time.time() * 1000))
    pos = lg.position()
    open_intents = [r for r in lg.open_intents() if r.get("action") in ("enter", "exit")]
    if open_intents or lg.needs_unwind():
        intent = open_intents[-1] if open_intents else {}
        perp = intent.get("perp") or pos
        target = _exit_target(pairs, lg, perp)
        reason = "open_intent_or_unhedged" if target else "reconciliation_pair_unavailable"
        d = {"action": "reconcile_exit", "pair": target, "leg_usd": 0.0, "reason": reason}
        receipt = None
        if live and target is not None:
            ex, info = make_clients()
            receipt = execute.exit(ex, info, address, target, lg,
                                   resolves_intent_id=intent.get("intent_id"))
        elif target is None:
            receipt = {"result": "reconciliation_pending", "reason": "pair_unavailable", "perp": perp}
        _report_once(lg, today,
                     f"Hyperliquid carry {today}: equity ${eq:.2f}, account-equity net P&L ${net_pnl_usd:.2f} "
                     f"(reconcile exit; live={'yes' if live else 'no'}). Address {address}",
                     send)
        return {"decision": _decision(d), "equity": eq, "net_pnl_usd": net_pnl_usd, "receipt": receipt}

    d = policy.decide(pairs, pos, eq, day_start, peak, caps)
    receipt = None
    if live:
        if d["action"] == "enter":
            ex, info = make_clients()
            receipt = execute.enter(ex, info, address, d["pair"], d["leg_usd"], lg)
        elif d["action"] in ("exit", "halt") and pos:
            target = d["pair"] or _exit_target(pairs, lg, pos)
            if target is None:
                receipt = {"result": "reconciliation_pending", "reason": "pair_unavailable", "perp": pos}
            else:
                ex, info = make_clients()
                receipt = execute.exit(ex, info, address, target, lg)
    apr = f"{d['pair'].funding_apr_24h:.1%}" if d.get("pair") else "-"
    _report_once(lg, today,
                 f"Hyperliquid carry {today}: equity ${eq:.2f}, account-equity net P&L ${net_pnl_usd:.2f} "
                 f"(day start ${day_start:.2f}, peak ${peak:.2f}), "
                 f"position {lg.position() or 'none'}, decision {d['action']} ({d['reason']}), funding {apr}, "
                 f"live={'yes' if live else 'no'}. Address {address}", send)
    return {"decision": _decision(d), "equity": eq, "net_pnl_usd": net_pnl_usd, "receipt": receipt}


def main() -> int:
    caps = _caps_from_env(os.environ)
    import wallet
    from hyperliquid.exchange import Exchange
    from hyperliquid.info import Info
    from hyperliquid.utils import constants

    acct = wallet.load_or_create()
    state = Path(os.environ.get("LIFE_MANAGER_STATE_ROOT",
                                Path.home() / ".local/state/life-manager/hyperliquid-carry"))
    lg = ledger.Ledger(state / "journal.jsonl")
    live = os.environ.get("HL_CARRY_LIVE") == "1"
    tg = HERE.parent.parent / "_shared" / "send-telegram.sh"
    send = lambda text: subprocess.run(["bash", str(tg), text], capture_output=True, timeout=30, check=True)
    make = lambda: (Exchange(acct, constants.MAINNET_API_URL), Info(constants.MAINNET_API_URL, skip_ws=True))
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    result = wake(market.post_info, make, lg, acct.address, caps, live, today, send)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
