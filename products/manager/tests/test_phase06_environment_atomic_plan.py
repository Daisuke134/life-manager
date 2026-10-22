"""Phase06 scoped atomic task breakdown must map to ONE canonical 113-task SSOT.

This is a contract for an implementation plan, not empirical field evidence.
"""
import json
import re
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
ROADMAP=ROOT/"docs/roadmap/PHASE06_TO_COMPLETION_RESEARCH_JA.md"
SOURCES=ROOT/"docs/research/crossfield-20261021/SOURCES.json"


class AtomicStructuralInterventionPlanContracts(unittest.TestCase):
    def test_all_six_remaining_F_tasks_have_nine_concrete_implementation_steps(self):
        text=ROADMAP.read_text(encoding="utf-8")
        self.assertIn("Phase06 — Environment-First Atomic Execution Plan",text)
        self.assertIn("Reuse → Connect → Evaluate → Improve",text)
        self.assertIn("not a second SSOT",text)
        for group in ("F004","F005","F006","F007","F008","F009"):
            for i in range(1,10):
                token=f"`{group}.E{i:02d}`"
                with self.subTest(task=token):
                    self.assertEqual(text.count(token),1)
                    line=next(line for line in text.splitlines() if token in line)
                    self.assertTrue(line.startswith("|"))
                    self.assertGreaterEqual(line.count("|"),6)
                    self.assertIn("`",line)
        self.assertIn("54 concrete substeps",text)

    def test_environment_not_money_minting_and_rcts_not_faked(self):
        text=ROADMAP.read_text(encoding="utf-8")
        for term in ("GetCalFresh","J-PAL","GOV.UK","GrowthBook",
                     "Playwright","axe-core","DoWhy","NO_ACTION",
                     "NOT_MEASURED","P2_ARTIFACT_ONLY","FRICTION",
                     "STANDING_AUTHORITY","RCT", "counterfactual",
                     "negative or null", "human welfare"):
            with self.subTest(term=term): self.assertIn(term,text)
        self.assertIn("scope amendment proposal",text)
        self.assertIn("F007",text)
        self.assertIn("F004",text)

    def test_source_registry_uses_existing_real_world_precedents(self):
        rows=json.loads(SOURCES.read_text(encoding="utf-8"))
        by={r["id"]:r for r in rows}
        for sid in ("cfa-getcalfresh-environment",
                    "jpal-snap-enrollment-rct",
                    "gds-end-to-end-environment",
                    "gds-real-completion-rate",
                    "w3c-wcag22"):
            with self.subTest(source_id=sid):
                self.assertIn(sid,by)
                self.assertTrue(by[sid]["url"].startswith("https://"))
                self.assertIn(by[sid]["rights"],{
                    "PUBLIC_DOC_ONLY","OPEN_SOURCE_CHECK_LICENSE","REVIEW_BEFORE_USE"})
        self.assertEqual(len(rows),87)

    def test_one_canonical_registry_preserves_original_field_acceptance(self):
        tasks=json.loads((ROOT/"docs/roadmap/tasks.json").read_text(encoding="utf-8"))
        by={t["id"]:t for t in tasks}
        self.assertEqual(len(by),113)
        self.assertEqual(by["F004"]["status"],"skipped")
        self.assertEqual(by["F007"]["status"],"skipped")
        self.assertEqual(by["F005"]["status"],"todo")
        self.assertEqual(by["F006"]["status"],"todo")
        self.assertEqual(by["F008"]["status"],"todo")
        self.assertEqual(by["F009"]["status"],"todo")
        self.assertEqual(by["H005"]["status"],"skipped")


if __name__=="__main__":
    unittest.main()
