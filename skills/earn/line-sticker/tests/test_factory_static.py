"""Stage-routing contract for the static line inside the shared factory state machine
(factory.py run_plan/run_character/run_images/run_package dispatch). No network, no browser -
mirrors tests/test_factory.py's fake-deps style exactly, adding only the static_* fields.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))
import factory as MODULE  # noqa: E402


def _animated_plan(set_dir, prior, market_items=None):
    return {
        "theme": "test", "series_of": None, "character_id": "char-test-001", "character_prompt": "a test mascot",
        "motions": [{"id": f"m{i}", "prompt": f"motion {i}"} for i in range(30)],
        "listing": {"title": {"ja": "テスト", "en": "Test"}, "description": {"ja": "説明", "en": "desc"}},
    }


def _static_plan(set_dir, prior, market_items=None):
    return {
        "series_of": "set-000", "character_id": "char-test-001", "character_prompt": "a test mascot",
        "theme": "static-test",
        "stickers": [{"id": f"s{i}", "prompt": f"pose {i}", "tags": ["はぁ"]} for i in range(16)],
        "main_id": "s0", "tab_id": "s1",
        "listing": {"title": {"ja": "静止画テスト", "en": "Static Test"}, "description": {"ja": "説明", "en": "desc"}},
    }


def _fake_static_deps(**overrides) -> MODULE.Deps:
    base = dict(
        planner=_animated_plan,
        character_image=lambda set_dir, plan: (set_dir / "ref-padded.png").write_bytes(b"png"),
        clips_runner=lambda set_dir, plan: None,
        apng_runner=lambda set_dir, plan: None,
        selector=lambda set_dir, plan: {},
        packager=lambda set_dir, plan_path, order, main_id, tab_id: None,
        validator=lambda package_dir: {"status": "ready"},
        submit=lambda set_dir, item, listing, tags: {
            "product_id": "123", "url": "https://example.test/sticker/123", "state": "review_requested",
        },
        notify=lambda set_dir, payload: None,
        max_usd_per_set=Decimal("4"),
        max_sets_per_day=5,
        type_decider=lambda state_root: "static",
        static_planner=_static_plan,
        static_images_runner=lambda set_dir, plan: [
            (set_dir / "candidates").mkdir(exist_ok=True),
            *[(set_dir / "candidates" / f"{s['id']}.png").write_bytes(b"png") for s in plan["stickers"]],
            *[(set_dir / "candidates" / f"{s['id']}.cost.json").write_text('{"estimated_usd": "0.02"}')
              for s in plan["stickers"]],
        ],
        static_packager=lambda set_dir, order, main_id, tab_id: (set_dir / "package").mkdir(exist_ok=True),
        static_validator=lambda package_dir: {"status": "ready"},
    )
    base.update(overrides)
    return MODULE.Deps(**base)


class StaticStageRouting(unittest.TestCase):
    def test_plan_stage_tags_the_set_as_static_when_type_decider_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            deps = _fake_static_deps()
            MODULE.wake(state_root, deps)  # plan -> character
            draft = MODULE._read_json(state_root / "set-001" / "plan-draft.json")
            self.assertEqual(draft["type"], "static")
            self.assertEqual(draft["stickers"][0]["id"], "s0")

    def test_character_stage_routes_static_to_images_not_clips(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            deps = _fake_static_deps()
            MODULE.wake(state_root, deps)  # plan
            report = MODULE.wake(state_root, deps)  # character
            self.assertEqual(report["next_stage"], "images")

    def test_full_static_run_reaches_submitted_without_clips_or_select(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            deps = _fake_static_deps()
            stages_seen = []
            for _ in range(6):
                stages_seen.append(MODULE.wake(state_root, deps)["stage"])
            set_dir = state_root / "set-001"
            self.assertEqual(MODULE.read_stage(set_dir), "submitted")
            self.assertEqual(stages_seen, ["plan", "character", "images", "package", "submit"] + stages_seen[5:])
            self.assertNotIn("clips", stages_seen)
            self.assertNotIn("select", stages_seen)
            listing = MODULE._read_json(set_dir / "listing.json")
            self.assertEqual(listing["type"], "static_sticker")
            self.assertEqual(listing["count"], 16)
            self.assertEqual(listing["price_jpy"], 190)

    def test_incomplete_images_retries_the_images_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            deps = _fake_static_deps(static_images_runner=lambda set_dir, plan: (set_dir / "candidates").mkdir(exist_ok=True))
            MODULE.wake(state_root, deps)  # plan
            MODULE.wake(state_root, deps)  # character -> images
            report = MODULE.wake(state_root, deps)  # images stays images (no files written)
            self.assertEqual(report["action"], "retry")
            self.assertEqual(report["stage"], "images")

    def test_package_stage_dispatches_to_the_static_packager_and_validator(self) -> None:
        calls = []

        def static_packager(set_dir, order, main_id, tab_id):
            calls.append(("package", order, main_id, tab_id))
            (set_dir / "package").mkdir(exist_ok=True)

        def animated_packager(set_dir, plan_path, order, main_id, tab_id):
            calls.append(("animated_package",))

        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            deps = _fake_static_deps(static_packager=static_packager, packager=animated_packager)
            for _ in range(4):
                MODULE.wake(state_root, deps)  # plan, character, images, package
            self.assertEqual(calls, [("package", [f"s{i}" for i in range(16)], "s0", "s1")])


class LineTypeHistory(unittest.TestCase):
    def test_recent_line_types_reads_each_sets_plan_draft(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            for i, line_type in enumerate(["static", "animated"], 1):
                set_dir = state_root / f"set-{i:03d}"
                set_dir.mkdir(parents=True)
                MODULE._atomic_write_json(set_dir / "plan-draft.json", {"type": line_type})
            self.assertEqual(MODULE._recent_line_types(state_root), ["static", "animated"])


class TextModeForwarding(unittest.TestCase):
    def test_character_stage_forwards_text_mode_and_phrases_to_plan_json(self) -> None:
        def text_plan(set_dir, prior, market_items=None):
            plan = _static_plan(set_dir, prior, market_items)
            plan["text_mode"] = "with_text"
            for sticker in plan["stickers"]:
                sticker["text"] = "了解"
            return plan
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            deps = _fake_static_deps(static_planner=text_plan)
            MODULE.wake(state_root, deps)
            MODULE.wake(state_root, deps)
            plan = MODULE._read_json(state_root / "set-001" / "plan.json")
            self.assertEqual(plan["text_mode"], "with_text")
            self.assertEqual(plan["stickers"][0]["text"], "了解")


if __name__ == "__main__":
    unittest.main()
