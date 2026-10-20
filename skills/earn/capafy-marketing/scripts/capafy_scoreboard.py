#!/usr/bin/env python3
"""Daily Capafy scoreboard: money stages kept separate, never rounded unknown to 0."""
from __future__ import annotations
import datetime, json, os, sys
from decimal import Decimal
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

STATE = Path(os.environ.get("CAPAFY_STATE_DIR") or (Path.home() / ".local/state/life-manager/state"))


def _d(v):
    return None if v in (None, "") else Decimal(str(v))


def _money_text(v):
    amount = _d(v)
    return "未確認" if amount is None else f"${amount:.2f}"


def _window(reconcile: dict, window: str) -> tuple[dict, dict]:
    funnel: dict[str, dict] = {}
    ct: dict[str, dict] = {}
    for agent in ((reconcile.get("traffic_sources") or {}).get("by_agent") or {}).values():
        for s in (agent.get(window) or {}).get("by_source") or []:
            f = funnel.setdefault(s.get("source_type") or "unknown", {"views": 0, "paid_orders": 0, "sales_usd": Decimal("0")})
            f["views"] += s.get("views") or 0
            f["paid_orders"] += s.get("paid_orders") or 0
            f["sales_usd"] += _d(s.get("sales_usd")) or 0
            # A ct= link's visits land as sourceType="ct" sourceName="<token>"; a matching
            # sale lands as a separate sourceType="campaign" row with the same token -- see
            # skills/writer-agent/config/products.json "tracking". Merge both by token.
            if s.get("source_type") not in ("ct", "campaign"):
                continue
            token = s.get("source_name") or "unknown"
            c = ct.setdefault(token, {"views": 0, "paid_orders": 0, "sales_usd": Decimal("0")})
            c["views"] += s.get("views") or 0
            c["paid_orders"] += s.get("paid_orders") or 0
            c["sales_usd"] += _d(s.get("sales_usd")) or 0
    for row in (*funnel.values(), *ct.values()):
        row["sales_usd"] = f"{row['sales_usd']:.2f}"
    return funnel, ct


def build_scoreboard(analytics: dict, reconcile: dict) -> dict:
    t = analytics.get("account_totals") or {}
    bal = analytics.get("balances") or {}
    money = {
        "gross_30d": (t.get("last_30d") or {}).get("gross_usd"),
        "after_fee_estimate_30d": t.get("net30_usd"),
        "contribution_estimate_30d": t.get("profit30_actual_usd"),
        "cost_30d": t.get("cost30_actual_usd"),
        "payout_waiting": bal.get("balance_payout_usd"),
        "pending": bal.get("balance_pending_usd"),
        "bank_received_total": bal.get("paid_out_usd"),
    }
    streak = 0
    for day in reversed(analytics.get("daily_revenue_trend_last_30d") or []):
        if (day.get("revenue") or 0) > 0:
            break
        streak += 1
    rows = analytics.get("per_skill_rows") or []
    selling = sum(1 for r in rows if (_d(r.get("stats_30d_revenue_usd")) or 0) > 0)
    never = sum(1 for r in rows if (_d(r.get("since_launch_gross_usd")) or 0) == 0
                and (_d(r.get("stats_30d_revenue_usd")) or 0) == 0)
    funnel, ct = _window(reconcile, "last_30d")
    funnel_7d, ct_7d = _window(reconcile, "last_7d")
    for c in ct_7d.values():  # D1 binary verdicts per ct token over 7 days
        c["reach"] = "pass" if c["views"] > 0 else "fail"
        c["convert"] = "pass" if c["paid_orders"] > 0 else "fail"
    return {"money": money, "zero_revenue_streak_days": streak,
            "skills": {"total": len(rows), "selling": selling, "never_sold": never}, "funnel": funnel, "ct": ct,
            "funnel_7d": funnel_7d, "ct_7d": ct_7d}


