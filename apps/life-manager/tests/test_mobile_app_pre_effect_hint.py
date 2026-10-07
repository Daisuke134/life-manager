from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


SCRIPT = Path(__file__).parents[1] / "scripts" / "mobile-app"


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(0o700)


def _run_mobile_app(
    tmp_path: Path, *, reconcile_status: int, runner_status: int,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    home = tmp_path / "home"
    home.mkdir()
    env_file = tmp_path / "marketing.env"
    env_file.write_text("LM_POSTIZ_API_KEY=test-only\n", encoding="utf-8")
    calls = tmp_path / "calls.log"
    hint = tmp_path / "entrypoint-result.json"
    hint.write_text(json.dumps({"status": "pre_effect_failure", "effect": 0}) + "\n")
    hint.chmod(0o600)

    fake_python = tmp_path / "python3"
    _write_executable(fake_python, """#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  */mobile-postiz-provider-reconcile.py)
    printf 'reconcile\\n' >> "$CALLS"
    exit "$RECONCILE_STATUS"
    ;;
  */run-with-timeout.py)
    if [[ -e "$LIFE_MANAGER_RESULT_HINT_PATH" ]]; then
      printf 'runner:hint-present\\n' >> "$CALLS"
    else
      printf 'runner:hint-absent\\n' >> "$CALLS"
    fi
    printf 'runner\\n' >> "$CALLS"
    exit "$RUNNER_STATUS"
    ;;
  *)
    exit 99
    ;;
esac
""")
    fake_node = tmp_path / "node"
    _write_executable(fake_node, """#!/usr/bin/env bash
set -euo pipefail
case "$1" in
  */mobile-app-command.js)
    printf 'test-runner.js\\tpublish\\tproduct\\torigin\\tworkspace\\n'
    ;;
  */mobile-effect-result.js)
    exit 0
    ;;
  *)
    exit 98
    ;;
esac
""")

    env = os.environ.copy()
    env.update({
        "HOME": str(home),
        "LIFE_MANAGER_MARKETING_ENV_FILE": str(env_file),
        "LIFE_MANAGER_NODE": str(fake_node),
        "LIFE_MANAGER_PYTHON": str(fake_python),
        "LIFE_MANAGER_RESULT_HINT_PATH": str(hint),
        "CALLS": str(calls),
        "RECONCILE_STATUS": str(reconcile_status),
        "RUNNER_STATUS": str(runner_status),
        "TMPDIR": str(tmp_path),
    })
    result = subprocess.run(
        ["bash", str(SCRIPT), "life-manager-honne-ja"],
        cwd=SCRIPT.parents[3], env=env, text=True, capture_output=True, check=False,
    )
    return result, hint, calls


def test_reconcile_failure_preserves_no_publish_hint_and_skips_runner(tmp_path):
    result, hint, calls = _run_mobile_app(
        tmp_path, reconcile_status=1, runner_status=1,
    )

    assert result.returncode == 75
    assert json.loads(hint.read_text(encoding="utf-8")) == {
        "status": "pre_effect_failure", "effect": 0,
    }
    assert calls.read_text(encoding="utf-8").splitlines() == ["reconcile"]


def test_successful_reconcile_clears_hint_before_runner_starts(tmp_path):
    result, hint, calls = _run_mobile_app(
        tmp_path, reconcile_status=0, runner_status=1,
    )

    assert result.returncode == 1
    assert not hint.exists()
    assert calls.read_text(encoding="utf-8").splitlines() == [
        "reconcile", "runner:hint-absent", "runner",
    ]
