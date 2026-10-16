import datetime as dt
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import factory_fence_reconcile as MODULE  # noqa: E402

Q = dt.datetime(2026, 10, 8, 17, 15, tzinfo=dt.timezone.utc)
LATE = Q + dt.timedelta(minutes=6)


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

    def test_no_local_item_after_the_run_does_not_prove_no_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-014", "submitted", {"product_id": "1", "state": "review_requested",
                                                "created_at": _iso(Q - dt.timedelta(hours=2)),
                                                "review_requested_at": _iso(Q - dt.timedelta(hours=1), z=True)})
            _set(root, "set-015", "submit", None)
            p = self.proof(root)
            self.assertFalse(p["verified"])
            self.assertEqual(p["reason"], "official_line_no_effect_readback_required")

    def test_readback_rewriting_a_selling_set_is_not_an_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            item = {"product_id": "1", "state": "on_sale", "created_at": _iso(Q - dt.timedelta(days=3)),
                    "review_requested_at": _iso(Q - dt.timedelta(days=2)),
                    "state_observed": _iso(Q + dt.timedelta(minutes=1)), "purchase_url": "https://x",
                    "store_public": True, "last_auto_resubmit_at": _iso(Q + dt.timedelta(minutes=1))}
            _set(root, "set-001", "submitted", item)
            proof = self.proof(root)
            self.assertFalse(proof["verified"])
            self.assertEqual(proof["reason"], "official_line_no_effect_readback_required")

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

    def test_a_stage_advance_without_local_item_still_needs_official_no_effect_readback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-015", "package", None)
            proof = self.proof(root)
            self.assertFalse(proof["verified"])
            self.assertEqual(proof["reason"], "official_line_no_effect_readback_required")

    def test_local_absence_stays_fenced_even_after_old_no_effect_delay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-015", "submit", None)
            proof = self.proof(root, now=LATE)
            self.assertFalse(proof["verified"])
            self.assertEqual(proof["reason"], "official_line_no_effect_readback_required")


