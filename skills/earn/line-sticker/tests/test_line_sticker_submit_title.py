"""A duplicate title must turn into a distinctive retry, not a 15s OK-dialog timeout.

Measured 2026-10-07 01:41Z: set-005 "ふわふわペンギンの気持ちスタンプ" hit Creators Market's inline
「既に存在するタイトルのため利用できません」 before any confirm dialog, so the submit waited for an
OK button that never came and the wake ended effect-unknown.
"""
import asyncio
import sys
import itertools
import datetime
import unittest
from unittest.mock import AsyncMock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import line_sticker_submit as MODULE  # noqa: E402
import features_readback as FEATURES  # noqa: E402


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

    def test_no_character_name_falls_back_to_a_numbered_title(self) -> None:
        # set-015 (2026-10-08): character_name was empty, so a duplicate title could never be retried
        # and the factory stalled on "既に存在するタイトルのため利用できません".
        out = MODULE._retitle({"title": {"ja": "星くずカワウソの毎日返事【文字入り】", "en": "Stardust Otter Daily Reply (with text)"}})
        self.assertIsNotNone(out)
        # Over the limit with vol.2 added: the words before 【文字入り】 give way, the mark stays whole.
        self.assertTrue(out["title"]["ja"].endswith("【文字入り】 vol.2"), out["title"]["ja"])
        self.assertTrue(out["title"]["en"].endswith("(with text) vol.2"), out["title"]["en"])
        self.assertTrue(all(MODULE._title_units(t) <= MODULE.TITLE_MAX for t in out["title"].values()))

    def test_a_numbered_title_that_is_taken_again_counts_up(self) -> None:
        listing = {"title": {"ja": "もちハム vol.2", "en": "Mochi vol.2"}}
        self.assertEqual(MODULE._retitle(listing)["title"], {"ja": "もちハム vol.3", "en": "Mochi vol.3"})

    def test_a_long_title_is_clamped_to_make_room_for_the_number(self) -> None:
        out = MODULE._retitle({"title": {"ja": "とても長いスタンプのタイトルがここに入ります毎日使える", "en": "A very long sticker title that fills the limit"}})
        self.assertTrue(all(MODULE._title_units(t) <= MODULE.TITLE_MAX for t in out["title"].values()))
        self.assertTrue(all(t.endswith("vol.2") for t in out["title"].values()))


class TitleAttempts(unittest.TestCase):
    """The order of titles tried when Creators Market says a title is already taken."""

    LISTING = {"character_name": "Stardust Otter",
               "title": {"ja": "星くずカワウソの毎日返事【文字入り】", "en": "Stardust Otter Daily Reply (with text)"}}

    def test_original_then_numbered_forms_without_end(self) -> None:
        # Dais 2026-10-12: no cap. Only a "title already taken" answer moves to the next number (any
        # other error stops the attempt), so counting until a free volume is found cannot loop.
        attempts = list(itertools.islice(MODULE._title_attempts(self.LISTING), 101))
        self.assertEqual(attempts[0]["title"], self.LISTING["title"])
        self.assertTrue(attempts[1]["title"]["ja"].endswith("【文字入り】 vol.2"), attempts[1]["title"]["ja"])
        self.assertTrue(attempts[2]["title"]["ja"].endswith("【文字入り】 vol.3"), attempts[2]["title"]["ja"])
        self.assertTrue(attempts[100]["title"]["ja"].endswith("vol.101"), attempts[100]["title"]["ja"])
        self.assertEqual(len({a["title"]["ja"] for a in attempts}), 101)

    def test_without_a_name_it_numbers_the_same_way(self) -> None:
        attempts = list(itertools.islice(MODULE._title_attempts({"title": {"ja": "もちハム", "en": "Mochi"}}), 3))
        self.assertEqual(attempts[0]["title"], {"ja": "もちハム", "en": "Mochi"})
        self.assertTrue(attempts[1]["title"]["ja"].endswith("vol.2"))


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



class SeriesDepth(unittest.TestCase):
    def test_a_long_running_series_still_finds_a_free_volume(self) -> None:
        # 2026-10-12: set-031 "星くずカワウソの毎日返事【文字入り】" found the base and vol.2-vol.5 taken by our
        # own earlier sets and crashed every wake with TitleTaken; top sellers number deep (ちいかわ５).
        titles = [a["title"]["ja"] for a in itertools.islice(MODULE._title_attempts(
            {"title": {"ja": "星くずカワウソの毎日返事【文字入り】", "en": "Stardust Otter Replies (with text)"}}), 40)]
        self.assertTrue(any("vol.20" in t for t in titles), titles[-3:])


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
    def __init__(self, clicked: list[str], value: str, *, checked_after_click: bool = True) -> None:
        self._clicked = clicked
        self._value = value
        self._checked_after_click = checked_after_click

    async def count(self) -> int:
        return 1

    @property
    def first(self):
        return self

    async def evaluate(self, script: str) -> None:
        self._clicked.append(self._value)

    async def is_checked(self) -> bool:
        return self._value in self._clicked and self._checked_after_click


