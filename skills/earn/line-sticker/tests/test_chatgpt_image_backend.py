"""chatgpt_image_backend.generate() and the static/character callers' fallback-to-Gemini wiring.

No network, no subprocess: the CLI-missing path is exercised directly (CLI really isn't at a
bogus path), and the callers are tested by monkeypatching chatgpt_image_backend itself so a
raised ChatGptImageGenUnavailable is observably routed to the Gemini fallback.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
                with mock.patch.dict(os.environ, {"LINE_STICKER_GEMINI_FALLBACK": "1"}):
                    image, backend, cost = mod._generate_sticker_image(ref, "a cute otter", "waving happily", "test-task")
        finally:
            mod._gemini_sticker_image = original_gemini
            BACKEND.generate = original_backend_generate
        self.assertEqual(backend, "gemini_fallback")
        self.assertEqual(cost, STATIC.STATIC_IMAGE_COST_USD)
        self.assertEqual(calls["gemini_prompt"], "waving happily")

    def test_paid_gemini_fallback_is_off_by_default(self) -> None:
        def fake_generate(prompt, **kwargs):
            raise BACKEND.ChatGptImageGenUnavailable("cli not installed")

        def fake_gemini(ref_path, prompt):
            raise AssertionError("paid Gemini must not be called")

        import line_sticker_static as mod
        original_gemini, original_backend_generate = mod._gemini_sticker_image, BACKEND.generate
        mod._gemini_sticker_image, BACKEND.generate = fake_gemini, fake_generate
        try:
            with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("LINE_STICKER_GEMINI_FALLBACK", None)
                with self.assertRaises(BACKEND.ChatGptImageGenUnavailable):
                    mod._generate_sticker_image(Path(tmp) / "ref.png", "a cute otter", "waving", "test-task")
        finally:
            mod._gemini_sticker_image, BACKEND.generate = original_gemini, original_backend_generate

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


class SharedBrowserSession(unittest.TestCase):
    def test_generation_uses_relay_and_leaves_the_stable_session_to_cli(self) -> None:
        calls = []

        def fake_run(args, **kwargs):
            calls.append(list(args))
            output = Path(args[args.index("-o") + 1])
            output.write_bytes(b"image")
            return subprocess.CompletedProcess(args, 0, "", "")

        with mock.patch.object(BACKEND.subprocess, "run", side_effect=fake_run):
            with mock.patch.dict(os.environ, {"LIFE_MANAGER_RUN_ID": "run-a"}):
                first = BACKEND.generate("first prompt")
                second = BACKEND.generate("second prompt")
            with mock.patch.dict(os.environ, {"LIFE_MANAGER_RUN_ID": "run-b"}):
                third = BACKEND.generate("third prompt")
        try:
            for args in calls:
                self.assertNotIn("--session", args)
                self.assertIn("--profile", args)
                self.assertEqual(args[args.index("--profile") + 1], "relay")
        finally:
            first.unlink(missing_ok=True)
            second.unlink(missing_ok=True)
            third.unlink(missing_ok=True)

    def test_timeout_does_not_close_the_shared_imagegen_session(self) -> None:
        timeout_error = subprocess.TimeoutExpired(
            ["chatgpt-imagegen", "private prompt"], 310, stderr="private timeout output")
        calls = []

        def fake_run(args, **kwargs):
            calls.append((list(args), kwargs))
            if len(calls) == 1:
                raise timeout_error
            return subprocess.CompletedProcess(args, 1, "private close output", "private close error")

        with tempfile.TemporaryDirectory() as tmp:
            cli = Path(tmp) / "chatgpt-imagegen"
            cli.touch()
            with mock.patch.object(BACKEND, "CLI", cli):
                with mock.patch.object(BACKEND.subprocess, "run", side_effect=fake_run):
                    with mock.patch("shutil.which", return_value="/mock/chrome-use"):
                        with self.assertRaises(BACKEND.ChatGptImageGenUnavailable) as caught:
                            BACKEND.generate("private prompt")

        self.assertIs(caught.exception.__cause__, timeout_error)
        self.assertIn("timed out", str(caught.exception))
        self.assertNotIn("private", str(caught.exception))
        self.assertEqual(len(calls), 1)
        self.assertNotIn("close", calls[0][0])


if __name__ == "__main__":
    unittest.main()
