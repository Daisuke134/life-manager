#!/usr/bin/env python3
"""Focused test for browser_reel_publish._dismiss_consent_interstitial.

Root cause (2026-10-07): the line-sticker-distribute sell loop's browser_reel
transport failed on every natural run with outcome "file chooser load failed",
reached stuck at "composer". Screenshots from the failed runs
(/tmp/ig-reels-shots/1-composer.png, 2-loadfail.png) show the real cause: an
Instagram "Instagramを利用するには次の項目に同意が必要です" GDPR-style consent
modal was covering the whole page. document.body.innerText still contains the
obscured profile's "プロフィールを編集" text (so _ensure_logged_in's
already-logged-in check passed), but the real composer never opened, so
post_reel.py's file-chooser click had nothing to click -- a 10s timeout later,
"file chooser load failed". This test locks in the eval_fn contract
_dismiss_consent_interstitial relies on, without a live browser.
"""
from __future__ import annotations

from pathlib import Path
import sys
import unittest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import browser_reel_publish as brp  # noqa: E402


class DismissConsentInterstitialTest(unittest.TestCase):
    def test_no_dialog_present_is_a_no_op(self):
        calls = []

        def fake_eval(js: str) -> str:
            calls.append(js)
            return '"none"'

        dismissed = brp._dismiss_consent_interstitial(
            "tid", cdp_host="h", cdp_port="1", eval_fn=fake_eval,
        )
        self.assertFalse(dismissed)
        self.assertEqual(len(calls), 1, "must not try to close a dialog that was never found")

    def test_dialog_present_toggles_agrees_and_closes(self):
        calls = []

        def fake_eval(js: str) -> str:
            calls.append(js)
            return '"agreed"' if len(calls) == 1 else '"closed"'

        dismissed = brp._dismiss_consent_interstitial(
            "tid", cdp_host="h", cdp_port="1", eval_fn=fake_eval,
        )
        self.assertTrue(dismissed)
        self.assertEqual(len(calls), 2, "must run the check+agree step then the close-confirmation step")

    def test_agree_button_still_disabled_is_reported_not_silently_dropped(self):
        calls = []

        def fake_eval(js: str) -> str:
            calls.append(js)
            return '"no-agree-btn"'

        dismissed = brp._dismiss_consent_interstitial(
            "tid", cdp_host="h", cdp_port="1", eval_fn=fake_eval,
        )
        self.assertFalse(dismissed)
        self.assertEqual(len(calls), 1, "must not click a close button that was never reached")


if __name__ == "__main__":
    unittest.main()
