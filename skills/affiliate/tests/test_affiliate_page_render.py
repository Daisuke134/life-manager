import hashlib
import json
import re
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import owned_publish as module


LINK = "https://try.elevenlabs.io/elevenlabs-discovered-voice-changer-en-1"
# Shape of the live voice-changer page: bare CTA URL, direct citation links.
LEGACY = "\n\n".join((
    "ElevenLabs Voice Changer transforms a recording. [ElevenLabs Voice Changer](https://elevenlabs.io/voice-changer)",
    "Plans are listed on the pricing page. [ElevenLabs pricing](https://elevenlabs.io/pricing)",
    "Disclosure: This article contains an affiliate link.",
    f"If those constraints match your project, review ElevenLabs Voice Changer here: {LINK}",
))


def anchors(markdown):
    return re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", markdown)


class RenderAffiliateMarkdownTest(unittest.TestCase):
    def test_every_cta_is_a_real_link_to_the_tracked_link(self):
        rendered = module.render_affiliate_markdown(LEGACY, LINK)
        # No bare tracked URL survives outside markdown link syntax.
        self.assertNotRegex(rendered, r"(?<!\()" + re.escape(LINK))
        self.assertTrue(anchors(rendered))
        self.assertEqual(set(anchors(rendered)), {LINK})

    def test_direct_merchant_links_are_rewritten_to_tracked_link(self):
        rendered = module.render_affiliate_markdown(LEGACY, LINK)
        self.assertNotIn("](https://elevenlabs.io", rendered)
        self.assertNotIn("](https://www.elevenlabs.io", rendered)

    def test_disclosure_directly_precedes_top_and_end_cta(self):
        rendered = module.render_affiliate_markdown(LEGACY, LINK)
        blocks = rendered.split("\n\n")
        cta = [i for i, block in enumerate(blocks) if module.CTA_TOP_MARKER in block]
        self.assertEqual(len(cta), 1)
        # Near the top: before any body paragraph that cites the merchant.
        self.assertLessEqual(cta[0], 2)
        self.assertTrue(blocks[cta[0] - 1].startswith(module.FULL_DISCLOSURE))
        # The first tracked link appears only after the disclosure.
        self.assertLess(rendered.find(module.FULL_DISCLOSURE), rendered.find(LINK))
        self.assertIn("independent ElevenLabs affiliate", module.FULL_DISCLOSURE)
        # End: the last block before attribution is a CTA, preceded by disclosure.
        self.assertEqual(blocks[-1], module.ATTRIBUTION)
        self.assertIn(f"]({LINK})", blocks[-2])
        self.assertTrue(blocks[-3].startswith(module.FULL_DISCLOSURE))

    def test_attribution_statement_required_by_terms(self):
        rendered = module.render_affiliate_markdown(LEGACY, LINK)
        self.assertIn("is not sponsored by, endorsed by, or affiliated with ElevenLabs", rendered)
        self.assertEqual(rendered.count(module.ATTRIBUTION), 1)

    def test_render_is_idempotent_and_keeps_legacy_readback_marker(self):
        once = module.render_affiliate_markdown(LEGACY, LINK)
        self.assertEqual(module.render_affiliate_markdown(once, LINK), once)
        self.assertIn("Disclosure: This article contains an affiliate link.", once)

    def test_heading_stays_first(self):
        rendered = module.render_affiliate_markdown("# Title\n\n" + LEGACY, LINK)
        self.assertTrue(rendered.startswith("# Title\n\n" + module.FULL_DISCLOSURE))

    def test_unknown_merchant_link_is_left_unchanged(self):
        self.assertEqual(module.render_affiliate_markdown(LEGACY, "https://example.com/x"), LEGACY)

    def test_public_row_meta_description_omits_merchant_name(self):
        markdown = module.render_affiliate_markdown("# ElevenLabs Title\n\n" + LEGACY, LINK)
        row = module.public_row({
            "slug": "s-1", "title": "t", "built_at": "2026-10-17T00:00:00+00:00",
            "source_hashes": [], "markdown": markdown,
        })
        self.assertTrue(row["description"])
        self.assertNotRegex(row["description"], r"(?i)eleven")
        self.assertLessEqual(len(row["description"]), 200)
        # Unrendered legacy artifacts keep their exact public row.
        legacy = module.public_row({
            "slug": "s-1", "title": "t", "built_at": "2026-10-17T00:00:00+00:00",
            "source_hashes": [], "markdown": LEGACY,
        })
        self.assertNotIn("description", legacy)


