import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).parents[1]
sys.path.insert(0, str(SKILL / "scripts"))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SKILL / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CAPTURE = load("affiliate_source_capture_demand", "source_capture.py")
COMPOSE = load("affiliate_composition_owner_demand", "composition_owner.py")
FIXTURE = (SKILL / "tests" / "fixtures" / "elevenlabs-pricing-excerpt.md").read_text()
DAY = 86400


def skill_root(directory):
    root = Path(directory) / "skill"
    (root / "config" / "source-plans").mkdir(parents=True)
    shutil.copy(SKILL / "config" / "demand-pages.json", root / "config" / "demand-pages.json")
    return root


class DemandPageConfigTest(unittest.TestCase):
    def test_config_pages_are_publishable_and_cite_only_official_pages(self):
        pages = CAPTURE.demand_pages(SKILL)
        types = {page["page_type"] for page in pages}
        self.assertTrue({"pricing", "is-free", "alternatives", "versus",
                         "best-ai-voice-generator", "how-to"} <= types)
        self.assertEqual(len({page["slug"] for page in pages}), len(pages))
        for page in pages:
            plan = CAPTURE.demand_plan(page)
            self.assertIn("before paying", plan["buyer_intent"])
            self.assertLessEqual(len(f"{plan['plan_id']}-1"), 80)
            first = plan["sources"][0]["url"]
            # The CTA destination is the first cited elevenlabs.io source; pricing
            # and docs citations must stay direct links (#8278).
            self.assertTrue(first.startswith("https://elevenlabs.io/"))
            self.assertNotIn("/pricing", first)
            self.assertNotIn("/docs", first)
            for source in plan["sources"]:
                if not source["url"].startswith("https://elevenlabs.io/"):
                    self.assertEqual(source["evidence_class"], "competitor_official")
                self.assertNotIn("play.ht", source["url"])
            self.assertEqual(plan["pricing_table"], page["page_type"] in {"pricing", "is-free"})


class DemandPageDiscoveryTest(unittest.TestCase):
    def test_demand_pages_open_one_per_day_before_sitemap_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = skill_root(directory)
            state = Path(directory) / "state"
            with mock.patch.object(CAPTURE, "run_adapter", side_effect=AssertionError("sitemap")):
                first = CAPTURE.discover_official_plan(root, state, 10 * DAY)
                same_day = CAPTURE.discover_official_plan(root, state, 10 * DAY + 60)
                next_day = CAPTURE.discover_official_plan(root, state, 11 * DAY)
            self.assertEqual(first["discovery_mode"], "DEMAND_PAGE")
            self.assertEqual(first["plan_id"], "elevenlabs-demand-pricing-en")
            self.assertEqual(same_day["state"], "COOLDOWN")
            self.assertEqual(next_day["plan_id"], "elevenlabs-demand-best-voice-en")
            plan = CAPTURE.load_plan(root, "elevenlabs-demand-pricing-en", state)
            self.assertEqual(plan["page_type"], "pricing")
            self.assertTrue(plan["pricing_table"])
            bundle = CAPTURE.write_composition_bundle(state, plan, [{
                "source_id": plan["sources"][0]["id"], "locator": plan["sources"][0]["url"],
                "evidence_class": "official_product", "raw_sha256": "a" * 64,
            }])
            self.assertEqual(bundle["page_brief"], plan["page_brief"])
            self.assertTrue(bundle["pricing_table"])


class PricingTableTest(unittest.TestCase):
    def test_table_is_built_from_the_official_pricing_page(self):
        table = COMPOSE.pricing_table(FIXTURE)
        self.assertIn("| Starter | $6 | 30,000 | $5 |", table)
        self.assertIn("| Creator | $22 | 121,000 | $18.33 | $11 for the first month |", table)
        self.assertIn("| Business | $990 | 6,000,000 | $825 | 10 seats |", table)
        self.assertIn("| Enterprise | Custom |", table)
        self.assertIn("(https://elevenlabs.io/pricing)", table)

    def test_unparseable_pricing_page_fails_closed(self):
        with self.assertRaises(COMPOSE.CompositionError):
            COMPOSE.pricing_table("# Pricing\nContact sales.")


def write_source(state, source_id, locator, text, evidence_class="official_product"):
    digest = hashlib.sha256(text.encode()).hexdigest()
    directory = state / "sources" / source_id
    directory.mkdir(parents=True)
    (directory / f"{digest}.md").write_text(text)
    return {"source_id": source_id, "locator": locator,
            "evidence_class": evidence_class, "raw_sha256": digest}


