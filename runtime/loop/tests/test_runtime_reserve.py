"""ENOSPC recovery is bounded, private, and fail-closed."""

from __future__ import annotations

import errno
import os
import sqlite3
from pathlib import Path

import pytest

from runtime.loop.runtime_reserve import (
    RUNTIME_RESERVE_BYTES,
    ensure_runtime_reserve,
    retry_on_enospc,
    runtime_reserve_valid,
)


def _seed(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\0" * RUNTIME_RESERVE_BYTES)
    path.chmod(0o600)


def test_enospc_consumes_reserve_retries_once_and_restores(tmp_path: Path, monkeypatch) -> None:
    reserve = tmp_path / "state" / ".runtime-reserve"
    _seed(reserve)
    monkeypatch.setenv("LIFE_MANAGER_RUNTIME_RESERVE_PATH", str(reserve))
    target = tmp_path / "target"
    calls = 0

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError(errno.ENOSPC, "full")
        target.write_text("saved", encoding="utf-8")
        return "ok"

    assert retry_on_enospc(operation) == "ok"
    assert calls == 2
    assert target.read_text(encoding="utf-8") == "saved"
    assert runtime_reserve_valid(reserve)


def test_missing_or_malformed_reserve_does_not_retry_or_delete(tmp_path: Path, monkeypatch) -> None:
    reserve = tmp_path / "state" / ".runtime-reserve"
    reserve.parent.mkdir()
    reserve.write_text("not a reserve", encoding="utf-8")
    reserve.chmod(0o600)
    before = reserve.read_bytes()
    monkeypatch.setenv("LIFE_MANAGER_RUNTIME_RESERVE_PATH", str(reserve))
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise OSError(errno.ENOSPC, "full")

    with pytest.raises(OSError) as caught:
        retry_on_enospc(operation)
    assert caught.value.errno == errno.ENOSPC
    assert calls == 1
    assert reserve.read_bytes() == before


def test_other_errno_is_not_retried(tmp_path: Path, monkeypatch) -> None:
    reserve = tmp_path / "state" / ".runtime-reserve"
    _seed(reserve)
    monkeypatch.setenv("LIFE_MANAGER_RUNTIME_RESERVE_PATH", str(reserve))
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise OSError(errno.EIO, "io")

    with pytest.raises(OSError) as caught:
        retry_on_enospc(operation)
    assert caught.value.errno == errno.EIO
    assert calls == 1
    assert runtime_reserve_valid(reserve)


def test_sqlite_disk_full_is_retried_with_reserve(tmp_path: Path, monkeypatch) -> None:
    reserve = tmp_path / "state" / ".runtime-reserve"
    _seed(reserve)
    monkeypatch.setenv("LIFE_MANAGER_RUNTIME_RESERVE_PATH", str(reserve))
    calls = 0

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise sqlite3.OperationalError("database or disk is full")
        return "ok"

    assert retry_on_enospc(operation) == "ok"
    assert calls == 2
    assert runtime_reserve_valid(reserve)


def test_symlink_reserve_is_not_followed_or_removed(tmp_path: Path, monkeypatch) -> None:
    reserve = tmp_path / "state" / ".runtime-reserve"
    target = tmp_path / "important"
    target.write_text("keep", encoding="utf-8")
    reserve.parent.mkdir()
    reserve.symlink_to(target)
    monkeypatch.setenv("LIFE_MANAGER_RUNTIME_RESERVE_PATH", str(reserve))

    with pytest.raises(OSError) as caught:
        retry_on_enospc(lambda: (_ for _ in ()).throw(OSError(errno.ENOSPC, "full")))
    assert caught.value.errno == errno.ENOSPC
    assert reserve.is_symlink()
    assert target.read_text(encoding="utf-8") == "keep"


def test_ensure_creates_private_reserve(tmp_path: Path) -> None:
    reserve = tmp_path / "nested" / ".runtime-reserve"
    assert ensure_runtime_reserve(reserve)
    assert runtime_reserve_valid(reserve)
    assert os.stat(reserve).st_mode & 0o777 == 0o600
