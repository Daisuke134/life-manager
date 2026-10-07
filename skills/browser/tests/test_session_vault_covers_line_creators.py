"""The keepalive must warm the LINE Creators Market browser the sticker factory submits through.

Measured 2026-10-06: the line-creators profile had silently dropped its creator.line.me session
(redirect to access.line.me login) while the vault still held a 30h-old good copy. The sticker
factory, the review readback and the payout registration all stopped behind it until the vault was
restored by hand. No keepalive covered that browser, so nothing noticed.

Run: python3 -m pytest skills/browser/tests/test_session_vault_covers_line_creators.py
"""

from pathlib import Path

TICK = Path(__file__).resolve().parents[1] / "scripts" / "session_vault_tick.sh"
SOURCE = TICK.read_text(encoding="utf-8")


def _block():
    return SOURCE.split("line-creators browser", 1)[1]


def test_the_line_creators_browser_is_warmed_at_all():
    assert "line-creators:dais" in SOURCE


def test_it_resolves_the_port_without_taking_the_exclusive_lease():
    block = _block()
    assert "status line-creators:dais" in block
    assert "acquire line-creators:dais" not in block
    assert 'SESSION_VAULT_PORT="$LC_PORT"' in block


def test_it_dumps_into_its_own_vault_and_warms_an_authed_page():
    block = _block()
    assert ".cloak/vault/line-creators" in block
    assert "https://creator.line.me/my/" in block


def test_a_dead_session_is_restored_from_the_vault_before_alerting():
    block = _block()
    restore_at = block.index(" restore")
    alert_at = block.index("telegram_notify")
    assert restore_at < alert_at
    assert "sticker factory" in block
