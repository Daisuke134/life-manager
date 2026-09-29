"""Bounded retry support for runtime bookkeeping under ENOSPC.

The reserve is a preallocated, private file.  It is consumed only after a
bookkeeping write reports ``ENOSPC`` and is restored after the one retry.  A
missing, malformed, symlinked, or incorrectly-owned reserve never causes a
retry or a deletion.  This keeps the boundary fail-closed when the host cannot
prove that capacity recovery is safe.
"""

from __future__ import annotations

from contextlib import contextmanager
import errno
import fcntl
import os
import sqlite3
import stat
import time
from pathlib import Path
from typing import Callable, Iterator, TypeVar


RUNTIME_RESERVE_BYTES = 512 * 1024
DEFAULT_RUNTIME_RESERVE = (
    Path.home() / ".local/state/life-manager/life-manager-disk-cleanup/.runtime-reserve"
)
T = TypeVar("T")


class _ReserveUnavailable(Exception):
    """The first ENOSPC cannot be retried safely with the reserve."""


def runtime_reserve_path() -> Path:
    configured = os.environ.get("LIFE_MANAGER_RUNTIME_RESERVE_PATH", "").strip()
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_absolute():
            return candidate
    return DEFAULT_RUNTIME_RESERVE


def runtime_reserve_valid(path: Path | None = None) -> bool:
    reserve = path or runtime_reserve_path()
    try:
        info = reserve.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(info.st_mode)
        and stat.S_IMODE(info.st_mode) == 0o600
        and info.st_size == RUNTIME_RESERVE_BYTES
        and getattr(info, "st_blocks", 0) * 512 >= RUNTIME_RESERVE_BYTES
    )


@contextmanager
def _parent_lock(path: Path) -> Iterator[int]:
    """Serialize reserve consumption without allocating a lock file."""
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path.parent, flags)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield descriptor
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _restore_locked(path: Path, parent_fd: int) -> None:
    if runtime_reserve_valid(path):
        return
    try:
        info = path.lstat()
    except FileNotFoundError:
        info = None
    if info is not None:
        # Never remove an unexpected path while trying to repair capacity.
        raise OSError(errno.EACCES, "runtime reserve path is not a valid regular file", path)

    temporary_name = (
        f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    descriptor = -1
    try:
        descriptor = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=parent_fd,
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            remaining = RUNTIME_RESERVE_BYTES
            chunk = b"\0" * min(1024 * 1024, RUNTIME_RESERVE_BYTES)
            while remaining:
                written = handle.write(chunk[:remaining])
                if written != min(len(chunk), remaining):
                    raise OSError(errno.EIO, "short runtime reserve write")
                remaining -= written
            os.fchmod(handle.fileno(), 0o600)
            handle.flush()
            os.fsync(handle.fileno())
        if not runtime_reserve_valid(path.parent / temporary_name):
            raise OSError(errno.EIO, "runtime reserve readback failed")
        os.replace(temporary_name, path.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            os.unlink(temporary_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass


def _is_capacity_error(error: BaseException) -> bool:
    if isinstance(error, OSError):
        return error.errno == errno.ENOSPC
    if isinstance(error, sqlite3.OperationalError):
        message = str(error).lower()
        return any(marker in message for marker in (
            "database or disk is full",
            "unable to open database file",
            "no space left on device",
        ))
    return False


def ensure_runtime_reserve(path: Path | None = None) -> bool:
    """Create the reserve while capacity is healthy; never delete surprises."""
    reserve = path or runtime_reserve_path()
    try:
        reserve.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with _parent_lock(reserve) as parent_fd:
            if runtime_reserve_valid(reserve):
                return True
            try:
                reserve.lstat()
            except FileNotFoundError:
                pass
            else:
                return False
            _restore_locked(reserve, parent_fd)
            return runtime_reserve_valid(reserve)
    except OSError:
        return False


def _retry_with_reserve(operation: Callable[[], T], reserve: Path) -> T:
    try:
        reserve.parent.stat()
    except (FileNotFoundError, NotADirectoryError, PermissionError) as error:
        raise _ReserveUnavailable from error
    if not runtime_reserve_valid(reserve):
        raise _ReserveUnavailable
    with _parent_lock(reserve) as parent_fd:
        if not runtime_reserve_valid(reserve):
            raise _ReserveUnavailable
        os.unlink(reserve.name, dir_fd=parent_fd)
        os.fsync(parent_fd)
        try:
            return operation()
        finally:
            try:
                _restore_locked(reserve, parent_fd)
            except OSError:
                # Preserve the operation's result/error.  The next healthy
                # cleanup wake will recreate the reserve.
                pass


def retry_on_enospc(operation: Callable[[], T]) -> T:
    """Run ``operation`` once, then retry once after consuming the reserve."""
    try:
        return operation()
    except Exception as first:
        if not _is_capacity_error(first):
            raise
        reserve = runtime_reserve_path()
        try:
            return _retry_with_reserve(operation, reserve)
        except _ReserveUnavailable:
            raise first
