from __future__ import annotations

import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[4]
WATCHDOG = ROOT / "bin" / "disk-watchdog.sh"
MAINTENANCE_15D = ROOT / "bin" / "disk-cleanup-15d.sh"
INSTALLER = ROOT / "skills/self/disk-cleanup/install-launchd.sh"
MAINTENANCE_INSTALLER = ROOT / "skills/self/disk-cleanup/install-launchd-15d.sh"
WATCHDOG_PLIST = ROOT / "skills/self/disk-cleanup/launchd/com.anicca.disk-watchdog.plist"
MAINTENANCE_15D_PLIST = ROOT / "skills/self/disk-cleanup/launchd/com.anicca.disk-cleanup-15d.plist"


def test_watchdog_dispatches_to_governor_without_touching_worktrees_or_simulator(tmp_path: Path) -> None:
    source = WATCHDOG.read_text(encoding="utf-8")
    for forbidden in (
        "git worktree",
        "git ",
        "rm -rf",
        "find ",
        "truncate ",
        "worktree unlock",
        "worktree remove",
        "worktree prune",
        "anicca-worktrees",
        "anicca-clones",
        ".worktrees",
        "CoreSimulator",
    ):
        assert forbidden not in source

    home = tmp_path / "home"
    release = home / "loops/current"
    governor = release / "skills/self/disk-cleanup/disk_cleanup.py"
    worktree_marker = home / ".cache/anicca-worktrees/active/progress.txt"
    simulator_marker = home / "Library/Developer/CoreSimulator/Devices/device/data.txt"
    governor.parent.mkdir(parents=True)
    worktree_marker.parent.mkdir(parents=True)
    simulator_marker.parent.mkdir(parents=True)
    governor.write_text("# fake governor\n", encoding="utf-8")
    worktree_marker.write_text("active work\n", encoding="utf-8")
    simulator_marker.write_text("shipping device data\n", encoding="utf-8")

    capture = tmp_path / "argv.txt"
    fake_python = tmp_path / "python-capture"
    fake_python.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE_ARGS"\n',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    env = os.environ | {
        "HOME": str(home),
        "LIFE_MANAGER_RUNTIME_PYTHON": str(fake_python),
        "CAPTURE_ARGS": str(capture),
    }

    subprocess.run(["/bin/sh", str(WATCHDOG)], env=env, check=True)

    assert capture.read_text(encoding="utf-8").splitlines() == [
        str(governor),
        "--home",
        str(home),
        "--state-dir",
        str(home / ".local/state/life-manager/state"),
    ]
    assert worktree_marker.read_text(encoding="utf-8") == "active work\n"
    assert simulator_marker.read_text(encoding="utf-8") == "shipping device data\n"


def test_15d_maintenance_plist_uses_exact_interval_and_stable_wrapper() -> None:
    assert MAINTENANCE_15D_PLIST.is_file(), "the recurring 15-day launchd owner is missing"
    with MAINTENANCE_15D_PLIST.open("rb") as source:
        plist = plistlib.load(source)

    assert plist["Label"] == "com.anicca.disk-cleanup-15d"
    assert plist["ProgramArguments"] == ["__MAINTENANCE_15D_SCRIPT__"]
    assert plist["StartInterval"] == 15 * 24 * 60 * 60
    assert plist["RunAtLoad"] is True
    assert plist["StandardOutPath"].endswith("/maintenance-15d.out.log")
    assert plist["StandardErrorPath"].endswith("/maintenance-15d.err.log")
    assert "CoreSimulator" not in str(plist)
    assert "worktree" not in str(plist).lower()


