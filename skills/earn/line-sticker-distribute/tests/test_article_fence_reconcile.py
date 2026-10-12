import datetime as dt
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import article_fence_reconcile as MODULE  # noqa: E402

Q = dt.datetime(2026, 10, 11, 0, 6, tzinfo=dt.timezone.utc)
LATE = Q + dt.timedelta(seconds=MODULE.NO_EFFECT_MIN_AGE_SECONDS + 1)
SLUG = "line-sticker-set-005-2026-10-11-09"


def landing(*slugs):
    return {"ok": True, "head": "abc123",
            "articles": [{"slug": s, "sha": f"sha-{s}", "at": Q.isoformat()} for s in slugs]}


class BuildProof(unittest.TestCase):
    def proof(self, readback, ledgered=frozenset({SLUG}), now=LATE):
        return MODULE.build_proof("line-sticker-articles:x", Q, now=now, landing=readback,
                                  ledger_slugs=set(ledgered))

    def test_every_window_article_ledgered_proves_no_unaccounted_effect_after_age(self) -> None:
        p = self.proof(landing(SLUG))
        self.assertTrue(p["verified"])
        self.assertFalse(p["effected"])
        self.assertIn("github:abc123", p["provider_receipt_id"])

    def test_an_empty_window_after_age_proves_no_effect(self) -> None:
        self.assertTrue(self.proof(landing())["verified"])

    def test_all_ledgered_but_too_recent_stays_fenced(self) -> None:
        p = self.proof(landing(SLUG), now=Q + dt.timedelta(minutes=5))
        self.assertFalse(p["verified"])
        self.assertTrue(p["reason"].startswith("too_recent:"))

    def test_an_unledgered_article_on_the_landing_never_closes_the_fence(self) -> None:
        # It may be this run's publish whose ledger write never happened.
        other = "line-sticker-set-009-2026-10-11-09"
        p = self.proof(landing(SLUG, other))
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


class RunsInIsolatedMode(unittest.TestCase):
    def test_the_script_starts_under_python_dash_I(self) -> None:
        script = Path(__file__).resolve().parents[1] / "scripts" / "article_fence_reconcile.py"
        done = subprocess.run([sys.executable, "-I", str(script), "--help"], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr[-400:])


if __name__ == "__main__":
    unittest.main()
