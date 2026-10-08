import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import factory_fence_reconcile as MODULE  # noqa: E402

Q = dt.datetime(2026, 10, 8, 17, 15, tzinfo=dt.timezone.utc)
LATE = Q + dt.timedelta(seconds=MODULE.NO_EFFECT_MIN_AGE_SECONDS + 1)


def _set(root: Path, name: str, stage: str, item: dict | None, updated: dt.datetime) -> None:
    """File mtimes are what the adapter reads, so set them to ``updated`` explicitly."""
    import os
    d = root / name
    d.mkdir()
    stamp = updated.timestamp()
    (d / "stage.json").write_text(json.dumps({"stage": stage}))
    os.utime(d / "stage.json", (stamp, stamp))
    if item is not None:
        (d / "creators-item.json").write_text(json.dumps(item))
        os.utime(d / "creators-item.json", (stamp, stamp))


class BuildProof(unittest.TestCase):
    def proof(self, root: Path, now: dt.datetime = LATE) -> dict:
        return MODULE.build_proof("line-sticker-factory-hourly:x", Q, now=now, state_root=root)

    def test_no_item_created_since_the_run_started_proves_no_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-014", "submitted", {"product_id": "1", "state": "review_requested"}, Q - dt.timedelta(hours=1))
            _set(root, "set-015", "submit", None, Q + dt.timedelta(minutes=2))
            p = self.proof(root)
            self.assertTrue(p["verified"])
            self.assertFalse(p["effected"])

    def test_an_item_touched_after_the_run_started_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-015", "submit", {"product_id": "2", "state": "images_uploaded"}, Q + dt.timedelta(minutes=2))
            self.assertFalse(self.proof(root)["verified"])

    def test_a_stage_advance_alone_is_not_an_external_effect(self) -> None:
        # stage.json moves on every wake; a run that only advanced stages never reached LINE.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-015", "package", None, Q + dt.timedelta(minutes=10))
            self.assertTrue(self.proof(root)["verified"])

    def test_too_recent_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-015", "submit", None, Q)
            self.assertFalse(self.proof(root, now=Q + dt.timedelta(minutes=3))["verified"])


if __name__ == "__main__":
    unittest.main()
