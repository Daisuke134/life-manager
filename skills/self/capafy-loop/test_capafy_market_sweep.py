from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).with_name("capafy_market_sweep.py")


def load_module():
    spec = importlib.util.spec_from_file_location("capafy_market_sweep", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def agent(agent_id, sales, tags="hook,tiktok", subscription=None, download=None):
    billings = []
    if subscription:
        for cycle, price in subscription.items():
            billings.append({"billingMode": "subscription", "cycleType": cycle, "cyclePrice": price})
    if download is not None:
        billings.append({"billingMode": "download", "oneTimeFee": download})
    return {"agentId": agent_id, "title": f"Agent {agent_id}", "tags": tags,
            "salesVolume": sales, "billings": billings}


def test_dedupe_agents_keeps_last_write_unique_by_id():
    module = load_module()
    batch1 = [agent("1", 10), agent("2", 20)]
    batch2 = [agent("1", 999)]  # same id, later batch wins

    result = module.dedupe_agents([batch1, batch2])

    by_id = {a["agentId"]: a for a in result}
    assert set(by_id) == {"1", "2"}
    assert by_id["1"]["salesVolume"] == 999


def test_aggregate_price_bands_only_uses_successful_sellers():
    module = load_module()
    agents = [
        agent("low", 1, subscription={"week": 99.99}),   # below median sales -> excluded
        agent("mid", 500, subscription={"week": 9.99}),
        agent("hi", 1000, subscription={"week": 12.99}),
        agent("zero", 0, subscription={"week": 500.00}),  # zero sales -> excluded even if >= threshold
    ]

    out = module.aggregate_price_bands(agents)

    assert out["total_agents"] == 4
    week = out["bands"]["week"]
    assert week["sample_size"] == 2
    assert week["p25"] in (9.99, 12.99)
    assert 9.99 <= week["median"] <= 12.99
    assert "99.99" not in str(week)


def test_aggregate_price_bands_download_uses_one_time_fee():
    module = load_module()
    agents = [agent("a", 100, tags="humanizer", subscription=None, download=9.99),
              agent("b", 100, tags="humanizer", subscription=None, download=14.99)]

    out = module.aggregate_price_bands(agents)

    assert out["bands"]["download"]["sample_size"] == 2


def test_top_uncovered_categories_skips_our_own_tags():
    module = load_module()
    agents = [
        agent("a", 900, tags="hook,tiktok"),          # matches our "hook" catalog -> excluded
        agent("b", 800, tags="finance,stock"),        # not covered -> candidate
        agent("c", 5, tags="finance,stock"),          # below min_sales -> excluded
    ]
    covered = ["hook lab", "tiktok script"]

    ranked = module.top_uncovered_categories(agents, covered, min_sales=50)

    assert len(ranked) == 1
    assert ranked[0]["tag"] == "finance"
    assert ranked[0]["total_sales"] == 800
