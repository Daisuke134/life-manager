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
        self.assertEqual(out["title"]["ja"], "Stardust Penguinのスタンプ")  # full-width counts 2: 51 > 40
        # 51 chars would break Creators Market's 40-char limit (live 2026-10-07 06:23Z): name-led instead.
        self.assertEqual(out["title"]["en"], "Stardust Penguin Stickers")
        self.assertTrue(all(MODULE._title_units(t) <= MODULE.TITLE_MAX for t in out["title"].values()))
        self.assertEqual(listing["title"]["ja"], "ふわふわペンギンの気持ちスタンプ")  # input untouched

    def test_short_titles_keep_the_original_with_the_name(self) -> None:
        out = MODULE._retitle({"character_name": "Pip", "title": {"ja": "もちハム", "en": "Mochi Hamster"}})
        self.assertEqual(out["title"], {"ja": "もちハム (Pip)", "en": "Mochi Hamster (Pip)"})

    def test_no_character_name_means_no_retry(self) -> None:
        self.assertIsNone(MODULE._retitle({"title": {"ja": "a", "en": "b"}}))


class InlineTitleError(unittest.TestCase):
    def test_inline_duplicate_message_is_title_taken(self) -> None:
        self.assertTrue(MODULE._is_title_taken(["既に存在するタイトルのため利用できません"]))
        self.assertTrue(MODULE._is_title_taken(["The title already exists"]))
        self.assertFalse(MODULE._is_title_taken(["必須項目です"]))



class _FakePage:
    def __init__(self, body):
        self.body = body
        self.clicked = False

    async def inner_text(self, selector):
        return self.body

    def locator(self, *a, **k):
        raise AssertionError("must not click リクエスト when already in review")


class RequestReviewIsIdempotent(unittest.TestCase):
    def test_already_in_review_is_marked_without_clicking(self) -> None:
        import asyncio
        page = _FakePage("アイテム管理 ステータス 審査待ち 編集に戻す")
        original_goto = MODULE._goto

        async def no_goto(page, url):
            return None

        MODULE._goto = no_goto
        try:
            out = asyncio.run(MODULE._request_review(page, {"product_id": "1", "state": "tagged"}))
        finally:
            MODULE._goto = original_goto
        self.assertEqual(out["state"], "review_requested")
        self.assertEqual(out["state_observed"], "審査待ち")

    def test_review_processing_counts_as_in_review(self) -> None:
        import asyncio
        # Live 2026-10-07: approved-in-processing items show 審査処理中.
        self.assertEqual(asyncio.run(MODULE._review_status(_FakePage("ステータス\n審査処理中\n表示情報"))), "審査処理中")
        import creators_readback
        self.assertIn("審査処理中", creators_readback.STATUSES)

    def test_status_ignores_words_outside_the_status_field(self) -> None:
        import asyncio
        page = _FakePage("お知らせ 審査中のアイテムについて ステータス リジェクト")
        self.assertIsNone(asyncio.run(MODULE._review_status(page)))


if __name__ == "__main__":
    unittest.main()


class IdempotentSteps(unittest.TestCase):
    def test_failed_overwrite_step_keeps_state_for_a_redo(self) -> None:
        import asyncio

        async def boom():
            raise RuntimeError("Target page, context or browser has been closed")

        out = asyncio.run(MODULE._idempotent_step(boom, {"state": "images_uploaded"}, "tagged"))
        self.assertEqual(out["state"], "images_uploaded")

    def test_successful_step_advances(self) -> None:
        import asyncio

        async def ok():
            return None

        out = asyncio.run(MODULE._idempotent_step(ok, {"state": "metadata_saved"}, "images_uploaded"))
        self.assertEqual(out["state"], "images_uploaded")


class FitListing(unittest.TestCase):
    def test_long_english_description_is_cut_at_a_sentence_within_160(self) -> None:
        # Live 2026-10-07 11:31Z set-007: a 188-char en description hit 160文字まで入力可能です.
        desc = ("Pokata the otter is ready for every autumn and winter occasion, from Halloween and "
                "Christmas to New Year. Send seasonal greetings and everyday feelings with big, cute motions.")
        out = MODULE._fit_listing({"title": {"en": "T", "ja": "た"}, "description": {"en": desc, "ja": "せつめい"}})
        self.assertLessEqual(MODULE._title_units(out["description"]["en"]), MODULE.DESC_MAX)
        self.assertTrue(out["description"]["en"].endswith("."))

    def test_japanese_description_counts_full_width_as_two(self) -> None:
        desc = "かわいい" * 30  # 120 chars = 240 units
        out = MODULE._fit_listing({"title": {"ja": "た"}, "description": {"ja": desc}})
        self.assertLessEqual(MODULE._title_units(out["description"]["ja"]), MODULE.DESC_MAX)

    def test_short_listing_is_untouched(self) -> None:
        listing = {"title": {"en": "Mochi Hamster"}, "description": {"en": "Cute."}}
        self.assertEqual(MODULE._fit_listing(listing), listing)


class CleanCharacters(unittest.TestCase):
    def test_curly_quote_and_emoji_are_normalised(self) -> None:
        out = MODULE._fit_listing({"title": {"en": "Animated! Mofutan’s Life \U0001F9A6"}, "description": {"en": "Hi…"}})
        self.assertEqual(out["title"]["en"], "Animated! Mofutan's Life")
        self.assertEqual(out["description"]["en"], "Hi...")

    def test_cut_title_does_not_end_on_a_connector(self) -> None:
        out = MODULE._fit_listing({"title": {"en": "Animated! Mofutan's Polite Family & Oshi Life"}, "description": {}})
        self.assertEqual(out["title"]["en"], "Animated! Mofutan's Polite Family")


class _FakeRadio:
    def __init__(self, clicked: list[str], value: str) -> None:
        self._clicked = clicked
        self._value = value

    async def count(self) -> int:
        return 1

    @property
    def first(self):
        return self

    async def evaluate(self, script: str) -> None:
        self._clicked.append(self._value)


class _FakeSelectLocator:
    async def count(self) -> int:
        return 0


class _FakeCampaignPage:
    """Mimics only what ``_select_taste_character_campaign`` touches: no real <select>s, and one
    radio per requested value (every value in LINE's shared feature-campaign radio group "exists").
    """

    def __init__(self) -> None:
        self.clicked: list[str] = []

    def locator(self, selector: str, *a, **k):
        if selector == "select":
            return _FakeSelectLocator()
        # 参加しない has no value attribute; the live DOM reports its .value as "on".
        value = selector.split("value='")[1].rstrip("']") if "value='" in selector else "on"
        assert "value='on'" not in selector, "CSS [value='on'] never matches the live radio"
        return _FakeRadio(self.clicked, value)


class SelectCampaign(unittest.TestCase):
    def test_a_feature_value_clicks_that_exact_radio_not_on(self) -> None:
        import asyncio
        page = _FakeCampaignPage()
        asyncio.run(MODULE._select_taste_character_campaign(page, {"campaign_value": "835"}))
        self.assertEqual(page.clicked, ["835"])

    def test_null_campaign_value_clicks_the_non_participation_radio(self) -> None:
        import asyncio
        page = _FakeCampaignPage()
        asyncio.run(MODULE._select_taste_character_campaign(page, {"campaign_value": None}))
        self.assertEqual(page.clicked, ["on"])

    def test_missing_campaign_value_key_also_defaults_to_non_participation(self) -> None:
        import asyncio
        page = _FakeCampaignPage()
        asyncio.run(MODULE._select_taste_character_campaign(page, {}))
        self.assertEqual(page.clicked, ["on"])
