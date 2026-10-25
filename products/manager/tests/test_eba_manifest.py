"""Regression tests for the catalog-only EBA v1 manifest contract."""

from __future__ import annotations

import json
import sys
import unittest
from collections import Counter
from pathlib import Path

MANAGER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MANAGER_ROOT))

from manager_core import eba_manifest  # noqa: E402


INVENTORY = MANAGER_ROOT / "docs/research/evals/EVAL_LANDSCAPE_20261022.json"


class EbaCatalogManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inventory_bytes = INVENTORY.read_bytes()
        cls.inventory = json.loads(cls.inventory_bytes)
        cls.manifest = eba_manifest.build_catalog(cls.inventory_bytes)

    def assert_manifest_error(self, document: dict, code: str) -> None:
        with self.assertRaises(eba_manifest.EbaManifestError) as raised:
            eba_manifest.validate_catalog(document, self.inventory_bytes)
        self.assertEqual(raised.exception.code, code)

    def test_inventory_is_pinned_and_catalog_preserves_all_90_source_records(self) -> None:
        self.assertEqual(len(self.inventory), 90)
        self.assertEqual(
            self.manifest["source_inventory"]["sha256"],
            "a57feea7c2e96b90d6e9b664346224d756ef59da0e4b3a37857609c0c60bb634",
        )
        self.assertEqual(len(self.manifest["candidates"]), 90)
        self.assertEqual(
            [item["source"] for item in self.manifest["candidates"]], self.inventory
        )
        eba_manifest.validate_catalog(self.manifest, self.inventory_bytes)

    def test_inventory_rights_status_has_no_precleared_candidate(self) -> None:
        self.assertEqual(
            Counter(item["rights"] for item in self.inventory),
            {
                "UPSTREAM_LICENSE_CHECK": 66,
                "DATA_RIGHTS_REVIEW_REQUIRED": 18,
                "PUBLIC_METHOD_ONLY": 6,
            },
        )
        self.assertFalse(
            any(item["rights"] not in {"UPSTREAM_LICENSE_CHECK", "DATA_RIGHTS_REVIEW_REQUIRED", "PUBLIC_METHOD_ONLY"}
                for item in self.inventory)
        )

    def test_catalog_has_seven_separate_unscored_dimensions(self) -> None:
        self.assertEqual(
            [item["id"] for item in self.manifest["dimensions"]],
            ["forecast", "sim", "intervention", "decision", "execution", "welfare", "generalization"],
        )
        self.assertTrue(
            all(item["status"] == "NOT_RUN" and item["score"] is None for item in self.manifest["dimensions"])
        )
        self.assertIsNone(self.manifest["claim_limits"]["global_score"])

    def test_unverified_metadata_stays_unknown_and_not_run(self) -> None:
        for candidate in self.manifest["candidates"]:
            self.assertEqual(candidate["rights_clearance"], "NOT_VERIFIED")
            self.assertEqual(candidate["version_status"], "NOT_PINNED")
            self.assertIsNone(candidate["population"])
            self.assertIsNone(candidate["unit"])
            self.assertIsNone(candidate["labels"])
            self.assertIsNone(candidate["holdout"])
            self.assertEqual(candidate["mapping_status"], "NOT_REVIEWED")
            self.assertEqual(candidate["execution_status"], "NOT_RUN")
            self.assertIsNone(candidate["score"])
            self.assertEqual(candidate["human_outcome"], "NOT_MEASURED")
            self.assertEqual(candidate["unmeasured"], [candidate["source"]["does_not_prove"]])
        self.assertEqual(self.manifest["claim_limits"]["missingness"], "UNKNOWN_NOT_ZERO")

    def test_changed_inventory_bytes_are_rejected(self) -> None:
        with self.assertRaises(eba_manifest.EbaManifestError) as raised:
            eba_manifest.validate_catalog(self.manifest, self.inventory_bytes + b" ")
        self.assertEqual(raised.exception.code, "SOURCE_HASH_MISMATCH")

    def test_duplicate_or_missing_candidate_ids_are_rejected(self) -> None:
        duplicate = json.loads(json.dumps(self.manifest))
        duplicate["candidates"][1]["id"] = duplicate["candidates"][0]["id"]
        self.assert_manifest_error(duplicate, "DUPLICATE_CANDIDATE_ID")

        missing = json.loads(json.dumps(self.manifest))
        missing["candidates"].pop()
        self.assert_manifest_error(missing, "CANDIDATE_SET_MISMATCH")

    def test_candidate_mapping_requires_review_before_dimension_assignment(self) -> None:
        mapped = json.loads(json.dumps(self.manifest))
        mapped["candidates"][0]["dimension_ids"] = ["forecast"]
        self.assert_manifest_error(mapped, "UNREVIEWED_DIMENSION_MAPPING")

    def test_scores_cannot_appear_before_a_run_or_as_a_global_score(self) -> None:
        scored = json.loads(json.dumps(self.manifest))
        scored["candidates"][0]["score"] = 0.8
        self.assert_manifest_error(scored, "SCORE_WHILE_NOT_RUN")

        global_score = json.loads(json.dumps(self.manifest))
        global_score["claim_limits"]["global_score"] = 0.8
        self.assert_manifest_error(global_score, "GLOBAL_SCORE_FORBIDDEN")

    def test_rights_cannot_be_promoted_by_catalog_metadata(self) -> None:
        upgraded = json.loads(json.dumps(self.manifest))
        upgraded["candidates"][0]["rights_clearance"] = "VERIFIED"
        self.assert_manifest_error(upgraded, "RIGHTS_NOT_VERIFIED")


if __name__ == "__main__":
    unittest.main()
