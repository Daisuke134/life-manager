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


def _iso(t: dt.datetime, z: bool = False) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ") if z else t.replace(tzinfo=None).isoformat()


def _set(root: Path, name: str, stage: str, item: dict | str | None) -> None:
    """Evidence lives in the item's own fields; file mtimes are irrelevant (readback rewrites them)."""
    d = root / name
    d.mkdir()
    (d / "stage.json").write_text(json.dumps({"stage": stage}))
    if item is not None:
        (d / "creators-item.json").write_text(item if isinstance(item, str) else json.dumps(item))


class BuildProof(unittest.TestCase):
    def proof(self, root: Path, now: dt.datetime = LATE) -> dict:
        return MODULE.build_proof("line-sticker-factory-hourly:x", Q, now=now, state_root=root)

    def test_no_item_created_since_the_run_started_proves_no_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-014", "submitted", {"product_id": "1", "state": "review_requested",
                                                "created_at": _iso(Q - dt.timedelta(hours=2)),
                                                "review_requested_at": _iso(Q - dt.timedelta(hours=1), z=True)})
            _set(root, "set-015", "submit", None)
            p = self.proof(root)
            self.assertTrue(p["verified"])
            self.assertFalse(p["effected"])

    def test_readback_rewriting_a_selling_set_is_not_an_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = {"product_id": "1", "state": "on_sale", "created_at": _iso(Q - dt.timedelta(days=3)),
                    "review_requested_at": _iso(Q - dt.timedelta(days=2)),
                    "state_observed": _iso(Q + dt.timedelta(minutes=1)), "purchase_url": "https://x",
                    "store_public": True, "last_auto_resubmit_at": _iso(Q + dt.timedelta(minutes=1))}
            _set(root, "set-001", "submitted", item)
            self.assertTrue(self.proof(root)["verified"])

    def test_a_completed_submission_confirmed_by_readback_closes_as_effected(self) -> None:
        # 2026-10-10: set-018 (48172824) was submitted by the fenced run itself and readback saw it
        # 審査待ち on Creators Market; the fence still held forever because only no-effect could close.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-018", "submitted", {
                "product_id": "48172824", "state": "review_requested", "state_observed": "審査待ち",
                "created_at": _iso(Q + dt.timedelta(minutes=18)),
                "review_requested_at": _iso(Q + dt.timedelta(minutes=35))})
            p = self.proof(root)
            self.assertTrue(p["verified"])
            self.assertTrue(p["effected"])
            self.assertIn("48172824", p["provider_receipt_id"])

    def test_a_completed_submission_without_an_official_status_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-018", "submitted", {
                "product_id": "48172824", "state": "review_requested", "state_observed": None,
                "review_requested_at": _iso(Q + dt.timedelta(minutes=35))})
            self.assertFalse(self.proof(root)["verified"])

    def test_a_mid_flight_item_that_creators_market_shows_closes_as_effected(self) -> None:
        # 2026-10-11: set-020 (48219727) stopped at images_uploaded, LINE shows it 編集中; submit
        # resumes from the recorded item, so the fence can close and the next wake finishes it.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-020", "submit", {
                "product_id": "48219727", "state": "images_uploaded", "state_observed": "編集中",
                "created_at": _iso(Q + dt.timedelta(minutes=10))})
            p = self.proof(root)
            self.assertTrue(p["verified"])
            self.assertTrue(p["effected"])
            self.assertIn("48219727:編集中", p["provider_receipt_id"])

    def test_a_mid_flight_item_not_yet_seen_by_readback_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-020", "submit", {"product_id": "48219727", "state": "images_uploaded",
                                             "created_at": _iso(Q + dt.timedelta(minutes=10))})
            self.assertFalse(self.proof(root)["verified"])

    def test_created_or_review_requested_after_run_start_stays_fenced(self) -> None:
        for field, z in (("created_at", False), ("created_at", True),
                         ("review_requested_at", False), ("review_requested_at", True)):
            with self.subTest(field=field, z=z), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                item = {"state": "review_requested", "created_at": _iso(Q - dt.timedelta(days=1)),
                        field: _iso(Q + dt.timedelta(minutes=2), z=z)}
                _set(root, "set-015", "submit", item)
                self.assertFalse(self.proof(root)["verified"])

    def test_mid_submission_state_stays_fenced(self) -> None:
        for state in ("metadata_saved", "images_uploaded", "tagged"):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _set(root, "set-015", "submit", {"state": state, "created_at": _iso(Q - dt.timedelta(days=1))})
                self.assertFalse(self.proof(root)["verified"])

    def test_unreadable_item_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-015", "submit", "{not json")
            self.assertFalse(self.proof(root)["verified"])

    def test_a_stage_advance_alone_is_not_an_external_effect(self) -> None:
        # stage.json moves on every wake; a run that only advanced stages never reached LINE.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-015", "package", None)
            self.assertTrue(self.proof(root)["verified"])

    def test_too_recent_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-015", "submit", None)
            self.assertFalse(self.proof(root, now=Q + dt.timedelta(minutes=3))["verified"])


if __name__ == "__main__":
    unittest.main()
