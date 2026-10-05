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


def agent(agent_id, sales, tags="hook,tiktok", subscription=None, download=None,
          developer="Anicca", category_id=5):
    billings = []
    if subscription:
        for cycle, price in subscription.items():
            billings.append({"billingMode": "subscription", "cycleType": cycle, "cyclePrice": price})
    if download is not None:
        billings.append({"billingMode": "download", "oneTimeFee": download})
    return {"agentId": agent_id, "title": f"Agent {agent_id}", "tags": tags,
            "salesVolume": sales, "billings": billings,
            "developerName": developer, "categoryId": category_id}


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


def test_compute_market_winners_shapes_fields_from_successful_sellers_only():
    module = load_module()
    agents = [
        agent("low", 1, subscription={"week": 99.99}),  # below median -> excluded
        agent("hi", 1000, subscription={"week": 12.99}, developer="TopDev", category_id=5),
        agent("dl", 500, subscription=None, download=9.99, developer="DlDev", category_id=11),
    ]

    winners = module.compute_market_winners(agents, "2026-10-04T00:00:00Z")

    by_id = {w["name"]: w for w in winners}
    assert "Agent low" not in by_id  # excluded (below median sales)
    assert by_id["Agent hi"] == {
        "name": "Agent hi", "developer": "TopDev", "category": 5,
        "price": 12.99, "cycle": "week", "sold": 1000, "observed_at": "2026-10-04T00:00:00Z",
    }
    assert by_id["Agent dl"]["cycle"] == "download"
    assert by_id["Agent dl"]["price"] == 9.99
    assert by_id["Agent dl"]["sold"] == 500


def test_fetch_category_agents_paginates_until_empty_page():
    """Measured gap (2026-10-05): CloneCut (14.4k sold, #1 on the capafy.ai Trending tab) was
    absent from the whole 843-agent keyword sweep because its title/tags never matched any of
    the ~52 DEFAULT_QUERIES. The public, paginated /public/category/hot endpoint enumerates
    every agent in a category regardless of keyword match -- fetch_category_agents must keep
    pulling pages until the API returns an empty page, not stop after page 1."""
    module = load_module()
    pages = {
        1: [agent("a", 100), agent("b", 50)],
        2: [agent("c", 30)],
        3: [],  # empty page -> stop
    }
    calls = []

    def fake_fetch_page(category_id, page):
        calls.append((category_id, page))
        return pages.get(page, [])

    result = module.fetch_category_agents(5, fetch_page=fake_fetch_page)

    assert [a["agentId"] for a in result] == ["a", "b", "c"]
    assert calls == [(5, 1), (5, 2), (5, 3)]


def test_fetch_category_agents_respects_max_pages_safety_cap():
    module = load_module()

    def fake_fetch_page(category_id, page):
        return [agent(f"x{page}", 1)]  # never-empty page -> would loop forever

    result = module.fetch_category_agents(5, fetch_page=fake_fetch_page, max_pages=3)

    assert len(result) == 3


def test_write_market_winners_roundtrips_to_tmp_path(tmp_path):
    module = load_module()
    winners = [{"name": "Agent hi", "developer": "TopDev", "category": 5,
                "price": 12.99, "cycle": "week", "sold": 1000, "observed_at": "2026-10-04T00:00:00Z"}]
    out_path = tmp_path / "capafy-market-winners-latest.json"

    module.write_market_winners(winners, path=out_path)

    import json
    assert json.loads(out_path.read_text())["items"] == winners
