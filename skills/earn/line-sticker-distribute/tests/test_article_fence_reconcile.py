import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import article_fence_reconcile as MODULE  # noqa: E402

Q = dt.datetime(2026, 10, 11, 0, 6, tzinfo=dt.timezone.utc)
LATE = Q + dt.timedelta(seconds=MODULE.NO_EFFECT_MIN_AGE_SECONDS + 1)
SLUG = "line-sticker-set-005-2026-10-11-09"
UNRELATED_SLUG = "line-sticker-set-005-2026-10-11-08"


def landing(*slugs):
    return {"ok": True, "head": "abc123",
            "articles": [{"slug": s, "sha": f"sha-{s}", "at": Q.isoformat()} for s in slugs]}


class BuildProof(unittest.TestCase):
    def proof(self, readback, ledgered=frozenset({UNRELATED_SLUG}), now=LATE):
        return MODULE.build_proof("line-sticker-articles:x", Q, now=now, landing=readback,
                                  ledger_slugs=set(ledgered))

    def test_every_window_article_ledgered_proves_no_unaccounted_effect_after_age(self) -> None:
        p = self.proof(landing(UNRELATED_SLUG))
        self.assertTrue(p["verified"])
        self.assertFalse(p["effected"])
        self.assertIn("github:abc123", p["provider_receipt_id"])

    def test_an_empty_window_after_age_proves_no_effect(self) -> None:
        self.assertTrue(self.proof(landing())["verified"])

    def test_all_ledgered_but_too_recent_stays_fenced(self) -> None:
        p = self.proof(landing(UNRELATED_SLUG), now=Q + dt.timedelta(minutes=5))
        self.assertFalse(p["verified"])
        self.assertTrue(p["reason"].startswith("too_recent:"))

    def test_an_unledgered_article_on_the_landing_never_closes_the_fence(self) -> None:
        # It may be this run's publish whose ledger write never happened.
        other = "line-sticker-set-009-2026-10-11-08"
        p = self.proof(landing(UNRELATED_SLUG, other))
        self.assertFalse(p["verified"])
        self.assertEqual(p["reason"], f"unledgered_article:{other}")

    def test_readback_failure_stays_fenced(self) -> None:
        p = self.proof({"ok": False, "reason": "github_readback_failed:CalledProcessError"})
        self.assertFalse(p["verified"])
        self.assertEqual(p["reason"], "github_readback_failed:CalledProcessError")


class Readback(unittest.TestCase):
    def test_ledger_slugs_come_from_published_urls_only(self) -> None:
        rows = {"2026-10-11@09": {"status": "published", "url": f"https://aniccaai.com/blog/{SLUG}"},
                "2026-10-11@12": {"status": "failed", "set_id": "set-009"},
                "2026-10-08": {"status": "published", "url": "https://aniccaai.com/blog/line-sticker-set-005-2026-10-08"}}
        self.assertEqual(MODULE.ledger_slugs(rows), {SLUG, "line-sticker-set-005-2026-10-08"})

    def test_git_log_name_only_output_becomes_slug_rows(self) -> None:
        out = ("@aaa|2026-10-11T09:20:00+09:00\n\n"
               f"apps/landing/data/research/{SLUG}.json\n"
               "@bbb|2026-10-11T12:21:00+09:00\n\n"
               "apps/landing/data/research/line-sticker-set-009-2026-10-11-12.json\n")
        self.assertEqual(MODULE.parse_added(out), [
            {"slug": SLUG, "sha": "aaa", "at": "2026-10-11T09:20:00+09:00"},
            {"slug": "line-sticker-set-009-2026-10-11-12", "sha": "bbb", "at": "2026-10-11T12:21:00+09:00"},
        ])


