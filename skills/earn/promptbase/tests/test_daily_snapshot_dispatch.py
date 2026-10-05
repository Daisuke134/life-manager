"""Exercise daily.sh with fake commands so no browser or provider is touched."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
DAILY = REPO_ROOT / "skills" / "earn" / "promptbase" / "daily.sh"


def _run_daily(tmp_path, *, occurrence=None, snapshot_rc=0):
    home = tmp_path / "home"
    home.mkdir()
    call_log = tmp_path / "calls.log"
    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_CALL_LOG"
if [ "$1" = "-c" ]; then
  exec "$FAKE_PY_REAL" "$@"
fi
case "$*" in
  *"readback.py"*) exit 0 ;;
  *"packager.py publish-list"*) printf '%s\\n' '{"agents":[]}' ;;
  *"select_next.py"*) printf '%s\\n' '{"slug":"reels-hook-lab","title":"Reels Hook Lab"}' ;;
  *"promptbase_fence_reconcile.py"*"--record-snapshot"*) exit "$FAKE_SNAPSHOT_RC" ;;
  *"gen_examples.py"*) exit 0 ;;
  *"publish.py"*"--confirm"*) exit 0 ;;
  *) exit 97 ;;
esac
""",
        encoding="utf-8",
    )
    fake_python.chmod(0o700)
    fake_guard = tmp_path / "browser-guard"
    fake_guard.write_text(
        """#!/bin/sh
case "$1" in
  acquire) printf '%s\\n' 'http://127.0.0.1:9222' ;;
  release) exit 0 ;;
  *) exit 98 ;;
esac
""",
        encoding="utf-8",
    )
    fake_guard.chmod(0o700)

    fixture_repo = tmp_path / "repo"
    fixture_daily = fixture_repo / "skills" / "earn" / "promptbase" / "daily.sh"
    fixture_daily.parent.mkdir(parents=True)
    shutil.copy2(DAILY, fixture_daily)
    (fixture_repo / "skills" / "capafy-autopublish" / "vendor" / "capafy-publisher").mkdir(parents=True)

    env = os.environ.copy()
    env["HOME"] = str(home)
    env["PY"] = str(fake_python)
    env["AI_BROWSER_GUARD"] = str(fake_guard)
    env["PROMPTBASE_LEDGER_PATH"] = str(tmp_path / "ledger.jsonl")
    env["FAKE_CALL_LOG"] = str(call_log)
    env["FAKE_PY_REAL"] = sys.executable
    env["FAKE_SNAPSHOT_RC"] = str(snapshot_rc)
    env.pop("LIFE_MANAGER_OCCURRENCE_ID", None)
    if occurrence is not None:
        env["LIFE_MANAGER_OCCURRENCE_ID"] = occurrence
    result = subprocess.run(
        ["/bin/bash", str(fixture_daily)], cwd=fixture_repo, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30,
    )
    calls = call_log.read_text(encoding="utf-8").splitlines() if call_log.exists() else []
    return result, calls


def test_daily_aborts_before_publish_when_occurrence_is_missing(tmp_path):
    result, calls = _run_daily(tmp_path)
    assert result.returncode != 0
    assert not any("publish.py" in call for call in calls)


def test_daily_aborts_before_publish_when_snapshot_write_fails(tmp_path):
    result, calls = _run_daily(
        tmp_path, occurrence="promptbase-loop-daily:run-1", snapshot_rc=1,
    )
    assert result.returncode != 0
    assert any("promptbase_fence_reconcile.py" in call for call in calls)
    assert not any("publish.py" in call for call in calls)


def test_daily_dispatches_one_confirm_after_snapshot_succeeds(tmp_path):
    result, calls = _run_daily(
        tmp_path, occurrence="promptbase-loop-daily:run-1", snapshot_rc=0,
    )
    publish_calls = [call for call in calls if "publish.py" in call]
    assert result.returncode == 0
    assert len(publish_calls) == 1
    assert "--confirm" in publish_calls[0]
