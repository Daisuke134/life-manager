from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
CHILD = ROOT / "skills/capafy-autopublish/scripts/daily_loop.sh"
PARENT = ROOT / "skills/self/capafy-loop/capafy-loop-daily.sh"


def _between(source: str, start: str, end: str) -> str:
    start_at = source.index(start)
    end_at = source.index(end, start_at)
    return source[start_at:end_at]


def _child_terminal_block() -> str:
    source = CHILD.read_text(encoding="utf-8")
    start = 'MAXTURNS_STREAK="$CAPAFY_STATE_DIR/.maxturns-streak"'
    return _between(source, start, "\nexit $RC") + "\nexit $RC"


def _parent_dispatch_block() -> tuple[str, str]:
    source = PARENT.read_text(encoding="utf-8")
    mark_start = "mark_healthy() {"
    mark_end = source.index("\n}\n", source.index(mark_start)) + len("\n}")
    dispatch_start = 'if [ "$VERDICT" = "PUBLISHABLE" ] && [ ! -f "$SELFHEAL_REQUEST" ]; then'
    dispatch_end = source.index("\nfi\n\nPROMPT=", source.index(dispatch_start)) + len("\nfi")
    return source[source.index(mark_start):mark_end], source[source.index(dispatch_start):dispatch_end]


def _run_parent_child(tmp_path: Path, *, post: str, rc: int, max_turns: bool = False) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path]:
    release = tmp_path / "release"
    child_path = release / "skills/capafy-autopublish/scripts/daily_loop.sh"
    child_state = tmp_path / "child-state"
    log = tmp_path / "loop.log"
    child_marker = child_state / ".capafy-healthy-pass"
    parent_last_pass = tmp_path / ".last-pass"
    parent_healthy = tmp_path / ".parent-healthy"
    child_state.mkdir(parents=True)
    if max_turns:
        (child_state / ".maxturns-streak").write_text("2\n", encoding="utf-8")
    child_path.parent.mkdir(parents=True)
    if max_turns:
        log.write_text("Reached max turns\n", encoding="utf-8")

    child_setup = "\n".join(
        (
            "set -uo pipefail",
            f"POST={shlex.quote(post)}",
            f"RC={rc}",
            f"MARK={shlex.quote(str(child_marker))}",
            f"CAPAFY_STATE_DIR={shlex.quote(str(child_state))}",
            f"LOG={shlex.quote(str(log))}",
            "TS=test",
            'PRE_ONLINE=""',
            'POST_ONLINE=""',
            _child_terminal_block(),
            "",
        )
    )
    child_path.write_text(child_setup, encoding="utf-8")

    mark_healthy, parent_dispatch = _parent_dispatch_block()
    parent_script = "\n".join(
        (
            "set -uo pipefail",
            f"export LIFE_MANAGER_RELEASE_ROOT={shlex.quote(str(release))}",
            f"export SELFHEAL_REQUEST={shlex.quote(str(tmp_path / 'no-selfheal-request'))}",
            f"export LOG={shlex.quote(str(log))}",
            f"export LAST_PASS_MARKER={shlex.quote(str(parent_last_pass))}",
            f"export HEALTHY_MARKER={shlex.quote(str(parent_healthy))}",
            "VERDICT=PUBLISHABLE",
            mark_healthy,
            parent_dispatch,
            "",
        )
    )
    result = subprocess.run(["bash", "-c", parent_script], capture_output=True, text=True, check=False)
    return result, child_marker, parent_last_pass, parent_healthy


@pytest.mark.parametrize("terminal", ["blocked", "max_turns_stuck"])
def test_failed_child_with_zero_runner_status_never_marks_parent_healthy(tmp_path: Path, terminal: str) -> None:
    result, child_marker, parent_last_pass, parent_healthy = _run_parent_child(
        tmp_path,
        post="PUBLISHABLE",
        rc=0,
        max_turns=terminal == "max_turns_stuck",
    )

    assert result.returncode == 1
    assert not child_marker.exists()
    assert not parent_last_pass.exists()
    assert not parent_healthy.exists()


@pytest.mark.parametrize("terminal", ["blocked", "max_turns_stuck"])
def test_failed_child_preserves_existing_nonzero_runner_status(tmp_path: Path, terminal: str) -> None:
    result, child_marker, parent_last_pass, parent_healthy = _run_parent_child(
        tmp_path,
        post="PUBLISHABLE",
        rc=124,
        max_turns=terminal == "max_turns_stuck",
    )

    assert result.returncode == 124
    assert not child_marker.exists()
    assert not parent_last_pass.exists()
    assert not parent_healthy.exists()


@pytest.mark.parametrize("post", ["DRAINED", "CAP_FULL"])
def test_legitimate_noop_still_marks_child_and_parent_healthy(tmp_path: Path, post: str) -> None:
    result, child_marker, parent_last_pass, parent_healthy = _run_parent_child(
        tmp_path,
        post=post,
        rc=0,
    )

    assert result.returncode == 0
    assert child_marker.exists()
    assert parent_last_pass.exists()
    assert parent_healthy.exists()
