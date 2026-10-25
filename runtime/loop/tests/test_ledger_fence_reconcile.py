import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ledger_fence_reconcile as MODULE  # noqa: E402

Q = dt.datetime(2026, 9, 17, 19, 0, tzinfo=dt.timezone.utc)
LATE = Q + dt.timedelta(seconds=MODULE.NO_EFFECT_MIN_AGE_SECONDS + 1)


def _published(ts: dt.datetime, **extra) -> dict:
    return {"ts": ts.isoformat().replace("+00:00", "Z"), "platform": "tiktok", "status": "published",
            "public_readback_verified": True, "provider_id": "cmu5yzfsb04aps00y9i7s7rrw",
            "public_url": "https://www.tiktok.com/@anicca.comedy/video/7686600583180045585", **extra}


class LifeManagerDaily(unittest.TestCase):
    def proof(self, rows, now=LATE):
        return MODULE.build_proof("life-manager-daily", "life-manager-daily:tiktok-retry-20260918-3", Q,
                                  now=now, rows=rows)

    def test_a_published_row_after_the_run_queued_closes_as_effected(self) -> None:
        # 2026-09-17: queued 19:00Z, distribution.jsonl holds a verified TikTok publish at 20:29Z.
        p = self.proof([_published(Q - dt.timedelta(days=1)), _published(Q + dt.timedelta(minutes=89))])
        self.assertTrue(p["verified"])
        self.assertTrue(p["effected"])
        self.assertIn("cmu5yzfsb04aps00y9i7s7rrw", p["provider_receipt_id"])

    def test_only_older_or_failed_rows_and_an_old_fence_close_as_no_effect(self) -> None:
        p = self.proof([_published(Q - dt.timedelta(hours=2)),
                        {"ts": (Q + dt.timedelta(minutes=3)).isoformat(), "status": "failed"}])
        self.assertTrue(p["verified"])
        self.assertFalse(p["effected"])
        self.assertEqual(p["rows_since_queued"], 1)

    def test_a_recent_fence_without_a_receipt_stays_held(self) -> None:
        p = self.proof([], now=Q + dt.timedelta(hours=1))
        self.assertFalse(p["verified"])
        self.assertTrue(p["reason"].startswith("too_recent"))

    def test_an_unreadable_ledger_never_proves_anything(self) -> None:
        p = self.proof([{"_unreadable": "/x/distribution.jsonl"}])
        self.assertFalse(p["verified"])


class MarketingMineDaily(unittest.TestCase):
    def test_gap_evidence_with_a_telegram_receipt_is_the_effect(self) -> None:
        rows = [{"observed_at": (Q + dt.timedelta(minutes=5)).isoformat(), "telegram": {"message_id": 42}}]
        p = MODULE.build_proof("marketing-mine-daily", "marketing-mine-daily:x", Q, now=LATE, rows=rows)
        self.assertTrue(p["verified"] and p["effected"])
        self.assertIn("telegram:", p["provider_receipt_id"])

    def test_gap_evidence_without_telegram_is_local_only(self) -> None:
        rows = [{"observed_at": (Q + dt.timedelta(minutes=5)).isoformat(), "telegram": None}]
        p = MODULE.build_proof("marketing-mine-daily", "marketing-mine-daily:x", Q, now=LATE, rows=rows)
        self.assertTrue(p["verified"])
        self.assertFalse(p["effected"])


class LoadRows(unittest.TestCase):
    def test_jsonl_and_json_glob_are_both_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.jsonl").write_text(json.dumps({"ts": "x"}) + "\n\n" + json.dumps({"ts": "y"}) + "\n")
            (root / "e").mkdir()
            (root / "e" / "1.json").write_text(json.dumps({"observed_at": "z"}))
            (root / "e" / "bad.json").write_text("{not json")
            rows = MODULE.load_rows([root / "a.jsonl", root / "e" / "*.json"])
            self.assertEqual([r.get("ts") for r in rows[:2]], ["x", "y"])
            self.assertEqual(rows[2], {"observed_at": "z"})
            self.assertIn("_unreadable", rows[3])


if __name__ == "__main__":
    unittest.main()