class RerenderLivePagesTest(unittest.TestCase):
    def write_page(self, state, slug, markdown, link, owned_state="LIVE"):
        sha = hashlib.sha256(markdown.encode()).hexdigest()
        for folder, value in (
            ("content", {
                "slug": slug, "title": "t", "state": "READY_FOR_PUBLICATION",
                "markdown": markdown, "content_sha256": sha, "disclosure": "affiliate_link",
                "source_hashes": [], "readback_markers": ["Disclosure: This article contains an affiliate link."],
                "readback_links": [link], "built_at": "2026-10-17T00:00:00+00:00",
            }),
            ("policy", {"decision": "PASS", "content_sha256": sha, "receipt_type": "CONTENT_POLICY"}),
            ("owned-publications", {"state": owned_state, "content_sha256": sha, "slug": slug}),
        ):
            (state / folder).mkdir(parents=True, exist_ok=True)
            (state / folder / f"{slug}.json").write_text(json.dumps(value))

    def test_dry_run_reports_without_writing_and_apply_republishes_through_owned_publish(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            self.write_page(state, "voice-changer", LEGACY, LINK)
            self.write_page(state, "draft", LEGACY, LINK, owned_state="INTENT")
            before = (state / "content" / "voice-changer.json").read_bytes()
            calls = []
            args = Namespace(state=state, landing_root=state, apply=False, slug=None,
                             remote="origin", branch="main", repository="r", base_url="https://aniccaai.com")
            result = module.rerender(args, publisher=lambda a: calls.append(a.slug) or {"state": "LIVE"})
            self.assertEqual([row["slug"] for row in result["pages"]], ["voice-changer"])
            row = result["pages"][0]
            self.assertEqual(row["state"], "WOULD_REPUBLISH")
            self.assertEqual(row["before"]["tracked_anchors"], 0)
            self.assertGreaterEqual(row["after"]["tracked_anchors"], 2)
            self.assertEqual(row["before"]["direct_merchant_links"], 2)
            self.assertEqual(row["after"]["direct_merchant_links"], 0)
            self.assertEqual((state / "content" / "voice-changer.json").read_bytes(), before)
            self.assertEqual(calls, [])

            args.apply = True
            result = module.rerender(args, publisher=lambda a: calls.append(a.slug) or {"state": "LIVE"})
            self.assertEqual(calls, ["voice-changer"])
            artifact = json.loads((state / "content" / "voice-changer.json").read_text())
            policy = json.loads((state / "policy" / "voice-changer.json").read_text())
            self.assertEqual(artifact["content_sha256"], hashlib.sha256(artifact["markdown"].encode()).hexdigest())
            self.assertEqual(policy["content_sha256"], artifact["content_sha256"])
            self.assertEqual(policy["decision"], "PASS")
            module.load_artifact(state, "voice-changer")

            # Already rendered pages are a no-op on the next run.
            calls.clear()
            (state / "owned-publications" / "voice-changer.json").write_text(json.dumps(
                {"state": "LIVE", "content_sha256": artifact["content_sha256"]}))
            result = module.rerender(args, publisher=lambda a: calls.append(a.slug) or {"state": "LIVE"})
            self.assertEqual(result["pages"][0]["state"], "CURRENT")
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
