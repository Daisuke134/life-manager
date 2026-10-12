import importlib
import json
import tempfile
import unittest
from pathlib import Path


class ResumeRoutingTests(unittest.TestCase):
    def _resume_tree(self, root: Path) -> None:
        files = [
            root / "resumes" / "japanese.pdf",
            root / "resumes" / "engineering.pdf",
            root / "resumes" / "technical-business.pdf",
        ]
        for index, path in enumerate(files):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(f"%PDF-1.4 resume-{index}".encode())
        (root / "manifest.v1.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "resumes": {
                        "engineering": "resumes/engineering.pdf",
                        "technical_business": "resumes/technical-business.pdf",
                        "japanese": "resumes/japanese.pdf",
                    },
                }
            ),
            encoding="utf-8",
        )

    def test_japanese_posting_selects_japanese_resume_regardless_of_role_family(self):
        self.assertIsNotNone(
            importlib.util.find_spec("job_search_loop.resume_routing")
        )
        routing = importlib.import_module("job_search_loop.resume_routing")
        select_resume = getattr(routing, "select_resume", None)
        self.assertIsNotNone(select_resume)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._resume_tree(root)

            result = select_resume(
                posting_text=(
                    "生成AIエンジニアを募集します。金融機関向けAIエージェントの"
                    "設計・開発・評価を担当し、プロダクトチームと連携します。"
                ),
                role_family="customer_success",
                materials_root=root,
            )

            self.assertEqual(result["posting_language"], "ja")
            self.assertEqual(result["resume_variant"], "japanese")
            self.assertEqual(
                Path(result["resume_path"]).name,
                "japanese.pdf",
            )

    def test_runtime_business_alias_uses_approved_business_resume(self):
        routing = importlib.import_module("job_search_loop.resume_routing")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._resume_tree(root)
            result = routing.select_resume(posting_text="Help enterprise customers.", role_family="technical_business", materials_root=root)
            self.assertEqual(result["resume_variant"], "technical_business")

    def test_english_posting_keeps_english_role_variant(self):
        self.assertIsNotNone(
            importlib.util.find_spec("job_search_loop.resume_routing")
        )
        routing = importlib.import_module("job_search_loop.resume_routing")
        select_resume = getattr(routing, "select_resume", None)
        self.assertIsNotNone(select_resume)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._resume_tree(root)

            engineering = select_resume(
                posting_text="Build and evaluate production AI agents for banking workflows.",
                role_family="engineering",
                materials_root=root,
            )
            business = select_resume(
                posting_text="Help enterprise customers adopt reliable AI products.",
                role_family="customer_success",
                materials_root=root,
            )

            self.assertEqual(engineering["posting_language"], "en")
            self.assertEqual(engineering["resume_variant"], "engineering")
            self.assertEqual(
                Path(engineering["resume_path"]).name,
                "engineering.pdf",
            )
            self.assertEqual(business["posting_language"], "en")
            self.assertEqual(business["resume_variant"], "technical_business")
            self.assertEqual(
                Path(business["resume_path"]).name,
                "technical-business.pdf",
            )


if __name__ == "__main__":
    unittest.main()
