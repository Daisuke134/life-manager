import os, re, subprocess, tempfile, time
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "daily_loop.sh"


def _lock_block() -> str:
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index('LOCK_DIR="$CAPAFY_STATE_DIR/.daily_loop.lockdir"')
    end = text.index("\nfi\n", start) + 4
    return text[start:end]


def _run(state: Path) -> str:
    script = f'CAPAFY_STATE_DIR="{state}"; LOG="{state}/log"; TS=t\n{_lock_block()}echo ACQUIRED\n'
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True).stdout


def test_dead_owner_is_stolen_live_owner_is_respected() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp)
        lock = state / ".daily_loop.lockdir"
        lock.mkdir()
        dead = subprocess.Popen(["true"]); dead.wait()
        (lock / "pid").write_text(str(dead.pid))
        assert "ACQUIRED" in _run(state)
        assert not lock.exists()  # released by the EXIT trap

        lock.mkdir()
        (lock / "pid").write_text(str(os.getpid()))
        assert "ACQUIRED" not in _run(state)

        (lock / "pid").unlink()
        old = time.time() - 120
        os.utime(lock, (old, old))
        assert "ACQUIRED" in _run(state)
