"""Explicit v2 Phase06 scope, protecting history and user-authorized no-facility path.

A retired external field trial is NOT a successful study; owned artifact P2
is NOT causal evidence that an individual suffers less.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs/roadmap/tasks.json"
ARCHIVE = ROOT / "docs/verification/PHASE06_V1_SCOPE_ARCHIVE_20261022.json"
SPEC = ROOT / "docs/specs/2026-10-22-phase06-owned-public-good-scope-amendment.md"


class RetiredLegacyScopeContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = json.loads(REGISTRY.read_text(encoding="utf8"))
        cls.by = {x["id"]: x for x in cls.tasks}
        cls.archive = json.loads(ARCHIVE.read_text(encoding="utf8"))
        cls.history = {x["id"]: x for x in cls.archive["rows"]}

    def test_original_registry_still_has_same_113_ids_and_archived_rows(self):
        self.assertEqual(len(self.tasks), 113)
        self.assertEqual(len(self.by), len(self.tasks))
        self.assertEqual(self.archive["task_registry_blob_sha"],
                         "4fc30e02e7ebb3226e3e199beb4d1a956c1c6123")
        self.assertEqual(set(self.history),
                         {"F004", "F005", "F006", "F007", "F008", "F009"})
        for row in self.archive["rows"]:
            self.assertIn(row["status"], {"todo","blocked"})
            self.assertTrue(row["change"] and row["verify"])

    def test_obsolete_finance_and_facility_gates_are_waived_not_done(self):
        for task_id in ("F004","F007"):
            with self.subTest(task_id=task_id):
                task=self.by[task_id]
                historical=self.history[task_id]
                self.assertEqual(task["status"], "skipped")
                self.assertEqual(task["scope_version"], 2)
                self.assertEqual(task["original_status"],"blocked")
                self.assertEqual(task["original_change"], historical["change"])
                self.assertEqual(task["original_verify"], historical["verify"])
                self.assertEqual(task["original_depends"], historical["depends"])
                self.assertEqual(task["original_external"], historical["external"])
                self.assertGreater(len(task["waiver_reason"]),35)
                self.assertEqual(task["waiver_scope"],"RETIRED_NOT_COMPLETED")
                self.assertEqual(task["external"],"none")

    def test_active_phase06_does_not_depend_on_retired_gates(self):
        waived={"F004","F007"}
        for t in self.tasks:
            if t["id"] in waived: continue
            with self.subTest(id=t["id"]):
                self.assertTrue(not waived.intersection(t["depends"]),
                                f"{t['id']} still depends on retired trial")
        for tid in ("F005","F006","F008","F009"):
            t=self.by[tid]
            self.assertEqual(t["scope_version"],2)
            self.assertIn(t["status"],("todo","done"))
            self.assertEqual(t["external"],"none")
            self.assertTrue(t["original_change"] and t["original_verify"])
            self.assertTrue(t["original_depends"])
            self.assertNotIn("屋内センサー",t["change"])
            self.assertNotIn("設備所有者",t["change"])
        self.assertIn("K009",self.by["F005"]["depends"])
        self.assertIn("K010",self.by["F008"]["depends"])

    def test_original_H005_scientific_waiver_is_untouched(self):
        self.assertEqual(self.by["H005"]["status"],"skipped")
        self.assertIn("H005 analysis-set reproduction waived", self.by["H005"]["waiver_scope"])

    def test_product_scope_distinguishes_public_delivery_from_human_outcome(self):
        text=SPEC.read_text(encoding="utf-8")
        self.assertIn("NOT_MEASURED",text)
        self.assertIn("P2",text)
        self.assertIn("owner",text.lower())
        self.assertIn("NO_ACTION",text)
        self.assertIn("waived",text.lower())
        self.assertIn("F004",text)
        self.assertIn("F007",text)


if __name__ == "__main__":
    unittest.main()