def render_text(b: dict, comparisons: list[dict] | None = None) -> str:
    m = b["money"]
    lines = [f"Capafy 成績表: 30日 gross {_money_text(m['gross_30d'])} / 手数料推計後 {_money_text(m['after_fee_estimate_30d'])} / OpenRouter実費 {_money_text(m['cost_30d'])} / 寄与推計 {_money_text(m['contribution_estimate_30d'])}",
             "手数料推計後は売上の80%を仮定。全費用後の確定利益は未確認。",
             f"出金待ち ${m['payout_waiting']} / 確定待ち ${m['pending']} / 口座着金 累計 ${m['bank_received_total']}",
             f"売上0の連続日数 {b['zero_revenue_streak_days']} / 売れている {b['skills']['selling']} 本・一度も売れていない {b['skills']['never_sold']} 本"]
    for src, f in sorted(b["funnel"].items(), key=lambda kv: -kv[1]["views"])[:5]:
        lines.append(f"流入 {src}: {f['views']} view → {f['paid_orders']} 件 ${f['sales_usd']}")
    for token, t in sorted((b.get("ct") or {}).items(), key=lambda kv: -kv[1]["views"]):
        lines.append(f"ct {token}: {t['views']} view → {t['paid_orders']} 件 ${t['sales_usd']}")
    for token, t in sorted((b.get("ct_7d") or {}).items(), key=lambda kv: -kv[1]["views"]):
        lines.append(f"7日 ct {token}: {t['views']} view → {t['paid_orders']} 件 届く={t['reach']} 売れる={t['convert']}")
    if comparisons is not None:
        pending = 0
        for c in comparisons:
            if c.get("pending"):
                pending += 1
                continue
            before, after = c["before"], c["after"]
            lines.append(
                f"変更 {c['date']} {c.get('name') or c['agent_id']}: {c['change']} | "
                f"検索 view {before['search_views_7d']}→{after['search_views_7d']}, "
                f"検索成約 {before['search_paid_7d']}→{after['search_paid_7d']}, "
                f"7日売上 ${before['revenue_7d']}→${after['revenue_7d']}"
            )
        lines.append(f"比較待ち {pending} 件")
    return "\n".join(lines)


def snapshot_rows(analytics: dict, reconcile: dict, date: str) -> list[dict]:
    """One row per agent: today's search/7d funnel + revenue, for later before/after comparison."""
    by_agent = (reconcile.get("traffic_sources") or {}).get("by_agent") or {}
    rows = []
    for r in analytics.get("per_skill_rows") or []:
        agent_id = r.get("agent_id")
        sources = ((by_agent.get(agent_id) or {}).get("last_7d") or {}).get("by_source") or []
        search = next((s for s in sources if s.get("source_name") == "search"), {})
        rows.append({
            "date": date,
            "agent_id": agent_id,
            "name": r.get("name"),
            "search_views_7d": search.get("views") or 0,
            "search_paid_7d": search.get("paid_orders") or 0,
            "views_7d": sum(s.get("views") or 0 for s in sources),
            "orders_7d": r.get("stats_7d_orders") or 0,
            "revenue_7d": r.get("stats_7d_revenue_usd") or "0.00",
        })
    return rows


def append_snapshot_jsonl(path: Path, rows: list[dict], date: str) -> bool:
    """Append today's rows once; re-running the same date is a no-op (idempotent)."""
    existing_dates = set()
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing_dates.add(json.loads(line).get("date"))
            except json.JSONDecodeError:
                pass
    if date in existing_dates:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return True


def load_changes_jsonl(path: Path) -> list[dict]:
    """Read-only change log. Missing file = no comparisons (never invented)."""
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def compare_changes(changes: list[dict], snapshots: list[dict], today: str) -> list[dict]:
    """Before/after a listing change, using the nearest available snapshot.

    A change is only considered once date+7 <= today. Missing snapshots are
    never treated as 0 — they're reported as pending instead.
    """
    by_agent: dict[str, list[dict]] = {}
    for row in snapshots:
        by_agent.setdefault(row["agent_id"], []).append(row)
    for rows in by_agent.values():
        rows.sort(key=lambda r: r["date"])

    def nearest_before(rows, date):
        candidates = [r for r in rows if r["date"] <= date]
        return candidates[-1] if candidates else None

    def nearest_after(rows, date, limit):
        candidates = [r for r in rows if date <= r["date"] <= limit]
        return candidates[0] if candidates else None

    out = []
    for ch in changes:
        change_date = datetime.date.fromisoformat(ch["date"])
        after_date = (change_date + datetime.timedelta(days=7)).isoformat()
        if after_date > today:
            continue
        rows = by_agent.get(ch["agent_id"], [])
        before = nearest_before(rows, ch["date"])
        after = nearest_after(rows, after_date, today)
        if before is None or after is None:
            out.append({"date": ch["date"], "agent_id": ch["agent_id"], "change": ch["change"], "pending": True})
        else:
            out.append({
                "date": ch["date"], "agent_id": ch["agent_id"], "change": ch["change"],
                "name": after.get("name") or before.get("name"),
                "before": before, "after": after,
            })
    return out


if __name__ == "__main__":
    a = json.loads((STATE / "capafy-skill-analytics.json").read_text())
    r = json.loads((STATE / "capafy-hourly-reconcile.json").read_text())
    board = build_scoreboard(a, r)

    today = datetime.datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat() if ZoneInfo else datetime.date.today().isoformat()
    snap_path = STATE / "capafy-scoreboard-daily.jsonl"
    rows = snapshot_rows(a, r, today)
    append_snapshot_jsonl(snap_path, rows, today)
    snapshots = load_changes_jsonl(snap_path)  # jsonl of rows, same reader works
    changes = load_changes_jsonl(STATE / "capafy-listing-changes.jsonl")
    comparisons = compare_changes(changes, snapshots, today)

    print(json.dumps({**board, "comparisons": comparisons}, ensure_ascii=False) if "--json" in sys.argv
          else render_text(board, comparisons))
