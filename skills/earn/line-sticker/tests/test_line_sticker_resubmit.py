"""Unit tests for the リジェクト fixer: model action routing, the 2-per-product cap, and the
status-readback fence that must hold before a re-request counts as success.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import jsonschema

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))
import line_sticker_resubmit as MODULE  # noqa: E402

SCHEMA = json.loads((MODULE_ROOT / "schemas/resubmit-action.schema.json").read_text())


class ActionSchema(unittest.TestCase):
    def test_every_closed_action_validates(self) -> None:
        for action in ("leave_features", "retitle", "retag", "cannot_fix"):
            jsonschema.validate({"action": action, "reason": "テスト"}, SCHEMA)

    def test_unknown_action_is_rejected(self) -> None:
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate({"action": "delete_item", "reason": "x"}, SCHEMA)


class DailyCounterGuard(unittest.TestCase):
    def test_counter_pattern_extracts_the_used_count(self) -> None:
        match = MODULE.DAILY_COUNTER_RE.search("本日のリクエスト回数 30 / 30 に達しました")
        self.assertEqual(int(match.group(1)), 30)

    def test_counter_pattern_ignores_unrelated_numbers(self) -> None:
        self.assertIsNone(MODULE.DAILY_COUNTER_RE.search("ステータス: 審査待ち"))


class Cap(unittest.TestCase):
    def test_cap_reached_skips_the_model_and_notifies(self, ) -> None:
        calls = {"decide_action": 0, "notify": []}
        self.addCleanup(setattr, MODULE, "decide_action", MODULE.decide_action)
        self.addCleanup(setattr, MODULE, "notify", MODULE.notify)
        MODULE.decide_action = lambda *a, **k: calls.__setitem__("decide_action", calls["decide_action"] + 1)
        MODULE.notify = lambda set_dir, payload: calls["notify"].append(payload)

        item = {"product_id": "48067450", "auto_resubmit_count": MODULE.MAX_AUTO_RESUBMITS}
        result = MODULE.resubmit(Path("/tmp/nonexistent-set-dir"), item, "rejection text")

        self.assertEqual(calls["decide_action"], 0)
        self.assertEqual(result["resubmit_decision"], "cannot_fix")
        self.assertEqual(result["resubmit_decision_reason"], "auto_resubmit_cap_reached")
        self.assertEqual(len(calls["notify"]), 1)


class CannotFixRouting(unittest.TestCase):
    def test_cannot_fix_never_touches_the_browser(self) -> None:
        self.addCleanup(setattr, MODULE, "decide_action", MODULE.decide_action)
        self.addCleanup(setattr, MODULE.subprocess, "run", MODULE.subprocess.run)
        MODULE.decide_action = lambda *a, **k: {"action": "cannot_fix", "reason": "画像内容の問題"}

        def _fail_if_called(*a, **k):
            raise AssertionError("cannot_fix must not acquire the browser lease")
        MODULE.subprocess.run = _fail_if_called

        item = {"product_id": "48067450", "auto_resubmit_count": 0}
        result = MODULE.resubmit(Path("/tmp/nonexistent-set-dir"), item, "画像内容に問題があります")

        self.assertEqual(result["resubmit_decision"], "cannot_fix")
        self.assertEqual(result["resubmit_decision_reason"], "画像内容の問題")


class StatusReadbackFence(unittest.TestCase):
    """Re-request is an external effect: the cap counter may only advance after the page itself
    reads back 審査待ち/審査中, never from the click succeeding alone."""

    def _run_with_drive_result(self, drive_result: dict) -> dict:
        self.addCleanup(setattr, MODULE, "decide_action", MODULE.decide_action)
        self.addCleanup(setattr, MODULE.subprocess, "run", MODULE.subprocess.run)
        self.addCleanup(setattr, MODULE.asyncio, "run", MODULE.asyncio.run)
        MODULE.decide_action = lambda *a, **k: {"action": "leave_features", "reason": "特集条件を外す"}
        MODULE.subprocess.run = lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "http://127.0.0.1:9231\n"})()
        MODULE.asyncio.run = lambda coro: (coro.close(), drive_result)[1]
        item = {"product_id": "48067450", "auto_resubmit_count": 0}
        return MODULE.resubmit(Path("/tmp/nonexistent-set-dir"), item, "特集の参加条件を満たしておりません")

    def test_review_requested_increments_the_cap_counter(self) -> None:
        result = self._run_with_drive_result({"product_id": "48067450", "state": "review_requested",
                                                "state_observed": "審査待ち"})
        self.assertEqual(result["auto_resubmit_count"], 1)
        self.assertIn("last_auto_resubmit_at", result)

    def test_no_status_match_does_not_increment_the_cap_counter(self) -> None:
        result = self._run_with_drive_result({"product_id": "48067450", "state": "resubmit_blocked",
                                                "resubmit_block_reason": "daily_request_cap_30"})
        self.assertNotIn("auto_resubmit_count", result)

    def test_action_choice_is_recorded_even_on_fence_failure(self) -> None:
        result = self._run_with_drive_result({"product_id": "48067450"})
        self.assertEqual(result["resubmit_decision"], "leave_features")


if __name__ == "__main__":
    unittest.main()
