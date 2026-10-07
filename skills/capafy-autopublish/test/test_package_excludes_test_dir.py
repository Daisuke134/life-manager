"""Catalog test/ fixtures must never ship in the uploaded package.

2026-10-07: the only two listings whose catalog dirs held test/ (hook-lab,
marketing-strategist) showed "セキュリティスキャン 注意" to buyers while every
other listing showed "通常"; Hook Lab's ~1 sale/day stopped the day that
version went live.
"""
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "publish_prepare.sh"


class PackageExcludesTestDir(unittest.TestCase):
    def test_test_dir_removed_after_clean_ws_copy(self):
        text = SCRIPT.read_text()
        copy_at = text.index('cp -R "$SKILL_DIR" "$WS/skills/$SKILL_NAME"')
        self.assertIn('rm -rf "$WS/skills/$SKILL_NAME/test"', text[copy_at:copy_at + 600])


if __name__ == "__main__":
    unittest.main()
