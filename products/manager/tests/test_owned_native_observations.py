"""Private native E16 observations stay separate from sandbox and policy scores."""
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest

from manager_core.learning import NativeTechnicalObservation, PolicyLearner


NOW = datetime(2026, 10, 23, 1, 0, tzinfo=timezone.utc)
EFFECT = "a" * 64
CANDIDATE = "b" * 64
RECEIPT = "c" * 40
SOURCE_REF = "https://github.com/Daisuke134/life-manager/tree/" + "d" * 40
SERVED_REF = "https://daisuke134.github.io/life-manager/manager-support/"


def observation(**changes):
    values = dict(
        effect_key=EFFECT,
        candidate_sha256=CANDIDATE,
        receipt_ref=RECEIPT,
        observed_at=NOW,
        measure_id="owned.pages.commit_present",
        unit="boolean_occurrence",
        status="VERIFIED",
        proof_level="P1",
        native_value=1,
        missing_reason=None,
        human_outcome="NOT_MEASURED",
        provenance_refs=(SOURCE_REF,),
    )
    values.update(changes)
    return NativeTechnicalObservation(**values)


class OwnedNativeObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "learning.sqlite"
        self.learner = PolicyLearner(self.path)

    def test_validated_p1_and_p2_are_separate_exact_facts(self):
        p1 = observation()
        p2 = observation(
            measure_id="owned.pages.current_bytes_match",
            unit="exact_public_artifact_bytes",
            proof_level="P2",
            native_value=4647,
            provenance_refs=(SOURCE_REF, SERVED_REF),
        )

        self.learner.record_native_technical_observation(p1)
        self.learner.record_native_technical_observation(p2)

        rows = self.learner.native_technical_observations()
        self.assertEqual([(r.proof_level, r.native_value) for r in rows], [("P1", 1), ("P2", 4647)])
        self.assertEqual({r.effect_key for r in rows}, {EFFECT})
        self.assertEqual({r.candidate_sha256 for r in rows}, {CANDIDATE})
        self.assertTrue(all(r.human_outcome == "NOT_MEASURED" for r in rows))

    def test_unknown_is_null_with_reason_and_never_zero(self):
        unknown = observation(status="UNKNOWN", native_value=None, missing_reason="PUBLIC_GET_TIMEOUT")
        self.learner.record_native_technical_observation(unknown)
        stored = self.learner.native_technical_observations()[0]
        self.assertIsNone(stored.native_value)
        self.assertEqual(stored.missing_reason, "PUBLIC_GET_TIMEOUT")

    def test_identical_retry_is_idempotent_and_conflicting_same_fact_is_rejected(self):
        first = observation()
        first_id = self.learner.record_native_technical_observation(first)
        retry_id = self.learner.record_native_technical_observation(first)
        self.assertEqual(first_id, retry_id)
        self.assertEqual(len(self.learner.native_technical_observations()), 1)
        with self.assertRaises(ValueError):
            self.learner.record_native_technical_observation(observation(status="REGRESSION", native_value=0))
        self.assertEqual(len(self.learner.native_technical_observations()), 1)

    def test_later_current_snapshot_preserves_historical_verified_record(self):
        historic = observation(proof_level="P2", measure_id="owned.pages.current_bytes_match",
                               unit="exact_public_artifact_bytes", native_value=4647,
                               provenance_refs=(SERVED_REF,))
        current_pending = observation(
            proof_level="P2", measure_id="owned.pages.current_bytes_match",
            unit="exact_public_artifact_bytes", status="PENDING", native_value=None,
            missing_reason="DIFFERENT_SERVED_VERSION", observed_at=NOW.replace(minute=1),
            provenance_refs=(SERVED_REF,),
        )
        self.learner.record_native_technical_observation(historic)
        self.learner.record_native_technical_observation(current_pending)
        rows = self.learner.native_technical_observations()
        self.assertEqual([r.status for r in rows], ["VERIFIED", "PENDING"])
        self.assertEqual([r.native_value for r in rows], [4647, None])

    def test_strict_binding_value_unit_proof_and_time_validation(self):
        invalid = [
            {"effect_key": "effect-1"},
            {"candidate_sha256": "A" * 64},
            {"receipt_ref": "not-a-provider-commit"},
            {"native_value": True},
            {"native_value": float("nan")},
            {"unit": ""},
            {"proof_level": "P0"},
            {"proof_level": "P3"},
            {"human_outcome": "IMPROVED"},
            {"observed_at": datetime(2026, 10, 23, 1, 0)},
            {"status": "UNKNOWN", "native_value": None},
            {"status": "VERIFIED", "native_value": None, "missing_reason": "unknown"},
            {"status": "PENDING", "native_value": 0, "missing_reason": None},
        ]
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ValueError):
                observation(**change)

    def test_p0_sandbox_and_scalar_policy_state_are_untouched(self):
        self.learner.initialize("fixed-policy")
        self.learner.record_sandbox_technical({
            "status": "UNKNOWN", "writes": None, "deployed": False,
            "proof_level": "P0", "human_outcome": "NOT_MEASURED",
        })
        self.learner.propose("candidate", 0.1, 0.1, ["train"], ["test"])

        self.learner.record_native_technical_observation(observation())

        self.assertEqual(self.learner.active(), "fixed-policy")
        self.assertEqual(len(self.learner.sandbox_technical_observations()), 1)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM policies").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM native_technical_observations").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sandbox_technical_observations").fetchone()[0], 1)

    def test_api_rejects_untyped_caller_json(self):
        with self.assertRaises(TypeError):
            self.learner.record_native_technical_observation({"status": "VERIFIED"})


if __name__ == "__main__":
    unittest.main()