class PositiveEffectRecovery(unittest.TestCase):
    SLOT = "2026-10-11@09"
    STORE_URL = "https://line.me/S/sticker/37293554"
    COMMIT = "e" * 40

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.article_state = self.root / "articles"
        self.article_state.mkdir()
        self.line_state = self.root / "line-sticker"
        item_dir = self.line_state / "set-005"
        item_dir.mkdir(parents=True)
        (item_dir / "creators-item.json").write_text(json.dumps({
            "state_observed": "販売中", "purchase_url": self.STORE_URL,
            "title_ja": "既存セット",
        }))
        (item_dir / "listing.json").write_text(json.dumps({"title": {"ja": "既存セット"}}))
        self.ledger_path = self.article_state / "article-ledger.json"
        self.ledger_path.write_text(json.dumps({self.SLOT: {"attempts": 1, "set_id": "set-005"}}))
        self.article = {
            "slug": SLUG, "sha": self.COMMIT, "at": "2026-10-11T09:50:51+09:00",
            "date": "2026-10-11", "title": "既存セットの記事",
            "markdown": f"[LINE STOREでスタンプを見る]({self.STORE_URL})",
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def reconcile(self, *, resolve: bool = False, store_url: str | None = None,
                  markdown: str | None = None) -> dict:
        article = dict(self.article)
        if markdown is not None:
            article["markdown"] = markdown
        elif store_url is not None:
            article["markdown"] = f"[LINE STOREでスタンプを見る]({store_url})"
        with patch.object(MODULE, "STATE_ROOT", self.article_state), \
                patch.object(MODULE, "fenced_row", return_value=("claimed", Q)), \
                patch.object(MODULE, "read_landing_articles", return_value={
                    "ok": True, "head": "a" * 40, "articles": [article],
                }), \
                patch.dict(os.environ, {"LINE_STICKER_STATE_ROOT": str(self.line_state)}):
            return MODULE.reconcile("line-sticker-articles:x", resolve=resolve)

    def test_exact_published_slot_is_positive_effect_and_not_no_effect(self) -> None:
        result = self.reconcile()

        self.assertTrue(result["verified"], result)
        self.assertTrue(result["effected"])
        self.assertEqual(result["provider_receipt_id"], f"github:{self.COMMIT}|line-sticker-article:{SLUG}")
        self.assertEqual(result["ledger_patch"]["entry"]["commit"], self.COMMIT)
        self.assertNotIn("status", json.loads(self.ledger_path.read_text())[self.SLOT])

    def test_positive_effect_resolution_records_publication_before_closing_fence(self) -> None:
        with patch("runtime.host.resource_admission.resolve_unknown_occurrence", return_value=True) as close:
            result = self.reconcile(resolve=True)

        self.assertTrue(result.get("closed"), result)
        row = json.loads(self.ledger_path.read_text())[self.SLOT]
        self.assertEqual(row["status"], "published")
        self.assertEqual(row["url"], f"https://aniccaai.com/blog/{SLUG}")
        self.assertEqual(row["title"], "既存セットの記事")
        self.assertEqual(row["commit"], self.COMMIT)
        self.assertTrue(close.called)

    def test_wrong_store_cta_cannot_recover_or_close_the_occurrence(self) -> None:
        result = self.reconcile(resolve=True, store_url="https://line.me/S/sticker/00000000")

        self.assertFalse(result["verified"])
        self.assertNotIn("closed", result)
        self.assertNotIn("status", json.loads(self.ledger_path.read_text())[self.SLOT])

    def test_bare_wrong_store_url_is_not_hidden_by_the_canonical_cta(self) -> None:
        markdown = ("本文の誤URL https://line.me/S/sticker/00000000\n\n"
                    f"[LINE STOREでスタンプを見る]({self.STORE_URL})")
        result = self.reconcile(resolve=True, markdown=markdown)

        self.assertFalse(result["verified"])
        self.assertNotIn("closed", result)
        self.assertNotIn("status", json.loads(self.ledger_path.read_text())[self.SLOT])

    def test_later_slot_article_cannot_be_attributed_to_this_occurrence(self) -> None:
        later_slot = "2026-10-11@10"
        self.ledger_path.write_text(json.dumps({later_slot: {"attempts": 1, "set_id": "set-005"}}))
        later = {**self.article, "slug": "line-sticker-set-005-2026-10-11-10",
                 "at": "2026-10-11T10:01:00+09:00"}
        with patch.object(MODULE, "STATE_ROOT", self.article_state), \
                patch.object(MODULE, "fenced_row", return_value=("claimed", Q)), \
                patch.object(MODULE, "read_landing_articles", return_value={
                    "ok": True, "head": "a" * 40, "articles": [later],
                }), patch.dict(os.environ, {"LINE_STICKER_STATE_ROOT": str(self.line_state)}):
            result = MODULE.reconcile("line-sticker-articles:x")

        self.assertFalse(result["verified"], result)

    def test_unverified_article_in_exact_slot_cannot_be_closed_as_no_effect(self) -> None:
        row = {"attempts": 1, "set_id": "set-005", "status": "published",
               "url": f"https://aniccaai.com/blog/{SLUG}", "title": "既存セットの記事",
               "commit": self.COMMIT}
        self.ledger_path.write_text(json.dumps({self.SLOT: row}))

        result = self.reconcile(store_url="https://line.me/S/sticker/00000000")

        self.assertFalse(result["verified"], result)
        self.assertNotEqual(result.get("effected"), False)


class RunsInIsolatedMode(unittest.TestCase):
    def test_the_script_starts_under_python_dash_I(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "article_fence_reconcile.py"
        done = subprocess.run([sys.executable, "-I", str(script), "--help"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr[-400:])


if __name__ == "__main__":
    unittest.main()
