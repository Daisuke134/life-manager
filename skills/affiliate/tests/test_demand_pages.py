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
        self.assertIn("fetched 2026-10-15", COMPOSE.pricing_table(FIXTURE, "2026-10-15"))

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
            self.assertEqual(handoff["page_type"], "pricing")

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


class FocusGateTest(unittest.TestCase):
    def setUp(self):
        self.loop = load("affiliate_local_loop_demand", "local_loop.py")
        self.directory = tempfile.TemporaryDirectory()
        self.state = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def focus(self, age_days):
        from datetime import datetime, timedelta, timezone
        created = datetime.now(timezone.utc) - timedelta(days=age_days)
        self.loop.atomic_json(self.state / "focused-cohort" / "latest.json", {
            "placement_id": "subtitle-en-1", "created_at": created.isoformat(),
            "placement_expansion_state": "PAUSED_FOR_FOCUSED_COHORT",
        })

    def test_demand_page_publishes_while_focus_is_active(self):
        self.focus(1)
        self.assertTrue(self.loop.focused_publication_allowed(
            self.state, "elevenlabs-demand-pricing-en-1", {},
            {"plan_id": "elevenlabs-demand-pricing-en", "page_type": "pricing"},
        ))
        # Only a configured demand plan bypasses, not any truthy page_type.
        self.assertFalse(self.loop.focused_publication_allowed(
            self.state, "other-en-1", {}, {"plan_id": "other-en", "page_type": "pricing"},
        ))

    def test_unexpired_focus_still_blocks_other_new_pages(self):
        self.focus(6)
        self.assertFalse(self.loop.focused_publication_allowed(self.state, "new-en-1", {}, {}))
        self.assertFalse(self.loop.focus_expired(self.state))

    def test_expired_focus_allows_any_page_and_keeps_the_file(self):
        self.focus(self.loop.FOCUS_TTL_SECONDS / 86400 + 0.01)
        self.assertTrue(self.loop.focused_publication_allowed(self.state, "new-en-1", {}, {}))
        self.assertTrue(self.loop.focus_expired(self.state))
        self.assertTrue((self.state / "focused-cohort" / "latest.json").is_file())

    def test_expired_focus_no_longer_holds_legacy_publication(self):
        self.focus(8)
        with (
            mock.patch.object(self.loop, "advance_generic_publication",
                              return_value={"state": "ALREADY_LIVE", "public_url": None}),
            mock.patch.object(self.loop, "advance_legacy_dedicated_publication",
                              return_value={"state": "X_LIVE", "public_url": "u"}) as legacy,
        ):
            result = self.loop.advance_known_publication(
                self.state, self.state / "landing", 9326, self.state / "private.md",
            )
        legacy.assert_called_once()
        self.assertEqual(result["state"], "X_LIVE")


    def campaign(self, plan_id, control=None):
        handoff = {
            "receipt_type": "CAMPAIGN_HANDOFF", "state": "READY_FOR_POLICY",
            "plan_id": plan_id, "locale": "en", "slug": f"{plan_id}-guide",
            "source_set_sha256": "e" * 64, "title": "t", "buyer_intent": "b before paying",
            "cited_sources": [{"locator": "https://elevenlabs.io/x", "raw_sha256": "f" * 64}],
            "owned_article_markdown": (
                "Intro [docs](https://elevenlabs.io/x).\n\n"
                "Disclosure: This article contains an affiliate link.\n\n"
                "Try it: {{AFFILIATE_LINK}}"
            ),
            "x_copy": "Affiliate link disclosure: t {{OWNED_ARTICLE_URL}}",
            "disclosure": "Disclosure: This article contains an affiliate link.",
        }
        if control:
            handoff["experiment"] = {"control_placement_id": control, "decision_id": plan_id}
        fingerprint = hashlib.sha256(json.dumps(
            handoff, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        body = json.dumps({**handoff, "handoff_fingerprint": fingerprint},
                          sort_keys=True, separators=(",", ":")).encode()
        path = self.state / "campaign-handoffs" / f"{plan_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        self.loop.atomic_json(self.state / "campaign-policy" / f"{plan_id}.json", {
            "receipt_type": "GENERIC_CAMPAIGN_POLICY", "state": "PASS",
            "decision": "PASS", "plan_id": plan_id, "locale": "en",
            "handoff_sha256": hashlib.sha256(body).hexdigest(),
            "handoff_fingerprint": fingerprint, "source_set_sha256": "e" * 64,
            "checks": {"ok": True}, "semantic_audit": {"decision": "PASS"},
        })

    def test_expired_focus_archives_its_variants_and_caps_other_pages_per_day(self):
        self.focus(8)
        variants = [f"a-variant-{n}-en" for n in range(4)]
        for plan_id in variants:
            self.campaign(plan_id, control="subtitle-en-1")
        for plan_id in ("b-plain-en", "c-plain-en"):
            self.campaign(plan_id)
        owned = mock.Mock(side_effect=lambda args: {
            "state": "LIVE", "public_url": f"https://aniccaai.com/blog/{args.slug}"})
        posted = mock.Mock(side_effect=lambda args: {
            "state": "LIVE", "public_url": f"https://x.com/a/status/{args.placement}"})
        acquire = mock.Mock(return_value={
            "state": "VERIFIED", "deduplicated": True, "private_link_field": "f",
            "provider_link_key": "k", "destination_sha256": None,
        })
        results = []
        with mock.patch.object(self.loop, "elevenlabs_link",
                               return_value="https://try.elevenlabs.io/p"):
            for _ in range(8):
                results.append(self.loop.advance_generic_publication(
                    self.state, self.state / "landing", 9326, self.state / "private.md",
                    owned_publisher=owned, x_publisher=posted, link_acquirer=acquire,
                ))
        published = {call.args[0].slug for call in owned.call_args_list}
        self.assertEqual(published, {"b-plain-en-guide"})
        self.assertEqual(posted.call_count, 1)
        for plan_id in variants:
            archive = json.loads((self.state / "campaign-archive" / f"{plan_id}.json").read_text())
            self.assertEqual(archive["state"], "ARCHIVED_FOCUS_EXPIRED")
            self.assertTrue((self.state / "campaign-policy" / f"{plan_id}.json").is_file())
        self.assertEqual(self.loop.post_focus_generic_started_today(self.state), 1)
        self.assertTrue(any(row.get("post_focus_daily_cap_reached") for row in results))


if __name__ == "__main__":
    unittest.main()
