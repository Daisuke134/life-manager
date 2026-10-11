from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WORKER = ROOT / "skills/writer-agent/scripts/article-resume-pending.sh"


def test_adopted_run_with_publication_state_can_reach_foreground_publication():
    source = WORKER.read_text(encoding="utf-8")
    assert 'if [ "$ADOPTION_ACTIVE" -eq 1 ]' in source
    assert 'if [ -f "$GENERATION_RUN_DIR/gates/publication-state.json" ]; then' in source
    assert 'PUBLICATION_HANDOFF_READY=1' in source
    assert 'repair-unbound-force' in source


def test_quality_scan_loads_its_real_sibling_modules_from_an_unrelated_cwd(tmp_path):
    import os
    import subprocess
    import sys

    source = WORKER.read_text(encoding="utf-8")
    marker = 'PENDING_QUALITY_RUN_ID="$(python3 - "$STATE_DIR" "$QUALITY_LEDGER" "$QUALITY_FEEDBACK_CONTROL" <<\'PY\'\n'
    scan = source.split(marker, 1)[1].split("\nPY\n)", 1)[0]
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-", str(tmp_path / "state"), str(tmp_path / "ledger.jsonl"),
         str(ROOT / "skills/writer-agent/scripts/quality_feedback_recovery.py")],
        input=scan, text=True, capture_output=True, cwd=tmp_path, env=env, timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
