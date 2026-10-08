import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import readback_fence_reconcile as MODULE  # noqa: E402

Q = dt.datetime(2026, 10, 8, 18, 45, tzinfo=dt.timezone.utc)
LATE = Q + dt.timedelta(seconds=MODULE.NO_EFFECT_MIN_AGE_SECONDS + 1)


def _item(root: Path, name: str, **fields) -> None:
    d = root / name
    d.mkdir()
    (d / "creators-item.json").write_text(json.dumps(fields))


class BuildProof(unittest.TestCase):
    def proof(self, root: Path, now: dt.datetime = LATE) -> dict:
        return MODULE.build_proof("line-sticker-readback-hourly:x", Q, now=now, state_root=root)

    def test_a_read_only_run_that_resubmitted_nothing_proves_no_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # readback rewrites creators-item.json on every status change; that is not an external effect.
            _item(root, "set-014", product_id="1", state_observed="審査待ち")
            p = self.proof(root)
            self.assertTrue(p["verified"])
            self.assertFalse(p["effected"])

    def test_an_auto_resubmit_after_the_run_started_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _item(root, "set-010", product_id="2", last_auto_resubmit_at=(Q + dt.timedelta(minutes=3)).isoformat())
            self.assertFalse(self.proof(root)["verified"])

    def test_an_auto_resubmit_before_the_run_started_is_not_this_runs_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _item(root, "set-010", product_id="2", last_auto_resubmit_at=(Q - dt.timedelta(hours=1)).isoformat())
            self.assertTrue(self.proof(root)["verified"])

    def test_too_recent_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _item(root, "set-014", product_id="1")
            self.assertFalse(self.proof(root, now=Q + dt.timedelta(minutes=1))["verified"])


if __name__ == "__main__":
    unittest.main()
