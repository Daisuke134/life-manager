"""2026-10-21 research communication contract: provenance and scientific boundaries."""
from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"


class RadiantCommunicationContract(unittest.TestCase):
    def test_radiant_updates_existing_company_not_duplicate(self):
        m = json.loads((DOCS / "landscape/2026-10-20-behavior-intervention-entities.json").read_text())
        orgs = [o for group in m["clusters"] for o in group["organizations"]]
        self.assertEqual(len(orgs), 30)
        self.assertEqual(len(m["clusters"]), 7)
        self.assertEqual(len({o["entity_name"] for o in orgs}), 30)
        autonomy = next(g for g in m["clusters"] if g["category"] == "Autonomous business & economic evaluation")
        self.assertEqual({o["entity_name"] for o in autonomy["organizations"]},
                         {"Andon Labs", "Anthropic", "OpenAI", "METR"})
        andon = next(o for o in orgs if o["entity_name"] == "Andon Labs")
        self.assertIn("andonlabs.com/evals/vending-bench-2", andon["official_source"])
        self.assertIn("Simulated", andon["evidence_status"])
        self.assertEqual(len([o for o in orgs if o["entity_name"] == "Artificial Societies"]), 1)
        company = next(o for o in orgs if o["entity_name"] == "Artificial Societies")
        self.assertEqual(company["product"], "Radiant")
        self.assertEqual(company["official_source"], "https://societies.ai/radiant")
        self.assertIn("Vendor-reported", company["evidence_status"])

    def test_deep_dive_distinguishes_internal_metrics_and_peer_reviewed_group_result(self):
        p = (DOCS / "research/societies/RADIANT_2026-10-21_JA.md").read_text()
        for phrase in ("2609.30030", "2609.27690", "33,299", "68,280", "0.08", "0.31", "TVD", "自己申告", "未実証"):
            self.assertIn(phrase, p)
        self.assertIn("doi.org/10.1111/bjop.12764", p)
        self.assertIn("20–3,500", p)
        self.assertIn("12–3,500", p)

    def test_lab_deck_manifest_has_sources_and_no_false_human_causal_claim(self):
        p = (DOCS / "presentations/BEHAVIOR_SIMULATION_LAB_DECK_V2_2026-10-21.md").read_text()
        self.assertIn("44-slide", p)
        self.assertIn("PPTX", p)
        self.assertIn("arxiv.org/html/2609.30030", p)
        self.assertIn("independently", p)
        self.assertIn("unverified", p.lower())
        self.assertIn("ec4e3a0f5b6e02833af69e01a3143c92d2ab57af1bed28a9face09c7c920e7e1", p)

    def test_newsletter_readers_can_distinguish_event_date_and_publication(self):
        charter = (DOCS / "newsletter/NEWSLETTER_PRODUCT_CHARTER.md").read_text()
        issue = (DOCS / "newsletter/2026-10-21-launch-issue.md").read_text()
        self.assertIn("Launch issue", issue)
        self.assertIn("not a claim that every item was published today", issue)
        self.assertIn("not posted", issue)
        self.assertIn("October 1", issue)
        self.assertIn("company", charter.lower())
        self.assertIn("No invented", charter)
        self.assertIn("X/social publication is DISABLED", charter)
        self.assertIn("book", charter.lower())

    def test_public_article_does_not_claim_radiant_caused_real_world_welfare(self):
        p = (DOCS / "articles/manager-radiant-societies-field-guide-en.md").read_text()
        for url in ("https://societies.ai/radiant", "https://societies.ai/eval",
                    "https://societies.ai/as-benchmark",
                    "https://arxiv.org/html/2609.30030"):
            self.assertIn(url, p)
        self.assertIn("has not demonstrated independently verified net improvements", p)
        self.assertIn("company-published results", p)
        self.assertIn("not", p.lower())


if __name__ == "__main__":
    unittest.main()
