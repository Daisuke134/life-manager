"""The "(文字あり)" twin of an on-sale animated set: same APNGs with the phrase drawn on, $0.

Top indie LINE creators sell the same art twice (e.g. "もちわさ日3(文字あり)" next to the text-less
one) and text versions dominate the store (SSOT row 17 step 1). No network, no browser.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import factory as MODULE  # noqa: E402
import seedance_set  # noqa: E402
from test_factory import _fake_deps  # noqa: E402

NUMBERED = [f"{n:02d}.png" for n in range(1, 25)]
GENERATION = {"character_sha256": "a" * 64, "plan_sha256": "b" * 64, "clip_receipts": [], "actual_cost_usd": "0"}


def _apng(path: Path, durations=(300, 700), loop=3, shift=0) -> None:
    frames = []
    for index, _ in enumerate(durations):
        frame = Image.new("RGBA", (320, 270), (0, 0, 0, 0))
        frame.paste((200, 120, 60, 255), (60 + shift + 10 * index, 40, 200 + shift + 10 * index, 230))
        frames.append(frame)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=list(durations), loop=loop)


def _seed_set(state_root: Path, number: int, *, draft=None, observed="販売中", real_apng=False,
              package=True, item_extra=None) -> Path:
    set_dir = state_root / f"set-{number:03d}"
    set_dir.mkdir(parents=True)
    MODULE._atomic_write_json(set_dir / "plan-draft.json",
                              draft if draft is not None else {"type": "animated", "character_id": "char-otter-001"})
    MODULE._atomic_write_json(set_dir / "listing.json", {
        "title": {"ja": "動く！こむぎの甘えん坊スタンプ", "en": "Daily Otter"},
        "description": {"ja": "説明", "en": "desc"},
        "type": "animated_sticker", "count": 24, "price_jpy": 250, "main": "m0", "tab": "m1",
    })
    MODULE._atomic_write_json(set_dir / "select.json", {
        "order": [f"m{i}" for i in range(24)], "main": "m0", "tab": "m1",
        "taste_id": "1", "character_category_id": "12",
    })
    MODULE._atomic_write_json(set_dir / "tags.json", {f"{n:02d}": [f"ことば{n}", "タグ"] for n in range(1, 25)})
    MODULE._atomic_write_json(set_dir / "creators-item.json", {
        "product_id": str(100 + number), "state": "review_requested", "state_observed": observed, **(item_extra or {}),
    })
    MODULE._atomic_write_json(set_dir / "stage.json", {
        "stage": "submitted", "started_at": "2026-01-01T00:00:00+00:00", "cost_usd": "0",
    })
    if package:
        out = set_dir / "package"
        out.mkdir()
        for n, name in enumerate(NUMBERED, 1):
            _apng(out / name, shift=n) if real_apng else (out / name).write_bytes(b"png")
        if real_apng:
            _apng(out / "main.png", shift=30)
            Image.new("RGBA", (96, 74), (200, 120, 60, 255)).save(out / "tab.png")
        else:
            (out / "main.png").write_bytes(b"main-apng")
            (out / "tab.png").write_bytes(b"tab-png")
        MODULE._atomic_write_json(out / "provenance.json", {
            "set_id": set_dir.name, "character_id": "char-otter-001", "rights": "original_ai_generated",
            "providers": {"image": "img", "animation": "anim"}, "assets": {}, "generation": GENERATION,
        })
    return set_dir


class TextVariantSource(unittest.TestCase):
    def test_picks_an_on_sale_animated_set_without_a_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            source = _seed_set(state_root, 1)
            self.assertEqual(MODULE.text_variant_source(state_root), source)

    def test_skips_static_unsold_already_varied_variant_and_packageless_sets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            _seed_set(state_root, 1, draft={"type": "static", "character_id": "c"})
            _seed_set(state_root, 2, observed="審査中")
            _seed_set(state_root, 3)
            _seed_set(state_root, 4, draft={"type": "animated", "variant_of": "set-003", "character_id": "c"})
            _seed_set(state_root, 5, package=False)
            self.assertIsNone(MODULE.text_variant_source(state_root))
            source = _seed_set(state_root, 6)
            self.assertEqual(MODULE.text_variant_source(state_root), source)


class WakeMakesTextVariant(unittest.TestCase):
    def test_wake_creates_the_variant_at_stage_package_without_planning(self) -> None:
        def fail_planner(*args, **kwargs):
            raise AssertionError("a text variant reuses the source art; the planner must not run")

        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            source = _seed_set(state_root, 1, real_apng=True,
                               item_extra={"title_ja": "動く！ポンタの毎日敬語スタンプ"})
            report = MODULE.wake(state_root, _fake_deps(planner=fail_planner, max_sets_per_day=5))
            variant = state_root / "set-002"
            self.assertEqual((report["set"], report["next_stage"]), ("set-002", "package"))
            self.assertEqual(MODULE.read_stage(variant), "package")
            self.assertEqual(MODULE.sets_started_today(state_root), 1)
            self.assertEqual(MODULE._read_json(variant / "plan-draft.json"), {
                "type": "animated", "variant_of": "set-001", "text_mode": "with_text",
                "character_id": "char-otter-001",
            })
            for name in ("select.json", "tags.json"):
                self.assertEqual(MODULE._read_json(variant / name), MODULE._read_json(source / name))
            listing = MODULE._read_json(variant / "listing.json")
            # The title filed on the store (after a duplicate-title retitle) is the one buyers pair
            # with; "スタンプ" is dropped so the mark fits Creators Market's width limit.
            self.assertEqual(listing["title"], {"ja": "動く！ポンタの毎日敬語(文字あり)", "en": "Daily Otter (with text)"})
            self.assertEqual(listing["description"], {"ja": "文字ありのスタンプです。説明", "en": "desc"})
            self.assertEqual((listing["type"], listing["count"], listing["price_jpy"]), ("animated_sticker", 24, 250))

            package = variant / "package"
            for name in ("main.png", "tab.png"):
                self.assertEqual((package / name).read_bytes(), (source / "package" / name).read_bytes())
            provenance = json.loads((package / "provenance.json").read_text())
            self.assertEqual(provenance["set_id"], "set-002")
            self.assertEqual(provenance["generation"], GENERATION)
            self.assertEqual(set(provenance["assets"]), set(NUMBERED) | {"main.png", "tab.png"})
            self.assertEqual(provenance["assets"]["01.png"]["sha256"],
                             hashlib.sha256((package / "01.png").read_bytes()).hexdigest())
            with zipfile.ZipFile(package / "submission.zip") as archive:
                self.assertEqual(sorted(archive.namelist()), sorted(NUMBERED + ["main.png", "tab.png"]))
            events = [json.loads(line) for line in (state_root / MODULE.EVENTS_LOG_NAME).read_text().splitlines()]
            self.assertTrue(any(e.get("set") == "set-002" and e.get("variant_of") == "set-001" for e in events))
            # Each source gets exactly one twin: the next new set is a normal plan again.
            self.assertIsNone(MODULE.text_variant_source(state_root))

    def test_variant_package_is_validated_not_rebuilt(self) -> None:
        def fail_packager(*args, **kwargs):
            raise AssertionError("the variant package is already built from the source APNGs")

        with tempfile.TemporaryDirectory() as tmp:
            state_root = Path(tmp)
            variant = state_root / "set-001"
            variant.mkdir()
            MODULE._atomic_write_json(variant / "plan-draft.json", {"type": "animated", "variant_of": "set-000"})
            MODULE._atomic_write_json(variant / "select.json", {"order": [], "main": "m0", "tab": "m1"})
            MODULE.write_stage(variant, "package")
            validated = []
            deps = _fake_deps(packager=fail_packager,
                              validator=lambda package_dir: validated.append(package_dir) or {"status": "ready"})
            report = MODULE.wake(state_root, deps)
            self.assertEqual(report["next_stage"], "submit")
            self.assertEqual(validated, [variant / "package"])


class TextApng(unittest.TestCase):
    def test_phrase_is_drawn_on_every_frame_keeping_timing_loop_and_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "src.png", Path(tmp) / "dst.png"
            _apng(src, durations=(300, 700), loop=3)
            seedance_set.text_apng(src, dst, "ありがとう")
            with Image.open(src) as before, Image.open(dst) as after:
                self.assertEqual((after.n_frames, after.size, after.info["loop"]), (2, (320, 270), 3))
                durations = []
                for index in range(2):
                    before.seek(index)
                    after.seek(index)
                    durations.append(after.info["duration"])
                    self.assertNotEqual(after.convert("RGBA").tobytes(), before.convert("RGBA").tobytes())
            # Not the writer's default even split (500/500): the source's own timing survives.
            self.assertEqual(durations, [300, 700])


if __name__ == "__main__":
    unittest.main()
