from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "adversary-daily.sh"


def test_scheduled_adversary_is_a_codex_cli_pipeline():
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"$CODEX_BIN" exec --ephemeral' in source
    assert "claude -p" not in source
