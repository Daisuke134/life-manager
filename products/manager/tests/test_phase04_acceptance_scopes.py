"""Phase04 acceptance receipts: engineering success must NOT imply human or causal evidence."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class Phase04HonestAcceptance(unittest.TestCase):
    def tasks(self):
        return {row["id"]: row for row in json.loads(
            (ROOT / "docs/roadmap/tasks.json").read_text(encoding="utf-8"))}

    def test_waived_phase03_and_soc_sci_data_hold_are_unchanged(self):
        t = self.tasks()
        self.assertEqual(t["H005"]["status"], "skipped")
        self.assertEqual(t["S002"]["status"], "blocked")
        rights = json.loads((ROOT / "docs/research/source-rights.json").read_text())
        by_id = {x["id"]: x for x in rights["sources"]}
        self.assertEqual(by_id["socsci210-data"]["permissions"]["local_research"], "hold")
        self.assertEqual(by_id["socsci210-data"]["permissions"]["raw_redistribution"], "hold")

    def test_independent_method_and_simulation_tasks_have_narrow_evidence_gates(self):
        t = self.tasks()
        for name in ("S006", "S007", "S008"):
            row = t[name]
            self.assertEqual(row["status"], "done")
            self.assertTrue(row.get("original_change"))
            self.assertTrue(row.get("original_verify"))
            self.assertTrue(row.get("scope_override"))
            self.assertTrue(row.get("verification_scope"))
            self.assertIn("github.com/Daisuke134/life-manager/actions/runs/", row["evidence_run"])
            self.assertFalse(row.get("human_effect_verified", False))
        self.assertIn("R005", t["S006"]["depends"])
        self.assertIn("S003", t["S007"]["depends"])
        self.assertEqual(t["S008"]["depends"], ["S007"])
        self.assertEqual(t["S004"]["status"], "todo")
        self.assertEqual(t["S005"]["status"], "todo")

    def test_reports_cannot_claim_mobility_predictive_fit_is_causal_benefit(self):
        doc = (ROOT / "docs/research/public_aggregate/PHASE04_UCI_BIKESHARE_EMPIRICAL_JA.md").read_text()
        social = (ROOT / "docs/verification/S007_CONCORDIA_TECHNICAL_JA.md").read_text()
        for required in (
            "[-50.30, 391.18]", "57,569 bytes", "BYTE_IDENTICAL",
            "SocSci210", "未実施", "未測定", "39545601251",
        ):
            self.assertIn(required, doc)
        self.assertIn("39545009858", social)
        self.assertIn("Modality Parsing JSON Error", social)
        self.assertIn("現実世界", social)
        self.assertIn("実測", doc)
        self.assertNotIn("Managerが苦しみを減らしたことを証明", doc)
        self.assertNotIn('human_behavior_fidelity_score": 1', social)


if __name__ == "__main__":
    unittest.main()
