import os
import subprocess
from pathlib import Path


SCRIPT = Path(__file__).parent / "reddit-loop-healthcheck.sh"
DAILY = Path(__file__).parent / "reddit-loop-daily.sh"
REPO = Path(__file__).parents[2]


def test_daily_resolves_shared_runner_from_repository(tmp_path):
    result = subprocess.run(
        ["/bin/bash", str(DAILY)],
        env={**os.environ, "HOME": str(tmp_path), "AGENT_WIRING_PROBE_ONLY": "1"},
        capture_output=True,
        text=True,
        check=True,
    )

    assert str(REPO / "skills/earn/marketing-engine/run_agent.sh") in result.stdout


def test_stale_heartbeat_is_reported_without_launchd_or_nohup_recovery(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    marker = tmp_path / "mutation"
    function = f'() {{ printf x >> "{marker}"; return 1; }}'
    result = subprocess.run(
        # A regression to the legacy lock must never touch the production /tmp lock.
        ["/bin/bash", "-c", """
mkdir() { if [ "$*" = "/tmp/.reddit-loop-healthcheck.lock" ]; then return 0; fi; command mkdir "$@"; }
rmdir() { if [ "$*" = "/tmp/.reddit-loop-healthcheck.lock" ]; then return 0; fi; command rmdir "$@"; }
export -f mkdir rmdir
exec /bin/bash "$1"
""", "healthcheck-test", str(SCRIPT)],
        env={
            **os.environ,
            "HOME": str(home),
            "BASH_FUNC_launchctl%%": function,
            "BASH_FUNC_nohup%%": function,
            "BASH_FUNC_tmux%%": "() { return 1; }",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert not marker.exists()
    assert "stale/missing" in result.stderr
    assert not (home / ".local/state/life-manager/reddit/logs/reddit-loop-healthcheck.log").exists()
