import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import job_journal as JOURNAL
from job_journal import (
    JobStateError,
    reconcile_effect,
    resume_effect,
    start_effect,
    unresolved_effect,
    verify_effect,
)


class JobJournalTest(unittest.TestCase):
    def test_write_ahead_identity_reconcile_gate_and_verified_history(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            job = start_effect(state, "X_POST", "placement-1", {"content_sha256": "a" * 64},
                               {"state": "NOT_FOUND"}, 3600)
            self.assertEqual(job["state"], "EFFECT_STARTED")
            self.assertEqual(job["attempt"], 1)
            self.assertTrue(job["run_id"] and job["job_id"] and job["action_fingerprint"])
            with self.assertRaises(JobStateError):
                start_effect(state, "X_POST", "placement-1", {"content_sha256": "a" * 64},
                             {"state": "NOT_FOUND"}, 3600)
            resumed = resume_effect(state, "X_POST", "placement-1")
            self.assertEqual(resumed["state"], "EFFECT_STARTED")
            self.assertEqual(resumed["run_id"], job["run_id"])
            self.assertEqual(resumed["job_id"], job["job_id"])
            self.assertEqual(resumed["attempt"], 2)
            done = reconcile_effect(state, "X_POST", "placement-1", {"state": "LIVE", "public_id": "123"})
            self.assertEqual(done["state"], "VERIFIED")
            self.assertEqual(done["run_id"], job["run_id"])
            self.assertEqual(done["job_id"], job["job_id"])
            self.assertEqual(done["attempt"], 3)
            self.assertTrue(done["resumed"])
            self.assertEqual(len((state / "job-events.jsonl").read_text().splitlines()), 3)
            self.assertEqual((state / "job-events.jsonl").stat().st_mode & 0o077, 0)

    def test_target_index_avoids_owner_wide_job_scan(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            job = start_effect(
                state, "X_POST", "placement-1", {"content_sha256": "a" * 64},
                {"state": "NOT_FOUND"}, 3600,
            )
            # A direct target index must make unrelated historical key files
            # irrelevant to the hot recovery path.
            (state / "jobs" / "key-malformed.json").write_text("not-json")
            self.assertEqual(
                unresolved_effect(state, "X_POST", "placement-1")["job_id"],
                job["job_id"],
            )
            done = reconcile_effect(
                state, "X_POST", "placement-1", {"state": "LIVE", "public_id": "123"},
            )
            self.assertEqual(done["job_id"], job["job_id"])
            self.assertEqual(done["state"], "VERIFIED")

    def test_unresolved_target_blocks_a_different_action_fingerprint(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            job = start_effect(
                state, "X_POST", "placement-1", {"content_sha256": "a" * 64},
                {"state": "NOT_FOUND"}, 3600,
            )
            with self.assertRaisesRegex(JobStateError, "requires reconciliation"):
                start_effect(
                    state, "X_POST", "placement-1", {"content_sha256": "b" * 64},
                    {"state": "NOT_FOUND"}, 3600,
                )
            self.assertEqual(
                unresolved_effect(state, "X_POST", "placement-1")["job_id"],
                job["job_id"],
            )

    def test_legacy_effect_backfills_target_index_once(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            job = start_effect(
                state, "X_POST", "placement-1", {"content_sha256": "a" * 64},
                {"state": "NOT_FOUND"}, 3600,
            )
            target_indexes = list((state / "jobs").glob("target-*.json"))
            self.assertEqual(len(target_indexes), 1)
            target_indexes[0].unlink()

            migrated = unresolved_effect(state, "X_POST", "placement-1")
            self.assertEqual(migrated["job_id"], job["job_id"])
            self.assertEqual(len(list((state / "jobs").glob("target-*.json"))), 1)

            # The second lookup proves the migrated index is authoritative and
            # does not rescan every legacy key receipt.
            (state / "jobs" / "key-malformed.json").write_text("not-json")
            resumed = resume_effect(state, "X_POST", "placement-1")
            self.assertEqual(resumed["job_id"], job["job_id"])
            self.assertEqual(resumed["attempt"], 2)

    def test_empty_legacy_lookup_is_cached_for_the_target(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            start_effect(
                state, "X_POST", "other-placement", {"content_sha256": "a" * 64},
                {"state": "NOT_FOUND"}, 3600,
            )

            self.assertIsNone(unresolved_effect(state, "X_POST", "placement-1"))
            (state / "jobs" / "key-malformed.json").write_text("not-json")
            self.assertIsNone(unresolved_effect(state, "X_POST", "placement-1"))

    def test_malformed_target_index_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            start_effect(
                state, "X_POST", "placement-1", {"content_sha256": "a" * 64},
                {"state": "NOT_FOUND"}, 3600,
            )
            target_index = next((state / "jobs").glob("target-*.json"))
            target_index.write_text("not-json")
            with self.assertRaises(JobStateError):
                unresolved_effect(state, "X_POST", "placement-1")

    def test_invalid_target_index_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            start_effect(
                state, "X_POST", "placement-1", {"content_sha256": "a" * 64},
                {"state": "NOT_FOUND"}, 3600,
            )
            target_index = next((state / "jobs").glob("target-*.json"))
            row = json.loads(target_index.read_text())
            row["state"] = "UNKNOWN"
            target_index.write_text(json.dumps(row))
            with self.assertRaisesRegex(JobStateError, "target job index is invalid"):
                unresolved_effect(state, "X_POST", "placement-1")

    def test_malformed_target_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            start_effect(
                state, "X_POST", "placement-1", {"content_sha256": "a" * 64},
                {"state": "NOT_FOUND"}, 3600,
            )
            target_index = next((state / "jobs").glob("target-*.json"))
            row = json.loads(target_index.read_text())
            row["job_id"] = "f" * 64
            target_index.write_text(json.dumps(row))
            with self.assertRaisesRegex(JobStateError, "target job index is invalid"):
                unresolved_effect(state, "X_POST", "placement-1")

    def test_started_target_survives_crash_before_secondary_indexes(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            real_atomic_json = JOURNAL.atomic_json
            writes = []

            def crash_after_first_write(path, value):
                writes.append(path)
                if len(writes) == 1:
                    real_atomic_json(path, value)
                    return
                raise OSError("simulated secondary-index crash")

            with patch.object(JOURNAL, "atomic_json", side_effect=crash_after_first_write):
                with self.assertRaisesRegex(OSError, "secondary-index crash"):
                    start_effect(
                        state, "X_POST", "placement-1", {"content_sha256": "a" * 64},
                        {"state": "NOT_FOUND"}, 3600,
                    )

            with self.assertRaisesRegex(JobStateError, "requires reconciliation"):
                start_effect(
                    state, "X_POST", "placement-1", {"content_sha256": "b" * 64},
                    {"state": "NOT_FOUND"}, 3600,
                )

    def test_legacy_duplicate_target_still_requires_quarantine(self):
        with tempfile.TemporaryDirectory() as root:
            state = Path(root)
            job = start_effect(
                state, "X_POST", "placement-1", {"content_sha256": "a" * 64},
                {"state": "NOT_FOUND"}, 3600,
            )
            next((state / "jobs").glob("target-*.json")).unlink()
            action_fingerprint = "d" * 64
            job_key = hashlib.sha256(
                f"X_POST\0placement-1\0{action_fingerprint}".encode()
            ).hexdigest()
            job_id = hashlib.sha256(f"{job_key}\0{job['sequence']}".encode()).hexdigest()
            duplicate = dict(
                job,
                action_fingerprint=action_fingerprint,
                job_id=job_id,
                job_key=job_key,
            )
            (state / "jobs" / f"key-{duplicate['job_key']}.json").write_text(
                json.dumps(duplicate)
            )
            with self.assertRaisesRegex(JobStateError, "multiple unresolved effects"):
                unresolved_effect(state, "X_POST", "placement-1")


if __name__ == "__main__":
    unittest.main()
