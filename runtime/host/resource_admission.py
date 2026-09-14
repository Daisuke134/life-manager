"""Small FIFO semaphore for finite Life Manager runs."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import pwd
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable


def process_start(pid: int) -> str | None:
    ps = shutil.which("ps")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0 or not ps:
        return None
    result = subprocess.run(
        [ps, "-p", str(pid), "-o", "lstart="], capture_output=True,
        text=True, check=False,
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def state_root() -> Path:
    configured = os.environ.get("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT")
    if configured:
        return Path(configured).expanduser()
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    return home / ".local/state/life-manager/host-admission/resources"


def atomic_json(path: Path, value: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _row(path: Path) -> dict[str, object] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _live(path: Path) -> bool:
    value = _row(path)
    return bool(value and process_start(value.get("pid")) == value.get("process_start"))


def _capacity(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as error:
        raise RuntimeError(f"invalid capacity: {name}") from error
    if not 1 <= value <= 64:
        raise RuntimeError(f"invalid capacity: {name}")
    return value


def try_acquire(resource_class: str, owner_id: str) -> tuple[Path | None, str]:
    """Atomically claim a slot; live waiters are served FIFO within each class."""
    if resource_class not in {"agent", "deterministic"} or not owner_id:
        raise RuntimeError("invalid resource identity")
    root = state_root()
    owners, tickets = root / "owners", root / "tickets"
    for path in (root, owners, tickets):
        path.mkdir(parents=True, exist_ok=True, mode=0o700); os.chmod(path, 0o700)
    descriptor = os.open(root / "control.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        owner_rows = []
        for path in owners.glob("*.json"):
            if not _live(path):
                path.unlink(missing_ok=True); continue
            owner_rows.append(_row(path) or {})
        if any(row.get("owner_id") == owner_id for row in owner_rows):
            return None, "owner_busy"

        digest = hashlib.sha256(owner_id.encode()).hexdigest()
        matches = list(tickets.glob(f"{resource_class}-*-{digest}.json"))
        ticket = matches[0] if matches else tickets / (
            f"{resource_class}-{time.time_ns():020d}-{digest}.json")
        started = process_start(os.getpid())
        if not started:
            raise RuntimeError("process identity unavailable")
        atomic_json(ticket, {"version": 1, "pid": os.getpid(),
                    "process_start": started, "owner_id": owner_id})

        total_limit = _capacity("LIFE_MANAGER_HOST_MAX_FINITE_RUNS", 3)
        class_limit = _capacity(
            "LIFE_MANAGER_HOST_MAX_AGENT_RUNS" if resource_class == "agent"
            else "LIFE_MANAGER_HOST_MAX_DETERMINISTIC_RUNS",
            1 if resource_class == "agent" else 2,
        )
        if len(owner_rows) >= total_limit or sum(
            row.get("resource_class") == resource_class for row in owner_rows
        ) >= class_limit:
            return None, "capacity_busy"

        head = None
        for candidate in sorted(tickets.glob(f"{resource_class}-*.json")):
            if _live(candidate):
                head = candidate
                break
            candidate.unlink(missing_ok=True)
        if head is not None and head != ticket:
            return None, "fifo_wait"

        claim = owners / f"{digest}-{os.getpid()}.json"
        atomic_json(claim, {"version": 1, "pid": os.getpid(),
                    "process_start": started, "owner_id": owner_id,
                    "resource_class": resource_class})
        ticket.unlink(missing_ok=True)
        return claim, "acquired"
    finally:
        os.close(descriptor)


def acquire(resource_class: str, owner_id: str,
            cancelled: Callable[[], bool] = lambda: False) -> Path:
    delay = 1.0
    while True:
        if cancelled():
            raise InterruptedError("resource admission interrupted")
        claim, reason = try_acquire(resource_class, owner_id)
        if claim is not None:
            if cancelled():
                release(claim)
                raise InterruptedError("resource admission interrupted")
            return claim
        time.sleep(delay)
        delay = min(15.0, delay * 2 if reason == "fifo_wait" else 5.0)


def release(claim: Path) -> None:
    value = _row(claim)
    if (not value or value.get("pid") != os.getpid()
            or value.get("process_start") != process_start(os.getpid())):
        raise RuntimeError("resource claim ownership mismatch")
    claim.unlink()
