from __future__ import annotations

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).with_name("capafy_daily_decision.py")


def load_module():
    spec = importlib.util.spec_from_file_location("capafy_daily_decision", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def row(agent_id, name, net, cost, orders=0, model="Claude Sonnet 4.6"):
    return {"agent_id": agent_id, "name": name, "model": model,
            "net_revenue_30d_usd": net, "cost_30d_actual_usd": cost, "stats_30d_orders": orders}


def server(agent_id, status="online", version="v1"):
    return {agent_id: {"agentId": agent_id, "agentStatus": status, "latestAgentVersionId": version}}


CATALOG = {
    "Hook Lab": {"dir_name": "hook-lab", "dir_path": "/repo/skills/capafy/catalog/hook-lab",
                 "pricing": {"week": 9.99}, "has_update": False},
    "Japanese Humanizer": {"dir_name": "japanese-humanizer",
                            "dir_path": "/repo/skills/capafy/catalog/japanese-humanizer",
                            "pricing": {"download": 1.99}, "has_update": False},
}

BANDS = {"bands": {"week": {"p25": 9.99, "median": 12.99, "p75": 14.99, "sample_size": 5},
                    "download": {"p25": 9.99, "median": 9.99, "p75": 12.99, "sample_size": 5}}}


def test_losing_money_queues_model_switch_when_not_already_cheap():
    module = load_module()
    rows = [row("hook", "Hook Lab", net=19.91, cost=20.31)]  # cost > 30% of net, and net<cost

    decisions = module.decide_actions(rows, server("hook"), CATALOG, BANDS, {})

    finding = decisions[0]["findings"][0]
    assert finding["action"] == "queue_update"
    assert finding["update"]["target_model_id"] == "deepseek/deepseek-v4.1-flash"
    assert finding["update"]["agent_id"] == "hook"
    assert finding["update"]["from_version_id"] == "v1"


def test_losing_money_skipped_when_already_cheap_model():
    module = load_module()
    rows = [row("hook", "Hook Lab", net=19.91, cost=20.31, model="DeepSeek V4.1 Flash")]

    decisions = module.decide_actions(rows, server("hook"), CATALOG, BANDS, {})

    assert decisions[0]["findings"][0]["action"] == "manual_review"


def test_losing_money_skipped_when_update_already_pending():
    module = load_module()
    rows = [row("hook", "Hook Lab", net=19.91, cost=20.31)]
    catalog_pending = {**CATALOG, "Hook Lab": {**CATALOG["Hook Lab"], "has_update": True}}

    decisions = module.decide_actions(rows, server("hook"), catalog_pending, BANDS, {})

    assert decisions[0]["findings"][0] == {"rule": "losing_money", "action": "skip",
                                            "reason": "update_already_queued"}


def test_losing_money_skipped_when_server_status_under_review():
    module = load_module()
    rows = [row("hook", "Hook Lab", net=19.91, cost=20.31)]

    decisions = module.decide_actions(rows, server("hook", status="under_review"), CATALOG, BANDS, {})

    assert decisions[0]["findings"][0] == {"rule": "losing_money", "action": "skip", "reason": "pending_review"}


def test_underpriced_download_queues_reprice():
    module = load_module()
    rows = [row("jh", "Japanese Humanizer", net=0, cost=0)]  # not losing (cost=0)

    decisions = module.decide_actions(rows, server("jh"), CATALOG, BANDS, {})

    finding = decisions[0]["findings"][0]
    assert finding["action"] == "queue_update"
    assert finding["update"]["target_one_time_fee"] == "9.99"


def test_subscription_underprice_is_reported_not_queued_cp1_unsupported():
    module = load_module()
    catalog_cheap_week = {"Hook Lab": {**CATALOG["Hook Lab"], "pricing": {"week": 3.99}}}
    rows = [row("hook", "Hook Lab", net=0, cost=0)]

    decisions = module.decide_actions(rows, server("hook"), catalog_cheap_week, BANDS, {})

    finding = decisions[0]["findings"][0]
    assert finding["action"] == "blocked_no_cp1_support"
    assert finding["cycle"] == "week"


def test_zero_sales_with_views_flags_retire_candidate():
    module = load_module()
    rows = [row("hook", "Hook Lab", net=0, cost=0, orders=0)]

    decisions = module.decide_actions(rows, server("hook"), CATALOG, BANDS, {"hook": 50})

    kinds = [f["action"] for f in decisions[0]["findings"]]
    assert "retire_or_rewrite_candidate" in kinds


def test_zero_sales_low_views_is_not_flagged():
    module = load_module()
    rows = [row("hook", "Hook Lab", net=0, cost=0, orders=0)]

    decisions = module.decide_actions(rows, server("hook"), CATALOG, BANDS, {"hook": 3})

    kinds = [f["action"] for f in decisions[0]["findings"]]
    assert "retire_or_rewrite_candidate" not in kinds


HOOK_LAB_FAMILY_CATALOG = {
    "Hook Lab": {"dir_name": "hook-lab", "dir_path": "/repo/skills/capafy/catalog/hook-lab",
                 "pricing": {}, "has_update": False},
    "Ad Hook Lab": {"dir_name": "ad-hook-lab", "dir_path": "/repo/skills/capafy/catalog/ad-hook-lab",
                    "pricing": {}, "has_update": False},
    "Reels Hook Lab": {"dir_name": "reels-hook-lab", "dir_path": "/repo/skills/capafy/catalog/reels-hook-lab",
                       "pricing": {}, "has_update": False},
}


def test_winner_clone_stops_when_two_live_children_underperform():
    module = load_module()
    rows = [
        row("hook", "Hook Lab", net=100, cost=10, orders=11),
        row("ad", "Ad Hook Lab", net=0, cost=0, orders=0),
        row("reels", "Reels Hook Lab", net=0, cost=0, orders=0),
    ]
    servers = {**server("hook"), **server("ad"), **server("reels")}

    decisions = module.decide_actions(rows, servers, HOOK_LAB_FAMILY_CATALOG, BANDS, {})

    hook_decision = next(d for d in decisions if d["name"] == "Hook Lab")
    finding = next(f for f in hook_decision["findings"] if f["rule"] == "winner_clone")
    assert finding == {
        "rule": "winner_clone", "action": "stop", "parent": "Hook Lab",
        "reason": "children_underperform", "children": ["Ad Hook Lab", "Reels Hook Lab"],
    }
    assert not any(f.get("action") == "queue_opportunity" for f in hook_decision["findings"])


def test_winner_clone_queues_opportunity_when_fewer_than_two_children_underperform():
    module = load_module()
    catalog = {"TikTok Script Pro": {"dir_name": "tiktok-script-pro",
                                      "dir_path": "/repo/skills/capafy/catalog/tiktok-script-pro",
                                      "pricing": {}, "has_update": False}}
    rows = [row("tsp", "TikTok Script Pro", net=50, cost=5, orders=4)]

    decisions = module.decide_actions(rows, server("tsp"), catalog, BANDS, {})

    finding = next(f for f in decisions[0]["findings"] if f["rule"] == "winner_clone")
    assert finding == {
        "rule": "winner_clone", "action": "queue_opportunity",
        "opportunity": {
            "kind": "winner_clone", "parent_agent_id": "tsp", "parent_title": "TikTok Script Pro",
            "tag": "winner_clone_tsp",
            "requirement": "different input, output and use case from parent and existing children "
                           "(Capafy doc 4.2: no near-identical mass uploads)",
        },
    }


def test_winner_clone_not_triggered_below_order_threshold():
    module = load_module()
    rows = [row("hook", "Hook Lab", net=0, cost=0, orders=2)]

    decisions = module.decide_actions(rows, server("hook"), HOOK_LAB_FAMILY_CATALOG, BANDS, {})

    assert not any(f["rule"] == "winner_clone" for f in decisions[0]["findings"])


def test_winner_clone_child_matching_parent_does_not_count_as_underperforming():
    module = load_module()
    rows = [
        row("hook", "Hook Lab", net=100, cost=10, orders=11),
        row("ad", "Ad Hook Lab", net=100, cost=10, orders=11),  # matches parent -> not underperforming
        row("reels", "Reels Hook Lab", net=0, cost=0, orders=0),  # underperforming
    ]
    servers = {**server("hook"), **server("ad"), **server("reels")}

    decisions = module.decide_actions(rows, servers, HOOK_LAB_FAMILY_CATALOG, BANDS, {})

    hook_decision = next(d for d in decisions if d["name"] == "Hook Lab")
    finding = next(f for f in hook_decision["findings"] if f["rule"] == "winner_clone")
    assert finding["action"] == "queue_opportunity"  # only 1 underperforming child, stop rule needs >= 2


def test_queue_update_file_does_not_overwrite_existing(tmp_path):
    module = load_module()
    existing = tmp_path / "UPDATE.json"
    existing.write_text('{"agent_id": "x"}')

    wrote = module.queue_update_file(tmp_path, {"agent_id": "y"})

    assert wrote is False
    assert json.loads(existing.read_text())["agent_id"] == "x"


def test_queue_update_file_writes_when_absent(tmp_path):
    module = load_module()

    wrote = module.queue_update_file(tmp_path, {"agent_id": "y", "reason": "r"})

    assert wrote is True
    assert json.loads((tmp_path / "UPDATE.json").read_text())["agent_id"] == "y"


def test_parse_listing_pricing_reads_table_rows():
    module = load_module()
    text = "## Pricing\n| cycle | price | cap | trial |\n|---|---|---|---|\n| week | $9.99 | 30 | No Free Trial |\n"

    assert module.parse_listing_pricing(text) == {"week": 9.99}


def test_append_opportunity_dedupes_by_tag(tmp_path):
    module = load_module()
    path = tmp_path / "opps.json"

    module.append_opportunity(path, {"tag": "finance", "total_sales": 100, "example_title": "X",
                                     "example_sales": 100}, "2026-09-29T00:00:00Z")
    data = module.append_opportunity(path, {"tag": "finance", "total_sales": 200, "example_title": "Y",
                                            "example_sales": 200}, "2026-09-30T00:00:00Z")

    assert len(data["items"]) == 1
    assert data["items"][0]["example_title"] == "Y"


def test_rank_shelves_prefers_big_market_where_we_are_thin():
    module = load_module()
    market_winners = [
        {"name": "Big Seller A", "category": "finance", "sold": 900},
        {"name": "Big Seller B", "category": "finance", "sold": 100},
        {"name": "Small Seller", "category": "hook", "sold": 50},
    ]
    own_rows = [
        {"agent_id": "1", "category": "hook", "stats_30d_orders": 10},
        {"agent_id": "2", "category": "hook", "stats_30d_orders": 5},
        {"agent_id": "3", "category": "hook", "stats_30d_orders": 2},
    ]  # 3 own listings already crowding "hook"; "finance" has 0 -> should rank first

    shelves = module.rank_shelves(market_winners, own_rows)

    assert shelves[0]["category"] == "finance"
    assert shelves[0]["market_sold_total"] == 1000
    assert shelves[0]["our_listings"] == 0
    assert shelves[0]["our_sales_30d"] == 0
    assert shelves[0]["score"] == 1000  # 1000 / (1 + 0)

    hook = next(s for s in shelves if s["category"] == "hook")
    assert hook["market_sold_total"] == 50
    assert hook["our_listings"] == 3
    assert hook["our_sales_30d"] == 17
    assert hook["score"] == 12.5  # 50 / (1 + 3)


def test_main_appends_top_shelf_opportunity_when_winners_file_present(tmp_path, monkeypatch):
    module = load_module()
    state_home = tmp_path / "state"
    state_home.mkdir()
    monkeypatch.setattr(module, "STATE_HOME", tmp_path)  # keep glob("state/capafy-market-agents-*") off real data
    monkeypatch.setattr(module, "ANALYTICS_PATH", state_home / "capafy-skill-analytics.json")
    monkeypatch.setattr(module, "HOURLY_RECONCILE_PATH", state_home / "capafy-hourly-reconcile.json")
    monkeypatch.setattr(module, "PRICE_BANDS_PATH", state_home / "capafy-market-price-bands-latest.json")
    monkeypatch.setattr(module, "DECISIONS_DIR", state_home / "capafy-daily-decisions")
    monkeypatch.setattr(module, "OPPORTUNITIES_PATH", state_home / "capafy-candidate-opportunities.json")
    monkeypatch.setattr(module, "MARKET_WINNERS_PATH", state_home / "capafy-market-winners-latest.json")
    monkeypatch.setattr(module, "build_catalog_index", lambda *a, **kw: {})
    monkeypatch.setattr(module, "fetch_server_agents", lambda: [
        {"agentId": "1", "agentStatus": "online", "latestAgentVersionId": "v1", "categoryId": "hook"},
    ])

    module.ANALYTICS_PATH.write_text(json.dumps({"per_skill_rows": [
        {"agent_id": "1", "name": "Hook Lab", "model": "Claude Sonnet 4.6",
         "net_revenue_30d_usd": "10.00", "cost_30d_actual_usd": "1.00", "stats_30d_orders": 2},
    ]}), encoding="utf-8")
    module.MARKET_WINNERS_PATH.write_text(json.dumps({"items": [
        {"name": "Big Seller", "category": "finance", "sold": 900},
        {"name": "Small Seller", "category": "hook", "sold": 10},
    ]}), encoding="utf-8")

    module.main()

    opportunities = json.loads(module.OPPORTUNITIES_PATH.read_text())["items"]
    shelf_items = [item for item in opportunities if item.get("kind") == "market_shelf"]
    assert len(shelf_items) == 1
    assert shelf_items[0]["category"] == "finance"
    assert shelf_items[0]["tag"] == "shelf_category_finance"


def test_write_decision_record_is_dated_and_readable(tmp_path):
    module = load_module()

    path = module.write_decision_record([], None, "2026-09-29T12:00:00Z", "summary", path_dir=tmp_path)

    assert path.name == "2026-09-29.json"
    assert json.loads(path.read_text())["telegram_summary"] == "summary"


def test_rank_shelves_names_capafy_categories():
    m = load_module()
    ranked = m.rank_shelves([{"category": 11, "sold": 10}, {"category": 999, "sold": 1}], [])
    assert ranked[0]["category_name"] == "Finance"
    assert ranked[1]["category_name"] == "unknown"


def test_winner_clone_ignores_free_order_parent():
    m = load_module()
    rows = [{"agent_id": "3332784488", "name": "Japanese Humanizer", "status": "online",
             "stats_30d_orders": 5, "net_revenue_30d_usd": "0.00", "cost_30d_actual_usd": None,
             "model": "Claude Sonnet 4.6"}]
    catalog = {"Japanese Humanizer": {"dir_path": "/x/japanese-humanizer", "dir_name": "japanese-humanizer", "has_update": False}}
    out = m.decide_actions(rows, {"3332784488": {"agentStatus": "online"}}, catalog, {}, {})
    findings = [f for d in out for f in d["findings"] if f.get("rule") == "winner_clone"]
    assert findings == []


def test_profitable_seller_is_frozen_no_reprice_queued():
    # Dais 2026-10-06: an Agent that is selling at a profit is not repriced;
    # the 9/29 run of version updates on the winners preceded 7 days of zero orders.
    module = load_module()
    rows = [row("jh", "Japanese Humanizer", net=8.0, cost=0.1, orders=1)]

    decisions = module.decide_actions(rows, server("jh"), CATALOG, BANDS, {})

    assert decisions[0]["findings"][0] == {"rule": "underpriced", "action": "skip",
                                            "reason": "profitable_seller_frozen"}
