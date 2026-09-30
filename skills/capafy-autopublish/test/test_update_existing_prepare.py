from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "daily_loop.sh"


def test_update_existing_uses_fenced_deterministic_prepare() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'd.get("action") == "update_existing"' in source
    assert "UPDATE_EXPECTED_FROM_VERSION" in source
    assert 'EXPECTED_UPDATE_ID="$UPDATE_EXPECTED_ID"' in source
    assert 'EXPECTED_UPDATE_FROM_VERSION="$UPDATE_EXPECTED_FROM_VERSION"' in source
