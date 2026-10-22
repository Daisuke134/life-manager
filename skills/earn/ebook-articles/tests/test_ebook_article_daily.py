import datetime as dt
import json
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ebook_article_daily as MODULE  # noqa: E402
import ebook_article_fence_reconcile as RECONCILE  # noqa: E402

JST = dt.timezone(dt.timedelta(hours=9))


class Slots(unittest.TestCase):
    """2026-10-16: the eBook Instagram lanes cannot post without a human (English Monk Instagram
    is not connected, Postiz rejects a new channel with 402), so free aniccaai.com articles are the
    account-free lane. They run in hours no other landing writer uses."""

    def test_each_hour_maps_to_one_product(self) -> None:
        self.assertEqual(MODULE.product_for_hour(1), "ebook-en")
        self.assertEqual(MODULE.product_for_hour(2), "ebook-ja")
        self.assertIsNone(MODULE.product_for_hour(12))

    def test_hours_avoid_the_sticker_and_writer_landing_slots(self) -> None:
        sticker = {7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}
        writer = set(range(6, 24))
        self.assertFalse(set(MODULE.SLOT_PRODUCTS) & (sticker | writer))

    def test_registry_wakes_exactly_at_the_slot_hours(self) -> None:
        registry = json.loads((MODULE.REPO_ROOT / "config/loop-registry.json").read_text())
        owner = registry["loops"]["ebook-articles"]
        self.assertEqual(sorted(s["Hour"] for s in owner["cadence"]["calendar_interval"]), sorted(MODULE.SLOT_PRODUCTS))
        self.assertEqual(owner["entrypoint"], "skills/earn/ebook-articles/ebook-articles.sh")

    def test_published_or_exhausted_slots_are_not_due(self) -> None:
        now = dt.datetime(2026, 10, 17, 1, 5, tzinfo=JST)
        self.assertTrue(MODULE.due(now, {}))
        self.assertFalse(MODULE.due(now, {"2026-10-17@01": {"status": "published", "attempts": 1}}))
        self.assertFalse(MODULE.due(now, {"2026-10-17@01": {"status": "failed", "attempts": 2}}))
        self.assertFalse(MODULE.due(dt.datetime(2026, 10, 17, 12, 5, tzinfo=JST), {}))


class Product(unittest.TestCase):
    def test_products_come_from_the_marketing_registry(self) -> None:
        en = MODULE.load_product("ebook-en")
        ja = MODULE.load_product("ebook-ja")
        self.assertEqual(en["destination_url"], "https://aniccaai.com/monk")
        self.assertEqual(ja["destination_url"], "https://aniccaai.com/achan")
        self.assertEqual(en["language"], "en")
        self.assertEqual(ja["language"], "ja")

    def test_the_checkout_link_is_appended_once_by_code(self) -> None:
        md = MODULE.build_markdown("T", "body", "https://aniccaai.com/monk", "Read The Anicca Reset")
        self.assertTrue(md.startswith("# T\n"))
        self.assertEqual(md.count("https://aniccaai.com/monk"), 1)

    def test_slug_is_product_and_slot(self) -> None:
        self.assertEqual(MODULE.slug_for("ebook-en", "2026-10-17@01"), "ebook-en-2026-10-17-01")

    def test_prompt_avoids_recent_titles_and_carries_only_approved_claims(self) -> None:
        product = MODULE.load_product("ebook-en")
        prompt = MODULE.prompt_for(product, ["Old title"])
        self.assertIn("Old title", prompt)
        for claim in product["approved_claims"]:
            self.assertIn(claim, prompt)


class Run(unittest.TestCase):
    def test_a_failed_publish_is_recorded_and_never_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            now = dt.datetime(2026, 10, 17, 2, 5, tzinfo=JST)
            with patch.object(MODULE, "compose", side_effect=RuntimeError("boom")):
                entry = MODULE.run(now, state)
            ledger = json.loads((state / "article-ledger.json").read_text())
        self.assertEqual(entry["status"], "failed")
        self.assertEqual(ledger["2026-10-17@02"]["product_id"], "ebook-ja")
        self.assertEqual(ledger["2026-10-17@02"]["attempts"], 1)

    def test_not_due_hour_does_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            entry = MODULE.run(dt.datetime(2026, 10, 17, 12, 5, tzinfo=JST), Path(temporary))
            self.assertEqual(entry, {"state": "not_due"})
            self.assertFalse((Path(temporary) / "article-ledger.json").exists())


