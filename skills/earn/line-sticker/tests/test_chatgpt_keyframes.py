"""chatgpt_keyframes: sprite-sheet slicing -> frames, and the assembled APNG meets LINE's
animated-sticker limits (reuses line_sticker.parse_png, the same structural validator the
official package validator calls)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image, ImageDraw

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))
import chatgpt_keyframes as MODULE  # noqa: E402
import line_sticker  # noqa: E402

POLICY = json.loads((MODULE_ROOT / "official-policy.json").read_text())


def _fake_sheet(cols: int, rows: int, cell: int = 64) -> Image.Image:
    """A synthetic grid sprite sheet: green background, one shrinking red square per cell so
    frames are distinguishable (stands in for a real chatgpt-imagegen sprite sheet)."""
    sheet = Image.new("RGB", (cols * cell, rows * cell), (0, 255, 0))
    draw = ImageDraw.Draw(sheet)
    for row in range(rows):
        for col in range(cols):
            index = row * cols + col
            size = 10 + index
            x0, y0 = col * cell + cell // 2 - size, row * cell + cell // 2 - size
            draw.rectangle([x0, y0, x0 + size * 2, y0 + size * 2], fill=(200, 30, 30))
    return sheet


class SliceGridTest(unittest.TestCase):
    def test_slices_grid_into_cols_times_rows_frames(self) -> None:
        cols, rows = MODULE.GRID
        sheet = _fake_sheet(cols, rows)
        frames = MODULE.slice_grid(sheet, cols, rows)
        self.assertEqual(len(frames), cols * rows)
        self.assertTrue(all(frame.size == (64, 64) for frame in frames))

    def test_grid_frame_count_satisfies_line_apng_policy(self) -> None:
        cols, rows = MODULE.GRID
        self.assertGreaterEqual(cols * rows, POLICY["apng"]["min_frames"])
        self.assertLessEqual(cols * rows, POLICY["apng"]["max_frames"])


class ApngAssemblyTest(unittest.TestCase):
    def test_apng_from_sliced_sheet_passes_line_sticker_parse_png(self) -> None:
        cols, rows = MODULE.GRID
        with tempfile.TemporaryDirectory() as tmp:
            set_dir = Path(tmp)
            (set_dir / "clips").mkdir()
            _fake_sheet(cols, rows).save(set_dir / "clips" / "wave-sheet.png")
            plan = {"motions": [{"id": "wave", "prompt": "wave", "plays": 2}]}
            MODULE.apng(set_dir, plan)
            path = set_dir / "candidates" / "wave.png"
            self.assertTrue(path.is_file())
            self.assertLessEqual(path.stat().st_size, POLICY["max_file_bytes"])
            parsed = line_sticker.parse_png(path)
            self.assertTrue(parsed["animated"])
            self.assertEqual(parsed["width"], POLICY["sticker"]["max_width"])
            self.assertEqual(parsed["height"], POLICY["sticker"]["max_height"])
            self.assertGreaterEqual(parsed["frames"], POLICY["apng"]["min_frames"])
            self.assertLessEqual(parsed["frames"], POLICY["apng"]["max_frames"])
            self.assertIn(parsed["color_type"], POLICY["required_color_types"])


class ClipsReceiptTest(unittest.TestCase):
    def test_clips_writes_zero_cost_receipt_per_motion(self) -> None:
        plan = {"character_prompt": "a round orange hamster mascot",
                "motions": [{"id": "wave", "prompt": "waving hello"}]}
        with tempfile.TemporaryDirectory() as tmp:
            set_dir = Path(tmp)
            sheet_path = set_dir / "clips" / "wave-sheet.png"

            def fake_generate(prompt: str, out_path: Path, *, timeout: int = 280) -> None:
                self.assertIn("a round orange hamster mascot", prompt)
                self.assertIn("waving hello", prompt)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                _fake_sheet(*MODULE.GRID).save(out_path)

            with mock.patch.object(MODULE, "generate_sheet", side_effect=fake_generate):
                MODULE.clips(set_dir, plan)
            receipt = json.loads((set_dir / "clips" / "wave.json").read_text())
            self.assertEqual(receipt["estimated_usd"], 0)
            self.assertEqual(receipt["provider"], "chatgpt-imagegen")
            self.assertTrue(sheet_path.is_file())

    def test_clips_skips_motion_when_chatgpt_imagegen_unavailable(self) -> None:
        plan = {"character_prompt": "x", "motions": [{"id": "wave", "prompt": "wave"}]}
        with tempfile.TemporaryDirectory() as tmp:
            set_dir = Path(tmp)
            with mock.patch.object(MODULE, "generate_sheet",
                                    side_effect=MODULE.ChatGptImageGenUnavailable("no cli")):
                MODULE.clips(set_dir, plan)
            self.assertFalse((set_dir / "clips" / "wave.json").exists())


if __name__ == "__main__":
    unittest.main()
