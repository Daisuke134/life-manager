import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = Path(__file__).resolve().parent / "run.sh"


def _run(tmp_path, free_kib: int, guard_script: str, foundation_script: str = "#!/bin/sh\nexit 1\n"):
    home = tmp_path / "home"
    home.mkdir()
    calls = tmp_path / "lm-loop.calls"
    cli = tmp_path / "lm-loop"
    cli.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{calls}"\n')
    cli.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    guard = tmp_path / "browser-guard.sh"
    guard.write_text(guard_script)
    guard.chmod(0o755)
    foundation = tmp_path / "ensure_browser.sh"
    foundation.write_text(foundation_script)
    foundation.chmod(0o755)
    df_function = (
        '() { printf "Filesystem 1024-blocks Used Available Capacity Mounted on\\n'
        f'disk 1 1 {free_kib} 1% /\\n"; }}'
    )
    result = subprocess.run(
        ["/bin/bash", str(SCRIPT)],
        env={
            **os.environ,
            "HOME": str(home),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "LIFE_MANAGER_REPO": str(ROOT),
            "LIFE_MANAGER_LOOP_CLI": str(cli),
            "LIFE_MANAGER_BROWSER_GUARD": str(guard),
            "LIFE_MANAGER_BROWSER_FOUNDATION": str(foundation),
            "BASH_FUNC_df%%": df_function,
            "BASH_FUNC_sleep%%": "() { :; }",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    return result, calls


def test_low_disk_requests_cleanup_through_lm_loop(tmp_path):
    result, calls = _run(
        tmp_path, free_kib=1,
        guard_script="#!/bin/sh\necho http://localhost:9222\nexit 0\n",
    )
    assert result.returncode == 75
    assert calls.read_text().strip() == "restart life-manager-disk-cleanup"


def test_browser_lease_busy_defers_without_touching_foundation(tmp_path):
    # exit 9 == BUSY per browser-guard.sh's contract: another owner already holds
    # the lease. This is normal, not a failure, and must never fall through to
    # the identity-mismatch recovery path.
    result, calls = _run(
        tmp_path, free_kib=4 * 1024 * 1024,
        guard_script="#!/bin/sh\nexit 9\n",
        foundation_script='#!/bin/sh\nprintf "recovery must not run" >&2\nexit 1\n',
    )
    assert result.returncode == 75
    assert not calls.exists() or calls.read_text().strip() == ""


def test_browser_identity_mismatch_recovers_then_reacquires(tmp_path):
    # exit 10 == identity mismatch/unreachable per browser-guard.sh's contract:
    # the registered foundation script is asked to recover the daily-driver
    # profile, then exactly one more lease attempt is made.
    guard_calls = tmp_path / "guard.calls"
    guard_script = f"""#!/bin/sh
printf "%s\\n" "$*" >> "{guard_calls}"
n=$(wc -l < "{guard_calls}")
if [ "$n" -eq 1 ]; then
  exit 10
fi
echo http://[::1]:9333
exit 0
"""
    result, calls = _run(
        tmp_path, free_kib=4 * 1024 * 1024,
        guard_script=guard_script,
        foundation_script="#!/bin/sh\necho RECOVERED\n",
    )
    # Downstream stages (context preflight, deck verification, the real agent
    # runner) are not stubbed here, so this only asserts the browser stage
    # itself: recovery ran exactly once and the lease was re-acquired
    # afterward, i.e. the script did not defer at rc=75 for a browser reason.
    assert guard_calls.read_text().count("acquire") == 2
    if result.returncode == 75:
        assert "browser" not in result.stderr and "browser" not in (
            (tmp_path / "home" / ".local" / "state" / "life-manager" / "fundraiser" / "fundraiser.log")
            .read_text() if (tmp_path / "home" / ".local" / "state" / "life-manager" / "fundraiser" / "fundraiser.log").exists() else ""
        )


def test_browser_identity_mismatch_with_failed_recovery_defers(tmp_path):
    result, calls = _run(
        tmp_path, free_kib=4 * 1024 * 1024,
        guard_script="#!/bin/sh\nexit 10\n",
        foundation_script="#!/bin/sh\necho FAILED\n",
    )
    assert result.returncode == 75


def test_invalid_browser_endpoint_is_rejected(tmp_path):
    result, _ = _run(
        tmp_path, free_kib=4 * 1024 * 1024,
        guard_script="#!/bin/sh\necho http://evil.example.test:9222\nexit 0\n",
    )
    assert result.returncode == 75