class ComposeDiagnostics(unittest.TestCase):
    def test_failed_compose_retains_evidence_and_launcher_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            observed = {}
            def failed(args, **kwargs):
                evidence = Path(args[args.index("--evidence-dir") + 1])
                evidence.mkdir(parents=True, exist_ok=True)
                (evidence / "summary.json").write_text('{"state":"failed"}')
                observed["path"] = evidence
                if hasattr(kwargs.get("stderr"), "write"):
                    kwargs["stderr"].write("agent-runner: provider unavailable\n")
                return subprocess.CompletedProcess(args, 1)
            with patch.object(MODULE.subprocess, "run", side_effect=failed):
                with self.assertRaisesRegex(RuntimeError, "compose_failed:1"):
                    MODULE.compose(MODULE.load_product("ebook-en"), [], state, "ebook-article-test")
            evidence = observed["path"]
            self.assertTrue((evidence / "summary.json").is_file())
            self.assertIn("provider unavailable", (evidence / "launcher.stderr.log").read_text())

    def test_cli_reports_failed_slot_with_nonzero_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(MODULE, "run", return_value={"status": "failed", "error": "compose_failed:1"}):
                self.assertEqual(MODULE.main(["--state-root", temporary]), 1)


class FenceProof(unittest.TestCase):
    QUEUED = dt.datetime(2026, 10, 16, 16, 5, tzinfo=dt.timezone.utc)  # 2026-10-17 01:05 JST

    def _article(self, slug: str, at: str, markdown: str) -> dict:
        return {"slug": slug, "sha": "a" * 40, "at": at, "date": slug[9:19], "title": "T", "markdown": markdown}

    def test_no_article_in_window_and_old_enough_closes_as_no_effect(self) -> None:
        proof = RECONCILE.build_proof("o", self.QUEUED, now=self.QUEUED + dt.timedelta(hours=2),
                                      landing={"ok": True, "head": "h" * 40, "articles": []}, ledger_rows={})
        self.assertTrue(proof["verified"])
        self.assertFalse(proof["effected"])

    def test_too_recent_or_failed_readback_stays_fenced(self) -> None:
        recent = RECONCILE.build_proof("o", self.QUEUED, now=self.QUEUED + dt.timedelta(minutes=5),
                                       landing={"ok": True, "head": "h", "articles": []}, ledger_rows={})
        failed = RECONCILE.build_proof("o", self.QUEUED, now=self.QUEUED + dt.timedelta(hours=2),
                                       landing={"ok": False, "reason": "github_readback_failed:X"}, ledger_rows={})
        self.assertFalse(recent["verified"])
        self.assertFalse(failed["verified"])

    def test_the_slot_article_with_its_checkout_link_is_recorded_as_the_effect(self) -> None:
        article = self._article("ebook-en-2026-10-17-01", "2026-10-16T16:20:00+00:00",
                                "# T\n\nbody\n\n[Read](https://aniccaai.com/monk)\n")
        rows = {"2026-10-17@01": {"attempts": 1, "product_id": "ebook-en"}}
        proof = RECONCILE.build_proof("o", self.QUEUED, now=self.QUEUED + dt.timedelta(hours=2),
                                      landing={"ok": True, "head": "h" * 40, "articles": [article]}, ledger_rows=rows)
        self.assertTrue(proof["verified"])
        self.assertTrue(proof["effected"])
        self.assertEqual(proof["ledger_patch"]["entry"]["url"], "https://aniccaai.com/blog/ebook-en-2026-10-17-01")

    def test_an_unexplained_article_keeps_the_fence(self) -> None:
        article = self._article("ebook-ja-2026-10-17-02", "2026-10-16T16:30:00+00:00", "x")
        proof = RECONCILE.build_proof("o", self.QUEUED, now=self.QUEUED + dt.timedelta(hours=2),
                                      landing={"ok": True, "head": "h", "articles": [article]}, ledger_rows={})
        self.assertFalse(proof["verified"])
        self.assertIn("unledgered_article", proof["reason"])


if __name__ == "__main__":
    unittest.main()
