import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "content.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("affiliate_content", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ContentPolicyTest(unittest.TestCase):
    def test_generated_tts_api_contract_keeps_secret_link_out_of_model_output(self):
        markdown = "\n".join((
            f"# {MODULE.TTS_API_TITLE}", MODULE.DISCLOSURE,
            "## A benchmark before you pay", "benchmark " * 400,
            *MODULE.TTS_API_URLS,
            "[Try ElevenLabs]({{AFFILIATE_LINK}})", "Last evidence refresh",
        ))
        self.assertEqual(
            MODULE.validate_tts_api_result({"title": MODULE.TTS_API_TITLE, "markdown": markdown}),
            markdown,
        )
        self.assertNotIn("try.elevenlabs.io", markdown)

    def test_disclosure_source_hash_and_owned_link_gate(self):
        link = "https://try.elevenlabs.io/unit"
        markdown = f"*{MODULE.DISCLOSURE}*\n\nUseful comparison. [Try it]({link})"
        artifact = {
            "markdown": markdown,
            "content_sha256": MODULE.hashlib.sha256(markdown.encode()).hexdigest(),
            "source_hashes": {"official": "abc"},
        }
        self.assertTrue(all(MODULE.policy_checks(artifact, {"official": "abc"}, link).values()))
        artifact["markdown"] = f"[Try it]({link})\n\n{MODULE.DISCLOSURE}"
        self.assertFalse(MODULE.policy_checks(artifact, {"official": "abc"}, link)["disclosure_before_first_cta"])

    def test_rendered_page_with_top_and_end_cta_passes_policy(self):
        link = "https://try.elevenlabs.io/unit"
        markdown = MODULE.render_affiliate_markdown(
            f"Intro [docs](https://elevenlabs.io/docs).\n\n{MODULE.DISCLOSURE}\n\nTry it: {link}", link,
        )
        artifact = {
            "markdown": markdown,
            "content_sha256": MODULE.hashlib.sha256(markdown.encode()).hexdigest(),
            "source_hashes": {"official": "abc"},
        }
        self.assertTrue(all(MODULE.policy_checks(artifact, {"official": "abc"}, link).values()))
        artifact["markdown"] = markdown + "\n\n[leak](https://elevenlabs.io/pricing)"
        artifact["content_sha256"] = MODULE.hashlib.sha256(artifact["markdown"].encode()).hexdigest()
        self.assertFalse(MODULE.policy_checks(artifact, {"official": "abc"}, link)["no_untracked_merchant_links"])

    def test_builders_render_tracked_page(self):
        template = (Path(__file__).parents[1] / "config" / "content" / "elevenlabs-en-v1.md").read_text()
        link = "https://try.elevenlabs.io/elevenlabs-en-1"
        markdown = MODULE.render_affiliate_markdown(template.replace("{{AFFILIATE_LINK}}", link), link)
        self.assertIn(MODULE.ATTRIBUTION, markdown)
        self.assertNotIn("](https://elevenlabs.io", markdown)

    def test_elevenagents_x_artifact_fits_platform_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary)
            publications = state / "owned-publications"
            publications.mkdir()
            slug = "elevenagents-for-customer-support"
            url = f"https://aniccaai.com/blog/{slug}"
            (publications / f"{slug}.json").write_text(
                json.dumps({"state": "LIVE", "public_url": url}), encoding="utf-8"
            )

            result = MODULE.build_x_agents(state)
            text = (state / "x-content" / "elevenagents-en-1.txt").read_text().strip()
            self.assertEqual(result["state"], "READY_FOR_X_PUBLICATION")
            self.assertLessEqual(len(text), 280)
            self.assertIn("Affiliate link", text)
            self.assertIn(url, text)


if __name__ == "__main__":
    unittest.main()