class OfficialCreatorsListing(unittest.TestCase):
    """No local hit: the account's own Creators Market item list (api/v2/sticker) is the receipt."""
    AGED = Q + dt.timedelta(seconds=MODULE.NO_EFFECT_MIN_AGE_SECONDS + 1)

    def root(self, tmp: str) -> Path:
        root = Path(tmp)
        _set(root, "set-041", "submitted", {"product_id": "48299386", "state": "review_requested",
                                            "state_observed": "販売中",
                                            "created_at": _iso(Q - dt.timedelta(days=1))})
        _set(root, "set-042", "submit", {})
        return root

    def proof(self, root: Path, creators: dict, now: dt.datetime = AGED) -> dict:
        return MODULE.build_proof("line-sticker-factory-hourly:x", Q, now=now, state_root=root,
                                  creators=creators)

    def test_complete_listing_with_no_new_unrecorded_item_proves_no_effect(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # 42100028 is a pre-loop item: older than every item recorded before the run.
            p = self.proof(self.root(tmp), {"ok": True, "ids": ["48299386", "42100028"], "total": 2})
            self.assertTrue(p["verified"])
            self.assertFalse(p["effected"])
            self.assertTrue(p["provider_receipt_id"].startswith("creators-market-item-list:2:"))

    def test_an_unrecorded_item_newer_than_the_run_baseline_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self.proof(self.root(tmp), {"ok": True, "ids": ["48300001", "48299386"], "total": 2})
            self.assertFalse(p["verified"])
            self.assertEqual(p["reason"], "unrecorded_creators_item:48300001")

    def test_an_incomplete_listing_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self.proof(self.root(tmp), {"ok": True, "ids": ["48299386"], "total": 2})
            self.assertFalse(p["verified"])
            self.assertEqual(p["reason"], "incomplete_creators_listing:1<2")

    def test_readback_failure_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self.proof(self.root(tmp), {"ok": False, "reason": "browser_unavailable"})
            self.assertFalse(p["verified"])
            self.assertEqual(p["reason"], "browser_unavailable")

    def test_too_recent_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self.proof(self.root(tmp), {"ok": True, "ids": ["48299386"], "total": 1}, now=LATE)
            self.assertFalse(p["verified"])
            self.assertTrue(p["reason"].startswith("too_recent:"))

    def test_without_any_item_recorded_before_the_run_an_unrecorded_item_stays_fenced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _set(root, "set-042", "submit", {})
            p = self.proof(root, {"ok": True, "ids": ["42100028"], "total": 1})
            self.assertFalse(p["verified"])
            self.assertEqual(p["reason"], "unrecorded_creators_item:42100028")

    def test_list_pages_parse_into_ids_and_total(self) -> None:
        pages = {1: {"items": [{"id": 48299386}, {"id": 48292978}], "pager": {"maxPage": 2, "totalEntries": 3}},
                 2: {"items": [{"id": 42100028}], "pager": {"maxPage": 2, "totalEntries": 3}}}
        self.assertEqual(MODULE.collect_listing(pages.__getitem__),
                         {"ok": True, "ids": ["48299386", "48292978", "42100028"], "total": 3})
        self.assertEqual(MODULE.collect_listing(lambda n: {"items": "x"})["ok"], False)


class ReleasedFenceRecovery(unittest.TestCase):
    def test_active_released_unknown_keeps_the_existing_readback_route(self) -> None:
        owner = MODULE.OWNER_ID
        occurrence = f"{owner}:active-run"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with sqlite3.connect(root / "admission-v2.sqlite3") as connection:
                connection.execute("CREATE TABLE occurrences(owner_id TEXT, occurrence_id TEXT, "
                                   "state TEXT, queued_at REAL, effect_unknown INTEGER)")
                connection.execute("INSERT INTO occurrences VALUES(?,?,?,?,?)",
                                   (owner, occurrence, "released", Q.timestamp(), 1))
            _set(root, "set-018", "submitted", {
                "product_id": "48172824", "state": "review_requested",
                "state_observed": "審査待ち", "created_at": _iso(Q + dt.timedelta(minutes=1))})
            with patch("runtime.host.resource_admission.state_root", return_value=root), \
                    patch.object(MODULE, "STATE_ROOT", root):
                proof = MODULE.reconcile(occurrence)
            self.assertTrue(proof["verified"])

    def test_released_recovery_uses_only_exact_occurrence_receipt_binding(self) -> None:
        owner = MODULE.OWNER_ID
        occurrence = f"{owner}:old-run"
        release_sha = "a" * 40
        exact = {"owner_id": owner, "occurrence_id": occurrence, "release_sha": release_sha}
        for binding, verified in [(exact, True), ({}, False),
                ({**exact, "occurrence_id": f"{owner}:later-run"}, False),
                ({**exact, "release_sha": "b" * 40}, False),
                ({**exact, "owner_id": "another-owner"}, False)]:
            with self.subTest(binding=binding), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                _set(root, "set-018", "submitted", {
                    "product_id": "48172824", "state": "review_requested",
                    "state_observed": "審査待ち", "created_at": _iso(Q + dt.timedelta(minutes=1)),
                    **binding})
                with patch.object(MODULE, "STATE_ROOT", root), \
                        patch.object(MODULE, "fenced_row", return_value=("released", Q, True)), \
                        patch.object(MODULE, "_terminal_unknown_release_sha", return_value=release_sha,
                                     create=True):
                    proof = MODULE.reconcile(occurrence)
                self.assertEqual(proof["verified"], verified)
                if not verified:
                    self.assertNotIn("provider_receipt_id", proof)

    def test_released_row_is_recoverable_only_with_exact_terminal_unknown_event(self) -> None:
        owner = MODULE.OWNER_ID
        occurrence = f"{owner}:run-1"
        release_sha = "a" * 40
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = root / "admission-v2.sqlite3"
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "CREATE TABLE occurrences(owner_id TEXT, occurrence_id TEXT, state TEXT, "
                    "queued_at REAL, effect_unknown INTEGER)"
                )
                connection.execute(
                    "INSERT INTO occurrences VALUES(?,?,?,?,?)",
                    (owner, occurrence, "released", Q.timestamp(), 0),
                )
            (root / "events.jsonl").write_text(json.dumps({
                "loop_id": owner,
                "owner_id": owner,
                "occurrence_id": occurrence,
                "release_sha": release_sha,
                "phase": "report",
                "status": "fail",
                "effect_class": "publish",
                "effect_status": "unknown",
            }) + "\n")

            with patch("runtime.host.resource_admission.state_root", return_value=root), \
                    patch.object(MODULE, "STATE_ROOT", root):
                state, queued_at, lost = MODULE.fenced_row(owner, occurrence)

        self.assertEqual(state, "released")
        self.assertEqual(queued_at, Q)
        self.assertTrue(lost)

    def test_released_row_without_exact_unknown_event_is_rejected(self) -> None:
        owner = MODULE.OWNER_ID
        occurrence = f"{owner}:run-1"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            database = root / "admission-v2.sqlite3"
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "CREATE TABLE occurrences(owner_id TEXT, occurrence_id TEXT, state TEXT, "
                    "queued_at REAL, effect_unknown INTEGER)"
                )
                connection.execute(
                    "INSERT INTO occurrences VALUES(?,?,?,?,?)",
                    (owner, occurrence, "released", Q.timestamp(), 0),
                )
            (root / "events.jsonl").write_text(json.dumps({
                "loop_id": owner,
                "owner_id": owner,
                "occurrence_id": f"{owner}:different-run",
                "release_sha": "a" * 40,
                "phase": "report",
                "status": "blocked",
                "effect_class": "publish",
                "effect_status": "unknown",
            }) + "\n")

            with patch("runtime.host.resource_admission.state_root", return_value=root), \
                    patch.object(MODULE, "STATE_ROOT", root):
                with self.assertRaises(ValueError):
                    MODULE.fenced_row(owner, occurrence)


if __name__ == "__main__":
    unittest.main()
