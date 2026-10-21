"""Canonical publication packaging: preserve legacy content, bind new source bytes."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "products/manager/scripts/build_blog_publication.py"
CONFIG = ROOT / "products/manager/publication/articles-2026-10-22.json"
PACKAGE = ROOT / "docs/research/manager/publication/2026-10-19"


class BlogPublicationTests(unittest.TestCase):
    def builder(self):
        self.assertTrue(SCRIPT.is_file(), "Missing canonical publication builder")
        spec = importlib.util.spec_from_file_location("manager_blog_builder", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def inputs(self):
        return json.loads(CONFIG.read_text()), json.loads((PACKAGE / "manifest.json").read_text())

    def test_all_nine_manuscripts_preserve_54_legacy_articles_and_deployed_supplements(self):
        builder = self.builder()
        config, original = self.inputs()
        package, copies, receipt = builder.build_publication(ROOT, config, original)
        managed = {a["slug"] for a in config["articles"]}
        legacy = [a for a in original["articles"] if a["slug"] not in managed]
        self.assertEqual(len(package["articles"]), 63)
        self.assertEqual(package["articles"][:54], legacy)
        self.assertEqual(package["media"], original["media"])
        self.assertEqual(len(copies), 9)
        self.assertEqual(len(receipt["articles"]), 9)
        by_slug = {a["slug"]: a for a in package["articles"]}
        self.assertEqual(by_slug["manager-evidence-cards-r007-r008-en"]["sha256"],
                         "708cc3a92402a57032529153190fce3d7204d4b1e5aebd0d3e191551d6791fb5")
        self.assertEqual(by_slug["manager-population-behavior-causality-field-guide-en"]["sha256"],
                         "43f09759d3541d753e88ae30d073f8791c78f2270094742dc04cd7841ac66756")
        self.assertFalse(receipt["publication_verified"])
        for article in package["articles"][54:]:
            self.assertEqual(hashlib.sha256(copies[article["package_path"]]).hexdigest(), article["sha256"])
            self.assertEqual(article["markdown"].encode(), copies[article["package_path"]])
            self.assertEqual(article["canonical_url"], "https://aniccaai.com/blog/" + article["slug"])

    def test_repeated_build_is_byte_identical_and_does_not_duplicate_articles(self):
        builder = self.builder()
        config, original = self.inputs()
        first = builder.build_publication(ROOT, config, original)
        second = builder.build_publication(ROOT, config, first[0])
        self.assertEqual(first, second)

    def test_manuscripts_without_frontmatter_or_relative_links_retain_exact_bytes(self):
        builder = self.builder()
        config, original = self.inputs()
        _, copies, _ = builder.build_publication(ROOT, config, original)
        for article in config["articles"][:7]:
            self.assertEqual(copies["en/" + article["slug"] + ".md"],
                             (ROOT / article["source"]).read_bytes(), article["slug"])

    def test_changed_source_bytes_fail_closed(self):
        builder = self.builder()
        config, original = self.inputs()
        config["articles"][0]["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Source hash mismatch"):
            builder.build_publication(ROOT, config, original)

    def test_duplicate_slug_or_duplicate_manuscript_is_rejected(self):
        builder = self.builder()
        config, original = self.inputs()
        duplicate_slug = copy.deepcopy(config)
        duplicate_slug["articles"][1]["slug"] = duplicate_slug["articles"][0]["slug"]
        with self.assertRaisesRegex(ValueError, "Duplicate article slug"):
            builder.build_publication(ROOT, duplicate_slug, original)
        duplicate_source = copy.deepcopy(config)
        for field in ("source", "source_sha256"):
            duplicate_source["articles"][1][field] = duplicate_source["articles"][0][field]
        with self.assertRaisesRegex(ValueError, "Duplicate manuscript"):
            builder.build_publication(ROOT, duplicate_source, original)

    def test_changed_legacy_content_or_added_unowned_article_is_rejected(self):
        builder = self.builder()
        config, original = self.inputs()
        changed = copy.deepcopy(original)
        changed["articles"][0]["title"] = "Unexpected legacy edit"
        with self.assertRaisesRegex(ValueError, "Legacy article inventory changed"):
            builder.build_publication(ROOT, config, changed)
        extra = copy.deepcopy(original)
        extra["articles"].append({"slug": "manager-unrelated-draft-en"})
        with self.assertRaisesRegex(ValueError, "Legacy article inventory changed"):
            builder.build_publication(ROOT, config, extra)

    def test_source_paths_cannot_escape_manager_docs(self):
        builder = self.builder()
        config, original = self.inputs()
        for path in ("/etc/passwd", "../../outside.md", "products/manager/docs/../../../AGENTS.md"):
            invalid = copy.deepcopy(config)
            invalid["articles"][0]["source"] = path
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "Source path"):
                builder.build_publication(ROOT, invalid, original)

    def test_frontmatter_removed_and_relative_links_bind_to_immutable_existing_sources(self):
        builder = self.builder()
        config, original = self.inputs()
        package, _, _ = builder.build_publication(ROOT, config, original)
        article = next(a for a in package["articles"] if a["slug"] == "manager-eba-benchmark-landscape-en")
        self.assertTrue(article["markdown"].startswith("# A Map of AI Evaluation"))
        self.assertNotIn("](../", article["markdown"])
        self.assertIn("https://github.com/Daisuke134/life-manager/blob/" + config["source_commit"] +
                      "/products/manager/docs/research/evals/EVAL_LANDSCAPE_20261022.json", article["markdown"])
        self.assertEqual(article["source_sha256"], next(a for a in config["articles"]
                         if a["slug"] == article["slug"])["source_sha256"])

    def test_unregistered_image_and_unsafe_link_fail_closed(self):
        builder = self.builder()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "products/manager/docs/articles/example.md"
            source.parent.mkdir(parents=True)
            source.write_text("# Example\n")
            for markdown, message in (("![image](https://example.com/unregistered.png)", "Unregistered image"),
                                      ("[link](javascript:alert)", "Unsafe link"),
                                      ("[missing](../not-present.md)", "Missing relative link")):
                with self.subTest(markdown=markdown), self.assertRaisesRegex(ValueError, message):
                    builder.public_markdown(markdown, source, root, "a" * 40, set())


if __name__ == "__main__":
    unittest.main()
