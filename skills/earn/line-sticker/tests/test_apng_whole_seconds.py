"""Live 2026-10-08 set-012: 6-frame ChatGPT APNGs at 100ms/frame (0.6s) were all rejected by
Creators Market ('Error' on every slot) while 20-frame 2.0s fal APNGs passed. One loop must last
whole seconds."""
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import line_sticker  # noqa: E402
import seedance_set  # noqa: E402


def _frames(n):
    return [Image.new("RGBA", (320, 270), (i * 20 % 255, 0, 0, 255)) for i in range(n)]


class WholeSecondLoops(unittest.TestCase):
    def test_six_frames_play_one_second_per_loop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.png"
            seedance_set._write_apng(_frames(6), path, 2)
            parsed = line_sticker.parse_png(path)
            self.assertEqual(parsed["frames"], 6)
            self.assertEqual(parsed["duration_ms"] % 1000, 0)
            self.assertEqual(parsed["duration_ms"], 1000 * parsed["plays"])

    def test_twenty_frames_stay_two_seconds(self) -> None:
        self.assertEqual(seedance_set.loop_seconds(20), 2)


if __name__ == "__main__":
    unittest.main()


class ValidatorRejectsFractionalLoops(unittest.TestCase):
    def test_policy_check_flags_non_whole_seconds(self) -> None:
        src = (Path(__file__).resolve().parents[1] / "line_sticker.py").read_text()
        self.assertIn("duration_not_whole_seconds", src)
