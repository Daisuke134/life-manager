import json
import tempfile
import unittest
from pathlib import Path

import sys

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import publish  # noqa: E402


class _Page:
    url = "https://promptbase.com/sell"

    def inner_text(self, selector):
        assert selector == "body"
        return "1/3\nNext: Prompt File"

    def screenshot(self, path, *, full_page):
        assert full_page is True
        Path(path).write_bytes(b"png")


class PublishDiagnosticsTest(unittest.TestCase):
    def test_step1_failure_records_page_boundary_and_screenshot(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory)
            publish._record_step1_failure(_Page(), evidence)

            payload = json.loads(
                (evidence / "step1_failure.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["url"], "https://promptbase.com/sell")
            self.assertEqual(payload["step"], "1/3")
            self.assertIn("Next: Prompt File", payload["body_text"])
            self.assertEqual((evidence / "step1_failure.png").read_bytes(), b"png")


if __name__ == "__main__":
    unittest.main()