class PricingPageDryRunTest(unittest.TestCase):
    def test_pricing_page_renders_from_fixture_with_tracked_cta_and_direct_citations(self):
        from owned_publish import ATTRIBUTION, merchant_free_description, render_affiliate_markdown

        with tempfile.TemporaryDirectory() as directory:
            root = skill_root(directory)
            state = Path(directory) / "state"
            with mock.patch.object(CAPTURE, "run_adapter", side_effect=AssertionError("sitemap")):
                CAPTURE.discover_official_plan(root, state, 10 * DAY)
            plan = CAPTURE.load_plan(root, "elevenlabs-demand-pricing-en", state)
            tts, pricing = plan["sources"][:2]
            rows = [
                write_source(state, tts["id"], tts["url"], "Text to speech product page."),
                write_source(state, pricing["id"], pricing["url"], FIXTURE, "official_price"),
            ]
            bundle = CAPTURE.write_composition_bundle(state, plan, rows)
            prompt = COMPOSE.prompt_for(state, bundle)
            self.assertIn("Pricing explainer", prompt)
            self.assertIn("{{PRICING_TABLE}}", prompt)
            self.assertNotIn("workflow tutorial", prompt)

            markdown = (
                "# ElevenLabs Pricing Explained\n\n"
                "Plans run from a free tier to custom enterprise pricing, and every "
                "plan draws from one monthly credit pool.\n\n"
                f"{COMPOSE.DISCLOSURE}\n\n"
                "[Try the ElevenLabs text to speech tool]({{AFFILIATE_LINK}})\n\n"
                "## The plans\n\n{{PRICING_TABLE}}\n\n"
                "## Which plan fits whom\n\n"
                "The [text to speech product](https://elevenlabs.io/text-to-speech) is on "
                "every plan; the [pricing page](https://elevenlabs.io/pricing) lists the "
                "commercial license from Starter upward. " + "Detail. " * 80
            )
            evidence = state / "composition-runs" / "run"
            evidence.mkdir(parents=True)
            (evidence / "result.json").write_text(json.dumps({
                "title": "ElevenLabs Pricing Explained", "markdown": markdown,
            }))
            (evidence / "summary.json").write_text(json.dumps({
                "result_path": str(evidence / "result.json"),
            }))
            with mock.patch.object(COMPOSE, "_ready_from_seal", return_value={"result_sha256": "b" * 64}):
                COMPOSE.build_handoff(root, state, bundle, {"evidence_dir": str(evidence)})
            handoff = json.loads((state / "campaign-handoffs" / f"{plan['plan_id']}.json").read_text())
            body = handoff["owned_article_markdown"]
            self.assertNotIn("{{PRICING_TABLE}}", body)
            self.assertIn("| Pro | $99 | 600,000 | $82.50 |", body)
            self.assertEqual(handoff["cited_sources"][0]["locator"], tts["url"])

            link = "https://try.elevenlabs.io/demo-placement"
            page = render_affiliate_markdown(
                body.replace("{{AFFILIATE_LINK}}", link), link,
                hashlib.sha256(tts["url"].encode()).hexdigest(),
            )
            blocks = page.split("\n\n")
            self.assertIn(link, blocks[2])  # tracked CTA above the fold
            self.assertIn(link, page[page.rindex("Disclosure"):])  # and at the end
            self.assertTrue(page.endswith(ATTRIBUTION))
            self.assertIn("](https://elevenlabs.io/pricing)", page)  # citation stays direct
            self.assertNotIn("(https://elevenlabs.io/text-to-speech)", page)
            self.assertNotRegex(merchant_free_description(page), r"(?i)eleven")

    def test_demand_page_must_cite_its_cta_destination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = skill_root(directory)
            state = Path(directory) / "state"
            with mock.patch.object(CAPTURE, "run_adapter", side_effect=AssertionError("sitemap")):
                CAPTURE.discover_official_plan(root, state, 10 * DAY)
            plan = CAPTURE.load_plan(root, "elevenlabs-demand-pricing-en", state)
            tts, pricing = plan["sources"][:2]
            rows = [
                write_source(state, tts["id"], tts["url"], "Text to speech product page."),
                write_source(state, pricing["id"], pricing["url"], FIXTURE, "official_price"),
            ]
            bundle = CAPTURE.write_composition_bundle(state, plan, rows)
            evidence = state / "composition-runs" / "run"
            evidence.mkdir(parents=True)
            (evidence / "result.json").write_text(json.dumps({
                "title": "Pricing", "markdown": (
                    f"# Pricing\n\n{COMPOSE.DISCLOSURE}\n\n[Try it]({{{{AFFILIATE_LINK}}}})\n\n"
                    "See the [pricing page](https://elevenlabs.io/pricing). " + "x " * 500
                ),
            }))
            (evidence / "summary.json").write_text(json.dumps({
                "result_path": str(evidence / "result.json"),
            }))
            with mock.patch.object(COMPOSE, "_ready_from_seal", return_value={"result_sha256": "b" * 64}):
                with self.assertRaises(COMPOSE.CompositionError):
                    COMPOSE.build_handoff(root, state, bundle, {"evidence_dir": str(evidence)})


if __name__ == "__main__":
    unittest.main()
