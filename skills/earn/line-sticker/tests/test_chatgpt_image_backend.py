"""chatgpt_image_backend.generate() and the static/character callers' fallback-to-Gemini wiring.

No network, no subprocess: the CLI-missing path is exercised directly (CLI really isn't at a
bogus path), and the callers are tested by monkeypatching chatgpt_image_backend itself so a
raised ChatGptImageGenUnavailable is observably routed to the Gemini fallback.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))
import chatgpt_image_backend as BACKEND  # noqa: E402
import line_sticker_static as STATIC  # noqa: E402


class GenerateMissingCli(unittest.TestCase):
    def test_missing_cli_raises_unavailable_not_a_bare_exception(self) -> None:
        original = BACKEND.CLI
        BACKEND.CLI = Path("/nonexistent/chatgpt-imagegen")
        try:
            with self.assertRaises(BACKEND.ChatGptImageGenUnavailable):
                BACKEND.generate("a test prompt")
        finally:
            BACKEND.CLI = original


class StaticStickerFallsBackToGemini(unittest.TestCase):
    def test_chatgpt_failure_falls_back_to_gemini_and_records_its_cost(self) -> None:
        from PIL import Image

        calls = {}

        def fake_generate(prompt, **kwargs):
            calls["prompt"] = prompt
            raise BACKEND.ChatGptImageGenUnavailable("cli not installed")

        def fake_gemini(ref_path, prompt):
            calls["gemini_prompt"] = prompt
            return Image.new("RGB", (64, 64), (0, 255, 0)), {"usage": "fake"}

        import line_sticker_static as mod
        original_gemini = mod._gemini_sticker_image
        mod._gemini_sticker_image = fake_gemini
        # chatgpt_image_backend is imported lazily inside _generate_sticker_image; patch the
        # module object it will import (same sys.modules entry).
        original_backend_generate = BACKEND.generate
        BACKEND.generate = fake_generate
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ref = Path(tmp) / "ref-padded.png"
                image, backend, cost = mod._generate_sticker_image(ref, "a cute otter", "waving happily", "test-task")
        finally:
            mod._gemini_sticker_image = original_gemini
            BACKEND.generate = original_backend_generate
        self.assertEqual(backend, "gemini_fallback")
        self.assertEqual(cost, STATIC.STATIC_IMAGE_COST_USD)
        self.assertEqual(calls["gemini_prompt"], "waving happily")

    def test_chatgpt_success_costs_zero(self) -> None:
        from PIL import Image

        tmp_png = Path(tempfile.mkstemp(suffix=".png")[1])
        Image.new("RGB", (64, 64), (0, 255, 0)).save(tmp_png)

        def fake_generate(prompt, **kwargs):
            return tmp_png

        import line_sticker_static as mod
        original_backend_generate = BACKEND.generate
        BACKEND.generate = fake_generate
        try:
            image, backend, cost = mod._generate_sticker_image(
                Path("/unused-ref.png"), "a cute otter", "waving happily", "test-task")
        finally:
            BACKEND.generate = original_backend_generate
        self.assertEqual(backend, "chatgpt_imagegen")
        self.assertEqual(str(cost), "0")
        self.assertFalse(tmp_png.exists())  # the temp PNG is deleted after loading


if __name__ == "__main__":
    unittest.main()
