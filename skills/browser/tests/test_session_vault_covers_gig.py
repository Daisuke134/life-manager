"""The keepalive must warm the browser the gig lanes actually use.

Measured 2026-09-07: `/mypage` and `/offers/add/<id>` both redirected to Coconala's top page on the
gig browser while :9222 stayed logged in. The keepalive only ever warmed :9222, so it reported
healthy for four days while Coconala applied to nothing. :9222 and the gig browser were once one
process behind a proxy, so warming one warmed both; when they were split, nothing extended this
roster.

The lane itself said what was wrong on every listing -- 「公式ページで募集受付中の応募フォームを
確認できなかったためです」-- but nothing tied that sentence to the session.

Run: python3 -m pytest skills/browser/tests/test_session_vault_covers_gig.py
"""

from pathlib import Path

import pytest

TICK = Path(__file__).resolve().parents[1] / "scripts" / "session_vault_tick.sh"
SOURCE = TICK.read_text(encoding="utf-8")


def test_the_gig_browser_is_warmed_at_all():
    assert "coconala:kosuke" in SOURCE, (
        "the gig lanes work in their own browser; warming only :9222 leaves that session to rot"
    )


def test_it_warms_the_leased_port_not_a_hardcoded_one():
    """browser-guard owns the port. Hardcoding one is how :9222 and the gig browser drifted apart."""
    gig = SOURCE.split("gig browser (coconala:kosuke)", 1)[1]
    assert 'SESSION_VAULT_PORT="$GIG_PORT"' in gig
    assert ":9223" not in gig.split("per-account clip browsers", 1)[0].replace("(coconala:kosuke :9223", "")


def test_it_resolves_the_port_without_taking_the_exclusive_lease():
    """Gating on `acquire` meant the healer almost never ran.

    Measured 2026-09-07 07:57:18: "lease BUSY ... skipping this tick", one second after the only
    pass that got through. The four gig lanes hold that lease nearly all the time -- five isolated
    contexts were live during the same measurement -- so the one job that can heal a dead session
    was the one job that never got to run.
    """
    gig = SOURCE.split("gig browser (coconala:kosuke)", 1)[1].split("per-account clip browsers", 1)[0]
    assert "status coconala:kosuke" in gig
    assert "acquire coconala:kosuke" not in gig


def test_no_lane_waits_for_this_and_this_waits_for_no_lane():
    """dump/keepalive/relogin open their own tab; the lanes work in their own contexts."""
    gig = SOURCE.split("gig browser (coconala:kosuke)", 1)[1].split("per-account clip browsers", 1)[0]
    assert "release coconala:kosuke" not in gig
    assert "not reachable, skipping" in gig


def test_a_dead_gig_session_alerts_and_says_what_it_costs():
    gig = SOURCE.split("gig browser (coconala:kosuke)", 1)[1].split("per-account clip browsers", 1)[0]
    assert "telegram_notify" in gig
    assert "GIG browser" in gig
    assert "every Coconala application stops" in gig


def test_a_provider_access_denial_alerts_without_claiming_login_expiry():
    gig = _gig_block()
    assert "GIG_DENIED" in gig
    assert "access_denied" in gig
    assert "provider access denied" in gig


@pytest.mark.parametrize("url", ["https://coconala.com/mypage/dashboard"])
def test_it_checks_a_page_that_requires_login(url):
    """A public page cannot tell logged in from logged out: Coconala sends anonymous users to /."""
    gig = SOURCE.split("gig browser (coconala:kosuke)", 1)[1].split("per-account clip browsers", 1)[0]
    assert url in gig


def _gig_block() -> str:
    return SOURCE.split("gig browser (coconala:kosuke)", 1)[1].split("per-account clip browsers", 1)[0]


def test_the_gig_session_is_banked_not_only_warmed():
    """Warming keeps a live session alive; only dump refreshes what the lane restores from.

    Measured 2026-09-07: vault/gig-daily-driver/auth-state.json was last written 2026-09-02 02:17,
    the day Coconala's applications stopped. The lane rehydrates its isolated contexts from that
    file, so it was restoring expired cookies every wake and landing on /login.
    """
    assert 'python3 "$V" dump' in _gig_block()


def test_the_dump_targets_the_gig_vault_not_the_default():
    """SESSION_VAULT_DIR defaults to ~/.cloak/vault/daily-driver -- the human browser's jar.

    Every dump this tick ever ran wrote there, which is why the gig vault went stale unnoticed.
    """
    gig = _gig_block()
    assert 'SESSION_VAULT_DIR="$GIG_VAULT"' in gig
    assert 'GIG_VAULT="$HOME/.cloak/vault/gig-daily-driver"' in gig


def test_banking_happens_before_warming():
    """Dump captures what is there now; warming afterwards keeps it from expiring."""
    gig = _gig_block()
    assert gig.index('python3 "$V" dump') < gig.index('python3 "$V" keepalive')
