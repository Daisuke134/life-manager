from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "post_contract.py"
SPEC = importlib.util.spec_from_file_location("post_contract", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class PostContractTests(unittest.TestCase):
    def test_japanese_slot_requires_japanese_text(self) -> None:
        self.assertTrue(MODULE.language_matches("ja", "これは次に試せる手順です"))
        self.assertFalse(MODULE.language_matches("ja", "Try this next."))
        self.assertFalse(MODULE.language_matches("ja", "Try this whole English paragraph next. 日本語"))
        self.assertFalse(MODULE.language_matches("ja", "人工智能产品增长"))

    def test_english_slot_rejects_japanese_text(self) -> None:
        self.assertTrue(MODULE.language_matches("en", "Try this next."))
        self.assertFalse(MODULE.language_matches("en", "次はこれを試す。"))
        self.assertFalse(MODULE.language_matches("en", "ﾂｷﾞﾊ ｺﾚｦ ﾀﾒｽ AI"))
        self.assertFalse(MODULE.language_matches("en", "12345"))
        self.assertFalse(MODULE.language_matches("en", "Попробуйте это"))

    def test_english_slot_rejects_latin_text_critic_identifies_as_spanish(self) -> None:
        for detected_language, expected_code in (("en", 0), ("es", 1), ("", 1)):
            with self.subTest(detected_language=detected_language):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--language", "en", "--text-file",
                     str(SCRIPT), "--detected-language", detected_language],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, expected_code,
                                 result.stdout + result.stderr)

    def test_english_precheck_leaves_latin_language_judgment_to_critic(self) -> None:
        candidates = (
            "Retry manually or abort; capture stderr.",
            "He crashed; restart manually, abort on timeout.",
            "He probado este paso antes de publicar; si falla, revisa los permisos.",
            "Has probado este paso antes de publicar; si falla, revisa los permisos.",
            "Or, cette étape permet de vérifier les droits avant de publier.",
            "Prüfe die Rechte in deinem Konto; starte danach erneut.",
        )
        for text in candidates:
            with self.subTest(text=text):
                self.assertTrue(MODULE.language_matches("en", text))

    def test_english_final_gate_requires_exact_critic_language_code(self) -> None:
        cases = (
            ("Retry manually or abort; capture stderr.", "en", True),
            ("He crashed; restart manually, abort on timeout.", "en", True),
            ("He probado este paso antes de publicar; si falla, revisa los permisos.", "es", False),
            ("Or, cette étape permet de vérifier les droits avant de publier.", "fr", False),
            ("Prüfe die Rechte in deinem Konto; starte danach erneut.", "de", False),
            ("Try this next.", "", False),
        )
        for text, detected_language, expected in cases:
            with self.subTest(detected_language=detected_language, text=text):
                self.assertEqual(
                    MODULE.language_matches("en", text, detected_language=detected_language),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
