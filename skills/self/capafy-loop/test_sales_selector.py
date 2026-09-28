from sales_selector import select_signal


def agent(agent_id: str, sales=None, recent=None) -> dict:
    return {"agentId": agent_id, "name": f"Agent {agent_id}", "agentStatus": "online",
            "sales": sales, "recentSales": recent, "rating": None, "reviewCount": 0}


def test_official_seller_winner_overrides_missing_legacy_agent_sales() -> None:
    official_winner = {
        "agent_id": "6839055303",
        "name": "Academic Humanizer — Human Voice, No AI Tells",
        "sales_usd": "9.99",
        "sku_type": "buyout",
        "revenue_kind": "one_time",
        "source": "official_publisher_console",
    }

    result = select_signal([agent("1", None, [0, 0])], company_orders=1, official_winner=official_winner)

    assert result["signal"] == "sales"
    assert result["company_orders"] == 1
    assert result["winner"] == official_winner
    assert result["attribution_status"] == "official_seller_ranking"


def test_agent_sales_identify_real_winner_including_recent_sales_array() -> None:
    result = select_signal([agent("1", 1, [0, 1]), agent("2", 0, [0, 4])], company_orders=5)

    assert result["signal"] == "sales"
    assert result["winner"]["agentId"] == "2"


def test_no_company_or_agent_sales_remains_none() -> None:
    result = select_signal([agent("1", None, None)], company_orders=0)

    assert result["signal"] == "none"


def test_winner_is_most_profitable_not_best_selling():
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location("ss", pathlib.Path(__file__).parent / "sales_selector.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    analytics = {"per_skill_rows": [
        {"agent_id": "hook", "name": "Hook Lab", "profit_30d_actual_usd": "-16.16", "stats_30d_orders": 11},
        {"agent_id": "slide", "name": "Slide Maker", "profit_30d_actual_usd": "15.98", "stats_30d_orders": 2},
        {"agent_id": "tiktok", "name": "TikTok Script Pro", "profit_30d_actual_usd": "11.85", "stats_30d_orders": 5},
    ]}
    official = {"source": "official_publisher_console", "agent_id": "hook", "name": "Hook Lab", "sales_usd": "34.88"}
    out = mod.select_signal([], 67, official, analytics)
    assert out["winner"]["name"] == "Slide Maker"
    assert [w["name"] for w in out["profit_winners"]] == ["Slide Maker", "TikTok Script Pro"]
    assert mod.select_signal([], 67, official, None)["winner"]["name"] == "Hook Lab"
