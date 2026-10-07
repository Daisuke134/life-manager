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
        tail = text[copy_at:copy_at + 600]
        # The copy comes from a read-only immutable release (2026-10-07: rm hit
        # "Permission denied" and failed the publish), so make it writable first.
        chmod_at = tail.index('chmod -R u+w "$WS/skills/$SKILL_NAME" 2>/dev/null')
        self.assertLess(chmod_at, tail.index('rm -rf "$WS/skills/$SKILL_NAME/test"'))


if __name__ == "__main__":
    unittest.main()
