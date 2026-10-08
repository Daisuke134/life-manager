"""Unit tests for the LINE sticker planner's series-vs-flagship prompt and plan schema."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
import sys
import tempfile
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


class GuardCampaignValue(unittest.TestCase):
    def test_a_value_present_in_open_features_passes_through(self) -> None:
        open_features = [{"value": "835", "title": "冬を感じるスタンプ", "deadline": "2026-12-04"}]
        self.assertEqual(MODULE._guard_campaign_value("835", open_features), "835")

    def test_null_stays_null(self) -> None:
        self.assertIsNone(MODULE._guard_campaign_value(None, []))

    def test_a_value_the_model_invented_is_dropped(self) -> None:
        self.assertIsNone(MODULE._guard_campaign_value("999", [{"value": "835"}]))

    def test_a_value_not_in_the_open_list_is_dropped_even_if_once_valid(self) -> None:
        # open_features already excludes expired entries; anything missing from it is unjoinable.
        self.assertIsNone(MODULE._guard_campaign_value("835", []))


class DeadlinePassed(unittest.TestCase):
    def test_missing_deadline_is_not_treated_as_passed(self) -> None:
        self.assertFalse(MODULE._deadline_passed(None, datetime.date(2026, 10, 8)))

    def test_future_deadline_is_not_passed(self) -> None:
        self.assertFalse(MODULE._deadline_passed("2026-12-04", datetime.date(2026, 10, 8)))

    def test_past_deadline_is_passed(self) -> None:
        self.assertTrue(MODULE._deadline_passed("2026-10-01", datetime.date(2026, 10, 8)))

    def test_unparseable_deadline_fails_closed(self) -> None:
        self.assertTrue(MODULE._deadline_passed("not-a-date", datetime.date(2026, 10, 8)))


class OpenFeatures(unittest.TestCase):
    def test_no_features_file_returns_empty(self) -> None:
        original = MODULE.FEATURES_FILE
        MODULE.FEATURES_FILE = Path(tempfile.mkdtemp()) / "missing-features.json"
        try:
            self.assertEqual(MODULE._open_features(datetime.date(2026, 10, 8)), [])
        finally:
            MODULE.FEATURES_FILE = original

    def test_expired_features_are_filtered_out(self) -> None:
        original = MODULE.FEATURES_FILE
        with tempfile.TemporaryDirectory() as tmp:
            MODULE.FEATURES_FILE = Path(tmp) / "features.json"
            MODULE.FEATURES_FILE.write_text(json.dumps({"features": [
                {"value": "811", "title": "秋を感じるスタンプ", "deadline": "2026-10-01"},
                {"value": "835", "title": "冬を感じるスタンプ", "deadline": "2026-12-04"},
            ]}))
            try:
                open_features = MODULE._open_features(datetime.date(2026, 10, 8))
            finally:
                MODULE.FEATURES_FILE = original
        self.assertEqual([f["value"] for f in open_features], ["835"])


class SelectorPromptIncludesOpenFeatures(unittest.TestCase):
    def test_prompt_names_the_open_feature_and_guard_drops_an_expired_one(self) -> None:
        original_features_file = MODULE.FEATURES_FILE
        original_run_agent = MODULE._run_agent
        captured = {}
        with tempfile.TemporaryDirectory() as tmp:
            set_dir = Path(tmp)
            MODULE.FEATURES_FILE = set_dir / "features.json"
            MODULE.FEATURES_FILE.write_text(json.dumps({"features": [
                {"value": "835", "title": "冬を感じるスタンプ", "deadline": "2099-12-04",
                 "conditions": "8個以上40個以下、新規キャラクターのみ"},
            ]}))
            (set_dir / "candidates-sheet.png").write_bytes(b"\x89PNG\r\n")

            def fake_run_agent(*, prompt, schema, evidence_dir, task_label, images=None):
                captured["prompt"] = prompt
                return {
                    "order": [f"m{i}" for i in range(24)], "main": "m0", "tab": "m1",
                    "rejected": [], "listing": {"title": {"ja": "た", "en": "t"}, "description": {"ja": "d", "en": "d"}},
                    "tags": [], "taste_id": "1", "character_category_id": "10",
                    "campaign_value": "835",
                }

            MODULE._run_agent = fake_run_agent
            try:
                plan = {"motions": [{"id": f"m{i}"} for i in range(30)], "listing": {}}
                result = MODULE.selector(set_dir, plan)
            finally:
                MODULE._run_agent = original_run_agent
                MODULE.FEATURES_FILE = original_features_file

        self.assertIn("冬を感じるスタンプ", captured["prompt"])
        self.assertIn("8個以上40個以下", captured["prompt"])
        self.assertEqual(result["campaign_value"], "835")

    def test_guard_nulls_out_a_value_that_is_not_actually_open(self) -> None:
        original_features_file = MODULE.FEATURES_FILE
        original_run_agent = MODULE._run_agent
        with tempfile.TemporaryDirectory() as tmp:
            set_dir = Path(tmp)
            MODULE.FEATURES_FILE = set_dir / "features.json"
            MODULE.FEATURES_FILE.write_text(json.dumps({"features": []}))
            (set_dir / "candidates-sheet.png").write_bytes(b"\x89PNG\r\n")

            def fake_run_agent(*, prompt, schema, evidence_dir, task_label, images=None):
                return {
                    "order": [f"m{i}" for i in range(24)], "main": "m0", "tab": "m1",
                    "rejected": [], "listing": {"title": {"ja": "た", "en": "t"}, "description": {"ja": "d", "en": "d"}},
                    "tags": [], "taste_id": "1", "character_category_id": "10",
                    "campaign_value": "835",  # the model picked a value that is not open any more
                }

            MODULE._run_agent = fake_run_agent
            try:
                plan = {"motions": [{"id": f"m{i}"} for i in range(30)], "listing": {}}
                result = MODULE.selector(set_dir, plan)
            finally:
                MODULE._run_agent = original_run_agent
                MODULE.FEATURES_FILE = original_features_file

        self.assertIsNone(result["campaign_value"])


if __name__ == "__main__":
    unittest.main()
