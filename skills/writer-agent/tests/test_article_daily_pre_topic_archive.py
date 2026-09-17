from __future__ import annotations

import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "article-daily.sh"


class ArticleDailyPreTopicArchiveTest(unittest.TestCase):
    def test_selfimprove_verify_defect_is_empty_pre_topic_archive(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        marker = '"gates/selfimprove-verify-defect.json"'
        self.assertIn(marker, source)
        self.assertIn(
            "and item.get(\"path\") in {",
            source,
        )
