#!/usr/bin/env python3
"""Focused tests for the line-sticker-distribute sell loop.

Covers the three contract points Dais asked for:
  - render only ever selects an on-sale (販売中) set
  - the caption always carries the store URL
  - the per-slot ledger fence blocks a duplicate post
plus the config-driven empty-target no-op and the parent dir's REPO_ROOT fix.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import caption_compose  # noqa: E402
import due_slot  # noqa: E402
import line_sticker_distribute as distribute  # noqa: E402
import line_sticker_distribute_ledger as ledger  # noqa: E402
import pick_set  # noqa: E402


def _write_set(root: Path, set_id: str, *, state_observed: str, clip_ids: list[str]) -> None:
    set_dir = root / set_id
    clips_dir = set_dir / "clips"
    clips_dir.mkdir(parents=True)
    for clip_id in clip_ids:
        (clips_dir / f"{clip_id}.mp4").write_bytes(b"fake-mp4")
    (set_dir / "creators-item.json").write_text(json.dumps({
        "state_observed": state_observed,
        "title_ja": f"{set_id}-title",
        "store_url": f"https://store.line.me/stickershop/product/{set_id}/ja",
    }), encoding="utf-8")
    (set_dir / "listing.json").write_text(json.dumps({
        "title": {"ja": f"{set_id}-title"},
        "character_name": "Test Otter",
    }), encoding="utf-8")


class PickSetOnSaleOnlyTest(unittest.TestCase):
    def test_skips_sets_not_on_sale(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_set(root, "set-review", state_observed="審査中", clip_ids=["a"])
            _write_set(root, "set-live", state_observed="販売中", clip_ids=["a", "b"])
            sets = pick_set.load_on_sale_sets(root)
            self.assertEqual([s["set_id"] for s in sets], ["set-live"])

    def test_no_sets_on_sale_returns_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_set(root, "set-review", state_observed="審査中", clip_ids=["a"])
            sets = pick_set.load_on_sale_sets(root)
            self.assertIsNone(pick_set.choose_set(sets, "any-seed"))


class CaptionIncludesStoreUrlTest(unittest.TestCase):
    def test_caption_always_contains_store_url(self):
        store_url = "https://store.line.me/stickershop/product/48077815/ja"
        caption = caption_compose.build_caption(
            hook="テストフック",
            title_ja="毎日使えるカワウソスタンプ",
            use_cases=["感謝"],
            store_url=store_url,
            hashtags=["#LINEスタンプ"],
        )
        self.assertIn(store_url, caption)

    def test_rejects_non_https_store_url(self):
        with self.assertRaises(ValueError):
            caption_compose.build_caption(
                hook="h", title_ja="t", use_cases=[], store_url="http://insecure",
                hashtags=["#x"],
            )

    def test_hashtags_never_contain_spaces(self):
        tags = caption_compose.pick_hashtags("Stardust Otter", seed_index=0)
        for tag in tags:
            self.assertNotIn(" ", tag)

    def test_include_link_false_omits_the_store_url(self):
        store_url = "https://store.line.me/stickershop/product/48077815/ja"
        caption = caption_compose.build_caption(
            hook="テストフック", title_ja="毎日使えるカワウソスタンプ", use_cases=[],
            store_url=store_url, hashtags=["#LINEスタンプ"], include_link=False,
        )
        self.assertNotIn(store_url, caption)
        self.assertIn("LINEスタンプで『毎日使えるカワウソスタンプ』と検索", caption)
        # a missing/non-https store_url is fine when no link is requested
        caption_compose.build_caption(
            hook="h", title_ja="t", use_cases=[], store_url="", hashtags=["#x"], include_link=False,
        )


class LedgerFenceTest(unittest.TestCase):
    def test_duplicate_post_for_same_slot_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ledger.json"
            key = "lane-a-2026-10-07T00:00:00Z"
            self.assertFalse(ledger.is_published(ledger_path, key))
            ledger.record(ledger_path, key, {"status": "published", "post_id": "p1"})
            self.assertTrue(ledger.is_published(ledger_path, key))
            # a different slot for the same lane is untouched
            self.assertFalse(ledger.is_published(ledger_path, "lane-a-2026-10-07T03:00:00Z"))

    def test_find_due_account_skips_already_published_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ledger.json"
            accounts = [{
                "lane_id": "lane-a", "platform": "tiktok", "integration_id": "x",
                "cadence_jst": ["00:00"], "timezone": "UTC",
            }]
            from datetime import datetime, timezone
            now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
            slot_at = due_slot.due_slot_iso(now, "UTC", ["00:00"])
            ledger.record(ledger_path, f"lane-a-{slot_at}", {"status": "published"})
            self.assertIsNone(distribute.find_due_account(accounts, ledger_path, now))

    def test_find_due_account_backs_off_after_a_recent_failure(self):
        """Root cause (2026-10-07, @stardust_doubutsu 20:18 JST slot): a
        browser_reel share can hang on Instagram's side and never reconcile
        (reached=shared-unconfirmed). Instagram readback 28min and even
        several hours later still showed no new reel -- a real, if
        intermittent, publish failure, not just a slow one. Retrying the
        exact same lane/slot again seconds later (every launchd wake inside
        the same ~2.5h cadence window) hammers a brand-new account with
        repeated real share attempts. A short cooldown after a failed
        attempt gives Instagram's own processing room before the next try,
        without blocking the slot past its cadence window."""
        with tempfile.TemporaryDirectory() as tmp:
            ledger_path = Path(tmp) / "ledger.json"
            accounts = [{
                "lane_id": "lane-a", "platform": "instagram", "transport": "browser_reel",
                "handle": "x", "browser_identity": "instagram:x",
                "cadence_jst": ["00:00"], "timezone": "UTC",
            }]
            from datetime import datetime, timedelta, timezone
            now = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
            slot_at = due_slot.due_slot_iso(now, "UTC", ["00:00"])
            key = f"lane-a-{slot_at}"
            ledger.record(ledger_path, key, {
                "status": "failed", "reason": "browser_reel publish did not reconcile",
                "attempted_at": now.isoformat(),
            })
            # immediately after the failure: still in cooldown, not due again
            self.assertIsNone(distribute.find_due_account(accounts, ledger_path, now))
            just_inside_cooldown = now + timedelta(minutes=distribute.RETRY_COOLDOWN_MINUTES - 1)
            self.assertIsNone(distribute.find_due_account(accounts, ledger_path, just_inside_cooldown))
            # once the cooldown has elapsed, the same still-unpublished slot is due again
            past_cooldown = now + timedelta(minutes=distribute.RETRY_COOLDOWN_MINUTES + 1)
            due = distribute.find_due_account(accounts, ledger_path, past_cooldown)
            self.assertIsNotNone(due)
            self.assertEqual(due[2], key)


class TransportValidationTest(unittest.TestCase):
    def test_browser_reel_requires_handle_and_browser_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "accounts.json"
            config_path.write_text(json.dumps({
                "schema_version": 1, "timezone": "Asia/Tokyo",
                "accounts": [{
                    "lane_id": "x", "platform": "instagram", "transport": "browser_reel",
                    "cadence_jst": ["08:00"],
                }],
            }), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                distribute.load_accounts(config_path)

    def test_postiz_still_requires_integration_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "accounts.json"
            config_path.write_text(json.dumps({
                "schema_version": 1, "timezone": "Asia/Tokyo",
                "accounts": [{"lane_id": "x", "platform": "tiktok", "cadence_jst": ["08:00"]}],
            }), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                distribute.load_accounts(config_path)

    def test_valid_browser_reel_account_loads_with_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "accounts.json"
            config_path.write_text(json.dumps({
                "schema_version": 1, "timezone": "Asia/Tokyo",
                "accounts": [{
                    "lane_id": "x", "platform": "instagram", "transport": "browser_reel",
                    "handle": "stardust_doubutsu", "browser_identity": "instagram:capafy-provision",
                    "link_in_caption": False, "cadence_jst": ["08:00"],
                }],
            }), encoding="utf-8")
            accounts = distribute.load_accounts(config_path)
            self.assertEqual(accounts[0]["transport"], "browser_reel")
            self.assertFalse(accounts[0]["link_in_caption"])

    def test_real_shipped_accounts_config_loads_cleanly(self):
        repo_root = Path(__file__).resolve().parents[4]
        real_config = repo_root / "config" / "line-sticker-distribute-accounts.json"
        accounts = distribute.load_accounts(real_config)
        for account in accounts:
            self.assertIn(account["transport"], ("postiz", "browser_reel"))
            self.assertNotIn(account.get("handle"), (None, "anicca.jp8", "aniccajp", "aniccajp2",
                                                       "anicca.bochi"))


class EmptyAccountsIsNoOpTest(unittest.TestCase):
    def test_empty_accounts_list_is_a_no_op_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "accounts.json"
            config_path.write_text(json.dumps({
                "schema_version": 1, "timezone": "Asia/Tokyo", "accounts": [],
            }), encoding="utf-8")
            result = distribute.run_pass(
                accounts_config=config_path,
                line_sticker_state_root=Path(tmp) / "line-sticker",
                state_root=Path(tmp) / "state",
                now=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
                dry_run=True,
                caption_hook_override=None,
            )
            self.assertEqual(result, {"state": "no_targets_configured"})

    def test_rejects_shared_brand_style_malformed_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "accounts.json"
            config_path.write_text(json.dumps({
                "schema_version": 1, "timezone": "Asia/Tokyo",
                "accounts": [{"lane_id": "x"}],
            }), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                distribute.load_accounts(config_path)


class DueSlotTest(unittest.TestCase):
    def test_due_slot_is_none_before_first_slot_of_the_day(self):
        from datetime import datetime, timezone
        now = datetime(2026, 10, 7, 0, 30, tzinfo=timezone.utc)
        self.assertIsNone(due_slot.due_slot_iso(now, "UTC", ["08:15", "20:15"]))

    def test_due_slot_picks_latest_passed_slot(self):
        from datetime import datetime, timezone
        now = datetime(2026, 10, 7, 21, 0, tzinfo=timezone.utc)
        slot = due_slot.due_slot_iso(now, "UTC", ["08:15", "20:15"])
        self.assertEqual(slot, "2026-10-07T20:15:00Z")


if __name__ == "__main__":
    unittest.main()
