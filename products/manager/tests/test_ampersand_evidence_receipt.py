"""E01: reproduce the original ten real API calls' P0 record, not simulated human benefit."""
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from manager_core.evidence import load_verified_trial

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/verification/ampersand-20261022/ten_case_raw.json"
RECEIPT = ROOT / "docs/verification/ampersand-20261022/ten_case_receipt.json"
KNOWN_SOURCE = "66997ea549f8d1373a7670b8a11add9af17613ea"
KNOWN_RAW_SHA256 = "c46503170d9fc337137d6283fb6d38821a29149f72609f751a79366103f70585"
KNOWN_ARTIFACT_ID = 12398755518


class AmpersandEvidenceReceiptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.receipt = json.loads(RECEIPT.read_text(encoding="utf8"))

    def test_raw_bytes_match_immutable_readback(self):
        self.assertTrue(DATA.is_file())
        self.assertEqual(sha256(DATA.read_bytes()).hexdigest(), KNOWN_RAW_SHA256)
        self.assertEqual(self.receipt["raw_sha256"], KNOWN_RAW_SHA256)
        self.assertEqual(self.receipt["source_commit"], KNOWN_SOURCE)
        self.assertEqual(self.receipt["artifact_id"], KNOWN_ARTIFACT_ID)
        self.assertEqual(self.receipt["run_id"], 39713799676)

    def test_trial_counts_are_derived_from_real_raw_rows(self):
        result = load_verified_trial(DATA, self.receipt)
        self.assertEqual(len(result["cases"]), 10)
        self.assertEqual(result["model_sessions_created"], 10)
        self.assertEqual(result["model_scored"], 10)
        self.assertEqual(result["model_matches_count"], 7)
        self.assertEqual(result["heldout_cases"], 7)
        self.assertEqual(result["heldout_model_matches"], 4)
        self.assertEqual(result["completed_followups"], 1)
        self.assertEqual(result["completed_kernel_audits"], 10)
        self.assertEqual(result["baseline_matches_count"], 5)
        self.assertTrue(all(c["kernel_action"] == "NO_ACTION" for c in result["cases"]))

    def test_missing_or_tampered_source_rejected(self):
        result = json.loads(DATA.read_text(encoding="utf8"))
        result["cases"][0]["model_decision"] = "PASS"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(result), encoding="utf8")
            with self.assertRaises(ValueError):
                load_verified_trial(path, self.receipt)

    def test_same_digest_but_forged_summary_rejected(self):
        raw = DATA.read_bytes()
        with TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_bytes(raw)
            result = json.loads(raw)
            # Provenance-independent mutation of an aggregate must be
            # cross-checked against immutable per-case data, even when
            # attacker updates both receipt and aggregate hash.
            result["heldout_model_matches"] = 99
            path.write_text(json.dumps(result), encoding="utf8")
            receipt = dict(self.receipt)
            receipt["raw_sha256"] = sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                load_verified_trial(path, receipt)

    def test_field_efficacy_and_cost_cannot_be_fabricated(self):
        result = load_verified_trial(DATA, self.receipt)
        self.assertEqual(result["real_people"], 0)
        self.assertEqual(result["real_world_effects"], 0)
        self.assertEqual(result["evidence_level"], "P0_SYNTHETIC_ONLY")
        self.assertEqual(result["real_human_outcome"], "NOT_MEASURED")
        self.assertIsNone(result["exact_settled_cost_usd"])

    def test_invalid_receipt_identity_is_not_provenance(self):
        for value in ("fake", 0, None):
            with self.subTest(value=value):
                receipt = dict(self.receipt)
                receipt["source_commit"] = value
                with self.assertRaises(ValueError):
                    load_verified_trial(DATA, receipt)


if __name__ == "__main__":
    unittest.main()
