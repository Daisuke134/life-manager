from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time

import pytest


ROOT = Path(__file__).resolve().parents[4]
WATCHDOG = ROOT / "bin" / "disk-watchdog.sh"
INSTALLER = ROOT / "skills/self/disk-cleanup/install-launchd.sh"
WATCHDOG_PLIST = ROOT / "skills/self/disk-cleanup/launchd/com.anicca.disk-watchdog.plist"
REGISTRY = ROOT / "config/loop-registry.json"
MAINTENANCE_ENTRYPOINT = ROOT / "skills/self/disk-cleanup/maintenance_entrypoint.py"


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
        '#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE_ARGS"\n'
        'printf "%s\\n" "${LIFE_MANAGER_DISK_INVENTORY_FAST:-}" > "$CAPTURE_FAST"\n',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    env = os.environ | {
        "HOME": str(home),
        "LIFE_MANAGER_RUNTIME_PYTHON": str(fake_python),
        "CAPTURE_ARGS": str(capture),
        "CAPTURE_FAST": str(tmp_path / "fast.txt"),
    }

    subprocess.run(["/bin/sh", str(WATCHDOG)], env=env, check=True)

    assert (tmp_path / "fast.txt").read_text().strip() == "1"
    assert capture.read_text(encoding="utf-8").splitlines() == [
        str(governor),
        "--home",
        str(home),
        "--state-dir",
        str(home / ".local/state/life-manager/state"),
    ]
    assert worktree_marker.read_text(encoding="utf-8") == "active work\n"
    assert simulator_marker.read_text(encoding="utf-8") == "shipping device data\n"


def test_15d_disk_maintenance_is_a_registry_managed_control_owner() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    owner = registry["loops"].get("life-manager-disk-cleanup-15d")

    assert owner is not None, "the 15-day maintenance owner must be managed by lm-loop"
    assert owner["label"] == "ai.anicca.life-manager-disk-cleanup-15d"
    assert owner["entrypoint"] == "skills/self/disk-cleanup/maintenance_entrypoint.py"
    assert owner["cadence"]["start_interval_seconds"] == 15 * 24 * 60 * 60
    assert owner["domain"] == "system"
    assert owner["system_role"] == "control"
    assert owner["effect_class"] == "none"
    assert owner["state_root"] == "~/.local/state/life-manager/life-manager-disk-cleanup-15d"
    assert owner["log_root"] == "~/.local/state/life-manager/life-manager-disk-cleanup-15d/logs"
    assert owner["state_root"] != registry["loops"]["life-manager-disk-cleanup"]["state_root"]


def test_15d_entrypoint_uses_shared_governor_and_host_state(tmp_path: Path, monkeypatch) -> None:
    assert MAINTENANCE_ENTRYPOINT.is_file(), "the registry-owned maintenance entrypoint is missing"
    sys.path.insert(0, str(MAINTENANCE_ENTRYPOINT.parent))
    try:
        spec = importlib.util.spec_from_file_location("disk_cleanup_maintenance_entrypoint", MAINTENANCE_ENTRYPOINT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)

    home = tmp_path / "home"
    home.mkdir()
    state_dir = tmp_path / "host-state"
    observed: dict[str, list[str]] = {}
    monkeypatch.setattr(sys, "argv", [str(MAINTENANCE_ENTRYPOINT)])
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LIFE_MANAGER_HOST_STATE_DIR", str(state_dir))

    def fake_main() -> int:
        observed["argv"] = sys.argv[1:]
        return 73

    monkeypatch.setattr(module.disk_cleanup, "main", fake_main)

    assert module.main() == 73
    assert observed["argv"] == ["--home", str(home), "--state-dir", str(state_dir)]


