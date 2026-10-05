#!/usr/bin/env python3
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from capafy_scoreboard import build_scoreboard, render_text, snapshot_rows, compare_changes, append_snapshot_jsonl

ANALYTICS = {
    "account_totals": {"last_30d": {"gross_usd": "82.77", "orders": 78}, "cost30_actual_usd": "34.50", "net30_usd": "66.22"},
    "balances": {"balance_payout_usd": "59.00", "balance_pending_usd": "11.02", "paid_out_usd": "0.00"},
    "per_skill_rows": [
        {"agent_id": "1", "name": "Hook Lab", "status": "online", "stats_30d_orders": 11, "stats_30d_revenue_usd": "24.89", "cost_30d_actual_usd": "0.34", "stats_7d_orders": 11, "stats_7d_revenue_usd": "24.89"},
        {"agent_id": "2", "name": "Dead", "status": "online", "stats_30d_orders": 0, "stats_30d_revenue_usd": "0.00", "since_launch_gross_usd": "0.00", "cost_30d_actual_usd": None},
    ],
    "daily_revenue_trend_last_30d": [{"date": "2026-10-03", "revenue": 0.0, "orders": 0}, {"date": "2026-10-04", "revenue": 0.0, "orders": 0}],
}
RECONCILE = {"traffic_sources": {"by_agent": {"1": {"last_30d": {"by_source": [
    {"source_type": "search", "views": 100, "paid_orders": 2, "sales_usd": "9.98"}]}}}}}


def test_scoreboard_separates_money_stages_and_flags_zero_streak():
    b = build_scoreboard(ANALYTICS, RECONCILE)
    assert b["money"] == {"gross_30d": "82.77", "earnings_after_cost_30d": "66.22", "cost_30d": "34.50",
                          "payout_waiting": "59.00", "pending": "11.02", "bank_received_total": "0.00"}
    assert b["zero_revenue_streak_days"] == 2
    assert b["skills"]["selling"] == 1 and b["skills"]["never_sold"] == 1
    assert b["funnel"]["search"] == {"views": 100, "paid_orders": 2, "sales_usd": "9.98"}


# Capafy reports a ct= link's visits as sourceType="ct" sourceName="<token>" and a matching
# sale as sourceType="campaign" campaignName="<token>" (same token, different row) -- see
# skills/writer-agent/config/products.json "tracking". The scoreboard must merge those two
# rows per token so each article/X ct= link shows its own views/orders/sales.
CT_RECONCILE = {"traffic_sources": {"by_agent": {
    "7686597754": {"last_30d": {"by_source": [
        {"source_type": "ct", "source_name": "capafy-distribute-youtube-script-writer",
         "views": 42, "paid_orders": 0, "sales_usd": "0.00"},
        {"source_type": "campaign", "source_name": "capafy-distribute-youtube-script-writer",
         "views": 0, "paid_orders": 3, "sales_usd": "29.97"},
    ]}},
    "2844813315": {"last_30d": {"by_source": [
        {"source_type": "ct", "source_name": "article-tiktok-script-pro",
         "views": 5, "paid_orders": 0, "sales_usd": "0.00"},
    ]}},
}}}


def test_scoreboard_merges_ct_and_campaign_rows_per_token():
    b = build_scoreboard(ANALYTICS, CT_RECONCILE)
    assert b["ct"] == {
        "capafy-distribute-youtube-script-writer": {"views": 42, "paid_orders": 3, "sales_usd": "29.97"},
        "article-tiktok-script-pro": {"views": 5, "paid_orders": 0, "sales_usd": "0.00"},
    }


def test_render_text_prints_one_line_per_ct_token():
    b = build_scoreboard(ANALYTICS, CT_RECONCILE)
    text = render_text(b)
    assert "ct capafy-distribute-youtube-script-writer: 42 view → 3 件 $29.97" in text
    assert "ct article-tiktok-script-pro: 5 view → 0 件 $0.00" in text


def test_render_text_has_no_ct_lines_when_no_ct_rows():
    b = build_scoreboard(ANALYTICS, RECONCILE)
    assert b["ct"] == {}
    assert "ct " not in render_text(b)


