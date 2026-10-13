import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import article_daily as MODULE  # noqa: E402

JST = dt.timezone(dt.timedelta(hours=9))


class Due(unittest.TestCase):
    """Dais 2026-10-11: distribute beyond Instagram/Threads. One article a day became five, in the
    hours Capafy does not publish to the same landing checkout (10:15/13:15)."""

    def test_each_publish_hour_is_its_own_slot(self) -> None:
        # Dais 2026-10-12: maximize distribution without Instagram; 15 slots, never Capafy's 10/13.
        self.assertEqual(len(MODULE.PUBLISH_HOURS), 15)
        for hour in MODULE.PUBLISH_HOURS:
            self.assertTrue(MODULE.due(dt.datetime(2026, 10, 11, hour, 6, tzinfo=JST), {}))
        for hour in (10, 13, 3):
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
        self.assertEqual(MODULE.pick(self.SETS, ledger, "seed", hour=15)["set_id"], "set-012")

    def test_once_every_set_is_covered_only_the_noon_slot_writes(self) -> None:
        # One article per set first; after that one a day, so the site is not flooded with repeats.
        ledger = {str(i): {"status": "published", "set_id": s["set_id"]} for i, s in enumerate(self.SETS)}
        self.assertIsNone(MODULE.pick(self.SETS, ledger, "seed", hour=15))
        self.assertIsNotNone(MODULE.pick(self.SETS, ledger, "seed", hour=12))

    def test_once_every_set_has_one_the_rotation_continues(self) -> None:
        ledger = {str(i): {"status": "published", "set_id": s["set_id"]} for i, s in enumerate(self.SETS)}
        self.assertIn(MODULE.pick(self.SETS, ledger, "seed", hour=12)["set_id"], {s["set_id"] for s in self.SETS})


class ArticleCandidates(unittest.TestCase):
    def test_on_sale_set_without_video_clips_can_receive_article(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sticker_root = root / "line-sticker"
            item_dir = sticker_root / "set-012"
            item_dir.mkdir(parents=True)
            store_url = "https://line.me/S/sticker/37168875"
            (item_dir / "creators-item.json").write_text(json.dumps({
                "state_observed": "販売中",
                "title_ja": "動く！おたーくんの丁寧な毎日",
                "purchase_url": store_url,
            }), encoding="utf-8")
            (item_dir / "listing.json").write_text(json.dumps({
                "title": {"ja": "動く！おたーくんの丁寧な毎日"},
                "character_name": "おたーくん",
            }), encoding="utf-8")
            state_root = root / "article-state"
            state_root.mkdir()
            published = {}

            class Publisher:
                def publish(self, **kwargs: object) -> dict[str, str]:
                    published.update(kwargs)
                    return {
                        "url": "https://aniccaai.com/blog/line-sticker-set-012-2026-10-14-07",
                        "title": "動く！おたーくんの丁寧な毎日",
                        "commit": "abc123",
                    }

            completed = type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            with (
                patch.object(MODULE, "compose", return_value={
                    "title": "動く！おたーくんの丁寧な毎日",
                    "body": "返事やお礼を伝えたい会話で使えるスタンプです。" * 20,
                }),
                patch.object(MODULE, "_publisher", return_value=Publisher()),
                patch.object(MODULE.subprocess, "run", return_value=completed),
                patch.dict(MODULE.os.environ, {
                    "ARTICLE_SELF_OWNED_LANDING_ROOT": str(root / "landing"),
                    "ARTICLE_SELF_OWNED_BASE_URL": "https://aniccaai.com",
                }),
            ):
                result = MODULE.run(
                    dt.datetime(2026, 10, 13, 22, 6, tzinfo=dt.timezone.utc),
                    sticker_root,
                    state_root,
                )

            self.assertEqual(result.get("status"), "published")
            self.assertEqual(result.get("set_id"), "set-012")
            self.assertEqual(published.get("cta_url"), store_url)
            article = Path(published["draft_path"]).read_text(encoding="utf-8")
            self.assertEqual(article.count(store_url), 1)


class BuildMarkdown(unittest.TestCase):
    def test_store_link_is_appended_exactly_once_under_an_h1(self) -> None:
        url = "https://store.line.me/stickershop/product/48067450/ja"
        text = MODULE.build_markdown("タイトル", "本文", url)
        self.assertTrue(text.startswith("# タイトル\n"))
        self.assertEqual(text.count(url), 1)


class ComposeFailure(unittest.TestCase):
    def test_provider_deferral_reason_is_preserved_without_raw_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            def run_agent(args: list[str], **_kwargs: object):
                evidence_dir = Path(args[args.index("--evidence-dir") + 1])
                evidence_dir.mkdir(parents=True)
                (evidence_dir / "summary.json").write_text(json.dumps({
                    "status": "provider_deferred",
                    "reason": "disk_headroom_low",
                    "attempt_count": 0,
                }))
                return type("Completed", (), {"returncode": 75})()

            with patch.object(MODULE.subprocess, "run", run_agent):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "line_sticker_article_compose_failed:75:disk_headroom_low",
                ):
                    MODULE.compose(
                        {"title_ja": "テスト", "character_name": "テスト"},
                        Path(tmp),
                        "line-sticker-article-test",
                    )


if __name__ == "__main__":
    unittest.main()
