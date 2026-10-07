"""Unit tests for the LINE sticker planner's series-vs-flagship prompt and plan schema."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

import jsonschema

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))
import line_sticker_planner as MODULE  # noqa: E402

SCHEMA = json.loads((MODULE_ROOT / "schemas/plan.schema.json").read_text())


def _base_plan(**overrides) -> dict:
    plan = {
        "theme": "敬語・仕事",
        "series_of": None,
        "character_id": "char-test-001",
        "character_prompt": "a test mascot",
        "motions": [
            {"id": f"m{i}", "prompt": f"motion {i}", "start": None, "seconds": None, "plays": None}
            for i in range(30)
        ],
        "listing": {"title": {"ja": "テスト", "en": "Test"}, "description": {"ja": "説明", "en": "desc"}},
    }
    plan.update(overrides)
    return plan


class PlanSchema(unittest.TestCase):
    def test_accepts_series_of_null_for_a_new_flagship(self) -> None:
        jsonschema.validate(_base_plan(), SCHEMA)

    def test_accepts_series_of_naming_a_prior_set(self) -> None:
        jsonschema.validate(_base_plan(series_of="set-003"), SCHEMA)

    def test_rejects_a_plan_missing_series_of(self) -> None:
        plan = _base_plan()
        del plan["series_of"]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(plan, SCHEMA)


class PlanPrompt(unittest.TestCase):
    def test_prompt_includes_prior_set_facts_and_series_judgment(self) -> None:
        prior_facts = [{
            "set": "set-003",
            "character_id": "char-stardust-otter-001",
            "character_description": "a stardust otter",
            "theme": "毎日リアクション",
            "title": {"ja": "毎日使えるカワウソスタンプ"},
            "state_observed": "販売中",
        }]
        prompt = MODULE._build_plan_prompt(prior_facts)
        self.assertIn("set-003", prompt)
        self.assertIn("char-stardust-otter-001", prompt)
        self.assertIn("販売中", prompt)
        self.assertIn("series_of", prompt)

    def test_prompt_with_no_prior_sets_still_asks_for_series_of(self) -> None:
        prompt = MODULE._build_plan_prompt([])
        self.assertIn("series_of", prompt)

    def test_prompt_tells_the_model_to_prefer_the_best_selling_character_once_sales_exist(self) -> None:
        prior_facts = [
            {"set": "set-003", "character_id": "char-otter-001", "character_description": "an otter",
             "theme": "毎日リアクション", "title": {"ja": "カワウソ"}, "state_observed": "販売中", "sales_jpy": 1200},
            {"set": "set-004", "character_id": "char-bear-001", "character_description": "a bear",
             "theme": "敬語", "title": {"ja": "クマ"}, "state_observed": "販売中", "sales_jpy": 0},
        ]
        prompt = MODULE._build_plan_prompt(prior_facts)
        self.assertIn("sales_jpy", prompt)
        self.assertIn("売上が最も大きいキャラクター", prompt)


if __name__ == "__main__":
    unittest.main()
