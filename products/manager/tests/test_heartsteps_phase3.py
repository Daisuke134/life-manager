import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import heartsteps_phase3 as hp


class Phase3Tests(unittest.TestCase):
    def fixture(self):
        rows = []
        # Four synthetic people, five slots/day, four days, fixed log-scale effect.
        for user in range(4):
            for index in range(20):
                day = index // 5
                sent = (index + user) % 2 == 0
                active = sent and index % 3 != 0
                sedentary = sent and not active
                pre = 10 + user + day
                baseline = math.log(pre + 0.5) + 0.3
                effect = 0.2 if sent else 0
                outcome = max(0, math.exp(baseline + effect) - 0.5)
                rows.append(
                    {
                        "user.index": str(user),
                        "decision.index.nogap": str(index),
                        "avail": "True",
                        "send": str(sent),
                        "send.active": str(active),
                        "send.sedentary": str(sedentary),
                        "jbsteps30": str(outcome),
                        "jbsteps30.zero": str(outcome),
                        "jbsteps30pre.zero": str(pre),
                    }
                )
        rows.append(
            {
                "user.index": "0",
                "decision.index.nogap": "",
                "avail": "True",
                "send": "False",
                "send.active": "False",
                "send.sedentary": "False",
                "jbsteps30": "0",
                "jbsteps30.zero": "0",
                "jbsteps30pre.zero": "0",
            }
        )
        rows.append(
            {
                "user.index": "0",
                "decision.index.nogap": "211",
                "avail": "True",
                "send": "False",
                "send.active": "False",
                "send.sedentary": "False",
                "jbsteps30": "0",
                "jbsteps30.zero": "0",
                "jbsteps30pre.zero": "0",
            }
        )
        rows.append(
            {
                "user.index": "0",
                "decision.index.nogap": "10",
                "avail": "False",
                "send": "True",
                "send.active": "True",
                "send.sedentary": "False",
                "jbsteps30": "0",
                "jbsteps30.zero": "0",
                "jbsteps30pre.zero": "0",
            }
        )
        return rows

    def test_study_day_is_zero_based_five_decisions(self):
        self.assertEqual(hp.study_day_from_decision_index(0), 0)
        self.assertEqual(hp.study_day_from_decision_index(4), 0)
        self.assertEqual(hp.study_day_from_decision_index(5), 1)
        self.assertEqual(hp.study_day_from_decision_index(209), 41)

    def test_select_analysis_excludes_missing_beyond_and_anomaly(self):
        selected, available, audit = hp.select_analysis_rows(self.fixture())
        self.assertEqual(len(selected), 80)
        self.assertEqual(len(available), 80)
        self.assertEqual(audit["missing_nogap_index"], 1)
        self.assertEqual(audit["beyond_day_41"], 1)
        self.assertEqual(audit["unavailable_but_sent_anomaly"], 1)

    def test_descriptive_summary_is_not_causal(self):
        _, available, _ = hp.select_analysis_rows(self.fixture())
        result = hp.descriptive_summary(available)
        self.assertEqual(result["participants"], 4)
        self.assertEqual(result["decision_points"], 80)
        self.assertTrue(result["descriptive_only"])
        self.assertFalse(result["causal_effect_estimated"])

    def test_cluster_wls_recovers_constructed_positive_effect(self):
        _, available, _ = hp.select_analysis_rows(self.fixture())
        result = hp.fit_any_suggestion(available, with_time=False)
        self.assertGreater(result["ratio"], 1.1)
        self.assertLess(result["ratio"], 1.35)
        self.assertEqual(result["clusters"], 4)
        self.assertEqual(result["covariance"], "cluster_robust_small_sample")

    def test_walking_model_excludes_sedentary_and_has_positive_effect(self):
        _, available, _ = hp.select_analysis_rows(self.fixture())
        result = hp.fit_walking_suggestion(available, with_time=False)
        self.assertGreater(result["n"], 0)
        self.assertGreater(result["ratio"], 1.0)
        self.assertEqual(result["center_probability"], 0.5)

    def test_singular_design_rejected(self):
        with self.assertRaises(ValueError):
            hp.weighted_cluster_regression(
                [[1, 1], [1, 1]], [1, 1], ["a", "a"], [1, 1]
            )

    def test_report_never_serializes_participant_rows(self):
        selected, available, audit = hp.select_analysis_rows(self.fixture())
        report = hp.build_phase3_report(selected, available, audit)
        rendered = str(report)
        self.assertNotIn("'user.index'", rendered)
        self.assertFalse(report["privacy"]["participant_rows_in_report"])


if __name__ == "__main__":
    unittest.main()
