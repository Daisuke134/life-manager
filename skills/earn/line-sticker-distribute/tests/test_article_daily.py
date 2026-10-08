import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import article_daily as MODULE  # noqa: E402

JST = dt.timezone(dt.timedelta(hours=9))


class Due(unittest.TestCase):
    def test_only_the_jst_noon_hour_is_due(self) -> None:
        self.assertTrue(MODULE.due(dt.datetime(2026, 10, 9, 12, 5, tzinfo=JST), {}))
        self.assertFalse(MODULE.due(dt.datetime(2026, 10, 9, 11, 59, tzinfo=JST), {}))
        self.assertFalse(MODULE.due(dt.datetime(2026, 10, 9, 13, 0, tzinfo=JST), {}))

    def test_published_or_exhausted_days_are_not_due(self) -> None:
        now = dt.datetime(2026, 10, 9, 12, 30, tzinfo=JST)
        self.assertFalse(MODULE.due(now, {"2026-10-09": {"status": "published", "attempts": 1}}))
        self.assertFalse(MODULE.due(now, {"2026-10-09": {"status": "failed", "attempts": 2}}))
        self.assertTrue(MODULE.due(now, {"2026-10-09": {"status": "failed", "attempts": 1}}))


class BuildMarkdown(unittest.TestCase):
    def test_store_link_is_appended_exactly_once_under_an_h1(self) -> None:
        url = "https://store.line.me/stickershop/product/48067450/ja"
        text = MODULE.build_markdown("タイトル", "本文", url)
        self.assertTrue(text.startswith("# タイトル\n"))
        self.assertEqual(text.count(url), 1)


if __name__ == "__main__":
    unittest.main()
