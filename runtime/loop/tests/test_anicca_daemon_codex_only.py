from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DAEMON = ROOT / "runtime" / "anicca-daemon.sh"


def test_supervised_local_loop_requires_codex_and_does_not_start_model_proxy():
    source = DAEMON.read_text(encoding="utf-8")
    assert 'ANICCA_BRAIN="${ANICCA_BRAIN:-codex}"' in source
    assert 'if [ "$ANICCA_BRAIN" != "codex" ]' in source
    assert "ensure_brain ||" not in source
