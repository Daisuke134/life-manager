"""State-machine contract tests for the LINE sticker factory owner (no network, no browser)."""

from __future__ import annotations

import datetime
import json
from decimal import Decimal
from pathlib import Path
import sys
import tempfile
import unittest

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))
import factory as MODULE  # noqa: E402


def _plan(set_dir, prior):
    return {
        "theme": "test", "character_id": "char-test-001", "character_prompt": "a test mascot",
        "motions": [{"id": f"m{i}", "prompt": f"motion {i}"} for i in range(30)],
        "listing": {"title": {"ja": "テスト", "en": "Test"}, "description": {"ja": "説明", "en": "desc"}},
    }


def _fake_deps(**overrides) -> MODULE.Deps:
    base = dict(
        planner=_plan,
        character_image=lambda set_dir, plan: (set_dir / "ref-padded.png").write_bytes(b"png"),
        clips_runner=lambda set_dir, plan: [
            (set_dir / "clips").mkdir(exist_ok=True),
            *[(set_dir / "clips" / f"{m['id']}.json").write_text("{}") for m in plan["motions"]],
        ],
        apng_runner=lambda set_dir, plan: None,
        selector=lambda set_dir, plan: {
            "order": [f"m{i}" for i in range(24)], "main": "m0", "tab": "m1",
            "listing": {"title": {"ja": "テスト", "en": "Test"}, "description": {"ja": "説明", "en": "desc"}},
            "tags": [{"sticker_number": f"{n:02d}", "tags": ["はぁ"]} for n in range(1, 25)],
            "taste_id": "1", "character_category_id": "10", "campaign_value": None,
        },
        packager=lambda set_dir, plan_path, order, main_id, tab_id: (set_dir / "package").mkdir(exist_ok=True),
        validator=lambda package_dir: {"status": "ready"},
        submit=lambda set_dir, item, listing, tags: {
            "product_id": "123", "url": "https://example.test/sticker/123", "state": "review_requested",
        },
        notify=lambda set_dir, payload: None,
        max_usd_per_set=Decimal("4"),
        max_sets_per_day=2,
    )
    base.update(overrides)
    return MODULE.Deps(**base)


class OneStagePerWake(unittest.TestCase):
    def test_advances_exactly_one_stage_per_wake(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            deps = _fake_deps(max_sets_per_day=1)
            stages_seen = []
            for _ in range(7):
                report = MODULE.wake(state_root, deps)
                stages_seen.append(report)
            set_dir = state_root / "set-001"
            self.assertEqual(MODULE.read_stage(set_dir), "submitted")
            seq = [r["stage"] for r in stages_seen]
            self.assertEqual(seq, list(MODULE.STAGES[:7]))
            self.assertTrue(all(r["action"] == "advanced" for r in stages_seen))

    def test_incomplete_clips_retries_same_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            deps = _fake_deps(clips_runner=lambda set_dir, plan: (set_dir / "clips").mkdir(exist_ok=True))
            MODULE.wake(state_root, deps)  # plan -> character
            MODULE.wake(state_root, deps)  # character -> clips
            report = MODULE.wake(state_root, deps)  # clips stays clips (no receipts written)
            self.assertEqual(report["action"], "retry")
            self.assertEqual(report["stage"], "clips")
            self.assertEqual(MODULE.read_stage(state_root / "set-001"), "clips")


class DailyCap(unittest.TestCase):
    def test_no_new_set_once_daily_cap_reached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            deps = _fake_deps(max_sets_per_day=1)
            for _ in range(7):
                MODULE.wake(state_root, deps)  # drive set-001 to submitted
            self.assertEqual(MODULE.read_stage(state_root / "set-001"), "submitted")
            report = MODULE.wake(state_root, deps)
            self.assertEqual(report, {"action": "skip", "reason": "daily_cap_reached", "started_today": 1})
            self.assertFalse((state_root / "set-002").exists())

    def test_second_set_starts_under_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            deps = _fake_deps(max_sets_per_day=2)
            for _ in range(7):
                MODULE.wake(state_root, deps)
            report = MODULE.wake(state_root, deps)
            self.assertEqual(report["action"], "advanced")
            self.assertEqual(report["set"], "set-002")


class SubmitFence(unittest.TestCase):
    def test_submit_is_resumable_and_never_double_creates(self) -> None:
        calls = []

        def flaky_submit(set_dir, item, listing, tags):
            calls.append(dict(item))
            if not item:
                return {"product_id": "999", "url": "https://example.test/sticker/999", "state": "metadata_saved"}
            return {**item, "state": "review_requested"}

        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            deps = _fake_deps(submit=flaky_submit)
            for _ in range(6):
                MODULE.wake(state_root, deps)  # plan..package
            set_dir = state_root / "set-001"
            self.assertEqual(MODULE.read_stage(set_dir), "submit")
            report1 = MODULE.wake(state_root, deps)  # submit sub-step 1: creates item
            self.assertEqual(report1["action"], "retry")
            item = json.loads((set_dir / "creators-item.json").read_text())
            self.assertEqual(item["state"], "metadata_saved")
            report2 = MODULE.wake(state_root, deps)  # submit sub-step 2: review_requested
            self.assertEqual(report2["next_stage"], "submitted")
            self.assertEqual(len(calls), 2)
            # Item is only ever created once: the second call carried the prior item, not {}.
            self.assertEqual(calls[1]["product_id"], "999")

    def test_replay_after_crash_reads_back_existing_item_not_a_new_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            set_dir = state_root / "set-001"
            set_dir.mkdir(parents=True)
            MODULE.write_stage(set_dir, "submit")
            MODULE._atomic_write_json(set_dir / "listing.json", {"title": {"ja": "x", "en": "x"}})
            MODULE._atomic_write_json(set_dir / "tags.json", {})
            MODULE._atomic_write_json(set_dir / "plan.json", {"motions": []})
            MODULE._atomic_write_json(set_dir / "creators-item.json", {
                "product_id": "555", "url": "https://example.test/sticker/555", "state": "images_uploaded",
            })
            seen_items = []

            def submit(sd, item, listing, tags):
                seen_items.append(item)
                return {**item, "state": "review_requested"}

            deps = _fake_deps(submit=submit)
            report = MODULE.wake(state_root, deps)
            self.assertEqual(seen_items, [{"product_id": "555", "url": "https://example.test/sticker/555", "state": "images_uploaded"}])
            self.assertEqual(report["next_stage"], "submitted")


class CostCap(unittest.TestCase):
    def test_halts_before_running_a_stage_over_cost_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            set_dir = state_root / "set-001"
            set_dir.mkdir(parents=True)
            MODULE.write_stage(set_dir, "clips")
            MODULE.add_cost(set_dir, Decimal("10"))
            deps = _fake_deps()
            report = MODULE.wake(state_root, deps)
            self.assertEqual(report["action"], "halt")
            self.assertEqual(report["reason"], "cost_cap_exceeded")


if __name__ == "__main__":
    unittest.main()
