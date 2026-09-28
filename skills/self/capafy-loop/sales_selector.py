#!/usr/bin/env python3
"""sales_selector.py (A5 / #9) — rank OUR OWN Capafy listings by real sales signal so the build
loop doubles down on what actually sells, instead of picking the next skill by blind judgment.

Data reality (measured 2026-07-19): the seller endpoint GET /agent/agents returns ONLY our own
listings (26), each with fields: sales, recentSales, rating, ratingCount, reviewCount, agentStatus.
There is NO reliable marketplace-wide ranking endpoint (POST /agent/agents/search is server-broken).
So this ranks OUR listings. When we have zero sales signal it says so honestly (no fabrication) and
tells the build loop to fall back to BEST_PRACTICES marketplace-winner research.

Output: ~/.local/state/life-manager/state/capafy-sales-ranking.json + a human summary printed to stdout.
The build loop reads the JSON in STEP2 to prioritize the winning category for the next listing.
"""
import json, os, subprocess, sys
from pathlib import Path

REPO_ROOT = Path(os.environ.get("LIFE_MANAGER_REPO", Path(__file__).resolve().parents[3]))
CAPAFY_HTTP = str(REPO_ROOT / "skills/capafy-autopublish/vendor/capafy-user/scripts/capafy_http.py")
STATE_HOME = Path(os.environ.get("LIFE_MANAGER_STATE_HOME", Path.home() / ".local/state/life-manager"))
OUT = STATE_HOME / "state/capafy-sales-ranking.json"
COMPANY_RECEIPT = STATE_HOME / "state/capafy-hourly-reconcile.json"


def _num(v):
    if isinstance(v, list):
        return sum(_num(item) for item in v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _fetch():
    r = subprocess.run(
        ["/opt/homebrew/bin/python3", CAPAFY_HTTP, "GET", "/agent/agents"],
        capture_output=True, text=True, timeout=60,
    )
    d = json.loads(r.stdout)
    lst = (((d or {}).get("data") or {}).get("list")) or []
    return lst if isinstance(lst, list) else []


def _score(a):
    # sales weighted highest, then recent momentum, then social proof (rating * reviews).
    return _num(a.get("sales")) * 10 + _num(a.get("recentSales")) * 5 + _num(a.get("rating")) * _num(a.get("reviewCount"))


def _company_signal(path=COMPANY_RECEIPT):
    try:
        value = json.loads(Path(path).read_text())
        orders = value.get("orders")
        orders = orders if isinstance(orders, int) and not isinstance(orders, bool) and orders >= 0 else None
        winner = value.get("seller_winner")
        return orders, winner if isinstance(winner, dict) else None
    except (OSError, json.JSONDecodeError, AttributeError):
        return None, None


ANALYTICS = STATE_HOME / "state/capafy-skill-analytics.json"


def profit_winners(analytics, limit=3):
    """Skills ranked by real 30d profit (net revenue minus OpenRouter actual cost).

    Gross sales alone picked Hook Lab, which sells most but loses money on Sonnet
    (2026-09-28: rev $19.91, cost $36.07). Cloning a loss-maker scales the loss.
    """
    rows = [r for r in (analytics or {}).get("per_skill_rows") or []
            if _num(r.get("profit_30d_actual_usd")) > 0]
    rows.sort(key=lambda r: (_num(r.get("profit_30d_actual_usd")),
                             _num(r.get("stats_30d_orders"))), reverse=True)
    return [{"agent_id": r.get("agent_id"), "name": r.get("name"),
             "profit_30d_usd": r.get("profit_30d_actual_usd"),
             "revenue_30d_usd": r.get("stats_30d_revenue_usd"),
             "orders_30d": r.get("stats_30d_orders")} for r in rows[:limit]]


def select_signal(agents, company_orders, official_winner=None, analytics=None):
    profitable = profit_winners(analytics)
    if profitable:
        top_names = ", ".join(f"'{w['name']}' (+${w['profit_30d_usd']}/30d)" for w in profitable)
        return {
            "ok": True, "signal": "sales", "listings": len(agents), "company_orders": company_orders,
            "winner": {"agent_id": profitable[0]["agent_id"], "name": profitable[0]["name"],
                       "source": "real_profit_30d"},
            "profit_winners": profitable, "attribution_status": "real_profit_30d",
            "advice": f"Most profitable skills (net revenue minus actual model cost, 30d): {top_names}. "
                      "Build the NEXT skill in one of these customer-job categories/styles, on the cheap "
                      "hosted model (DeepSeek V4.1 Flash). Do not clone a best-seller that loses money.",
        }
    ranked = sorted(agents, key=_score, reverse=True)
    total_sales = sum(_num(a.get("sales")) + _num(a.get("recentSales")) for a in agents)
    top = [
        {"name": a.get("name"), "agentId": a.get("agentId"), "status": a.get("agentStatus"),
         "sales": a.get("sales"), "recentSales": a.get("recentSales"),
         "rating": a.get("rating"), "reviewCount": a.get("reviewCount"), "score": _score(a)}
        for a in ranked[:5]
    ]
    if (
        isinstance(official_winner, dict)
        and official_winner.get("source") == "official_publisher_console"
        and official_winner.get("agent_id")
        and official_winner.get("name")
        and _num(official_winner.get("sales_usd")) > 0
    ):
        return {
            "ok": True, "signal": "sales", "listings": len(agents), "company_orders": company_orders,
            "winner": official_winner, "attribution_status": "official_seller_ranking",
            "advice": f"Official seller winner is '{official_winner['name']}'. Build the NEXT skill in the same customer-job category/style; this is {official_winner.get('revenue_kind', 'observed')} revenue, not subscription MRR proof.",
            "top_by_proxy": top,
        }
    if total_sales > 0:
        winner = ranked[0]
        return {
            "ok": True, "signal": "sales", "listings": len(agents), "company_orders": company_orders,
            "winner": {"name": winner.get("name"), "agentId": winner.get("agentId")},
            "advice": f"Our best-selling listing is '{winner.get('name')}'. Build the NEXT skill in the same category/style as this proven winner.",
            "top": top,
        }
    if company_orders is not None and company_orders > 0:
        return {
            "ok": True, "signal": "unattributed_sales", "listings": len(agents),
            "company_orders": company_orders,
            "attribution_status": "company_orders_exist_agent_sales_unavailable",
            "advice": "Company orders exist, but Capafy exposes no usable Agent-level winner signal. Do not fabricate a winner or clone a category. Rotate tracked marketing across existing online listings until Agent-level sales become observable.",
            "top_by_proxy": top,
        }
    return {
        "ok": True, "signal": "none", "listings": len(agents), "company_orders": company_orders,
        "advice": "No company or Agent-level sales signal is observable. Do not fabricate a winner; use marketplace research for the next differentiated candidate.",
        "top_by_proxy": top,
    }


def main():
    try:
        agents = _fetch()
    except Exception as e:  # network / server-broken — do not crash the loop
        out = {"ok": False, "error": f"fetch failed: {e}", "signal": "none", "advice": "use BEST_PRACTICES marketplace research"}
        json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=2)
        print(json.dumps(out)); return 0

    company_orders, official_winner = _company_signal()
    try:
        analytics = json.load(open(ANALYTICS))
    except (OSError, ValueError):
        analytics = None
    out = select_signal(agents, company_orders, official_winner, analytics)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
