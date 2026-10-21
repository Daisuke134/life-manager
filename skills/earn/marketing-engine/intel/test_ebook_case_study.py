#!/usr/bin/env python3
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile
import unittest


HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE / "ebook_case_study.py"
CASE_ID = "tactic.yangmun-journey-ebook-bundle.v1"
NON_EBOOK_CASE_ID = "tactic.gotcha-prd.v1"


class EbookCaseStudyTests(unittest.TestCase):
    def run_generator(self, case_id: str, output_format: str):
        tempdir = tempfile.TemporaryDirectory()
        output_path = pathlib.Path(tempdir.name) / "draft.md"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--case-id", case_id, "--format",
             output_format, "--out", str(output_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        return tempdir, output_path, result

    def test_article_draft_preserves_provenance_sources_and_unknowns(self):
        tempdir, output_path, result = self.run_generator(CASE_ID, "article")
        with tempdir:
            self.assertEqual(result.returncode, 0, result.stderr)
            article = output_path.read_text(encoding="utf-8")
            self.assertIn("live_observed", article)
            self.assertIn("https://www.yang-mun.com/pages/journey", article)
            self.assertIn("https://www.yang-mun.com/products/the-complete-collection-yang-mun", article)
            self.assertIn("Anicca result: not recorded", article)
            self.assertIn("Result evidence: not recorded", article)

    def test_x_post_draft_keeps_case_note_and_source_within_limit(self):
        tempdir, output_path, result = self.run_generator(CASE_ID, "x-post")
        with tempdir:
            self.assertEqual(result.returncode, 0, result.stderr)
            draft = output_path.read_text(encoding="utf-8")
            self.assertIn("https://www.yang-mun.com/pages/journey", draft)
            self.assertIn("https://www.yang-mun.com/products/the-complete-collection-yang-mun", draft)
            self.assertIn("https://aniccaai.com/blog/ebook-publishing-ai-monk-economy-2026", draft)
            self.assertIn("No Anicca result is recorded", draft)
            t_co_draft = draft.replace("https://www.yang-mun.com/pages/journey", "x" * 23)
            t_co_draft = t_co_draft.replace(
                "https://www.yang-mun.com/products/the-complete-collection-yang-mun", "x" * 23
            )
            t_co_draft = t_co_draft.replace(
                "https://aniccaai.com/blog/ebook-publishing-ai-monk-economy-2026", "x" * 23
            )
            self.assertLessEqual(len(t_co_draft), 280)

    def test_non_ebook_case_fails_without_writing_output(self):
        tempdir, output_path, result = self.run_generator(NON_EBOOK_CASE_ID, "article")
        with tempdir:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("does not apply to ebook", result.stderr)
            self.assertFalse(output_path.exists())


if __name__ == "__main__":
    unittest.main()
