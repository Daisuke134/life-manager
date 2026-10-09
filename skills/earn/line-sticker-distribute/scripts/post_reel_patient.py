#!/usr/bin/env python3
"""post_reel_patient.py -- run ig-reels-poster's post_reel with one change.

post_reel clicks シェア, then ~12s later navigates the SAME tab to the profile to poll for the new
reel. On a slow host the upload ('シェア中') takes longer than that, and the navigation cancels it
(2026-10-09: six watcher photos, profile count unchanged, outcome 'shared-unconfirmed'). This
runner leaves post_reel untouched and only delays a navigation that happens after the share click
until the spinner has cleared (or a budget runs out, after which post_reel proceeds as before).

Usage is post_reel's own: python3 post_reel_patient.py --video V --caption-file C --handle H --tid T [--live]
"""
from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import time

POST_REEL_DIR = Path("~/.agents/skills/ig-reels-poster/scripts").expanduser()
SHARE_WAIT_SECONDS = 150
POLL_SECONDS = 3
SPINNER_TEXT = "シェア中"


def patch(mod, *, wait_seconds=SHARE_WAIT_SECONDS, sleep=time.sleep, clock=time.monotonic) -> None:
    state = {"shared": False}
    real_shot, real_navigate = mod.shot, mod.cdp.navigate

    def shot(tid, name):
        if name == "6-sharing":
            state["shared"] = True
        return real_shot(tid, name)

    def sharing(tid) -> bool:
        try:
            return SPINNER_TEXT in str(mod.ev(tid, "document.body.innerText"))
        except Exception:  # noqa: BLE001 -- an unreadable page must not block the post
            return False

    def navigate(tid, url, *args, **kwargs):
        if state["shared"]:
            deadline = clock() + wait_seconds
            while clock() < deadline and sharing(tid):
                sleep(POLL_SECONDS)
        return real_navigate(tid, url, *args, **kwargs)

    mod.shot, mod.cdp.navigate = shot, navigate


def load_post_reel():
    source = POST_REEL_DIR / "post_reel.py"
    if source.is_file():
        loader = importlib.machinery.SourceFileLoader("post_reel", str(source))
    else:
        loader = importlib.machinery.SourcelessFileLoader(
            "post_reel", str(POST_REEL_DIR / "__pycache__/post_reel.cpython-314.pyc"))
    spec = importlib.util.spec_from_loader("post_reel", loader)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["post_reel"] = mod
    loader.exec_module(mod)
    return mod


def main() -> None:
    mod = load_post_reel()
    patch(mod)
    mod.main()


if __name__ == "__main__":
    main()
