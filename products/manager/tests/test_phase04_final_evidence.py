"""Phase04 signed-off engineering receipts must not imply scientific impact."""
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
DOCS=ROOT/"docs"

class Phase04ReceiptChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg={t["id"]:t for t in json.loads((DOCS/"roadmap/tasks.json").read_text())}
        cls.full=json.loads((DOCS/"research/socsci/PHASE04_REAL_210_STUDY_COUNTS.json").read_text())
        cls.mini=json.loads((DOCS/"research/socsci/PHASE04_S005_REAL_PRETRAINED_METRICS_2026-10-21.json").read_text())
        cls.small=json.loads((DOCS/"research/socsci/PHASE04_REAL_40_STUDY_SAME_SAMPLE_OPENMODEL_METRICS.json").read_text())

    def test_all_eight_atomic_task_receipts_preserve_scientific_warnings(self):
        for i in range(1,9):
            row=self.reg[f"S{i:03d}"]
            self.assertEqual(row["status"],"done")
            self.assertTrue(row.get("evidence_run"))
        for t in ("S002","S004","S005","S006","S007","S008"):
            row=self.reg[t]
            self.assertTrue(row.get("scope_override"))
            self.assertTrue(row.get("verification_scope"))
            self.assertFalse(row["human_effect_verified"])
        self.assertEqual(self.reg["H005"]["status"],"skipped")

    def test_real_40_study_data_with_no_participants_committed(self):
        z=self.full
        self.assertEqual(z["source_split"]["seen_rows"],2418748)
        self.assertEqual(z["source_split"]["unseen_rows"],482642)
        self.assertEqual(z["source_split"]["seen_studies"],170)
        self.assertEqual(z["source_split"]["unseen_studies"],40)
        self.assertEqual(z["source_split"]["overlap"],0)
        self.assertEqual(z["privacy"]["participant_records_published"],0)
        self.assertFalse(z["calibration"]["meaningful_individual_level_calibration_established"])
        self.assertTrue(z["abstention_policy"]["retrospective_error_alert_not_an_online_action_policy"])
        self.assertAlmostEqual(z["abstention_policy"]["train_only_leave_one_study_out_tvd_p90"],.60767102)
        self.assertEqual(sum(g["studies"] for g in z["subgroups"]),40)

    def test_same_sample_public_encoder_inference_not_original_socrates_model(self):
        z=self.mini
        self.assertEqual((z["study_split"]["train_rows"],z["study_split"]["unseen_rows"]),(3400,800))
        self.assertEqual(z["study_split"]["unseen_studies"],40)
        self.assertAlmostEqual(z["evaluation"]["frozen_pretrained_encoder_plus_trained_head"]["accuracy"],.245)
        self.assertAlmostEqual(z["evaluation"]["train_frequency_prior"]["accuracy"],.19375)
        self.assertTrue(z["limitations"]["numeric_response_code_semantics_not_uniform_across_studies"])
        self.assertTrue(z["privacy"]["raw_rows_stored_or_uploaded"] is False)
        self.assertEqual(z["research_receipt"]["model_license"],"Apache-2.0")

    def test_openmodel_negative_results_retained_and_no_privacy_leak(self):
        z=self.small
        self.assertEqual(z["evaluation"]["individual_test_rows"],320)
        self.assertEqual(z["evaluation"]["unseen_test_studies"],40)
        self.assertAlmostEqual(z["same_sample_scores"]["pretrained_coverage"],.425)
        self.assertAlmostEqual(z["same_sample_scores"]["pretrained_accuracy_including_abstentions_as_wrong"],.090625)
        self.assertEqual(z["subgroup"]["studies_with_zero_valid_model_responses"],12)
        self.assertFalse(z["scientific_scope"]["canonical_socrates_task_aware_metric_reproduced"])
        self.assertFalse(z["scientific_scope"]["independent_real_world_manager_benefit"])
        for key in ("prompts_in_report","published_per_person_predictions","participant_identifiers_in_report"):
            self.assertFalse(z["privacy"][key])

    def test_report_keeps_deployment_and_true_scientific_gates_separate(self):
        text=(DOCS/"verification/PHASE04_FINAL_REAL_DATA_EVIDENCE_JA.md").read_text()
        for required in ("Gate 1 = UNMET","22.8565%","24.500%","42.50%","ABSTAIN"):
            self.assertIn(required,text)
        gate=(DOCS/"roadmap/PRODUCT_COMPLETION_GATES.md").read_text()
        self.assertIn("Gate 1",gate)
        self.assertNotIn("FULL HUMAN SIMULATION VALIDATED",text)

if __name__=="__main__":
    unittest.main()