def test_15d_entrypoint_retries_only_structured_lock_busy(tmp_path: Path, monkeypatch, capsys) -> None:
    sys.path.insert(0, str(MAINTENANCE_ENTRYPOINT.parent))
    try:
        spec = importlib.util.spec_from_file_location("disk_cleanup_maintenance_retry", MAINTENANCE_ENTRYPOINT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(sys, "argv", [str(MAINTENANCE_ENTRYPOINT)])
    monkeypatch.setenv("HOME", str(home))
    calls = []
    waits = []

    def fake_main() -> int:
        calls.append(None)
        if len(calls) < 3:
            print(json.dumps({
                "ok": False,
                "status": "deferred",
                "reason": "cleanup_lock_busy",
                "effect": 0,
                "readback": 0,
            }))
            return 75
        print(json.dumps({"ok": True, "free_after": 123}))
        return 0

    monkeypatch.setattr(module.disk_cleanup, "main", fake_main)
    monkeypatch.setattr(time, "sleep", waits.append)

    assert module.main() == 0
    assert len(calls) == 3
    assert waits == [5, 5]
    assert capsys.readouterr().out.strip() == '{"ok": true, "free_after": 123}'


def test_15d_entrypoint_does_not_retry_other_exit_75_receipts(tmp_path: Path, monkeypatch, capsys) -> None:
    sys.path.insert(0, str(MAINTENANCE_ENTRYPOINT.parent))
    try:
        spec = importlib.util.spec_from_file_location("disk_cleanup_maintenance_no_retry", MAINTENANCE_ENTRYPOINT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)

    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(sys, "argv", [str(MAINTENANCE_ENTRYPOINT)])
    monkeypatch.setenv("HOME", str(home))
    calls = []
    waits = []

    def fake_main() -> int:
        calls.append(None)
        print(json.dumps({
            "ok": False,
            "status": "deferred",
            "reason": "different_lock_or_capacity_failure",
            "effect": 0,
            "readback": 0,
        }))
        return 75

    monkeypatch.setattr(module.disk_cleanup, "main", fake_main)
    monkeypatch.setattr(time, "sleep", waits.append)

    assert module.main() == 75
    assert len(calls) == 1
    assert waits == []
    assert json.loads(capsys.readouterr().out) == {
        "ok": False,
        "status": "deferred",
        "reason": "different_lock_or_capacity_failure",
        "effect": 0,
        "readback": 0,
    }


def test_installer_updates_only_stable_watchdog_label(tmp_path: Path) -> None:
    if sys.platform != "darwin" or not Path("/usr/bin/plutil").is_file():
        pytest.skip("launchd installer integration runs on macOS")

    fake_root = tmp_path / "repo"
    fake_home = tmp_path / "home"
    (fake_root / "bin").mkdir(parents=True)
    (fake_root / "skills/self/disk-cleanup/launchd").mkdir(parents=True)
    shutil.copy2(INSTALLER, fake_root / "skills/self/disk-cleanup/install-launchd.sh")
    shutil.copy2(WATCHDOG, fake_root / "bin/disk-watchdog.sh")
    shutil.copy2(WATCHDOG_PLIST, fake_root / "skills/self/disk-cleanup/launchd/com.anicca.disk-watchdog.plist")

    safe_calls = tmp_path / "launchctl-safe-calls.txt"
    safe = fake_root / "bin/launchctl-safe"
    safe.write_text(
        '#!/bin/sh\n'
        'set -eu\n'
        'printf "%s\\n" "$*" >> "$SAFE_CALLS"\n'
        'case "$1" in\n'
        '  list)\n'
        '    case "${LIST_MODE:-valid}" in\n'
        '      valid) printf "PID\\tStatus\\tLabel\\n0\\t0\\tcom.anicca.disk-watchdog\\n" ;;\n'
        '      empty) : ;;\n'
        '      malformed) printf "PID\\tStatus\\tLabel\\nx\\t0\\tcom.anicca.disk-watchdog\\n" ;;\n'
        '    esac ;;\n'
        '  bootout) [ "${FAIL_BOOTOUT:-0}" != 1 ] || exit 42 ;;\n'
        '  print)\n'
        '    case "${READBACK_MODE:-valid}" in\n'
        '      valid) printf "program = %s\\narguments = {\\n  %s\\n}\\n" "$EXPECTED_WATCHDOG_SCRIPT" "$EXPECTED_WATCHDOG_SCRIPT" ;;\n'
        '      wrong) printf "program = /bin/false\\narguments = {\\n  /bin/false\\n}\\nextra = %s\\n" "$EXPECTED_WATCHDOG_SCRIPT" ;;\n'
        '    esac ;;\n'
        'esac\n',
        encoding="utf-8",
    )
    safe.chmod(0o755)
    watchdog_script = fake_home / ".local/bin/disk-watchdog.sh"
    env = os.environ | {
        "HOME": str(fake_home),
        "SAFE_CALLS": str(safe_calls),
        "EXPECTED_WATCHDOG_SCRIPT": str(watchdog_script),
    }

    subprocess.run(
        ["/bin/sh", str(fake_root / "skills/self/disk-cleanup/install-launchd.sh")],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    wrapper = fake_home / ".local/bin/disk-watchdog.sh"
    installed_plist = fake_home / "Library/LaunchAgents/com.anicca.disk-watchdog.plist"
    with installed_plist.open("rb") as source:
        plist = plistlib.load(source)
    assert wrapper.read_bytes() == WATCHDOG.read_bytes()
    assert plist["Label"] == "com.anicca.disk-watchdog"
    assert plist["ProgramArguments"] == [str(wrapper)]
    calls = safe_calls.read_text(encoding="utf-8").splitlines()
    domain = f"gui/{os.getuid()}"
    assert calls == [
        "preflight",
        "list",
        f"bootout {domain}/com.anicca.disk-watchdog",
        f"bootstrap {domain} {installed_plist}",
        f"kickstart {domain}/com.anicca.disk-watchdog",
        f"print {domain}/com.anicca.disk-watchdog",
    ]

    old_wrapper = b"#!/bin/sh\n# old installed wrapper\n"
    old_plist = b"old installed plist\n"
    wrapper.write_bytes(old_wrapper)
    installed_plist.write_bytes(old_plist)
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
        assert installed_plist.read_bytes() == old_plist

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
