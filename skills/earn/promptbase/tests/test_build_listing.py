#!/usr/bin/env python3
"""Tests for the pure listing-text builder (no network/browser)."""
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
from build_listing import build_listing, TITLE_MAX, DESCRIPTION_MAX  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[4]
CATALOG_DIR = REPO_ROOT / "skills" / "capafy" / "catalog" / "reels-hook-lab"


class BuildListingTest(unittest.TestCase):
    def test_builds_from_real_catalog_skill(self):
        listing = build_listing(CATALOG_DIR)
        self.assertEqual(listing.slug, "reels-hook-lab")
        self.assertLessEqual(len(listing.title), TITLE_MAX)
        self.assertLessEqual(len(listing.description), DESCRIPTION_MAX)
        self.assertEqual(listing.price_usd, 4.99)
        self.assertEqual(listing.item_type, "Prompt")
        self.assertEqual(listing.generation_type, "Text")
        self.assertEqual(listing.model, "Claude")
        self.assertEqual(listing.model_version, "5 Sonnet")
        self.assertIn("Reels Hook Lab", listing.title)
        self.assertTrue(listing.example_input)
        self.assertTrue(listing.example_output)
        # the SKILL.md body must be present verbatim inside what gets pasted
        # into PromptBase's "prompt template" field
        skill_md = (CATALOG_DIR / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(skill_md.strip(), listing.prompt_instructions)
        # and the example-input bracket line precedes it (matches the live
        # Hook Lab listing's "[VAR]: value" prefix convention)
        self.assertTrue(listing.prompt_instructions.startswith("[TOPIC"))
        self.assertIn(listing.example_input, listing.prompt_instructions)

    def test_builds_from_football_analyst_demonstration_fixture(self):
        catalog_dir = REPO_ROOT / "skills" / "capafy" / "catalog" / "football-match-analyst"
        listing = build_listing(catalog_dir)

        self.assertEqual(listing.slug, "football-match-analyst")
        self.assertIn("Northbridge FC vs River Athletic", listing.example_input)
        self.assertIn("No reliable ranking is produced.", listing.example_output)

    def test_builds_sales_objection_reply_builder_from_verified_demonstration(self):
        catalog_dir = REPO_ROOT / "skills" / "capafy" / "catalog" / "sales-objection-reply-builder"
        listing = build_listing(catalog_dir)

        self.assertEqual(listing.slug, "sales-objection-reply-builder")
        self.assertIn("The tool we use today is cheaper", listing.example_input)
        self.assertIn("synthetic scenario", listing.example_input.lower())
        self.assertIn("$299/month", listing.example_input)
        self.assertIn("guided onboarding", listing.example_input.lower())
        self.assertIn("no published roi study", listing.example_input.lower())
        self.assertEqual(listing.example_output.count("### Variant "), 3)
        self.assertIn("guided onboarding", listing.example_output.lower())
        self.assertIn("no published roi study", listing.example_output.lower())
        self.assertIn("softened", listing.example_output.lower())
        self.assertEqual(listing.example_output.count("?"), 1)
        self.assertEqual(listing.example_output.count("### Follow-up question"), 1)
        for section in ("### Diagnosis", "### Proof gaps", "### Follow-up question", "### Honesty check"):
            self.assertIn(section, listing.example_output)

    def test_title_never_exceeds_promptbase_limit(self):
        listing = build_listing(CATALOG_DIR)
        self.assertLessEqual(len(listing.title), 40)

    def test_missing_listing_md_raises(self, ):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "broken-skill"
            tmp_path.mkdir()
            (tmp_path / "SKILL.md").write_text("---\nname: x\n---\nbody")
            with self.assertRaises(FileNotFoundError):
                build_listing(tmp_path)

    def test_missing_short_description_raises(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "broken-skill"
            (tmp_path / "evidence").mkdir(parents=True)
            (tmp_path / "SKILL.md").write_text("body")
            (tmp_path / "LISTING.md").write_text("## Title\nX\n")
            (tmp_path / "evidence" / "verified-demonstration.md").write_text(
                "## Concrete input\n```text\nhi\n```\n## Actual output\nok\n"
            )
            with self.assertRaises(ValueError):
                build_listing(tmp_path)


if __name__ == "__main__":
    unittest.main()
