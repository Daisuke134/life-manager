"""Canonical publication packaging: preserve legacy content, bind new source bytes."""
import copy
import base64
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

    def test_managed_manuscripts_preserve_54_legacy_articles_and_deployed_supplements(self):
        builder = self.builder()
        config, original = self.inputs()
        package, copies, receipt = builder.build_publication(ROOT, config, original)
        managed = {a["slug"] for a in config["articles"]}
        legacy = [a for a in original["articles"] if a["slug"] not in managed]
        self.assertEqual(len(package["articles"]), 54 + len(config["articles"]))
        self.assertEqual(package["articles"][:54], legacy)
        self.assertEqual(package["media"][:29], original["media"][:29])
        self.assertEqual(len(copies), len(config["articles"]) + len(config.get("media", [])))
        self.assertEqual(len(receipt["articles"]), len(config["articles"]))
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

    def fixture(self, root):
        """A real source tree with one manuscript and one frozen legacy image."""
        builder = self.builder()
        folder = root / "products/manager/docs/articles"
        folder.mkdir(parents=True)
        (folder / "evidence.txt").write_text("Independent evidence\n")
        raw = b"# English\n\n[Evidence](evidence.txt).\n"
        (folder / "english.md").write_bytes(raw)
        legacy_hash = hashlib.sha256(b"legacy image").hexdigest()
        original = {"articles": [], "media": [{
            "source": "docs/research/manager/articles/old.png",
            "package_path": "media/" + legacy_hash + ".png", "sha256": legacy_hash,
            "bytes": 12, "public_url": "https://aniccaai.com/blog/manager/media/" + legacy_hash + ".png"
        }], "publication_constraints": [
            "The legacy archive contains 27 Japanese and 27 English articles; the additive inventory has 9 further English articles. Existing diagrams remain attributed."
        ]}
        config = {"schema_version": 1, "source_commit": "a" * 40, "legacy": {
            "article_count": 0, "articles_sha256": builder.inventory_digest([]),
            "media_count": 1, "media_sha256": builder.inventory_digest(original["media"])
        }, "articles": [{
            "slug": "manager-fixture-en", "title": "English", "date": "2026-10-22",
            "description": "A fixture", "series_order": 1, "n_papers_cited": 0,
            "source": "products/manager/docs/articles/english.md",
            "source_sha256": hashlib.sha256(raw).hexdigest()
        }]}
        return builder, config, original

    def png(self, root):
        raw = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9ZQmcAAAAASUVORK5CYII=")
        source = "products/manager/docs/articles/figure.png"
        (root / source).write_bytes(raw)
        return {"source": source, "source_sha256": hashlib.sha256(raw).hexdigest()}, raw

    def test_japanese_article_uses_own_commit_and_preserves_existing_english_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            builder, config, original = self.fixture(root)
            before = builder.build_publication(root, config, original)[0]["articles"][0]
            raw = "# 日本語\n\n[出典](evidence.txt)。\n".encode()
            (root / "products/manager/docs/articles/japanese.md").write_bytes(raw)
            article = copy.deepcopy(config["articles"][0])
            article.update(slug="manager-fixture-ja", lang="ja", title="日本語",
                           source="products/manager/docs/articles/japanese.md",
                           source_sha256=hashlib.sha256(raw).hexdigest(), source_commit="b" * 40)
            config["articles"].append(article)
            try:
                package, copies, receipt = builder.build_publication(root, config, original)
            except ValueError as exc:
                self.fail("Valid bilingual inventory rejected: " + str(exc))
            self.assertEqual(package["articles"][0], before)
            japanese = package["articles"][1]
            self.assertEqual(japanese["lang"], "ja")
            self.assertEqual(japanese["package_path"], "ja/manager-fixture-ja.md")
            self.assertEqual(japanese["source_commit"], "b" * 40)
            self.assertIn("/blob/" + "b" * 40 + "/", japanese["markdown"])
            self.assertEqual(copies[japanese["package_path"]], japanese["markdown"].encode())
            self.assertEqual(receipt["articles"][1]["source_commit"], "b" * 40)
            self.assertIn("1 English and 1 Japanese", package["publication_constraints"][0])

    def test_invalid_language_and_per_article_commit_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            builder, config, original = self.fixture(root)
            for changes in ({"lang": "ja"}, {"lang": "fr"}, {"source_commit": "main"},
                            {"source_commit": "b" * 39}, {"source_commit": None}):
                invalid = copy.deepcopy(config)
                invalid["articles"][0].update(changes)
                with self.subTest(changes=changes), self.assertRaises(ValueError):
                    builder.build_publication(root, invalid, original)

    def test_additive_png_is_hash_bound_preserves_legacy_and_rebuilds_identically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            builder, config, original = self.fixture(root)
            item, raw = self.png(root)
            config["media"] = [item]
            url = "https://aniccaai.com/blog/manager/media/" + item["source_sha256"] + ".png"
            source = root / config["articles"][0]["source"]
            source.write_text(source.read_text() + "\n![Figure](" + url + ")\n")
            config["articles"][0]["source_sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            try:
                first = builder.build_publication(root, config, original)
            except ValueError as exc:
                self.fail("Valid additive PNG inventory rejected: " + str(exc))
            media = first[0]["media"]
            self.assertEqual(media[:1], original["media"])
            self.assertEqual(len(media), 2)
            self.assertEqual(media[1]["public_url"], url)
            self.assertEqual(media[1]["bytes"], len(raw))
            self.assertEqual(first[1][media[1]["package_path"]], raw)
            self.assertEqual(first[2]["media_count"], 2)
            self.assertEqual(first, builder.build_publication(root, config, first[0]))

    def test_media_hash_duplicates_and_unauthorized_replacement_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            builder, config, original = self.fixture(root)
            item, _ = self.png(root)
            config["media"] = [item]
            bad_hash = copy.deepcopy(config)
            bad_hash["media"][0]["source_sha256"] = "0" * 64
            duplicate = copy.deepcopy(config)
            duplicate["media"].append(copy.deepcopy(item))
            for invalid in (bad_hash, duplicate):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    builder.build_publication(root, invalid, original)
            first = builder.build_publication(root, config, original)[0]
            self.assertEqual(len(first["media"]), 2, "The new image must be packaged")
            for index in (0, 1):
                changed = copy.deepcopy(first)
                changed["media"][index]["source"] = "products/manager/docs/forged.png"
                with self.subTest(index=index), self.assertRaises(ValueError):
                    builder.build_publication(root, config, changed)

    def test_media_source_must_be_a_png_inside_manager_docs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            builder, config, original = self.fixture(root)
            item, raw = self.png(root)
            for path in ("/etc/passwd", "products/manager/docs/../../../outside.png",
                         "products/manager/docs/articles/figure.svg"):
                config["media"] = [{**item, "source": path}]
                with self.subTest(path=path), self.assertRaises(ValueError):
                    builder.build_publication(root, config, original)
            (root / item["source"]).write_bytes(b"not a PNG")
            config["media"] = [{**item, "source_sha256": hashlib.sha256(b"not a PNG").hexdigest()}]
            with self.assertRaises(ValueError):
                builder.build_publication(root, config, original)
            outside = root / "outside.png"
            outside.write_bytes(raw)
            source = root / item["source"]
            source.unlink()
            source.symlink_to(outside)
            config["media"] = [item]
            with self.assertRaises(ValueError):
                builder.build_publication(root, config, original)

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
