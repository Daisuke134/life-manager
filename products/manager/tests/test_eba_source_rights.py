"""Code-license evidence is separate from benchmark-data and human rights."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

MANAGER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGER_ROOT))

from manager_core import eba_manifest  # noqa: E402


RIGHTS_PATH = MANAGER_ROOT / "docs/research/source-rights.json"
INVENTORY_PATH = MANAGER_ROOT / "docs/research/evals/EVAL_LANDSCAPE_20261022.json"
EXPECTED_CODE_PINS = {
    "inspect-ai": ("MIT", "d1536eae98d7b8b9364c052f0e6d3de988e1aac9", "c593c2afc81388521eaeb03f0d1a4b01bc3e5147ed9cb16c1f129e5be353b6af", 1081),
    "concordia": ("Apache-2.0", "239f0e8275a55b186b99e133e06432cd681ff2e3", "8c6db340475136df3c1201d458fa5755698eace76e510471ecc9d857d6083dac", 11359),
    "oasis": ("Apache-2.0", "8607dba82d73f7bfc371b3beafe57cc844687be2", "950deb34b1341a0ac95236fae92fe247c318c3a83a62c9ebacbe1882530ab1f6", 11344),
    "tau2bench": ("MIT", "0c69df456a96aa76a1162591574dad9c427a34d7", "e67c5aa0074dfcaefd3c3a1aedb94cb539234aecd15d5a972574e3200e6252fe", 1072),
    "dowhy": ("MIT", "0629ba0d1009b685b8e835514cabea89f7b22e5a", "4be08a194b9c970bf9309ac19f09e7deaecb763957091bf08298bf0e897e7eab", 1159),
    "econml": ("MIT; BSD-3-Clause portions", "9f61a3376cbf41c5a9155f46bbafaaea9f281508", "e4503a01022a819cc3654273977885e4984cce87cd06bd81063d1bb36a056250", 2978),
    "ai-economist": ("BSD-3-Clause", "a84d5f3fdcabb207d9fde7754d34906903b3e184", "3360d12ecbe2fd87e7eddc6619daacfcb9132b2def5c3df6410941e1a2df6bfb", 1482),
    "omni-behavior": ("CC-BY-NC-SA-4.0", "cd36b45b09b4bdc4254cbbebf773e2f880d6638a", "9e502ba75fd0fd30cea5497b438a4bc12f07f02bc932a7a6041fd6a18b8f46a0", 20848),
}


class EbaCodeRightsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(RIGHTS_PATH.read_bytes())
        cls.records = {row["id"]: row for row in cls.registry["sources"]}
        cls.inventory = {row["id"]: row for row in json.loads(INVENTORY_PATH.read_bytes())}
        cls.catalog_bytes = INVENTORY_PATH.read_bytes()
        cls.catalog = eba_manifest.build_catalog(cls.catalog_bytes)

    def test_exact_repository_commit_and_license_file_hashes_are_pinned(self) -> None:
        for candidate_id, (license_name, commit, content_sha, byte_count) in EXPECTED_CODE_PINS.items():
            record = self.records[f"eba-code-{candidate_id}"]
            with self.subTest(candidate_id=candidate_id):
                self.assertEqual(record["license_expression"], license_name)
                self.assertEqual(record["artifact"]["revision"], commit)
                self.assertEqual(record["license_evidence_sha"], commit)
                evidence = record["license_review"]
                self.assertEqual(evidence["license_file_sha256"], content_sha)
                self.assertEqual(evidence["license_file_bytes"], byte_count)
                self.assertIn(commit, record["license_evidence_url"])
                self.assertIn(commit, record["source_url"])
                self.assertIn(candidate_id, self.inventory)

    def test_code_license_does_not_clear_dataset_or_task_content(self) -> None:
        for candidate_id in EXPECTED_CODE_PINS:
            record = self.records[f"eba-code-{candidate_id}"]
            with self.subTest(candidate_id=candidate_id):
                self.assertEqual(record["permissions"]["code_reuse"], "allowed_with_conditions")
                self.assertEqual(record["permissions"]["dataset_reuse"], "hold")
                self.assertEqual(record["permissions"]["task_content_reuse"], "hold")
                self.assertEqual(record["permissions"]["raw_redistribution"], "hold")
                self.assertEqual(record["permissions"]["live_use"], "hold")
                self.assertIn("dataset", record["unresolved"].lower())

        catalog_rights = {
            candidate["id"]: candidate["rights_clearance"]
            for candidate in self.catalog["candidates"]
        }
        self.assertTrue(all(catalog_rights[candidate_id] == "NOT_VERIFIED" for candidate_id in EXPECTED_CODE_PINS))

    def test_noncommercial_and_mixed_component_licenses_keep_their_restrictions(self) -> None:
        omni = self.records["eba-code-omni-behavior"]
        self.assertEqual(omni["permissions"]["commercial_code_use"], "hold")
        self.assertEqual(omni["permissions"]["noncommercial_code_use"], "allowed_with_conditions")
        self.assertEqual(omni["license_review"]["repository_spdx_metadata"], "NOASSERTION")

        econml = self.records["eba-code-econml"]
        self.assertEqual(econml["license_review"]["repository_spdx_metadata"], "NOASSERTION")
        self.assertIn("scikit-learn", econml["license_review"]["third_party_components"])
        self.assertIn("BSD-3-Clause", econml["license_review"]["third_party_components"])

    def test_archived_simulator_is_research_reference_not_live_dependency(self) -> None:
        record = self.records["eba-code-ai-economist"]
        self.assertTrue(record["artifact"]["archived"])
        self.assertEqual(record["permissions"]["live_use"], "hold")
        self.assertEqual(record["decision"], "REFERENCE_ONLY_NOT_VENDORED")


if __name__ == "__main__":
    unittest.main()
