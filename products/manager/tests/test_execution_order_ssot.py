"""Single Manager task-status authority + one executable E01-E16 order.

The original 113 task IDs remain intact. E01–E16 are implementation steps,
not independent field-effect tasks, and F005–F009 are acceptance gates.
"""
import json
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BACKLOG=ROOT/"docs/roadmap/ATOMIC_BACKLOG.md"
PLAN=ROOT/"docs/plans/2026-10-22-manager-core-execution-plan.md"
TASKS=ROOT/"docs/roadmap/tasks.json"
SPEC=ROOT/"docs/MANAGER_PRODUCT_SPEC.md"
README=ROOT/"README.md"
SCOPE_PLAN=ROOT/"docs/plans/2026-10-22-phase06-owned-digital-completion.md"
HISTORIC_MAP=ROOT/"docs/roadmap/PHASE06_TO_COMPLETION_RESEARCH_JA.md"

EXPECTED=[f"E{i:02d}" for i in range(1,17)]
GATES=["F005","F006","F008","F009"]


class ExecutionOrderContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks=json.loads(TASKS.read_text(encoding="utf-8"))
        cls.lookup={t["id"]:t for t in cls.tasks}

    def test_one_registry_has_explicit_next_cursor_and_order(self):
        t=self.lookup["F009"]
        self.assertEqual(len(self.tasks),113)
        self.assertEqual(len(self.lookup),113)
        self.assertEqual(t["technical_execution_sequence"],EXPECTED)
        # E01 must be completed before the next task becomes E02.
        self.assertEqual(t["technical_execution_cursor"], "E02")
        self.assertEqual(t["technical_execution_completed"], ["E01"])
        r = t["technical_execution_receipts"]["E01"]
        self.assertEqual(r["run_id"], 39727976132)
        self.assertEqual(r["raw_sha256"], "c46503170d9fc337137d6283fb6d38821a29149f72609f751a79366103f70585")
        self.assertEqual(r["result"], "VERIFIED_P0_NO_HUMAN_OUTCOME")
        self.assertEqual(t["acceptance_sequence"],GATES)
        self.assertEqual(t["technical_execution_plan"],str(PLAN.relative_to(ROOT)))
        self.assertEqual(self.lookup["F004"]["status"],"skipped")
        self.assertEqual(self.lookup["F007"]["status"],"skipped")
        self.assertTrue(all(self.lookup[x]["status"]=="todo" for x in GATES))

    def test_superpowers_plan_declares_all_E_steps_once_in_order(self):
        source=PLAN.read_text(encoding="utf-8")
        headings=re.findall(r"^## (E\d{2})\b",source,re.MULTILINE)
        self.assertEqual(headings,EXPECTED)
        self.assertIn("E01",source)
        self.assertIn("E16",source)
        self.assertIn("F005",source)
        self.assertIn("not the executable task order",source)
        self.assertIn("E01",source.split("F005",1)[0])

    def test_generated_backlog_starts_with_E_not_F(self):
        doc=BACKLOG.read_text(encoding="utf-8")
        self.assertIn("唯一の実装順",doc)
        before_rows=doc.split("## 00.",1)[0]
        self.assertIn("E01",before_rows)
        self.assertIn("E16",before_rows)
        self.assertIn("F005",before_rows)
        self.assertLess(before_rows.find("E01"), before_rows.find("F005"))
        self.assertIn("SSOT",before_rows)

    def test_active_spec_and_readme_agree(self):
        for doc in (SPEC,README):
            with self.subTest(doc=doc.name):
                head=doc.read_text(encoding="utf-8")[:2300]
                self.assertIn("E01",head)
                self.assertIn("E16",head)
                self.assertIn("F005",head)
                self.assertIn("F004",head)
                self.assertIn("F007",head)
                self.assertIn("tasks.json",head)

    def test_obsolete_F_detail_plan_cannot_override_order(self):
        for doc in (SCOPE_PLAN,HISTORIC_MAP):
            with self.subTest(doc=doc.name):
                head=doc.read_text(encoding="utf-8")[:1800]
                self.assertIn("E01",head)
                self.assertIn("E16",head)
                self.assertIn("歴史的",head)
                self.assertIn("実装順",head)


if __name__=="__main__":
    unittest.main()
