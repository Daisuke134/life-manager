"""Cross-field research/source and editorial safety contracts (not causal validation).

Verify our synthesis preserves source boundaries and cannot silently turn
vendor metrics or historical work into a Manager field Blessing.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit
import unittest

ROOT=Path(__file__).resolve().parents[1]
MATRIX=ROOT/"docs/research/crossfield-20261021/SOURCES.json"
REPORT=ROOT/"docs/research/crossfield-20261021/REPORT_JA.md"
TINKER=ROOT/"docs/research/crossfield-20261021/TINKER_EXPERIMENT_DESIGN.md"
PILOT=ROOT/"docs/research/crossfield-20261021/PHASE06_FIELD_BLUEPRINT.md"
ARTICLE=ROOT/"docs/articles/manager-prediction-intervention-blessing-en.md"
BOOK=ROOT/"docs/books/MANAGER_RESEARCH_BOOK_OUTLINE.md"
WEB=ROOT/"docs/website/RESEARCH_JOURNAL_DESIGN.md"


class CrossFieldResearchContracts(unittest.TestCase):
    def test_source_matrix_first_party_urls_and_no_false_rights(self):
        records=json.loads(MATRIX.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(records),24)
        self.assertEqual(len({r["id"] for r in records}),len(records))
        self.assertGreaterEqual(len({r["field"] for r in records}),8)
        required={"id","name","field","url","source_kind","supported_claim","limitation","reuse","rights"}
        for row in records:
            with self.subTest(id=row.get("id")):
                self.assertEqual(set(row),required)
                self.assertTrue(urlsplit(row["url"]).scheme=="https")
                self.assertTrue(urlsplit(row["url"]).hostname)
                for key in required:
                    self.assertIsInstance(row[key],str)
                    self.assertTrue(row[key].strip())
                self.assertIn(row["rights"],{"REVIEW_BEFORE_USE","PUBLIC_DOC_ONLY","OPEN_SOURCE_CHECK_LICENSE"})
                self.assertNotIn("Manager has verified real welfare impact",row["supported_claim"])

    def test_article_and_book_avoid_unmeasured_beneficiary_claim(self):
        docs=[REPORT,TINKER,PILOT,ARTICLE,BOOK,WEB]
        for path in docs:
            with self.subTest(doc=path.name):
                text=path.read_text(encoding="utf-8")
                self.assertGreater(len(text),1500)
                self.assertIn("https://",text)
        self.assertIn("Simile",REPORT.read_text(encoding="utf-8"))
        self.assertIn("Aaru",REPORT.read_text(encoding="utf-8"))
        self.assertIn("GoodDollar",REPORT.read_text(encoding="utf-8"))
        self.assertIn("Polymarket",REPORT.read_text(encoding="utf-8"))
        self.assertIn("Tinker",TINKER.read_text(encoding="utf-8"))
        self.assertIn("TRL",TINKER.read_text(encoding="utf-8"))
        pilot=PILOT.read_text(encoding="utf-8")
        for task in ("F004","F005","F006","F007","F008","F009"):
            self.assertIn(task,pilot)
        for required in ("NO_ACTION","NOT_MEASURED","P0","P4"):
            self.assertIn(required,pilot)
        article=ARTICLE.read_text(encoding="utf-8")
        self.assertIn("Why Prediction Is Not Intervention",article)
        self.assertIn("What we cannot claim",article)
        self.assertIn("No verified Manager-caused welfare improvement",article)
        self.assertIn("Methods",article)
        self.assertIn("References",article)
        self.assertIn("No production deployment",WEB.read_text(encoding="utf-8"))

    def test_canonical_registry_unchanged_and_grants_not_faked(self):
        tasks=json.loads((ROOT/"docs/roadmap/tasks.json").read_text(encoding="utf-8"))
        by_id={t["id"]:t for t in tasks}
        self.assertEqual(len(tasks),113)
        self.assertEqual(by_id["H005"]["status"],"skipped")
        self.assertEqual(by_id["F004"]["status"],"blocked")
        self.assertEqual(by_id["F007"]["status"],"blocked")
        self.assertEqual(by_id["F005"]["status"],"todo")
        self.assertEqual(by_id["F008"]["status"],"todo")


    def test_reuse_only_welfare_and_internet_first_sources(self):
        entries=json.loads(MATRIX.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(entries),60)
        ids={e["id"] for e in entries}
        for identifier in (
            "who-five","who-whodas","cfpb-financial-wellbeing",
            "oecd-subjective-wellbeing-2025","fao-food-insecurity-fies",
            "worldbank-poverty-platform","inspect-ai-evals",
            "openai-mentalhealthbench","nice-digital-health-evidence",
            "spirit-consort-2025","growthbook-experiments",
            "planout-internet-experiments","digital-public-goods-standard",
            "who-step-by-step","x402-protocol","axe-core-accessibility",
        ):
            self.assertIn(identifier,ids)
        families={e["field"] for e in entries}
        for name in ("mental_welfare_measure","physical_welfare_measure",
                     "financial_welfare_measure","online_experimentation",
                     "digital_public_goods","agent_evaluation","world_indicator"):
            self.assertIn(name,families)
        docs=[
            ROOT/"docs/MANAGER_NO_HUMAN_WORLD_ENGINEERING.md",REPORT,
            ROOT/"docs/roadmap/PHASE06_TO_COMPLETION_RESEARCH_JA.md",
            ROOT/"pilot/PHASE06_BLOCKER_REMOVAL_RUNBOOK.md",
            ROOT/"docs/MANAGER_PRODUCT_SPEC.md",
        ]
        for path in docs:
            contents=path.read_text(encoding="utf-8")
            self.assertIn("Reuse → Connect → Evaluate",contents)
            self.assertIn("NO_ACTION",contents)
        self.assertIn("Internet is a real-world environment",docs[0].read_text(encoding="utf-8"))
        self.assertIn("MENTAL",REPORT.read_text(encoding="utf-8"))
        self.assertIn("PHYSICAL",REPORT.read_text(encoding="utf-8"))
        self.assertIn("FINANCIAL",REPORT.read_text(encoding="utf-8"))
        self.assertIn("GrowthBook",docs[2].read_text(encoding="utf-8"))
        self.assertIn("F004",docs[3].read_text(encoding="utf-8"))
        self.assertIn("F007",docs[3].read_text(encoding="utf-8"))
        self.assertIn("no per-run human approval",docs[4].read_text(encoding="utf-8"))
        self.assertIn("NOT_MEASURED",REPORT.read_text(encoding="utf-8"))

if __name__=="__main__":
    unittest.main()
