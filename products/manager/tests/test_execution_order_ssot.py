"""Single Manager task-status authority + one executable E01-E16 order.

The original 113 task IDs remain intact. E01–E16 are implementation steps,
not independent field-effect tasks, and F005–F009 are acceptance gates.
"""
import json
import re
import unittest
from copy import deepcopy
from pathlib import Path
from scripts import make_roadmap

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
        # The cursor is the next unfinished E task. Only a tested contiguous
        # prefix of the immutable E order may be recorded as completed.
        completed = t["technical_execution_completed"]
        self.assertGreaterEqual(len(completed), 2)
        self.assertEqual(completed, EXPECTED[:len(completed)])
        self.assertLess(len(completed), len(EXPECTED))
        self.assertEqual(t["technical_execution_cursor"], EXPECTED[len(completed)])
        for stage in completed:
            self.assertIn(stage, t["technical_execution_receipts"])
            receipt = t["technical_execution_receipts"][stage]
            self.assertGreater(receipt["run_id"], 0)
            self.assertEqual(receipt["status"], "PASSED")
            self.assertGreaterEqual(receipt["full_suite_total"], 504 if stage == "E01" else 512)
        e01 = t["technical_execution_receipts"]["E01"]
        self.assertEqual(e01["run_id"], 39727976132)
        self.assertEqual(e01["raw_sha256"], "c46503170d9fc337137d6283fb6d38821a29149f72609f751a79366103f70585")
        self.assertEqual(e01["result"], "VERIFIED_P0_NO_HUMAN_OUTCOME")
        self.assertEqual(t["technical_execution_receipts"]["E02"]["run_id"], 39728515676)
        self.assertEqual(t["acceptance_sequence"],GATES)
        self.assertEqual(t["technical_execution_plan"],str(PLAN.relative_to(ROOT)))
        self.assertEqual(self.lookup["F004"]["status"],"skipped")
        self.assertEqual(self.lookup["F007"]["status"],"skipped")
        self.assertTrue(all(self.lookup[x]["status"]=="todo" for x in GATES))

    def _execution_fixture(self, completed, cursor):
        tasks = deepcopy(self.tasks)
        f009 = next(task for task in tasks if task["id"] == "F009")
        f009["technical_execution_completed"] = completed
        f009["technical_execution_cursor"] = cursor
        if "E16" in completed:
            # Fixture only: this synthetic receipt proves the terminal schema,
            # never the real E16 acceptance or canonical task-state completion.
            receipt = deepcopy(f009["technical_execution_receipts"]["E15"])
            receipt.update(run_id=99999999999, status="PASSED", full_suite_total=512)
            f009["technical_execution_receipts"]["E16"] = receipt
        return tasks

    def test_terminal_execution_cursor_requires_all_sixteen_receipts_and_renders_separately_from_F(self):
        tasks = self._execution_fixture(EXPECTED, None)
        make_roadmap.validate(tasks)

        rendered = make_roadmap.render(tasks)
        self.assertIn("E01–E16実装完了。F受入は別に証拠確認", rendered)
        self.assertNotIn("現在の次タスク:** `None`", rendered)
        self.assertIn("Total: 113 · Done: 69 · Todo: 41 · Blocked: 0 · Skipped: 3", rendered)

    def test_execution_cursor_rejects_missing_nonterminal_and_invalid_terminal_values(self):
        invalid = [
            (EXPECTED[:15], None),
            (EXPECTED, "E16"),
            (EXPECTED[:14] + ["E16"], None),
            (EXPECTED[:4] + ["E04"], "E06"),
            (["E02", "E01"], "E03"),
            (EXPECTED[:15], ""),
            (EXPECTED[:15], "DONE"),
            (EXPECTED[:15], "F005"),
        ]
        for completed, cursor in invalid:
            with self.subTest(completed=completed, cursor=cursor):
                with self.assertRaises(ValueError):
                    make_roadmap.validate(self._execution_fixture(completed, cursor))

        for completed, cursor in ((EXPECTED[:15], "E16"), (EXPECTED, None)):
            missing_cursor = self._execution_fixture(completed, cursor)
            next(task for task in missing_cursor if task["id"] == "F009").pop("technical_execution_cursor")
            with self.subTest(missing_cursor_after=len(completed)):
                with self.assertRaises(ValueError):
                    make_roadmap.validate(missing_cursor)

    def test_completed_execution_prefix_requires_passed_run_receipts_and_full_suite_floor(self):
        invalid_mutations = (
            lambda task: task["technical_execution_receipts"].pop("E15"),
            lambda task: task["technical_execution_receipts"]["E15"].update(status="BLOCKED"),
            lambda task: task["technical_execution_receipts"]["E15"].update(run_id=0),
            lambda task: task["technical_execution_receipts"]["E15"].update(full_suite_total=511),
        )
        for mutate in invalid_mutations:
            tasks = self._execution_fixture(EXPECTED[:15], "E16")
            f009 = next(task for task in tasks if task["id"] == "F009")
            mutate(f009)
            with self.subTest(mutation=mutate):
                with self.assertRaises(ValueError):
                    make_roadmap.validate(tasks)

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
