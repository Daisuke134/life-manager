"""Contract checks for R005: simulation plausibility != causal fidelity."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "https://arxiv.org/html/2604.02458v1"


class R005EvidenceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = json.loads((ROOT / "docs/research/R005_CAUSAL_ERROR_EVIDENCE.json").read_text(encoding="utf-8"))

    def test_every_record_has_population_condition_outcome_metric_and_first_source(self):
        self.assertGreaterEqual(len(self.rows), 15)
        for row in self.rows:
            with self.subTest(row=row.get("id")):
                for key in ("id", "dataset", "n_people", "n_countries", "model", "condition", "outcome", "metric", "value", "unit", "source_url", "source_section"):
                    self.assertIn(key, row)
                self.assertGreater(row["n_people"], 0)
                self.assertEqual(row["source_url"], SOURCE)
                self.assertIsInstance(row["value"], (int, float))
                self.assertIn(row["metric"], {"mean_absolute_ate_error", "signed_ate_error"})
                self.assertEqual(row["unit"], "percentage_points")

    def test_published_baselines_are_not_mislabelled_predictions(self):
        base = {row["model"]: row["value"] for row in self.rows if row["condition"] == "baseline_all_interventions"}
        self.assertEqual(base, {"GPT-4o-mini": 9.5, "Gemini 2.5 Flash Lite": 8.8, "Claude 3 Haiku": 9.2, "linear regression": 4.3, "LASSO": 4.2})
        self.assertTrue(all(row["metric"] == "mean_absolute_ate_error" for row in self.rows if row["condition"] == "baseline_all_interventions"))

    def test_class_bias_and_prompt_failure_are_separate_metrics(self):
        by_id = {row["id"]: row for row in self.rows}
        self.assertEqual(by_id["situational-belief"]["value"], 10.05)
        self.assertEqual(by_id["norms-action"]["value"], 0.64)
        self.assertEqual(by_id["fewshot-claude-action"]["value"], 44.2)
        self.assertEqual(by_id["fewshot-claude-action"]["metric"], "mean_absolute_ate_error")
        self.assertNotEqual(by_id["situational-belief"]["metric"], by_id["fewshot-claude-action"]["metric"])

    def test_r005_does_not_claim_realworld_manager_impact(self):
        note = (ROOT / "docs/research/R005_LI_JI_JA.md").read_text(encoding="utf-8")
        for phrase in ("59,508", "62か国", "推定誤差", "因果忠実度", "未査読", "未実装", "公開情報", "原実験との差"):
            self.assertIn(phrase, note)
        self.assertIn("manager-independent", (ROOT / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
