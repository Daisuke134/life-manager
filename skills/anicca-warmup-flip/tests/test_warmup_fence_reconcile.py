import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import warmup_fence_reconcile as MODULE  # noqa: E402

Q = dt.datetime(2026, 9, 17, 23, 38, tzinfo=dt.timezone.utc)
LATE = Q + dt.timedelta(seconds=MODULE.MIN_AGE_SECONDS + 1)


def _root(tmp: str) -> Path:
    root = Path(tmp)
    (root / "state").mkdir()
    (root / "state" / "postiz-integrations.json").write_text(json.dumps({"integrations": []}))
    return root


class BuildProof(unittest.TestCase):
    def proof(self, root: Path, now: dt.datetime = LATE) -> dict:
        return MODULE.build_proof("warmup-flip-daily:x", Q, now=now, state_root=root)

    def test_consistent_state_with_nothing_pending_closes_with_the_state_hash_as_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self.proof(_root(tmp))
            self.assertTrue(p["verified"])
            self.assertTrue(p["provider_receipt_id"].startswith("warmup-flip-state:"))

    def test_an_unrecovered_transaction_journal_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _root(tmp)
            (root / "warmup-flip-transaction.json").write_text("{}")
            self.assertFalse(self.proof(root)["verified"])

    def test_an_undelivered_graduation_message_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _root(tmp)
            (root / "pending-telegram.txt").write_text("x\n")
            self.assertFalse(self.proof(root)["verified"])

    def test_an_unreadable_state_file_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _root(tmp)
            (root / "state" / "postiz-integrations.json").write_text("{not json")
            self.assertFalse(self.proof(root)["verified"])

    def test_too_recent_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(self.proof(_root(tmp), now=Q + dt.timedelta(seconds=30))["verified"])


if __name__ == "__main__":
    unittest.main()
