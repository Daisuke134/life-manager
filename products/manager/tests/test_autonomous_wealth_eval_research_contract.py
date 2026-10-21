"""Ensure economic autonomy editorial/research claims never become fake field receipts."""
import json
from pathlib import Path
import unittest

DOCS = Path(__file__).resolve().parents[1] / "docs"

class WealthEvalResearchContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources=json.loads((DOCS/"research/autonomous_wealth_eval/PRIMARY_SOURCES_2026-10-21.json").read_text(encoding="utf-8"))
        cls.article=(DOCS/"articles/manager-autonomous-agent-money-is-not-wealth-en.md").read_text(encoding="utf-8")
        cls.protocol=(DOCS/"research/autonomous_wealth_eval/WEALTH_BLESSING_EVAL_PROTOCOL.md").read_text(encoding="utf-8")
        cls.landscape=json.loads((DOCS/"landscape/2026-10-20-behavior-intervention-entities.json").read_text(encoding="utf-8"))

    def test_source_registry_attributed_with_noninterchangeable_proof_categories(self):
        d=self.sources
        self.assertEqual(d["source_count"],len(d["sources"]))
        self.assertGreaterEqual(len(d["sources"]),25)
        ids=[x["id"] for x in d["sources"]]
        self.assertEqual(len(ids),len(set(ids)))
        for entry in d["sources"]:
            self.assertTrue(entry["actually_measures"] and entry["cannot_establish"])
            self.assertTrue(entry["source_url"].startswith(("https://","internal:")))
            self.assertTrue(entry["manager_reuse_decision"])
        self.assertIn("eitc-reminder-null-2022",ids)
        self.assertIn("eitc-reminder-2015",ids)

    def test_andon_in_company_map_without_repeating_radiant(self):
        organizations=[o["entity_name"] for g in self.landscape["clusters"] for o in g["organizations"]]
        self.assertEqual(len(organizations),30)
        self.assertEqual(len(set(organizations)),30)
        self.assertEqual(organizations.count("Andon Labs"),1)
        self.assertEqual(organizations.count("Artificial Societies"),1)

    def test_article_has_both_positive_and_null_field_experiments(self):
        for item in ("andonlabs.com/evals/vending-bench-2","openai.com/index/swe-lancer",
                     "10.1257/aer.20121493","10.1257/pol.20200603",
                     "No", "control", "NOT MEASURED"):
            self.assertIn(item,self.article)
        self.assertGreaterEqual(len(self.article.split()),4000)
        self.assertNotIn("Daisuke134",self.article)
        self.assertNotIn("/Users/",self.article)

    def test_only_reuse_schema_and_do_not_announce_a_wealth_blessing(self):
        for word in ("UNKNOWN_COST","NO_ACTION","ABSTAIN","LM-EAB","independent"):
            self.assertIn(word,self.protocol)
        for phrase in ("NO Manager-sourced field interventions","NOT_MEASURED","read-only"):
            self.assertIn(phrase,self.protocol)
        self.assertNotIn("CONCLUDED_P4_WELFARE_BENEFIT",self.protocol)

if __name__ == "__main__":
    unittest.main()
