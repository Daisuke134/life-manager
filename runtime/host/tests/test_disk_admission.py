from __future__ import annotations

import importlib.util
import json
import os
import pwd
import shutil
from types import SimpleNamespace
from pathlib import Path

import pytest


GUARD = Path(__file__).resolve().parents[1] / "disk_admission.py"


def load_guard():
    spec = importlib.util.spec_from_file_location("disk_admission_test", GUARD)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("available", (0, None, 2 * 1024**3 - 1, 2 * 1024**3))
def test_capacity_check_defers_before_child_or_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys, available,
):
    guard = load_guard()
    probes, children = [], []
    monkeypatch.setattr(guard, "disk_free_bytes", lambda p: probes.append(p) or available)
    monkeypatch.setattr(guard.os, "execvpe", lambda program, args, env: children.append((program, args)))
    target = tmp_path / "future" / "releases"
    result = guard.main(["--check-free-space", str(target)])
    assert result == (0 if available == guard.RECOVERY_FLOOR_BYTES else 75)
    assert children == []
    assert probes == [tmp_path]
    assert not target.parent.exists()
    if result == 75:
        receipt = json.loads(capsys.readouterr().out.strip())
        assert receipt["status"] == "deferred"
        assert receipt["available_bytes"] == available
        assert receipt["required_bytes"] == guard.RECOVERY_FLOOR_BYTES
        assert receipt["effect"] == receipt["readback"] == 0


def _write_cleanup_recovery_signal(path: Path) -> None:
    path.write_text(json.dumps({
        "owner_id": "host-disk-recovery",
        "reason": "disk_headroom_low",
        "required_bytes": 2 * 1024**3,
        "next_action": "restore_capacity_and_install_shared_disk_gate",
    }) + "\n", encoding="utf-8")
    path.chmod(0o600)


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    home = tmp_path / "home"
    host_state = home / ".local/state/life-manager/state"
    producer_state = home / ".local/state/life-manager/producer"
    host_state.mkdir(parents=True)
    producer_state.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LIFE_MANAGER_HOST_STATE_DIR", str(host_state))
    monkeypatch.setenv("LIFE_MANAGER_PRODUCER_STATE_DIR", str(producer_state))
    healthy = 16 * 1024**3
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: SimpleNamespace(
        total=healthy, used=0, free=healthy,
    ))
    for key in (
        "GIG_DISK_HEADROOM_KIB", "GIG_HOST_STATE_DIR", "GIG_STATE_DIR",
        "OPENCLAW_STATE_DIR", "DISK_CONTROL_STATE_DIR",
        "LIFE_MANAGER_IGNORE_DISK_WRITERS_STOP",
        "LIFE_MANAGER_IGNORE_DISK_PRESSURE_BLOCK",
    ):
        monkeypatch.delenv(key, raising=False)


def test_host_state_uses_os_owner_home_not_environment_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    home = tmp_path / "fresh-home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("LIFE_MANAGER_HOST_STATE_DIR")
    monkeypatch.delenv("LIFE_MANAGER_PRODUCER_STATE_DIR")
    guard = load_guard()
    owner_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    assert guard._host_state_dir() == owner_home / ".local/state/life-manager/state"
    assert guard._state_dir() == home / ".local/state/life-manager"


def test_disk_free_bytes_measures_the_requested_receipt_volume(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    path = tmp_path / "receipt-volume"
    calls = []
    guard = load_guard()
    monkeypatch.setattr(guard.shutil, "disk_usage", lambda actual: (
        calls.append(actual) or SimpleNamespace(total=100, used=40, free=60)
    ))

    assert guard.disk_free_bytes(path) == 60
    assert calls == [path]


@pytest.mark.parametrize("free_bytes", (0, None))
def test_low_or_unavailable_disk_measurement_does_not_block_child(
    tmp_path, monkeypatch, free_bytes,
):
    guard = load_guard()
    monkeypatch.setattr(guard, "disk_free_bytes", lambda _path: free_bytes)
    calls = []
    monkeypatch.setattr(guard.os, "execvpe", lambda *args: calls.append(args))

    assert guard.main(["/bin/true"]) == 0
    assert calls and calls[0][1] == ["/bin/true"]


@pytest.mark.parametrize("free_bytes", (None, -1, True, "unknown", "missing"))
def test_disk_free_bytes_returns_unavailable_for_invalid_measurements(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, free_bytes,
):
    guard = load_guard()
    if free_bytes is None:
        monkeypatch.setattr(guard.shutil, "disk_usage", lambda _path: (_ for _ in ()).throw(OSError()))
    elif free_bytes == "missing":
        monkeypatch.setattr(guard.shutil, "disk_usage", lambda _path: SimpleNamespace())
    else:
        monkeypatch.setattr(guard.shutil, "disk_usage", lambda _path: SimpleNamespace(
            total=100, used=40, free=free_bytes,
        ))

    assert guard.disk_free_bytes(tmp_path) is None


def test_cleanup_stop_signal_does_not_block_child(monkeypatch: pytest.MonkeyPatch):
    host_state = Path(os.environ["LIFE_MANAGER_HOST_STATE_DIR"])
    _write_cleanup_recovery_signal(host_state / "disk-writers.stop")
    guard = load_guard()
    calls = []
    monkeypatch.setattr(guard.os, "execvpe", lambda *args: calls.append(args))

    assert guard.main(["/bin/true"]) == 0
    assert calls and calls[0][1] == ["/bin/true"]


def test_operator_stop_signal_still_blocks_child(monkeypatch: pytest.MonkeyPatch):
    host_state = Path(os.environ["LIFE_MANAGER_HOST_STATE_DIR"])
    host_state.joinpath("disk-writers.stop").write_text("owner=operator\n", encoding="utf-8")
    guard = load_guard()
    calls = []
    monkeypatch.setattr(guard.os, "execvpe", lambda *args: calls.append(args))

    assert guard.main(["/bin/true"]) == 1
    assert calls == []
    receipt = json.loads(
        (Path(os.environ["LIFE_MANAGER_PRODUCER_STATE_DIR"])
         / "state/disk-headroom.json").read_text(encoding="utf-8")
    )
    assert receipt["reason"] == "disk_writers_stop"


def test_fresh_policy_directory_is_created_private(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    host_state = tmp_path / "missing"
    monkeypatch.setenv("LIFE_MANAGER_HOST_STATE_DIR", str(host_state))
    guard = load_guard()
    assert guard.disk_headroom_ok() is True
    assert host_state.stat().st_mode & 0o777 == 0o700


def test_fresh_producer_state_is_created_before_disk_measurement(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    producer_state = tmp_path / "new" / "producer"
    monkeypatch.setenv("LIFE_MANAGER_PRODUCER_STATE_DIR", str(producer_state))
    guard = load_guard()
    assert guard.disk_headroom_ok() is True
    assert producer_state.stat().st_mode & 0o777 == 0o700


def test_symlink_policy_directory_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    monkeypatch.setenv("LIFE_MANAGER_HOST_STATE_DIR", str(alias))
    guard = load_guard()
    assert guard.disk_headroom_ok() is False


def test_pressure_marker_is_advisory(monkeypatch: pytest.MonkeyPatch):
    host_state = Path(os.environ["LIFE_MANAGER_HOST_STATE_DIR"])
    host_state.joinpath("disk-pressure.block").write_text("blocked\n", encoding="utf-8")
    guard = load_guard()
    assert guard.disk_headroom_ok() is True


def test_cli_requires_child_command():
    guard = load_guard()
    assert guard.main([]) == 2
