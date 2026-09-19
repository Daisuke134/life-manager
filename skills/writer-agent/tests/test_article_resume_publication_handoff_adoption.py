from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKER = ROOT / "skills/writer-agent/scripts/article-resume-pending.sh"


def test_adopted_run_with_publication_state_can_reach_foreground_publication():
    source = WORKER.read_text(encoding="utf-8")
    assert 'if [ "$ADOPTION_ACTIVE" -eq 1 ]' in source
    assert 'if [ -f "$GENERATION_RUN_DIR/gates/publication-state.json" ]; then' in source
    assert 'PUBLICATION_HANDOFF_READY=1' in source
