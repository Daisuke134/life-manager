"""Contract for primary-source benchmark atlas and reproducible upstream-code audit.

No paper score / vendor claim may be silently promoted to an independent
Manager EBA result. No data license is inferred from public access.
"""
import json
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ATLAS = ROOT / "docs/research/evals/EVAL_LANDSCAPE_20261022.json"
AUDIT = ROOT / "docs/research/evals/UPSTREAM_CODE_AUDIT_20261022.md"
ARTICLE = ROOT / "docs/research/publications/EBA_BENCHMARK_LANDSCAPE_PUBLIC_ARTICLE_20261022.md"
ROADMAP = ROOT / "docs/roadmap/EBA_TO_FIELD_COMPLETION_ATOMIC.md"


class BenchmarkAtlasContracts(unittest.TestCase):
    def test_at_least_sixty_unique_primary_source_records(self):
        rows = json.loads(ATLAS.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(rows), 60)
        self.assertEqual(len({x["id"] for x in rows}),len(rows))
        categories = {r["family"] for r in rows}
        self.assertGreaterEqual(len(categories), 10)
        required = {"id","name","family","kind","url","original_reuse",
                    "metric","measures","does_not_prove","rights","inspection"}
        allowed_kind = {"benchmark","evaluation_harness","field_study",
                        "outcome_instrument","simulation_platform","dataset"}
        for r in rows:
            with self.subTest(id=r.get("id")):
                self.assertEqual(set(r),required)
                self.assertIn(r["kind"],allowed_kind)
                self.assertTrue(r["url"].startswith("https://"))
                self.assertIn(r["rights"],{"UPSTREAM_LICENSE_CHECK","PUBLIC_METHOD_ONLY",
                                           "DATA_RIGHTS_REVIEW_REQUIRED"})
                self.assertIn(r["inspection"],{"UPSTREAM_CODE_READ","DOCS_REVIEWED","PAPER_METHOD"})
                for key in required:
                    self.assertTrue(isinstance(r[key],str) and r[key].strip())

    def test_no_confusion_between_capability_and_welfare(self):
        rows=json.loads(ATLAS.read_text(encoding="utf-8"))
        for r in rows:
            if r["family"] not in {"welfare_outcome","field_causal_evidence"}:
                self.assertNotEqual(r["metric"],"verified beneficiary welfare")
            self.assertNotIn("Manager achieved verified human welfare",r["measures"])
        self.assertTrue(any(r["family"]=="behavior_simulation" for r in rows))
        self.assertTrue(any(r["family"]=="agent_security" for r in rows))
        self.assertTrue(any(r["family"]=="judge_quality" for r in rows))
        self.assertTrue(any(r["family"]=="real_world_agent" for r in rows))

    def test_code_audit_links_actual_upstream_paths_and_observations(self):
        s=AUDIT.read_text(encoding="utf-8")
        for name in ("Inspect AI","SWE-bench","AgentDojo","JudgeBench",
                     "Browser Use","WebArena","Open Bandit Pipeline"):
            self.assertIn(name,s)
        self.assertGreaterEqual(s.count("https://github.com/"),9)
        self.assertIn("Code was fetched",s)
        self.assertIn("not cloned locally",s)

    def test_public_article_and_full_completion_roadmap_exist(self):
        article=ARTICLE.read_text(encoding="utf-8")
        plan=ROADMAP.read_text(encoding="utf-8")
        for keyword in ("Evaluation vs Benchmark","Anthropic","Hamel Husain",
                        "OmniBehavior","SWE-bench","AgentDojo","CausalBench",
                        "WHO-5","EBA","negative results"):
            self.assertIn(keyword,article)
        for keyword in ("F004","F005","F006","F007","F008","F009",
                        "U002","V002","V006","Y008","G006","C002",
                        "P3","P4","NOT_MEASURED","DoWhy","Inspect AI"):
            self.assertIn(keyword,plan)
        t=json.loads((ROOT/"docs/roadmap/tasks.json").read_text(encoding="utf-8"))
        self.assertEqual(len(t),113)
        self.assertEqual({x["id"]:x["status"] for x in t}["F004"],"blocked")
        self.assertEqual({x["id"]:x["status"] for x in t}["F007"],"blocked")


if __name__ == "__main__":
    unittest.main()
