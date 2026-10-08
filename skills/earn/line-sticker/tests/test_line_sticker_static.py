"""Static-sticker package validator, sticker_type/count selection, and scheduling rule.

No network, no browser: builds tiny real PNGs with PIL so parse_png (line_sticker.py's byte-level
PNG/APNG parser, reused unmodified) actually decodes something, and exercises the pure
scheduling/selection helpers directly.
"""
from __future__ import annotations

import datetime
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))
import line_sticker_static as STATIC  # noqa: E402
import line_sticker_submit as SUBMIT  # noqa: E402


def _png(path: Path, size: tuple[int, int]) -> None:
    from PIL import Image
    Image.new("RGBA", size, (10, 20, 30, 128)).save(path)


def _build_package(root: Path, count: int = 16, *, main_size=(240, 240), tab_size=(96, 74),
                    sticker_size=(300, 260)) -> None:
    root.mkdir(parents=True, exist_ok=True)
    names = ["main.png", "tab.png"] + [f"{n:02d}.png" for n in range(1, count + 1)]
    _png(root / "main.png", main_size)
    _png(root / "tab.png", tab_size)
    for n in range(1, count + 1):
        _png(root / f"{n:02d}.png", sticker_size)
    with zipfile.ZipFile(root / "submission.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(root / name, name)


class ValidateStaticPackage(unittest.TestCase):
    def test_valid_16_sticker_package_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "package"
            _build_package(root, count=16)
            result = STATIC.validate_static_package(root)
            self.assertEqual(result, {"status": "ready", "sticker_count": 16, "errors": []})

    def test_odd_sticker_dimensions_are_rejected(self) -> None:
        # LINE requires even width/height on every sticker image (guideline: "even-numbered
        # height and width"); an odd dimension must fail, not silently resize on submit.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "package"
            _build_package(root, count=8, sticker_size=(301, 261))
            result = STATIC.validate_static_package(root)
            self.assertEqual(result["status"], "invalid")
            self.assertTrue(any(e.startswith("dimensions_invalid:01.png") for e in result["errors"]))

    def test_oversize_sticker_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "package"
            _build_package(root, count=8, sticker_size=(372, 260))
            result = STATIC.validate_static_package(root)
            self.assertIn("dimensions_invalid:01.png", result["errors"])

    def test_wrong_main_dimensions_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "package"
            _build_package(root, count=8, main_size=(200, 200))
            result = STATIC.validate_static_package(root)
            self.assertIn("dimensions_invalid:main.png", result["errors"])

    def test_missing_file_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "package"
            _build_package(root, count=8)
            (root / "03.png").unlink()
            result = STATIC.validate_static_package(root)
            self.assertEqual(result["status"], "invalid")
            self.assertIn("file_missing:03.png", result["errors"])

    def test_disallowed_sticker_count_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "package"
            _build_package(root, count=10)  # not one of 8/16/24/32/40
            result = STATIC.validate_static_package(root)
            self.assertIn("sticker_count_invalid", result["errors"])

    def test_zip_missing_file_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "package"
            _build_package(root, count=8)
            with zipfile.ZipFile(root / "submission.zip", "w", zipfile.ZIP_DEFLATED) as archive:
                archive.write(root / "main.png", "main.png")  # drop everything else
            result = STATIC.validate_static_package(root)
            self.assertIn("zip_membership_mismatch", result["errors"])


class SubmitTypeAndCountSelection(unittest.TestCase):
    def test_static_listing_selects_the_static_radio_value(self) -> None:
        self.assertEqual(SUBMIT._sticker_type_value({"type": "static_sticker"}), "static")

    def test_animated_listing_keeps_the_existing_animation_radio_value(self) -> None:
        self.assertEqual(SUBMIT._sticker_type_value({"type": "animated_sticker"}), "animation")
        self.assertEqual(SUBMIT._sticker_type_value({}), "animation")  # old callers with no type

    def test_image_count_reads_listing_count_or_item_sticker_count(self) -> None:
        self.assertEqual(SUBMIT._image_count_value({"count": 16}), "16")
        self.assertEqual(SUBMIT._image_count_value({"sticker_count": 16}), "16")
        self.assertEqual(SUBMIT._image_count_value({}), "24")  # unchanged animated default


class ChooseLineType(unittest.TestCase):
    def test_fal_403_marker_forces_static(self) -> None:
        marker = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "code": 403}
        self.assertEqual(STATIC.choose_line_type(Path("/x"), ["animated", "animated"], marker), "static")

    def test_stale_fal_marker_is_ignored(self) -> None:
        old = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=48)
        marker = {"at": old.isoformat(), "code": 403}
        # No marker influence left; falls through to the ratio rule with no history -> static anyway.
        self.assertEqual(STATIC.choose_line_type(Path("/x"), [], marker), "static")

    def test_no_history_defaults_to_static(self) -> None:
        self.assertEqual(STATIC.choose_line_type(Path("/x"), [], None), "static")

    def test_ratio_rule_tracks_the_top_seller_static_share(self) -> None:
        # 24/15 static/animated observed; once static share already exceeds that, pick animated.
        heavy_static = ["static"] * 8 + ["animated"] * 1
        self.assertEqual(STATIC.choose_line_type(Path("/x"), heavy_static, None), "animated")
        heavy_animated = ["static"] * 1 + ["animated"] * 8
        self.assertEqual(STATIC.choose_line_type(Path("/x"), heavy_animated, None), "static")


