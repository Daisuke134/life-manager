from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import lateness_check as lc  # noqa: E402


def test_heartbeat_wrapper_uses_stderr_without_growing_legacy_log(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[3]
    fixture = tmp_path / "repo"
    scripts = fixture / "skills/anicca-life-manager/scripts"
    scripts.mkdir(parents=True)
    (fixture / "runtime").mkdir()
    shutil.copyfile(source / "runtime/run-with-timeout.py", fixture / "runtime/run-with-timeout.py")
    (scripts / "lateness_check.py").write_text("import sys\nprint('lateness-diagnostic')\nsys.exit(23)\n")
    (scripts / "arrival.py").write_text("import sys\nprint('arrival-diagnostic')\nsys.exit(7)\n")
    state = tmp_path / "owner"
    (state / "logs").mkdir(parents=True)
    legacy = state / "logs/run.log"
    legacy.write_text("retained diagnostic\n")
    env_file = tmp_path / "empty.env"
    env_file.write_text("")
    result = subprocess.run(
        ["bash", str(source / "skills/anicca-life-manager/scripts/run.sh")],
        env={**os.environ, "LIFE_MANAGER_REPO": str(fixture),
             "LIFE_MANAGER_PYTHON": sys.executable, "LIFE_MANAGER_HOME": str(tmp_path / "home-state"),
             "LIFE_MANAGER_STATE_ROOT": str(state), "LIFE_MANAGER_ENV_FILE": str(env_file)},
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 23, "arrival failure must not replace the lateness result"
    assert "lateness-diagnostic" in result.stderr and "arrival-diagnostic" in result.stderr
    assert legacy.read_text() == "retained diagnostic\n"


def test_oversized_heartbeat_log_is_archived_without_data_loss(tmp_path: Path, monkeypatch) -> None:
    ledger = tmp_path / "heartbeat_log.jsonl"
    original = '{"event":1}\n{"event":2}\n'
    ledger.write_text(original, encoding="utf-8")
    monkeypatch.setattr(lc, "HEARTBEAT_LOG_MAX_BYTES", 1)

    lc._rotate_heartbeat_log_if_needed(ledger)

    archives = sorted(tmp_path.glob("heartbeat_log.*.jsonl.gz"))
    assert len(archives) == 1
    assert gzip.open(archives[0], "rt", encoding="utf-8").read() == original
    assert ledger.exists()
    assert ledger.read_text(encoding="utf-8") == ""


def test_orphan_rotating_heartbeat_log_is_restored_before_new_writes(tmp_path: Path) -> None:
    ledger = tmp_path / "heartbeat_log.jsonl"
    orphan = tmp_path / ".heartbeat_log.jsonl.crashed.rotating"
    original = '{"event":"orphan"}\n'
    orphan.write_text(original, encoding="utf-8")

    lc._rotate_heartbeat_log_if_needed(ledger)

    assert ledger.read_text(encoding="utf-8") == original
    assert not orphan.exists()
