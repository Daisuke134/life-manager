"""S001: metadata-only tests. No respondent/person fields in the test inputs."""
import json
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import socsci_split_audit as audit


class SocSciMetadataOnlyTests(unittest.TestCase):
    def example(self, **changes):
        mapping = {"seen": ["study_01", "study_02"], "unseen": ["study_03"]}
        mapping.update(changes)
        return json.dumps(mapping, separators=(",", ":")).encode("utf-8")

    def test_pinned_upstream_revision_and_no_respondent_ingestion(self):
        self.assertEqual(len(audit.PINNED_DATASET_REVISION), 40)
        self.assertEqual(audit.MAPPING_RELATIVE_PATH, "metadata/participant_mapping.json")
        self.assertEqual(audit.EXPECTED_STUDIES, {"seen": 170, "unseen": 40})
        self.assertIn("/resolve/", audit.MAPPING_URL)
        self.assertNotIn("/main/", audit.MAPPING_URL)

    def test_synthetic_small_split_and_digest_return_aggregates_only(self):
        blob = self.example()
        report = audit.inspect_study_mapping(
            blob, expected_blob=audit.git_blob_sha(blob),
            expected_bytes=len(blob), expected_studies={"seen": 2, "unseen": 1}
        )
        self.assertEqual(report["seen_studies"], 2)
        self.assertEqual(report["unseen_studies"], 1)
        self.assertEqual(report["overlap"], 0)
        self.assertEqual(report["total_studies"], 3)
        self.assertEqual(report["content_git_blob_sha1"], audit.git_blob_sha(blob))
        self.assertNotIn("study_01", json.dumps(report))
        self.assertNotIn("study_03", json.dumps(report))
        self.assertFalse(report["respondent_data_loaded"])

    def test_rejects_overlap_duplicates_and_unexpected_keys(self):
        for updates in (
            {"unseen": ["study_02"]},
            {"seen": ["study_01", "study_01"]},
            {"respondents": ["secret"]},
        ):
            with self.subTest(updates=updates):
                blob = self.example(**updates)
                with self.assertRaises(ValueError):
                    audit.inspect_study_mapping(
                        blob, expected_blob=audit.git_blob_sha(blob),
                        expected_bytes=len(blob), expected_studies={"seen": 2, "unseen": 1}
                    )

    def test_rejects_mismatched_bytes_hash_counts_and_non_study_ids(self):
        blob = self.example()
        cases = [
            (blob, "0" * 40, len(blob), {"seen": 2, "unseen": 1}),
            (blob, audit.git_blob_sha(blob), 999, {"seen": 2, "unseen": 1}),
            (blob, audit.git_blob_sha(blob), len(blob), {"seen": 170, "unseen": 40}),
        ]
        for data, digest, size, counts in cases:
            with self.assertRaises(ValueError):
                audit.inspect_study_mapping(data, expected_blob=digest,
                                            expected_bytes=size, expected_studies=counts)
        junk = json.dumps({"seen": ["study", True], "unseen": ["next"]}).encode()
        with self.assertRaises(ValueError):
            audit.inspect_study_mapping(junk, expected_blob=audit.git_blob_sha(junk),
                                        expected_bytes=len(junk),
                                        expected_studies={"seen": 2, "unseen": 1})


    def test_s003_leakage_guard_fails_closed_before_any_outcome_access(self):
        """A split audit is independent of training a predictive model."""
        from manager_core.calibration import assert_disjoint_groups
        assert_disjoint_groups(["experiment_A", "experiment_B"], ["experiment_C"])
        with self.assertRaises(ValueError):
            assert_disjoint_groups(["experiment_A", "experiment_B"], ["experiment_B"])
        with self.assertRaises(ValueError):
            assert_disjoint_groups(["experiment_C"], ["experiment_C"])

if __name__ == "__main__":
    unittest.main()
