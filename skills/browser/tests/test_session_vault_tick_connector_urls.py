from pathlib import Path


TICK = Path(__file__).resolve().parents[1] / "scripts" / "session_vault_tick.sh"


def test_session_vault_tick_warms_connector_provider_sessions():
    source = TICK.read_text(encoding="utf-8")
    assert '"https://connpass.com/dashboard/"' in source
    assert '"https://luma.com/home"' in source
