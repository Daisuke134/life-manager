import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from recycle_idle_browsers import recycle_targets, should_recycle  # noqa: E402

REG = {"identity": [
    {"id": "interactive:dais", "profile": "~/.cloak/profiles/daily-driver", "launched_by": "ai.anicca.dais-browser"},
    {"id": "lancers:dais", "profile": "~/.local/state/anicca/lancers/browser-profile", "launched_by": "ai.anicca.lancers-revenue-browser"},
    {"id": "colors:owner", "profile": "~/.cloak/profiles/colors", "launched_by": "skills/browser/ensure_provision_browser.sh"},
    {"id": "x:anicca", "profile": "~/.cloak/profiles/x-repost-daily", "launched_by": "~/loops/current/skills/browser/ensure_provision_browser.sh"},
]}


def test_only_launchd_keepalive_owners_and_never_dais_chrome():
    assert [t["id"] for t in recycle_targets(REG)] == ["lancers:dais"]


def test_recycles_only_after_max_age():
    assert should_recycle(5 * 3600, 4 * 3600) is True
    assert should_recycle(3 * 3600, 4 * 3600) is False
    assert should_recycle(None, 4 * 3600) is False