class TextBearingVariant(unittest.TestCase):
    """SSOT 5.L row 5 (L20): top creators sell the same character text-free AND 文字入り."""

    def _plan(self, **overrides) -> dict:
        plan = {
            "series_of": "set-003", "character_id": "char-x-001", "character_prompt": "a mascot",
            "theme": "毎日返事", "text_mode": "with_text",
            "copy_target": {"product_url": "https://store.line.me/stickershop/product/1", "theme": "返事",
                            "phrases": ["ありがとう"], "expression_style": "bold lettering",
                            "text_or_no_text": "text", "title_pattern": "<キャラ名>の毎日返事【文字入り】"},
            "format_gap": None,
            "stickers": [{"id": f"s{i}", "prompt": "pose", "tags": ["OK"], "text": "了解"} for i in range(16)],
            "main_id": "s0", "tab_id": "s1",
            "listing": {"title": {"ja": "キャラの毎日返事", "en": "Daily replies"},
                        "description": {"ja": "説明", "en": "desc"}},
        }
        plan.update(overrides)
        return plan

    def test_plan_schema_accepts_text_mode_and_sticker_text(self) -> None:
        import jsonschema
        schema = json.loads((MODULE_ROOT / "schemas/static-plan.schema.json").read_text())
        jsonschema.validate(self._plan(), schema)
        no_text = self._plan(text_mode="no_text",
                             stickers=[{"id": f"s{i}", "prompt": "p", "tags": ["OK"], "text": None} for i in range(16)])
        jsonschema.validate(no_text, schema)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate(self._plan(text_mode="maybe"), schema)

    def test_text_render_keeps_sticker_within_line_limits(self) -> None:
        from PIL import Image
        art = Image.new("RGB", (512, 512), (0, 255, 0))
        art.paste((200, 60, 60), (150, 120, 360, 400))
        plain = STATIC._fit_sticker(art)
        lettered = STATIC._fit_sticker(art, text="おつかれさま")
        self.assertEqual(lettered.size, plain.size)
        width, height = lettered.size
        self.assertTrue(width <= 370 and height <= 320 and width % 2 == 0 and height % 2 == 0)
        self.assertEqual(lettered.mode, "RGBA")
        alpha = lettered.getchannel("A")
        bbox = alpha.getbbox()
        self.assertTrue(bbox[0] >= 10 and bbox[1] >= 10 and bbox[2] <= width - 10 and bbox[3] <= height - 10)
        self.assertNotEqual(plain.tobytes(), lettered.tobytes())
        self.assertEqual(alpha.getpixel((0, 0)), 0)  # still transparent outside the art + lettering

    def test_text_listing_title_marks_the_text_version_within_limit(self) -> None:
        listing = STATIC.mark_text_listing({"title": {"ja": "動く！ふわもちうさぎの毎日返事スタンプ", "en": "Fuwamochi Bunny Daily Replies"},
                                            "description": {"ja": "説明", "en": "desc"}})
        self.assertTrue(listing["title"]["ja"].endswith("【文字入り】"))
        self.assertIn("with text", listing["title"]["en"].lower())
        for title in listing["title"].values():
            self.assertLessEqual(SUBMIT._title_units(title), SUBMIT.TITLE_MAX)
        self.assertEqual(STATIC.mark_text_listing(listing), listing)  # idempotent

    def test_text_mark_drops_the_generic_suffix_instead_of_cutting_a_word(self) -> None:
        # 48156132 (2026-10-08) was filed as "星くずカワウソの毎日返事ス【文字入り】".
        listing = STATIC.mark_text_listing({"title": {"ja": "星くずカワウソの毎日返事スタンプ",
                                                      "en": "Stardust Otter Daily Replies Stickers"},
                                            "description": {"ja": "説明", "en": "desc"}})
        self.assertEqual(listing["title"]["ja"], "星くずカワウソの毎日返事【文字入り】")


if __name__ == "__main__":
    unittest.main()