def test_15d_maintenance_wrapper_retries_only_cleanup_lock_busy(tmp_path: Path) -> None:
    assert MAINTENANCE_15D.is_file(), "the recurring maintenance wrapper is missing"
    home = tmp_path / "home"
    local_bin = home / ".local/bin"
    local_bin.mkdir(parents=True)
    calls = tmp_path / "watchdog-calls"
    watchdog = local_bin / "disk-watchdog.sh"
    watchdog.write_text(
        "#!/bin/sh\n"
        "count=0; [ ! -f \"$CALLS\" ] || count=$(cat \"$CALLS\")\n"
        "count=$((count + 1)); printf '%s\\n' \"$count\" > \"$CALLS\"\n"
        "if [ \"$count\" -eq 1 ]; then printf '%s\\n' '{\"ok\":false,\"status\":\"deferred\",\"reason\":\"cleanup_lock_busy\",\"effect\":0,\"readback\":0,\"capacity_recovery\":{\"status\":\"unknown\"}}'; exit 75; fi\n"
        "printf '%s\\n' '{\"capacity_recovery\":{\"status\":\"met\"}}'\n",
        encoding="utf-8",
    )
    watchdog.chmod(0o755)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "sleep").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (fake_bin / "sleep").chmod(0o755)

    result = subprocess.run(
        ["/bin/sh", str(MAINTENANCE_15D)],
        env=os.environ | {"HOME": str(home), "CALLS": str(calls), "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
    assert calls.read_text(encoding="utf-8").strip() == "2"
    assert "cleanup_lock_busy" in result.stdout
    assert "capacity_recovery" in result.stdout

    calls.write_text("0\n", encoding="utf-8")
    watchdog.write_text(
        "#!/bin/sh\n"
        "count=0; [ ! -f \"$CALLS\" ] || count=$(cat \"$CALLS\")\n"
        "count=$((count + 1)); printf '%s\\n' \"$count\" > \"$CALLS\"\n"
        "printf '%s\\n' '{\"ok\":false,\"status\":\"deferred\",\"reason\":\"cleanup_lock_busy\",\"effect\":0,\"readback\":0}'; exit 75\n",
        encoding="utf-8",
    )
    watchdog.chmod(0o755)
    result = subprocess.run(
        ["/bin/sh", str(MAINTENANCE_15D)],
        env=os.environ | {"HOME": str(home), "CALLS": str(calls), "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 75
    assert calls.read_text(encoding="utf-8").strip() == "3"

    calls.write_text("0\n", encoding="utf-8")
    watchdog.write_text(
        "#!/bin/sh\n"
        "count=0; [ ! -f \"$CALLS\" ] || count=$(cat \"$CALLS\")\n"
        "count=$((count + 1)); printf '%s\\n' \"$count\" > \"$CALLS\"\n"
        "printf '%s\\n' '{\"ok\":false,\"status\":\"deferred\",\"reason\":\"other_failure\",\"reason\":\"cleanup_lock_busy\",\"effect\":0,\"readback\":0}'; exit 75\n",
        encoding="utf-8",
    )
    watchdog.chmod(0o755)
    result = subprocess.run(
        ["/bin/sh", str(MAINTENANCE_15D)],
        env=os.environ | {"HOME": str(home), "CALLS": str(calls), "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 75
    assert calls.read_text(encoding="utf-8").strip() == "1"

    calls.write_text("0\n", encoding="utf-8")
    watchdog.write_text(
        "#!/bin/sh\n"
        "count=0; [ ! -f \"$CALLS\" ] || count=$(cat \"$CALLS\")\n"
        "count=$((count + 1)); printf '%s\\n' \"$count\" > \"$CALLS\"\n"
        "printf '%s\\n' '{\"ok\":false,\"status\":\"deferred\",\"reason\":\"cleanup_lock_busy\",\"effect\":0,\"readback\":0,\"unused\":NaN}'; exit 75\n",
        encoding="utf-8",
    )
    watchdog.chmod(0o755)
    result = subprocess.run(
        ["/bin/sh", str(MAINTENANCE_15D)],
        env=os.environ | {"HOME": str(home), "CALLS": str(calls), "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 75
    assert calls.read_text(encoding="utf-8").strip() == "1"


def test_installer_updates_stable_watchdog_and_15d_cleanup_labels(tmp_path: Path) -> None:
    if sys.platform != "darwin" or not Path("/usr/bin/plutil").is_file():
        pytest.skip("launchd installer integration runs on macOS")

    assert MAINTENANCE_INSTALLER.is_file(), "the 15-day launchd installer is missing"
    assert MAINTENANCE_15D_PLIST.is_file(), "the recurring 15-day launchd owner is missing"
    fake_root = tmp_path / "repo"
    fake_home = tmp_path / "home"
    (fake_root / "bin").mkdir(parents=True)
    (fake_root / "skills/self/disk-cleanup/launchd").mkdir(parents=True)
    shutil.copy2(INSTALLER, fake_root / "skills/self/disk-cleanup/install-launchd.sh")
    shutil.copy2(MAINTENANCE_INSTALLER, fake_root / "skills/self/disk-cleanup/install-launchd-15d.sh")
    shutil.copy2(WATCHDOG, fake_root / "bin/disk-watchdog.sh")
    shutil.copy2(MAINTENANCE_15D, fake_root / "bin/disk-cleanup-15d.sh")
    shutil.copy2(WATCHDOG_PLIST, fake_root / "skills/self/disk-cleanup/launchd/com.anicca.disk-watchdog.plist")
    shutil.copy2(MAINTENANCE_15D_PLIST, fake_root / "skills/self/disk-cleanup/launchd/com.anicca.disk-cleanup-15d.plist")

    safe_calls = tmp_path / "launchctl-safe-calls.txt"
    safe = fake_root / "bin/launchctl-safe"
    safe.write_text(
        '#!/bin/sh\n'
        'set -eu\n'
        'printf "%s\\n" "$*" >> "$SAFE_CALLS"\n'
        'case "$1" in\n'
        '  list)\n'
        '    case "${LIST_MODE:-valid}" in\n'
        '      valid)\n'
        '        printf "PID\\tStatus\\tLabel\\n0\\t0\\tcom.anicca.disk-watchdog\\n0\\t0\\tai.anicca.life-manager-disk-cleanup\\n"\n'
        '        [ ! -f "$HOME/Library/LaunchAgents/com.anicca.disk-cleanup-15d.plist" ] || printf "0\\t0\\tcom.anicca.disk-cleanup-15d\\n" ;;\n'
        '      empty) : ;;\n'
        '      malformed) printf "PID\\tStatus\\tLabel\\nx\\t0\\tcom.anicca.disk-watchdog\\n" ;;\n'
        '    esac ;;\n'
        '  bootout)\n'
        '    [ "${FAIL_BOOTOUT:-0}" != 1 ] || exit 42\n'
        '    case "$2" in\n'
        '      */com.anicca.disk-cleanup-15d)\n'
        '        [ "${FAIL_15D_BOOTOUT:-0}" != 1 ] || exit 43\n'
        '        if [ "${FAIL_15D_BOOTOUT_AFTER_FIRST:-0}" = 1 ]; then\n'
        '          count_file="$SAFE_CALLS.15d-bootout-count"\n'
        '          count=0; [ ! -f "$count_file" ] || count=$(cat "$count_file")\n'
        '          count=$((count + 1)); printf "%s\\n" "$count" > "$count_file"\n'
        '          [ "$count" -eq 1 ] || exit 44\n'
        '        fi ;;\n'
        '    esac ;;\n'
        '  print)\n'
        '    expected="$EXPECTED_WATCHDOG_SCRIPT"\n'
        '    stdout="$EXPECTED_WATCHDOG_STDOUT"\n'
        '    stderr="$EXPECTED_WATCHDOG_STDERR"\n'
        '    interval=60\n'
        '    case "$2" in\n'
        '      *com.anicca.disk-cleanup-15d)\n'
        '        plist="$HOME/Library/LaunchAgents/com.anicca.disk-cleanup-15d.plist"\n'
        '        expected=$(/usr/bin/plutil -extract ProgramArguments.0 raw -o - "$plist")\n'
        '        stdout=$(/usr/bin/plutil -extract StandardOutPath raw -o - "$plist")\n'
        '        stderr=$(/usr/bin/plutil -extract StandardErrorPath raw -o - "$plist")\n'
        '        interval=$(/usr/bin/plutil -extract StartInterval raw -o - "$plist") ;;\n'
        '    esac\n'
        '    case "${READBACK_MODE:-valid}:$2" in\n'
        '      wrong:*) printf "program = /bin/false\\narguments = {\\n  /bin/false\\n}\\nextra = %s\\n" "$EXPECTED_WATCHDOG_SCRIPT" ;;\n'
        '      maintenance_wrong_once:*com.anicca.disk-cleanup-15d)\n'
        '        count_file="$SAFE_CALLS.maintenance-readback-count"\n'
        '        count=0; [ ! -f "$count_file" ] || count=$(cat "$count_file")\n'
        '        count=$((count + 1)); printf "%s\\n" "$count" > "$count_file"\n'
        '        [ "$count" -ne 2 ] || interval=60\n'
        '        printf "program = %s\\narguments = {\\n  %s\\n}\\nstdout path = %s\\nstderr path = %s\\nrun interval = %s seconds\\n" "$expected" "$expected" "$stdout" "$stderr" "$interval" ;;\n'
        '      *) printf "program = %s\\narguments = {\\n  %s\\n}\\nstdout path = %s\\nstderr path = %s\\nrun interval = %s seconds\\n" "$expected" "$expected" "$stdout" "$stderr" "$interval" ;;\n'
        '    esac ;;\n'
        'esac\n',
        encoding="utf-8",
    )
    safe.chmod(0o755)
    watchdog_script = fake_home / ".local/bin/disk-watchdog.sh"
    logs = fake_home / ".local/state/life-manager/life-manager-disk-cleanup/logs"
    env = os.environ | {
        "HOME": str(fake_home),
        "SAFE_CALLS": str(safe_calls),
        "EXPECTED_WATCHDOG_SCRIPT": str(watchdog_script),
        "EXPECTED_MAINTENANCE_SCRIPT": str(fake_home / ".local/bin/disk-cleanup-15d.sh"),
        "EXPECTED_WATCHDOG_STDOUT": str(logs / "watchdog.out.log"),
        "EXPECTED_WATCHDOG_STDERR": str(logs / "watchdog.err.log"),
        "EXPECTED_MAINTENANCE_STDOUT": str(logs / "maintenance-15d.out.log"),
        "EXPECTED_MAINTENANCE_STDERR": str(logs / "maintenance-15d.err.log"),
    }

    subprocess.run(
        ["/bin/sh", str(fake_root / "skills/self/disk-cleanup/install-launchd.sh")],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    wrapper = fake_home / ".local/bin/disk-watchdog.sh"
    maintenance_wrapper = fake_home / ".local/bin/disk-cleanup-15d.sh"
    installed_plist = fake_home / "Library/LaunchAgents/com.anicca.disk-watchdog.plist"
    installed_maintenance_plist = fake_home / "Library/LaunchAgents/com.anicca.disk-cleanup-15d.plist"
    with installed_plist.open("rb") as source:
        plist = plistlib.load(source)
    with installed_maintenance_plist.open("rb") as source:
        maintenance_plist = plistlib.load(source)
    assert wrapper.read_bytes() == WATCHDOG.read_bytes()
    assert maintenance_wrapper.read_bytes() == MAINTENANCE_15D.read_bytes()
    assert plist["Label"] == "com.anicca.disk-watchdog"
    assert plist["ProgramArguments"] == [str(wrapper)]
    assert maintenance_plist["Label"] == "com.anicca.disk-cleanup-15d"
    assert maintenance_plist["ProgramArguments"] == [str(maintenance_wrapper)]
    assert maintenance_plist["StartInterval"] == 15 * 24 * 60 * 60
    assert maintenance_plist["RunAtLoad"] is True
    assert maintenance_plist["StandardOutPath"] == str(logs / "maintenance-15d.out.log")
    assert maintenance_plist["StandardErrorPath"] == str(logs / "maintenance-15d.err.log")
    calls = safe_calls.read_text(encoding="utf-8").splitlines()
    domain = f"gui/{os.getuid()}"
    assert calls == [
        "preflight",
        "list",
        f"bootout {domain}/com.anicca.disk-watchdog",
        f"bootstrap {domain} {installed_plist}",
        f"kickstart {domain}/com.anicca.disk-watchdog",
        f"print {domain}/com.anicca.disk-watchdog",
        "preflight",
        "list",
        f"bootstrap {domain} {installed_maintenance_plist}",
        f"print {domain}/com.anicca.disk-cleanup-15d",
    ]

    old_wrapper = wrapper.read_bytes()
    old_maintenance_wrapper = b"#!/bin/sh\n# previous 15-day wrapper\n"
    maintenance_wrapper.write_bytes(old_maintenance_wrapper)
    old_plist = installed_plist.read_bytes()
    with installed_maintenance_plist.open("rb") as source:
        previous_plist = plistlib.load(source)
    previous_plist["StartInterval"] = 86400
    previous_plist["StandardOutPath"] = str(logs / "maintenance-previous.out.log")
    previous_plist["StandardErrorPath"] = str(logs / "maintenance-previous.err.log")
    with installed_maintenance_plist.open("wb") as target:
        plistlib.dump(previous_plist, target)
    old_maintenance_plist = installed_maintenance_plist.read_bytes()
    failure_calls = tmp_path / "launchctl-safe-failure-calls.txt"
    failure = subprocess.run(
        ["/bin/sh", str(fake_root / "skills/self/disk-cleanup/install-launchd.sh")],
        env=env | {"SAFE_CALLS": str(failure_calls), "FAIL_BOOTOUT": "1"},
        capture_output=True,
        text=True,
    )
    assert failure.returncode == 42
    failed_calls = failure_calls.read_text(encoding="utf-8").splitlines()
    assert failed_calls == [
        "preflight",
        "list",
        f"bootout {domain}/com.anicca.disk-watchdog",
    ]
    assert wrapper.read_bytes() == old_wrapper
    assert maintenance_wrapper.read_bytes() == old_maintenance_wrapper
    assert installed_plist.read_bytes() == old_plist

    for mode in ("empty", "malformed"):
        bad_calls = tmp_path / f"launchctl-safe-{mode}-calls.txt"
        failed_list = subprocess.run(
            ["/bin/sh", str(fake_root / "skills/self/disk-cleanup/install-launchd.sh")],
            env=env | {"SAFE_CALLS": str(bad_calls), "LIST_MODE": mode},
            capture_output=True,
            text=True,
        )
        assert failed_list.returncode == 1
        assert bad_calls.read_text(encoding="utf-8").splitlines() == ["preflight", "list"]
        assert wrapper.read_bytes() == old_wrapper
        assert maintenance_wrapper.read_bytes() == old_maintenance_wrapper
        assert installed_plist.read_bytes() == old_plist
        assert installed_maintenance_plist.read_bytes() == old_maintenance_plist

    readback_calls = tmp_path / "launchctl-safe-readback-calls.txt"
    bad_readback = subprocess.run(
        ["/bin/sh", str(fake_root / "skills/self/disk-cleanup/install-launchd.sh")],
        env=env | {"SAFE_CALLS": str(readback_calls), "READBACK_MODE": "wrong"},
        capture_output=True,
        text=True,
    )
    assert bad_readback.returncode == 1
    assert readback_calls.read_text(encoding="utf-8").splitlines()[-1] == (
        f"print {domain}/com.anicca.disk-watchdog"
    )

    maintenance_bootout_calls = tmp_path / "launchctl-safe-maintenance-bootout-calls.txt"
    maintenance_bootout = subprocess.run(
        ["/bin/sh", str(fake_root / "skills/self/disk-cleanup/install-launchd-15d.sh")],
        env=env | {"SAFE_CALLS": str(maintenance_bootout_calls), "FAIL_15D_BOOTOUT": "1"},
        capture_output=True,
        text=True,
    )
    assert maintenance_bootout.returncode == 43
    assert maintenance_bootout_calls.read_text(encoding="utf-8").splitlines() == [
        "preflight",
        "list",
        f"print {domain}/com.anicca.disk-cleanup-15d",
        f"bootout {domain}/com.anicca.disk-cleanup-15d",
        "list",
        f"print {domain}/com.anicca.disk-cleanup-15d",
    ]
    assert maintenance_wrapper.read_bytes() == old_maintenance_wrapper
    assert installed_maintenance_plist.read_bytes() == old_maintenance_plist

    maintenance_readback_calls = tmp_path / "launchctl-safe-maintenance-readback-calls.txt"
    maintenance_readback = subprocess.run(
        ["/bin/sh", str(fake_root / "skills/self/disk-cleanup/install-launchd.sh")],
        env=env | {
            "SAFE_CALLS": str(maintenance_readback_calls),
            "READBACK_MODE": "maintenance_wrong_once",
        },
        capture_output=True,
        text=True,
    )
    assert maintenance_readback.returncode == 1
    assert maintenance_readback_calls.read_text(encoding="utf-8").splitlines()[-3:] == [
        f"bootout {domain}/com.anicca.disk-cleanup-15d",
        f"bootstrap {domain} {installed_maintenance_plist}",
        f"print {domain}/com.anicca.disk-cleanup-15d"
    ]
    assert maintenance_wrapper.read_bytes() == old_maintenance_wrapper
    assert installed_maintenance_plist.read_bytes() == old_maintenance_plist

    rollback_failure_calls = tmp_path / "launchctl-safe-rollback-failure-calls.txt"
    rollback_failure = subprocess.run(
        ["/bin/sh", str(fake_root / "skills/self/disk-cleanup/install-launchd.sh")],
        env=env | {
            "SAFE_CALLS": str(rollback_failure_calls),
            "READBACK_MODE": "maintenance_wrong_once",
            "FAIL_15D_BOOTOUT_AFTER_FIRST": "1",
        },
        capture_output=True,
        text=True,
    )
    assert rollback_failure.returncode == 1
    script_backups = list((fake_home / ".local/bin").glob("disk-cleanup-15d.sh.backup.*"))
    plist_backups = list((fake_home / "Library/LaunchAgents").glob("com.anicca.disk-cleanup-15d.plist.backup.*"))
    assert len(script_backups) == 1
    assert len(plist_backups) == 1
    assert script_backups[0].read_bytes() == old_maintenance_wrapper
    assert plist_backups[0].read_bytes() == old_maintenance_plist
