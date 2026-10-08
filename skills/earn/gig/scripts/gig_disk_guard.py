#!/usr/bin/env python3
"""Check Gig writer controls and disk measurement without a free-space floor."""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Sequence


# Free-space measurements are recorded for diagnosis, not used as an admission floor.
REQUIRED_BYTES = 0
RECEIPT_PATH = Path("state") / "disk-headroom.json"

_PRODUCER_GATE = "life-manager-producer-preflight"
_POLICY_FLAGS = (
    ("disk-writers.stop", "disk_writers_stop"),
)


def _state_dir() -> Path:
    return Path(os.environ.get("GIG_STATE_DIR") or (Path.home() / "gig"))


def _fsync_directory(directory: Path) -> None:
    """Flush the directory entry after replacing a receipt, then close the fd."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(str(directory), flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _write_receipt(state_dir: Path, receipt: dict[str, object]) -> str:
    """Atomically replace the lane-wide headroom receipt and return its JSON."""
    destination = state_dir / RECEIPT_PATH
    payload = json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    temporary: Path | None = None
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=".disk-headroom.", suffix=".tmp", dir=destination.parent,
        )
        temporary = Path(temporary_name)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        temporary = None
        _fsync_directory(destination.parent)
    except Exception as exc:  # The guard still fails closed if receipt storage is unavailable.
        print(f"gig_disk_guard: could not persist receipt: {exc}", file=sys.stderr)
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
    return payload


def _failure(
    reason: str,
    available_bytes: int | None,
    *,
    metadata: dict[str, object] | None = None,
) -> int:
    receipt: dict[str, object] = {
        "status": "failed",
        "failed": 1,
        "effect": 0,
        "readback": 0,
        "reason": reason,
        "required_bytes": REQUIRED_BYTES,
    }
    if available_bytes is not None:
        receipt["available_bytes"] = available_bytes
    if metadata:
        receipt.update(metadata)
    payload = _write_receipt(_state_dir(), receipt)
    print(payload)
    return 1


def _host_state_dir() -> Path:
    """Return the host control state without relying on a shell wrapper."""
    configured = (
        os.environ.get("GIG_HOST_STATE_DIR")
        or os.environ.get("DISK_CONTROL_STATE_DIR")
        or os.environ.get("OPENCLAW_STATE_DIR")
        or os.environ.get("LIFE_MANAGER_HOST_STATE_DIR")
    )
    if configured:
        return Path(configured).expanduser()
    # The production sentinel and emergency guard both write here. Installers can
    # override it above when Life Manager is used without OpenClaw.
    return Path.home() / ".openclaw" / "state"


def _producer_gate() -> tuple[str, Path] | None:
    """Read the shared Life Manager stop contract before starting a producer."""
    host_state = _host_state_dir()
    try:
        entry = host_state.lstat()
        if (
            not stat.S_ISDIR(entry.st_mode)
            or host_state.is_symlink()
            or entry.st_uid != os.getuid()
            or entry.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        ):
            return "disk_policy_unavailable", host_state
        next(iter(host_state.iterdir()), None)
    except FileNotFoundError:
        return "disk_policy_unavailable", host_state
    except OSError:
        return "disk_policy_unavailable", host_state
    for filename, reason in _POLICY_FLAGS:
        flag = host_state / filename
        try:
            entry = flag.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            # A control path that cannot be read is not proof that the host is safe.
            return "disk_policy_unavailable", flag
        if not stat.S_ISREG(entry.st_mode):
            return "disk_policy_unavailable", flag
        return reason, flag
    return None


def disk_headroom_ok() -> bool:
    """Return whether this producer may allocate new work on the host."""
    gate = _producer_gate()
    if gate is not None:
        reason, flag = gate
        try:
            available_bytes = int(shutil.disk_usage(_state_dir()).free)
        except Exception:
            available_bytes = None
        _failure(
            reason,
            available_bytes,
            metadata={
                "gate": _PRODUCER_GATE,
                "flag_path": str(flag),
            },
        )
        return False
    try:
        available_bytes = int(shutil.disk_usage(_state_dir()).free)
    except Exception:
        _failure("disk_headroom_unavailable", None)
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    remaining = list(sys.argv[1:] if argv is None else argv)
    if not remaining:
        print("gig_disk_guard: missing child argv", file=sys.stderr)
        return 2

    if not disk_headroom_ok():
        return 1

    os.execvpe(remaining[0], remaining, os.environ)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
