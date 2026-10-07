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
        "theme": "test", "series_of": None, "character_id": "char-test-001", "character_prompt": "a test mascot",
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


class FullRun(unittest.TestCase):
    def test_one_run_takes_a_new_set_all_the_way_to_submitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            report = MODULE.run(state_root, _fake_deps(max_sets_per_day=5))
            self.assertEqual(MODULE.read_stage(state_root / "set-001"), "submitted")
            self.assertEqual(report["action"], "advanced")
            self.assertEqual(report["next_stage"], "submitted")
            self.assertFalse((state_root / "set-002").exists())  # next set waits for the next run

    def test_run_stops_on_retry_instead_of_spinning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            deps = _fake_deps(clips_runner=lambda set_dir, plan: (set_dir / "clips").mkdir(exist_ok=True))
            report = MODULE.run(state_root, deps)
            self.assertEqual(report["action"], "retry")
            self.assertEqual(MODULE.read_stage(state_root / "set-001"), "clips")

    def test_run_respects_daily_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            deps = _fake_deps(max_sets_per_day=1)
            MODULE.run(state_root, deps)
            self.assertEqual(MODULE.run(state_root, deps)["action"], "skip")


class SubmittedCleanup(unittest.TestCase):
    def test_submitted_set_drops_candidates_but_keeps_package_and_clips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            MODULE.run(state_root, _fake_deps(max_sets_per_day=5))
            set_dir = state_root / "set-001"
            self.assertEqual(MODULE.read_stage(set_dir), "submitted")
            self.assertFalse((set_dir / "candidates").exists())
            self.assertTrue((set_dir / "package").exists())
            self.assertTrue((set_dir / "clips").exists())  # distribute renders from selected clips


class FullRunSubmit(unittest.TestCase):
    def test_run_keeps_going_through_submit_sub_states(self) -> None:
        states = iter(["metadata_saved", "images_uploaded", "tagged", "review_requested"])

        def staged_submit(set_dir, item, listing, tags):
            return {"product_id": "123", "url": "u", "state": next(states)}

        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            report = MODULE.run(state_root, _fake_deps(submit=staged_submit))
            self.assertEqual(report["next_stage"], "submitted")
            self.assertEqual(MODULE.read_stage(state_root / "set-001"), "submitted")


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


class SeriesSequel(unittest.TestCase):
    def test_series_of_copies_reference_and_skips_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            source_dir = state_root / "set-001"
            source_dir.mkdir(parents=True)
            (source_dir / "char-ref.png").write_bytes(b"source-char-ref")
            (source_dir / "ref-padded.png").write_bytes(b"source-ref-padded")

            new_dir = state_root / "set-002"
            new_dir.mkdir(parents=True)
            MODULE._atomic_write_json(new_dir / "plan-draft.json", {
                "theme": "敬語・仕事", "series_of": "set-001",
                "character_id": "char-test-001", "character_prompt": "a test mascot",
                "motions": [{"id": f"m{i}", "prompt": f"motion {i}"} for i in range(30)],
                "listing": {"title": {"ja": "テスト2", "en": "Test2"}, "description": {"ja": "説明", "en": "desc"}},
            })

            def fail_if_called(set_dir, plan):
                raise AssertionError("character_image must not be called for a series sequel")

            deps = _fake_deps(character_image=fail_if_called)
            next_stage = MODULE.run_character(new_dir, state_root, deps)
            self.assertEqual(next_stage, "clips")
            self.assertEqual((new_dir / "char-ref.png").read_bytes(), b"source-char-ref")
            self.assertEqual((new_dir / "ref-padded.png").read_bytes(), b"source-ref-padded")
            receipt = json.loads((new_dir / "char-ref.receipt.json").read_text())
            self.assertEqual(receipt, {"reused": True, "source_set": "set-001"})

    def test_unusable_series_of_falls_back_to_generation(self) -> None:
        # A model-named set that is missing, lacks reference art, or escapes state_root must not
        # wedge the character stage on every wake; it generates a fresh character instead.
        for series_of in ("set-009", "../set-001", "set-001"):
            with tempfile.TemporaryDirectory() as tmp:
                state_root = Path(tmp)
                (state_root / "set-001").mkdir()  # exists but has no reference art
                new_dir = state_root / "set-002"
                new_dir.mkdir()
                MODULE._atomic_write_json(new_dir / "plan-draft.json", {
                    "theme": "敬語", "series_of": series_of,
                    "character_id": "char-test-001", "character_prompt": "a test mascot",
                    "motions": [], "listing": {"title": {"ja": "t", "en": "t"}, "description": {"ja": "d", "en": "d"}},
                })
                calls = []
                deps = _fake_deps(character_image=lambda set_dir, plan: calls.append(set_dir))
                self.assertEqual(MODULE.run_character(new_dir, state_root, deps), "clips")
                self.assertEqual(calls, [new_dir], series_of)

    def test_prior_set_facts_feed_the_planner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            source_dir = state_root / "set-001"
            source_dir.mkdir(parents=True)
            MODULE._atomic_write_json(source_dir / "plan-draft.json", {
                "theme": "毎日リアクション", "series_of": None,
                "character_id": "char-otter-001", "character_prompt": "a stardust otter",
                "motions": [], "listing": {"title": {"ja": "x", "en": "x"}, "description": {"ja": "x", "en": "x"}},
            })
            MODULE._atomic_write_json(source_dir / "listing.json", {"title": {"ja": "毎日使えるカワウソ", "en": "Otter"}})
            MODULE._atomic_write_json(source_dir / "creators-item.json", {"state_observed": "販売中"})
            MODULE.write_stage(source_dir, "submitted")

            seen = {}

            def capturing_planner(set_dir, prior_facts):
                seen["facts"] = prior_facts
                return _plan(set_dir, prior_facts)

            deps = _fake_deps(planner=capturing_planner)
            MODULE.wake(state_root, deps)  # starts set-002, runs plan stage
            self.assertEqual(seen["facts"], [{
                "set": "set-001", "character_id": "char-otter-001",
                "character_description": "a stardust otter", "theme": "毎日リアクション",
                "title": {"ja": "毎日使えるカワウソ", "en": "Otter"}, "state_observed": "販売中",
            }])


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
