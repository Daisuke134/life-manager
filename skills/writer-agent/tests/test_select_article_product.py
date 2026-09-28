"""select_article_product.py: deterministic per-run product/CTA rotation.

Covers the new Capafy-traffic goal: the loop must not send every reader to the same
product forever, the rotation must be reproducible (same run_id -> same pick, so a
resumed run never lands on a different product mid-draft), and every Capafy pick must
carry a real registered agent_id plus a Capafy-native ct= campaign token.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "products.json"
SCRIPT_PATH = ROOT / "scripts" / "select_article_product.py"


def load_module():
    spec = importlib.util.spec_from_file_location("select_article_product", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_config_has_six_named_best_sellers_with_real_agent_ids():
    config = load_config()
    skills = config["products"]["capafy-skills"]["skills"]
    assert len(skills) == 6
    expected_agent_ids = {
        "8123079349", "8828622062", "9563867391",
        "2844813315", "7686597754", "3798949471",
    }
    assert {skill["agent_id"] for skill in skills.values()} == expected_agent_ids
    for slug, skill in skills.items():
        assert skill["buyer_problem"], f"{slug} is missing a buyer_problem"


def test_2026_09_29_picks_anicca_by_calendar_parity():
    module = load_module()
    config = load_config()
    result = module.select(config, "daily-2026-09-29")  # toordinal 739888, even -> anicca by this rotation
    assert result["product_id"] == "anicca"
    assert result["landing_url"] == "https://aniccaai.com/lm"
    assert result["capafy_skill"] is None
    assert result["ct"] == ""


def test_2026_09_28_picks_a_capafy_skill_with_a_ct_token():
    module = load_module()
    config = load_config()
    result = module.select(config, "daily-2026-09-28")  # toordinal 739887, odd -> capafy-skills
    assert result["product_id"] == "capafy-skills"
    assert result["landing_url"].startswith("https://capafy.ai/agent/")
    assert result["capafy_skill"] is not None
    assert result["ct"] == f"article-{result['capafy_skill']}"
    assert result["buyer_problem"]


def test_selection_is_deterministic_for_the_same_run_id():
    module = load_module()
    config = load_config()
    first = module.select(config, "daily-2026-10-03")
    second = module.select(config, "daily-2026-10-03")
    assert first == second


def test_capafy_days_rotate_through_different_skills():
    module = load_module()
    config = load_config()
    results = [module.select(config, f"daily-2026-10-{day:02d}") for day in range(1, 31)]
    picks = {r["capafy_skill"] for r in results if r["product_id"] == "capafy-skills"}
    assert picks == set(sorted(config["products"]["capafy-skills"]["skills"])), (
        "a full month did not visit every Capafy skill; rotation is not steady"
    )


def test_run_id_without_an_embedded_date_still_resolves_deterministically():
    module = load_module()
    config = load_config()
    first = module.select(config, "manual-run-abc")
    second = module.select(config, "manual-run-abc")
    assert first == second
    assert first["product_id"] in {"anicca", "capafy-skills"}


def test_cli_prints_one_json_object(tmp_path=None):
    import subprocess

    out = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--run-id", "daily-2026-09-29", "--config", str(CONFIG_PATH)],
        capture_output=True, text=True, check=True,
    ).stdout
    result = json.loads(out)
    assert result["product_id"] == "anicca"
