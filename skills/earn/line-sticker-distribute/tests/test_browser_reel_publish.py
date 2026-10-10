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

import json
import time
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

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


class PublishFocusesTheTabTest(unittest.TestCase):
    """Root cause (2026-10-07, measured): under launchd, 3 of 4 natural
    line-sticker-distribute runs ended reached='shared-unconfirmed',
    published=False -- IG registered the share click but the reel never
    showed up in the profile-href poll before the budget ran out. The same
    post_reel.py call made interactively (agent's Claude session, browser
    window visibly focused) always completed. post_reel.py's own compiled
    bytecode (~/.agents/skills/ig-reels-poster/scripts/__pycache__/
    post_reel.cpython-314.pyc) never references bring_front/focus/
    bringToFront/setFocusEmulationEnabled anywhere in its code objects --
    confirmed by walking co_names/co_consts. A launchd-spawned tab has no
    real OS window focus, so Chromium treats it as a background/occluded
    tab and throttles it (rAF, timers, video pipeline), slowing IG's own
    async upload/processing past post_reel.py's poll window. cdp.py already
    ships a `focus` command (Page.bringToFront + Emulation.
    setFocusEmulationEnabled + Page.setWebLifecycleState('active')) used by
    ig-account-warmer for the identical "background tab" problem -- the
    sibling precedent this loop skipped. publish() must call it on the new
    tab before doing anything else, so the tab never runs throttled
    regardless of real window/OS focus.
    """

    def test_focuses_new_tab_before_login_and_before_post_reel_subprocess(self):
        calls = []

        def fake_cdp(tid_cmd, *, cdp_host, cdp_port, timeout=60):
            calls.append(tid_cmd[0])
            if tid_cmd[0] == "new":
                return "TID123"
            return ""

        def fake_ensure_logged_in(tid, *, cdp_host, cdp_port, creds):
            calls.append("ensure_logged_in")

        fake_result = {"reached": "published", "published": True}

        def fake_run(args, **kwargs):
            calls.append("post_reel_subprocess")
            return mock.Mock(returncode=0, stdout=json.dumps(fake_result), stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            creds_path = Path(tmp) / "ig-handle.json"
            creds_path.write_text(json.dumps({"username": "handle", "pw": "x", "email": "a@b.com"}))

            with mock.patch.object(brp, "_cdp", side_effect=fake_cdp), \
                 mock.patch.object(brp, "_ensure_logged_in", side_effect=fake_ensure_logged_in), \
                 mock.patch.object(brp, "_lease", return_value="http://localhost:9222"), \
                 mock.patch.object(brp, "_release"), \
                 mock.patch.object(brp.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(Path, "expanduser", return_value=creds_path):
                result = brp.publish(
                    video=Path("video.mp4"), caption_file=Path("cap.txt"),
                    handle="handle", browser_identity="instagram:capafy-provision", live=True,
                )

        self.assertEqual(result, fake_result)
        self.assertIn("focus", calls, "new tab must be focus-emulated before any step runs")
        self.assertLess(
            calls.index("focus"), calls.index("ensure_logged_in"),
            "focus must happen before login, not only before the post_reel subprocess",
        )
        self.assertLess(
            calls.index("focus"), calls.index("post_reel_subprocess"),
            "focus must happen before the post_reel subprocess that clicks シェア",
        )


class ShareWatchTest(unittest.TestCase):
    """2026-10-09: four attempts, three different sets, every share stuck on 'シェア中'. One screenshot
    before and after cannot say whether the page is frozen or still working, so the publisher
    photographs the tab every few seconds while post_reel runs (observation only)."""

    def test_the_tab_is_photographed_while_post_reel_runs_and_never_breaks_the_post(self):
        shots = []

        def fake_cdp(tid_cmd, *, cdp_host, cdp_port, timeout=60):
            if tid_cmd[0] == "new":
                return "TID123"
            if tid_cmd[0] == "shot":
                shots.append(tid_cmd[2])
                raise brp.BrowserReelError("shot failed")  # an observer failure must not stop the post
            return ""

        def fake_run(args, **kwargs):
            deadline = time.monotonic() + 5  # post_reel "runs" until several photos exist (bounded)
            while len(shots) < 3 and time.monotonic() < deadline:
                time.sleep(0.02)
            return mock.Mock(returncode=0, stdout=json.dumps({"published": True}), stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            creds_path = Path(tmp) / "ig-handle.json"
            creds_path.write_text(json.dumps({"username": "handle", "pw": "x", "email": "a@b.com"}))
            with mock.patch.object(brp, "_cdp", side_effect=fake_cdp), \
                 mock.patch.object(brp, "_ensure_logged_in"), \
                 mock.patch.object(brp, "_lease", return_value="http://fake-host:1234"), \
                 mock.patch.object(brp, "_release"), \
                 mock.patch.object(brp, "WATCH_INTERVAL_SECONDS", 0.05), \
                 mock.patch.object(brp, "WATCH_DIR", Path(tmp) / "watch"), \
                 mock.patch.object(brp.subprocess, "run", side_effect=fake_run), \
                 mock.patch.object(Path, "expanduser", return_value=creds_path):
                result = brp.publish(video=Path("v.mp4"), caption_file=Path("c.txt"),
                                     handle="handle", browser_identity="instagram:x", live=True)
        self.assertEqual(result, {"published": True})
        self.assertGreaterEqual(len(shots), 3)
        names = {Path(p).name for p in shots}
        self.assertTrue(names <= {f"{i:02d}.png" for i in range(brp.WATCH_SLOTS)}, names)


if __name__ == "__main__":
    unittest.main()