class _FakeMissingRadio:
    async def count(self) -> int:
        return 0


class _FakeSelectLocator:
    async def count(self) -> int:
        return 0


class _FakeCampaignPage:
    """Mimics only what ``_select_taste_character_campaign`` touches: no real <select>s, and one
    radio per requested value (every value in LINE's shared feature-campaign radio group "exists").
    """

    def __init__(self, *, missing_values=(), unchecked_values=()) -> None:
        self.clicked: list[str] = []
        self.missing_values = set(missing_values)
        self.unchecked_values = set(unchecked_values)

    def locator(self, selector: str, *a, **k):
        if selector == "select":
            return _FakeSelectLocator()
        # 参加しない has no value attribute; the live DOM reports its .value as "on".
        value = selector.split("value='")[1].rstrip("']") if "value='" in selector else "on"
        assert "value='on'" not in selector, "CSS [value='on'] never matches the live radio"
        if value in self.missing_values:
            return _FakeMissingRadio()
        return _FakeRadio(self.clicked, value, checked_after_click=value not in self.unchecked_values)


class SelectCampaign(unittest.TestCase):
    class LivePage:
        def __init__(self) -> None:
            self.closed = False

        async def close(self) -> None:
            self.closed = True

    class Context:
        def __init__(self, live_page) -> None:
            self.live_page = live_page

        async def new_page(self):
            return self.live_page

    class SourcePage:
        def __init__(self, context) -> None:
            self.context = context

    def _selection(self) -> dict:
        order = [f"s{i}" for i in range(40)]
        return {
            "campaign_value": "835",
            "campaign_requirements": {
                "value": "835", "title": "冬を感じるスタンプ", "deadline": "2026-12-04",
                "min_sticker_count": 8, "max_sticker_count": 40, "min_price_jpy": 190,
                "min_theme_stickers": 12,
                "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
            "campaign_theme_ids": order[:12],
            "order": order,
        }

    @staticmethod
    def _listing(**overrides) -> dict:
        return {"count": 40, "price_jpy": 190, **overrides}

    def _select_with_matching_live_terms(self, page, selection, listing) -> None:
        current = {**selection["campaign_requirements"],
                   "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        with patch.object(MODULE, "_read_current_campaign_requirements", new_callable=AsyncMock,
                          return_value=current):
            asyncio.run(MODULE._select_taste_character_campaign(page, selection, listing))

    def test_live_campaign_requirements_are_read_from_official_announcement(self) -> None:
        live_page = self.LivePage()
        source_page = self.SourcePage(self.Context(live_page))
        feature = {
            "value": "835", "title": "冬を感じるスタンプ", "deadline": "2026-12-04",
            "conditions": "個数：8-40個\n金額：￥190～\n冬関連が8個以上",
        }
        with patch.object(FEATURES, "read_features_on_page", new_callable=AsyncMock,
                          return_value={"status": "ok", "features": [feature]}, create=True) as read_features:
            requirements = asyncio.run(MODULE._read_current_campaign_requirements(source_page, "835"))
        read_features.assert_awaited_once_with(live_page, FEATURES.FEATURE_PAGE)
        self.assertTrue(live_page.closed)
        self.assertEqual(requirements["min_price_jpy"], 190)
        self.assertEqual(requirements["min_theme_stickers"], 12)
        self.assertEqual(requirements["title"], "冬を感じるスタンプ")

    def test_missing_live_campaign_fails_closed(self) -> None:
        live_page = self.LivePage()
        source_page = self.SourcePage(self.Context(live_page))
        with patch.object(FEATURES, "read_features_on_page", new_callable=AsyncMock,
                          return_value={"status": "ok", "features": []}, create=True):
            with self.assertRaisesRegex(RuntimeError, "campaign_live_feature_unavailable"):
                asyncio.run(MODULE._read_current_campaign_requirements(source_page, "835"))
        self.assertTrue(live_page.closed)

    def test_selected_campaign_without_submit_eligibility_facts_fails_closed(self) -> None:
        import asyncio
        page = _FakeCampaignPage()
        with self.assertRaisesRegex(RuntimeError, "campaign_requirements_missing"):
            asyncio.run(MODULE._select_taste_character_campaign(page, {"campaign_value": "835"}))

    def test_selected_campaign_with_stale_conditions_fails_closed(self) -> None:
        import asyncio
        page = _FakeCampaignPage()
        selection = self._selection()
        selection["campaign_requirements"]["observed_at"] = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
        ).isoformat()
        with self.assertRaisesRegex(RuntimeError, "campaign_snapshot_stale"):
            asyncio.run(MODULE._select_taste_character_campaign(page, selection, self._listing()))

    def test_selected_campaign_reads_current_official_terms_before_clicking(self) -> None:
        import asyncio
        page = _FakeCampaignPage()
        selection = self._selection()
        current = {**selection["campaign_requirements"], "observed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        with patch.object(MODULE, "_read_current_campaign_requirements", new_callable=AsyncMock,
                          return_value=current, create=True) as read_current:
            asyncio.run(MODULE._select_taste_character_campaign(page, selection, self._listing()))
        read_current.assert_awaited_once_with(page, "835")
        self.assertEqual(page.clicked, ["835"])

    def test_selected_campaign_stops_if_current_official_terms_changed(self) -> None:
        import asyncio
        page = _FakeCampaignPage()
        selection = self._selection()
        current = {**selection["campaign_requirements"], "min_price_jpy": 250}
        with patch.object(MODULE, "_read_current_campaign_requirements", new_callable=AsyncMock,
                          return_value=current, create=True):
            with self.assertRaisesRegex(RuntimeError, "campaign_conditions_changed"):
                asyncio.run(MODULE._select_taste_character_campaign(page, selection, self._listing()))
        self.assertEqual(page.clicked, [])

    def test_selected_campaign_count_and_order_must_match_official_range(self) -> None:
        import asyncio
        page = _FakeCampaignPage()
        with self.assertRaisesRegex(RuntimeError, "campaign_item_count_ineligible"):
            asyncio.run(MODULE._select_taste_character_campaign(
                page, self._selection(), self._listing(count=41)
            ))
        self.assertEqual(page.clicked, [])

    def test_selected_campaign_price_must_meet_official_minimum(self) -> None:
        import asyncio
        page = _FakeCampaignPage()
        with self.assertRaisesRegex(RuntimeError, "campaign_item_price_ineligible"):
            asyncio.run(MODULE._select_taste_character_campaign(
                page, self._selection(), self._listing(price_jpy=189)
            ))
        self.assertEqual(page.clicked, [])

    def test_selected_campaign_rechecks_the_theme_margin_before_clicking(self) -> None:
        import asyncio
        page = _FakeCampaignPage()
        selection = self._selection()
        selection["campaign_theme_ids"] = selection["order"][:11]
        with self.assertRaisesRegex(RuntimeError, "campaign_theme_count_ineligible"):
            asyncio.run(MODULE._select_taste_character_campaign(page, selection, self._listing()))
        self.assertEqual(page.clicked, [])

    def test_a_feature_value_clicks_that_exact_radio_not_on(self) -> None:
        page = _FakeCampaignPage()
        self._select_with_matching_live_terms(page, self._selection(), self._listing())
        self.assertEqual(page.clicked, ["835"])

    def test_a_selected_campaign_with_no_radio_fails_closed(self) -> None:
        page = _FakeCampaignPage(missing_values={"835"})
        with self.assertRaisesRegex(RuntimeError, "campaign_radio_missing"):
            self._select_with_matching_live_terms(page, self._selection(), self._listing())

    def test_a_selected_campaign_that_does_not_check_fails_closed(self) -> None:
        page = _FakeCampaignPage(unchecked_values={"835"})
        with self.assertRaisesRegex(RuntimeError, "campaign_radio_unchecked"):
            self._select_with_matching_live_terms(page, self._selection(), self._listing())

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

    def test_non_participation_radio_missing_fails_closed(self) -> None:
        import asyncio
        page = _FakeCampaignPage(missing_values={"on"})
        with self.assertRaisesRegex(RuntimeError, "campaign_opt_out_radio_missing"):
            asyncio.run(MODULE._select_taste_character_campaign(page, {"campaign_value": None}))

    def test_non_participation_radio_that_does_not_check_fails_closed(self) -> None:
        import asyncio
        page = _FakeCampaignPage(unchecked_values={"on"})
        with self.assertRaisesRegex(RuntimeError, "campaign_opt_out_radio_unchecked"):
            asyncio.run(MODULE._select_taste_character_campaign(page, {}))
