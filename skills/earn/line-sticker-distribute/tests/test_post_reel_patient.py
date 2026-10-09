#!/usr/bin/env python3
"""post_reel_patient.patch: after シェア is clicked, do not leave the page until 「シェア中」 clears.

Root cause (2026-10-09, six watcher photos): post_reel polls the profile ~12s after the share
click by navigating the same tab away. On a slow host the upload takes longer than that, so the
navigation cancels it and every attempt ends 'shared-unconfirmed' with the profile count
unchanged. The fake module below stands in for post_reel (shot / ev / cdp.navigate).
"""
from __future__ import annotations

from pathlib import Path
import sys
import types
import unittest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import post_reel_patient as prp  # noqa: E402


def fake_module(texts):
    calls = []
    texts = list(texts)

    def ev(tid, expr):
        calls.append("ev")
        return texts.pop(0) if len(texts) > 1 else texts[0]

    mod = types.SimpleNamespace(
        shot=lambda tid, name: calls.append(f"shot:{name}"),
        ev=ev,
        cdp=types.SimpleNamespace(navigate=lambda tid, url: calls.append(f"nav:{url}")),
    )
    return mod, calls


class WaitForShareTest(unittest.TestCase):
    def test_navigation_waits_until_sharing_dialog_clears(self):
        mod, calls = fake_module(["シェア中", "シェア中", "リールをシェアしました"])
        prp.patch(mod, wait_seconds=60, sleep=lambda s: calls.append("sleep"))
        mod.shot("t", "6-sharing")
        mod.cdp.navigate("t", "https://www.instagram.com/h/")
        self.assertEqual(calls[-1], "nav:https://www.instagram.com/h/")
        self.assertEqual(calls.count("sleep"), 2)  # waited out two spinner reads, then went

    def test_navigation_before_share_is_not_delayed(self):
        mod, calls = fake_module(["シェア中"])
        prp.patch(mod, wait_seconds=60, sleep=lambda s: calls.append("sleep"))
        mod.cdp.navigate("t", "https://www.instagram.com/")
        self.assertEqual(calls, ["nav:https://www.instagram.com/"])

    def test_gives_up_after_the_budget_and_still_navigates(self):
        mod, calls = fake_module(["シェア中"])
        clock = iter(range(0, 1000, 20))
        prp.patch(mod, wait_seconds=60, sleep=lambda s: None, clock=lambda: next(clock))
        mod.shot("t", "6-sharing")
        mod.cdp.navigate("t", "https://www.instagram.com/h/")
        self.assertEqual(calls[-1], "nav:https://www.instagram.com/h/")

    def test_unreadable_page_does_not_block_the_post(self):
        mod, calls = fake_module(["x"])
        mod.ev = lambda tid, expr: (_ for _ in ()).throw(RuntimeError("cdp down"))
        prp.patch(mod, wait_seconds=60, sleep=lambda s: None)
        mod.shot("t", "6-sharing")
        mod.cdp.navigate("t", "https://www.instagram.com/h/")
        self.assertEqual(calls[-1], "nav:https://www.instagram.com/h/")


if __name__ == "__main__":
    unittest.main()
