"""A duplicate title must turn into a distinctive retry, not a 15s OK-dialog timeout.

Measured 2026-10-07 01:41Z: set-005 "ふわふわペンギンの気持ちスタンプ" hit Creators Market's inline
「既に存在するタイトルのため利用できません」 before any confirm dialog, so the submit waited for an
OK button that never came and the wake ended effect-unknown.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import line_sticker_submit as MODULE  # noqa: E402


class Retitle(unittest.TestCase):
    def test_both_languages_get_the_character_name(self) -> None:
        listing = {"character_name": "Stardust Penguin",
                   "title": {"ja": "ふわふわペンギンの気持ちスタンプ", "en": "Fluffy Penguin Feelings Stickers"}}
        out = MODULE._retitle(listing)
        self.assertEqual(out["title"]["ja"], "ふわふわペンギンの気持ちスタンプ (Stardust Penguin)")
        self.assertEqual(out["title"]["en"], "Fluffy Penguin Feelings Stickers (Stardust Penguin)"[:40])
        self.assertEqual(listing["title"]["ja"], "ふわふわペンギンの気持ちスタンプ")  # input untouched

    def test_no_character_name_means_no_retry(self) -> None:
        self.assertIsNone(MODULE._retitle({"title": {"ja": "a", "en": "b"}}))


class InlineTitleError(unittest.TestCase):
    def test_inline_duplicate_message_is_title_taken(self) -> None:
        self.assertTrue(MODULE._is_title_taken(["既に存在するタイトルのため利用できません"]))
        self.assertTrue(MODULE._is_title_taken(["The title already exists"]))
        self.assertFalse(MODULE._is_title_taken(["必須項目です"]))


if __name__ == "__main__":
    unittest.main()
