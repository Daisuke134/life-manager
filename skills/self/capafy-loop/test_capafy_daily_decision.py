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


def test_write_decision_record_is_dated_and_readable(tmp_path):
    module = load_module()

    path = module.write_decision_record([], None, "2026-09-29T12:00:00Z", "summary", path_dir=tmp_path)

    assert path.name == "2026-09-29.json"
    assert json.loads(path.read_text())["telegram_summary"] == "summary"
