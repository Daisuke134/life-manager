"""capafy_profit_report.py -- one Japanese Telegram block: money that reaches the bank.

Goal metric (SSOT 2026-09-29): profit = creator earnings (after Capafy's cut) - model API cost.
Reads the hourly reconcile snapshot only; never calls Capafy or OpenRouter itself.
"""
from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path

SNAPSHOT = Path.home() / ".local/state/life-manager/state/capafy-hourly-reconcile.json"


def _d(value) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def build_report(snap: dict, top: int = 8) -> str:
    money = snap.get("money") or {}
    gross = _d(money.get("gross_usd"))
    earned = _d(money.get("creator_earnings_usd"))
    share = earned / gross if gross else Decimal("0")
    api_month = _d((snap.get("openrouter") or {}).get("data", {}).get("usage_monthly"))

    names, cost = {}, {}
    for row in (snap.get("usage") or {}).get("agents") or []:
        aid = str(row.get("agent_id"))
        names[aid] = row.get("name") or aid
        cost[aid] = _d(row.get("estimated_model_cost_usd"))
    sales = {}
    for aid, data in ((snap.get("traffic_sources") or {}).get("by_agent") or {}).items():
        rows = (data.get("last_30d") or {}).get("by_source") or []
        sales[str(aid)] = sum((_d(r.get("sales_usd")) for r in rows), Decimal("0"))

    rows = []
    for aid in set(sales) | set(cost):
        take = sales.get(aid, Decimal("0")) * share
        rows.append((take - cost.get(aid, Decimal("0")), take, cost.get(aid, Decimal("0")), names.get(aid, aid)))
    rows = [r for r in rows if r[1] or r[2]]
    rows.sort(key=lambda r: r[0], reverse=True)

    lines = [
        f"Capafy 利益（銀行に入る額）{snap.get('observed_at', '')}",
        f"累計の取り分 ${earned:.2f}（売上 ${gross:.2f}）/ 今月の API 実費 ${api_month:.2f}"
        f" → 差し引き ${earned - api_month:.2f}",
        f"未払い残高 ${_d(money.get('balance_pending_usd')):.2f} / 振込可能 ${_d(money.get('balance_payout_usd')):.2f}",
        "スキル別 30日（取り分 − モデル費用 = 利益）:",
    ]
    for profit, take, spent, name in rows[:top]:
        lines.append(f"・{str(name)[:28]}: ${take:.2f} − ${spent:.2f} = ${profit:+.2f}")
    losers = [r for r in rows if r[0] < 0]
    if losers:
        lines.append(f"赤字スキル {len(losers)} 本（価格かモデルを直す対象）")
    return "\n".join(lines)


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else SNAPSHOT
    print(build_report(json.loads(path.read_text(encoding="utf-8"))))
    return 0


if __name__ == "__main__":
    demo = {"money": {"gross_usd": "10", "creator_earnings_usd": "8"},
            "openrouter": {"data": {"usage_monthly": 3}},
            "usage": {"agents": [{"agent_id": "a", "name": "A", "estimated_model_cost_usd": "5"}]},
            "traffic_sources": {"by_agent": {"a": {"last_30d": {"by_source": [{"sales_usd": "10"}]}}}}}
    out = build_report(demo)
    assert "差し引き $5.00" in out and "・A: $8.00 − $5.00 = $+3.00" in out, out
    sys.exit(main())
