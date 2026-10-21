"""Reuse-only welfare outcome crosswalk: NEVER add simulated outcomes into P3/P4."""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/"docs/research/crossfield-20261021/SOURCES.json"
BRIDGE=ROOT/"pilot/INTERNET_WELFARE_EVIDENCE_CROSSWALK.json"
CI=ROOT/"scripts/phase06_welfare_proof_gate.py"


class ReuseOnlyWelfareContracts(unittest.TestCase):
    def test_three_different_validated_instruments_no_composite_score(self):
        records=json.loads(BRIDGE.read_text(encoding="utf-8"))
        self.assertEqual({r["domain"] for r in records},{"MENTAL","PHYSICAL","FINANCIAL"})
        source_ids={r["id"] for r in json.loads(REGISTRY.read_text(encoding="utf-8"))}
        for r in records:
            with self.subTest(domain=r["domain"]):
                self.assertIn(r["source_registry_id"],source_ids)
                self.assertTrue(r["official_instrument_url"].startswith("https://"))
                self.assertEqual(r["beneficiary_welfare_status"],"NOT_MEASURED")
                self.assertIsNone(r["observed_people"])
                self.assertIsNone(r["measured_effect"])
                self.assertIsNone(r["confidence_interval"])
                self.assertEqual(r["proof_level"],"P0")
                self.assertTrue(r["licensed_outcome_instrument_required"])
                self.assertTrue(r["voluntary_outcome_measurement_required"])
                self.assertIn("NO_ACTION",r["comparator_requirement"])
                self.assertTrue(r["harms_and_attrition_required"])
                self.assertEqual(r["instrument_questions_embedded"],False)
        self.assertNotIn("global_suffering_score",BRIDGE.read_text(encoding="utf-8").lower())

    def test_public_artifact_p2_is_not_welfare_p3(self):
        from manager_core.outcome_ladder import proof_level
        technical=proof_level({"external_receipt":True,"independent_readback":True})
        self.assertEqual(technical,2)
        self.assertNotEqual(technical,3)
        self.assertEqual(proof_level({}),0)
        text=CI.read_text(encoding="utf-8")
        self.assertIn("from manager_core.outcome_ladder import proof_level",text)
        self.assertIn("NOT_MEASURED",text)
        self.assertIn("PUBLIC_ARTIFACT_ONLY",text)

    def test_source_registry_contains_provenance_of_actual_official_directory(self):
        data=json.loads(REGISTRY.read_text(encoding="utf-8"))
        refs={s["id"]:s for s in data}
        for id in ("growthbook-python-sdk","github-public-contents-readback","japan-mhlw-livelihood",
                   "japan-fsa-debt","japan-mhlw-mental","japan-mhlw-physical"):
            with self.subTest(id=id):
                self.assertIn(id,refs)
                self.assertIn(refs[id]["rights"],("PUBLIC_DOC_ONLY","OPEN_SOURCE_CHECK_LICENSE"))
        self.assertGreaterEqual(len(data),82)


if __name__=="__main__":
    unittest.main()
