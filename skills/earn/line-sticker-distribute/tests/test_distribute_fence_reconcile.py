import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import distribute_fence_reconcile as MODULE  # noqa: E402

Q = dt.datetime(2026, 10, 8, 8, 15, tzinfo=dt.timezone.utc)
LATE = Q + dt.timedelta(seconds=MODULE.NO_EFFECT_MIN_AGE_SECONDS + 1)
LEDGER = {"a": "https://www.instagram.com/stardust_doubutsu/reel/AAA/",
          "b": "https://www.instagram.com/stardust_doubutsu/reel/BBB/"}


class BuildProof(unittest.TestCase):
    def proof(self, reels, now=LATE):
        return MODULE.build_proof("line-sticker-distribute:x", Q, now=now, reels=reels, ledger_codes={"AAA", "BBB"})

    def test_complete_listing_with_only_ledgered_reels_proves_no_effect(self) -> None:
        p = self.proof({"ok": True, "codes": {"AAA", "BBB"}, "post_count": 2})
        self.assertTrue(p["verified"])
        self.assertFalse(p["effected"])

    def test_an_unledgered_reel_never_closes_the_fence(self) -> None:
        # It may be this run's post; closing as no-effect would let the slot post twice.
        p = self.proof({"ok": True, "codes": {"AAA", "BBB", "CCC"}, "post_count": 3})
        self.assertFalse(p["verified"])
        self.assertEqual(p["reason"], "unledgered_reel:CCC")

    def test_an_unledgered_reel_older_than_the_run_is_not_its_effect(self) -> None:
        p = self.proof({"ok": True, "codes": {"AAA", "BBB", "OLD"}, "post_count": 3,
                        "taken_at": {"OLD": "2026-10-07T04:20:00.000Z"}})
        self.assertTrue(p["verified"])

    def test_an_undated_unledgered_reel_stays_fenced(self) -> None:
        p = self.proof({"ok": True, "codes": {"AAA", "BBB", "OLD"}, "post_count": 3, "taken_at": {"OLD": None}})
        self.assertFalse(p["verified"])

    def test_incomplete_listing_stays_fenced(self) -> None:
        p = self.proof({"ok": True, "codes": {"AAA"}, "post_count": 2})
        self.assertFalse(p["verified"])

    def test_readback_failure_stays_fenced(self) -> None:
        self.assertFalse(self.proof({"ok": False, "reason": "browser_busy"})["verified"])

    def test_too_recent_stays_fenced(self) -> None:
        p = self.proof({"ok": True, "codes": {"AAA", "BBB"}, "post_count": 2}, now=Q + dt.timedelta(minutes=5))
        self.assertFalse(p["verified"])

    def test_ledger_codes_come_from_post_urls(self) -> None:
        rows = {"s1": {"post_url": LEDGER["a"]}, "s2": {"post_url": LEDGER["b"]}, "s3": {"status": "failed"}}
        self.assertEqual(MODULE.ledger_codes(rows), {"AAA", "BBB"})



class ThreadsLane(unittest.TestCase):
    """A Threads post is the same loop's effect: a fence closes only when Threads is all ledgered too."""

    REELS = {"ok": True, "codes": {"AAA", "BBB"}, "post_count": 2}

    def proof(self, threads, ledger=frozenset({"AAA", "BBB", "TTT"})):
        return MODULE.build_proof("line-sticker-distribute:x", Q, now=LATE, reels=self.REELS,
                                  ledger_codes=set(ledger), threads=threads)

    def test_ledger_codes_include_threads_post_urls(self) -> None:
        rows = {"s1": {"post_url": "https://www.threads.com/@stardust_doubutsu/post/TTT"}}
        self.assertEqual(MODULE.ledger_codes(rows), {"TTT"})

    def test_an_unledgered_threads_post_never_closes_the_fence(self) -> None:
        p = self.proof({"ok": True, "codes": {"TTT", "NEW"}})
        self.assertFalse(p["verified"])
        self.assertEqual(p["reason"], "unledgered_threads_post:NEW")

    def test_unreadable_threads_profile_stays_fenced(self) -> None:
        p = self.proof({"ok": False, "reason": "browser_unavailable"})
        self.assertFalse(p["verified"])
        self.assertEqual(p["reason"], "threads:browser_unavailable")

    def test_all_ledgered_threads_posts_allow_the_close(self) -> None:
        self.assertTrue(self.proof({"ok": True, "codes": {"TTT"}})["verified"])


if __name__ == "__main__":
    unittest.main()
