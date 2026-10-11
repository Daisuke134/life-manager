import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import article_daily as MODULE  # noqa: E402

JST = dt.timezone(dt.timedelta(hours=9))


class Due(unittest.TestCase):
    """Dais 2026-10-11: distribute beyond Instagram/Threads. One article a day became five, in the
    hours Capafy does not publish to the same landing checkout (10:15/13:15)."""

    def test_each_publish_hour_is_its_own_slot(self) -> None:
        for hour in MODULE.PUBLISH_HOURS:
            self.assertTrue(MODULE.due(dt.datetime(2026, 10, 11, hour, 6, tzinfo=JST), {}))
        for hour in (10, 11, 13, 14):
            self.assertFalse(MODULE.due(dt.datetime(2026, 10, 11, hour, 6, tzinfo=JST), {}))

    def test_published_or_exhausted_slots_are_not_due(self) -> None:
        now = dt.datetime(2026, 10, 11, 15, 30, tzinfo=JST)
        self.assertFalse(MODULE.due(now, {"2026-10-11@15": {"status": "published", "attempts": 1}}))
        self.assertFalse(MODULE.due(now, {"2026-10-11@15": {"status": "failed", "attempts": 2}}))
        self.assertTrue(MODULE.due(now, {"2026-10-11@12": {"status": "published", "attempts": 1}}))


class Pick(unittest.TestCase):
    SETS = [{"set_id": f"set-{n:03d}"} for n in (3, 5, 9, 12)]

    def test_a_set_without_an_article_is_written_first(self) -> None:
        ledger = {"2026-10-08": {"status": "published", "set_id": "set-005"},
                  "2026-10-09": {"status": "published", "set_id": "set-009"},
                  "2026-10-10@12": {"status": "published", "set_id": "set-003"}}
        self.assertEqual(MODULE.pick(self.SETS, ledger, "seed")["set_id"], "set-012")

    def test_once_every_set_has_one_the_rotation_continues(self) -> None:
        ledger = {str(i): {"status": "published", "set_id": s["set_id"]} for i, s in enumerate(self.SETS)}
        self.assertIn(MODULE.pick(self.SETS, ledger, "seed")["set_id"], {s["set_id"] for s in self.SETS})


class BuildMarkdown(unittest.TestCase):
    def test_store_link_is_appended_exactly_once_under_an_h1(self) -> None:
        url = "https://store.line.me/stickershop/product/48067450/ja"
        text = MODULE.build_markdown("タイトル", "本文", url)
        self.assertTrue(text.startswith("# タイトル\n"))
        self.assertEqual(text.count(url), 1)


if __name__ == "__main__":
    unittest.main()
