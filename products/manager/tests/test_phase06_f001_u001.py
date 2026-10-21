"""Phase06 F001 + U001 research-matrix acceptance, NO online effects.

Source URLs denote reviewed research candidates, never an actuation grant or a
verified independent beneficiary improvement. Canonical tasks.json stays SSOT.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "docs/product/opportunities.json"
MATRIX = ROOT / "docs/product/OPPORTUNITIES.md"
AUTHORITY = ROOT / "pilot/FEASIBILITY_AND_AUTHORITY.md"

REQUIRED = {"id", "domain", "name", "beneficiaries", "harm_mechanism",
            "public_observation", "source_urls", "operator",
            "operator_authority_status", "data_rights", "metric",
            "independent_outcome_evidence", "comparator", "feasibility",
            "blockers", "live_pilot_ready", "no_action"}

class DiscoveryContractTests(unittest.TestCase):
    def setUp(self):
        self.rows = json.loads(DATA.read_text(encoding="utf-8"))

    def test_F001_public_source_domain_operator_and_rights_are_explicit(self):
        self.assertGreaterEqual(len(self.rows), 5)
        self.assertGreaterEqual(len({x["id"] for x in self.rows}), 5)
        self.assertIn("finance", {x["domain"] for x in self.rows})
        self.assertIn("environment", {x["domain"] for x in self.rows})
        for candidate in self.rows:
            with self.subTest(id=candidate["id"]):
                self.assertEqual(set(candidate), REQUIRED)
                for field in ("name","beneficiaries","harm_mechanism",
                              "public_observation","operator","data_rights","metric",
                              "independent_outcome_evidence","comparator","feasibility"):
                    self.assertIsInstance(candidate[field], str)
                    self.assertTrue(candidate[field].strip())
                self.assertGreaterEqual(len(candidate["source_urls"]), 1)
                self.assertTrue(all(urlsplit(u).scheme == "https" and urlsplit(u).hostname
                                    for u in candidate["source_urls"]))
                self.assertIsInstance(candidate["blockers"], list)
                self.assertTrue(candidate["blockers"])

    def test_F001_no_unauthorized_pilot_or_external_effect(self):
        for candidate in self.rows:
            with self.subTest(id=candidate["id"]):
                self.assertIs(candidate["live_pilot_ready"], False)
                self.assertEqual(candidate["operator_authority_status"],"NOT_VERIFIED")
                self.assertIs(candidate["no_action"], True)
                self.assertIn(candidate["feasibility"], {
                    "READ_ONLY_RESEARCH", "SANDBOX_ONLY", "BLOCKED_LIVE_EFFECT"})
        txt=AUTHORITY.read_text(encoding="utf-8")
        self.assertIn("NO_ACTION",txt)
        self.assertIn("NOT_VERIFIED",txt)
        self.assertIn("NOT_MEASURED",txt)
        self.assertIn("Founder development approval",txt)

    def test_U001_at_least_three_comparable_causal_opportunities(self):
        all_domains={c["domain"] for c in self.rows}
        self.assertGreaterEqual(len(all_domains),3)
        for c in self.rows:
            self.assertTrue(c["harm_mechanism"])
            self.assertTrue(c["metric"])
            self.assertTrue(c["comparator"])
            self.assertTrue(c["independent_outcome_evidence"])
            self.assertTrue(c["beneficiaries"])
        matrix=MATRIX.read_text(encoding="utf-8")
        self.assertIn("NO_ACTION",matrix)
        self.assertIn("P0",matrix)
        self.assertIn("P4",matrix)
        for c in self.rows:
            self.assertIn(c["id"],matrix)
        self.assertIn("NOT_MEASURED",matrix)

    def test_existing_science_and_permission_blockers_remain(self):
        tasks=json.loads((ROOT/"docs/roadmap/tasks.json").read_text(encoding="utf-8"))
        t={x["id"]:x for x in tasks}
        self.assertEqual(len(t),113)
        for x in ("K001","K014","S008"):
            self.assertEqual(t[x]["status"],"done")
        self.assertEqual(t["H005"]["status"],"skipped")
        self.assertEqual(t["F004"]["status"],"blocked")
        self.assertEqual(t["F007"]["status"],"blocked")

if __name__ == "__main__":
    unittest.main()
