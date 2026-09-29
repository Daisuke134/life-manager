from __future__ import annotations

import datetime as dt
import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "select_capafy_distribute_skill.py"


def load_module():
    spec = importlib.util.spec_from_file_location("select_capafy_distribute_skill", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


PRODUCTS = {
    "products": {
        "capafy-skills": {
            "skills": {
                "hook-lab": {"agent_id": "111", "buyer_problem": "hook problem"},
                "slide-maker": {"agent_id": "222", "buyer_problem": "slide problem"},
                "tiktok-script-pro": {"agent_id": "333", "buyer_problem": "tiktok problem"},
            }
        }
    }
}


def analytics_with(rows: dict[str, dict]) -> dict:
    return {"per_skill_rows": [{"agent_id": agent_id, **fields} for agent_id, fields in rows.items()]}


def test_rank_skills_orders_by_30d_profit_then_revenue_fallback() -> None:
    module = load_module()
    analytics = analytics_with(
        {
            "111": {"profit_30d_actual_usd": "5.00"},
            "222": {"profit_30d_actual_usd": "20.00"},
            "333": {"net_revenue_30d_usd": "1.00"},  # no profit field -> falls back to revenue
        }
    )
    ranked = module.rank_skills(PRODUCTS, analytics)
    assert ranked == ["slide-maker", "hook-lab", "tiktok-script-pro"]


def test_rank_skills_puts_unmeasured_skills_last_in_stable_slug_order() -> None:
    module = load_module()
    analytics = analytics_with({"222": {"profit_30d_actual_usd": "3.00"}})
    ranked = module.rank_skills(PRODUCTS, analytics)
    assert ranked[0] == "slide-maker"
    assert ranked[1:] == ["hook-lab", "tiktok-script-pro"]  # alphabetical among unmeasured


def test_rank_skills_with_no_analytics_is_alphabetical() -> None:
    module = load_module()
    assert module.rank_skills(PRODUCTS, None) == ["hook-lab", "slide-maker", "tiktok-script-pro"]


def test_select_for_date_builds_ct_and_landing_from_ranked_pick() -> None:
    module = load_module()
    analytics = analytics_with({"222": {"profit_30d_actual_usd": "20.00"}, "111": {"profit_30d_actual_usd": "1.00"}})
    result = module.select_for_date(PRODUCTS, analytics, dt.date(2026, 9, 29), channel="capafy-distribute")
    assert result["ranked_slugs"][0] == "slide-maker"  # highest 30d profit ranks first
    assert result["capafy_skill"] == result["ranked_slugs"][result["rank"] - 1]
    assert result["landing_url"] == f"https://capafy.ai/agent/{PRODUCTS['products']['capafy-skills']['skills'][result['capafy_skill']]['agent_id']}"
    assert result["ct"] == f"capafy-distribute-{result['capafy_skill']}"
    assert result["ct"] != f"article-{result['capafy_skill']}"  # distinct channel from the main Writer loop's ct


def test_select_for_date_rotates_to_a_different_skill_the_next_day() -> None:
    module = load_module()
    picks = {
        module.select_for_date(PRODUCTS, None, dt.date(2026, 9, 29) + dt.timedelta(days=offset))["capafy_skill"]
        for offset in range(3)
    }
    assert picks == {"hook-lab", "slide-maker", "tiktok-script-pro"}


def test_select_for_date_is_deterministic_for_the_same_date() -> None:
    module = load_module()
    first = module.select_for_date(PRODUCTS, None, dt.date(2026, 9, 29))
    second = module.select_for_date(PRODUCTS, None, dt.date(2026, 9, 29))
    assert first == second