SNAP_RECONCILE = {"traffic_sources": {"by_agent": {
    "1": {"last_7d": {"by_source": [
        {"source_name": "search", "source_type": "internal", "views": 10, "paid_orders": 1, "sales_usd": "5.00"},
        {"source_name": "direct", "source_type": "direct", "views": 3, "paid_orders": 0, "sales_usd": "0.00"},
    ]}},
    "2": {"last_7d": {"by_source": []}},
}}}


def test_snapshot_rows_builds_one_row_per_agent():
    rows = snapshot_rows(ANALYTICS, SNAP_RECONCILE, "2026-10-04")
    row1 = next(r for r in rows if r["agent_id"] == "1")
    assert row1 == {
        "date": "2026-10-04", "agent_id": "1", "name": "Hook Lab",
        "search_views_7d": 10, "search_paid_7d": 1,
        "views_7d": 13, "orders_7d": 11, "revenue_7d": "24.89",
    }


def test_append_snapshot_jsonl_is_idempotent_per_date():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "capafy-scoreboard-daily.jsonl"
        rows = snapshot_rows(ANALYTICS, SNAP_RECONCILE, "2026-10-04")
        wrote1 = append_snapshot_jsonl(path, rows, "2026-10-04")
        wrote2 = append_snapshot_jsonl(path, rows, "2026-10-04")
        assert wrote1 is True
        assert wrote2 is False
        lines = path.read_text().splitlines()
        assert len(lines) == len(rows)


def _row(date, agent_id, views=10, paid=1, revenue="5.00"):
    return {"date": date, "agent_id": agent_id, "name": "Hook Lab",
            "search_views_7d": views, "search_paid_7d": paid,
            "views_7d": views, "orders_7d": paid, "revenue_7d": revenue}


def test_compare_changes_uses_exact_snapshots_when_present():
    changes = [{"date": "2026-10-01", "agent_id": "1", "change": "price up"}]
    snapshots = [
        _row("2026-10-01", "1", views=10, paid=1, revenue="5.00"),
        _row("2026-10-08", "1", views=20, paid=3, revenue="15.00"),
    ]
    out = compare_changes(changes, snapshots, "2026-10-08")
    assert out == [{
        "date": "2026-10-01", "agent_id": "1", "change": "price up", "name": "Hook Lab",
        "before": snapshots[0], "after": snapshots[1],
    }]


def test_compare_changes_falls_back_to_nearest_snapshot():
    changes = [{"date": "2026-10-01", "agent_id": "1", "change": "price up"}]
    # no snapshot exactly on 10-01 or 10-08; nearest earlier/later used instead.
    snapshots = [
        _row("2026-09-29", "1", views=8, paid=1, revenue="4.00"),
        _row("2026-10-09", "1", views=22, paid=3, revenue="16.00"),
    ]
    out = compare_changes(changes, snapshots, "2026-10-09")
    assert out[0]["before"]["date"] == "2026-09-29"
    assert out[0]["after"]["date"] == "2026-10-09"


def test_compare_changes_marks_pending_when_snapshot_missing_not_zero():
    changes = [{"date": "2026-10-01", "agent_id": "1", "change": "price up"}]
    snapshots = [_row("2026-10-01", "1")]  # no "after" snapshot exists yet
    out = compare_changes(changes, snapshots, "2026-10-08")
    assert out == [{"date": "2026-10-01", "agent_id": "1", "change": "price up", "pending": True}]
    # missing never coerces to a 0 comparison
    assert "before" not in out[0] and "after" not in out[0]


def test_compare_changes_skips_not_yet_due():
    changes = [{"date": "2026-10-04", "agent_id": "1", "change": "price up"}]
    out = compare_changes(changes, [_row("2026-10-04", "1")], "2026-10-05")
    assert out == []


if __name__ == "__main__":
    test_scoreboard_separates_money_stages_and_flags_zero_streak()
    test_scoreboard_merges_ct_and_campaign_rows_per_token()
    test_render_text_prints_one_line_per_ct_token()
    test_render_text_has_no_ct_lines_when_no_ct_rows()
    test_snapshot_rows_builds_one_row_per_agent()
    test_append_snapshot_jsonl_is_idempotent_per_date()
    test_compare_changes_uses_exact_snapshots_when_present()
    test_compare_changes_falls_back_to_nearest_snapshot()
    test_compare_changes_marks_pending_when_snapshot_missing_not_zero()
    test_compare_changes_skips_not_yet_due()
    print("OK")
