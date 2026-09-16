"""Small FIFO semaphore for finite Life Manager runs."""

from __future__ import annotations

import ctypes
import fcntl
import hashlib
import json
import os
import pwd
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable


ADMISSION_CLASSES = {"borrow", "revenue"}
ADMISSION_POLICY = "revenue-floor-v1"
RESOURCE_CLASSES = ("agent", "browser", "deterministic")

# ``admission_class`` remains the mixed-release capacity fence.  These
# explicit priorities are an ordering policy for durable waiters and are
# evaluated from persisted queue age at claim time.
BASE_PRIORITIES = ("critical_paid", "revenue", "support")
PRIORITY_RANK = {name: rank for rank, name in enumerate(BASE_PRIORITIES)}
PRIORITY_AGE_SECONDS = {
    "critical_paid": 5 * 60,
    "revenue": 30 * 60,
    "support": 2 * 60 * 60,
}
OCCURRENCE_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 300


class _ProcBsdInfo(ctypes.Structure):
    """Darwin's fixed PROC_PIDTBSDINFO record (sys/proc_info.h)."""

    _fields_ = [
        ("identity", ctypes.c_uint32 * 12),
        ("command", ctypes.c_char * 16),
        ("name", ctypes.c_char * 32),
        ("nfiles", ctypes.c_uint32),
        ("pgid", ctypes.c_uint32),
        ("pjobc", ctypes.c_uint32),
        ("terminal_device", ctypes.c_uint32),
        ("terminal_process_group", ctypes.c_uint32),
        ("nice", ctypes.c_int32),
        ("started_seconds", ctypes.c_uint64),
        ("started_microseconds", ctypes.c_uint64),
    ]


def _darwin_process_start(pid: int) -> str | None:
    try:
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        proc_pidinfo = libproc.proc_pidinfo
        proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                 ctypes.c_void_p, ctypes.c_int]
        proc_pidinfo.restype = ctypes.c_int
        value = _ProcBsdInfo()
        size = ctypes.sizeof(value)
        read = proc_pidinfo(pid, 3, 0, ctypes.byref(value), size)
    except (AttributeError, OSError):
        return None
    if read != size or value.identity[3] != pid or value.started_seconds <= 0:
        return None
    started = time.localtime(value.started_seconds)
    weekdays = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return (f"{weekdays[started.tm_wday]} {months[started.tm_mon - 1]} "
            f"{started.tm_mday:2d} {started.tm_hour:02d}:{started.tm_min:02d}:"
            f"{started.tm_sec:02d} {started.tm_year:04d}")


def process_start(pid: int) -> str | None:
    ps = shutil.which("ps")
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return None
    if sys.platform == "darwin":
        return _darwin_process_start(pid)
    if not ps:
        return None
    try:
        result = subprocess.run(
            [ps, "-p", str(pid), "-o", "lstart="], capture_output=True,
            text=True, check=False, timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def process_starts() -> dict[int, str] | None:
    """Read every process identity once, outside the admission lock."""
    ps = shutil.which("ps")
    if not ps:
        return None
    try:
        result = subprocess.run(
            [ps, "-axo", "pid=,lstart="], capture_output=True,
            text=True, check=False, timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    values: dict[int, str] = {}
    for line in result.stdout.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2:
            continue
        try:
            values[int(parts[0])] = parts[1]
        except ValueError:
            continue
    return values


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


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, TypeError):
        return False
    return True


def _live(path: Path, starts: dict[int, str | None] | None = None,
          snapshot_started_ns: int | None = None, *, probe_missing: bool = False) -> bool:
    value = _row(path)
    if not value or not isinstance(value.get("pid"), int):
        return False
    if starts is None:
        actual = process_start(value["pid"])
    else:
        if probe_missing and value["pid"] not in starts:
            starts[value["pid"]] = process_start(value["pid"])
        actual = starts.get(value["pid"])
    if actual is not None:
        if actual == value.get("process_start"):
            return True
        try:
            changed_after_snapshot = (
                snapshot_started_ns is not None
                and path.stat().st_mtime_ns >= snapshot_started_ns
            )
        except OSError:
            changed_after_snapshot = True
        return changed_after_snapshot and _pid_exists(value["pid"])
    return _pid_exists(value["pid"])


def _capacity(name: str, default: int, *, minimum: int = 1) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError as error:
        raise RuntimeError(f"invalid capacity: {name}") from error
    if not minimum <= value <= 64:
        raise RuntimeError(f"invalid capacity: {name}")
    return value


def _durable_paths() -> tuple[Path, Path, Path, Path]:
    root = state_root()
    owners, tickets = root / "owners", root / "tickets"
    for path in (root, owners, tickets):
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path, 0o700)
    return root, owners, tickets, root / "admission-v2.sqlite3"


def durable_protocol_version() -> int:
    path = state_root() / "protocol.json"
    if not path.is_file():
        return 1
    value = _row(path)
    if not value or value.get("version") not in {1, 2}:
        raise RuntimeError("invalid durable admission protocol")
    return int(value["version"])


def activate_durable_v2(*, allow_live_owners: bool = False) -> None:
    """Atomically enable v2 only after every legacy admission owner drains."""
    if durable_protocol_version() == 2:
        return
    root, owners, tickets, database = _durable_paths()
    starts, snapshot_started_ns = _identity_snapshot(owners, tickets)
    descriptor = os.open(root / "control.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        if durable_protocol_version() == 2:
            return
        for path in owners.glob("*.json"):
            if _live(path, starts, snapshot_started_ns):
                if allow_live_owners:
                    continue
                raise RuntimeError("legacy admission is not idle")
            path.unlink(missing_ok=True)
        for path in tickets.glob("*.json"):
            row = _row(path)
            if not row:
                path.unlink(missing_ok=True)
            elif row.get("version", 1) == 1:
                if _live(path, starts, snapshot_started_ns):
                    raise RuntimeError("legacy admission is not idle")
                path.unlink(missing_ok=True)
        if list(tickets.glob("*.json")):
            raise RuntimeError("legacy admission is not idle")
        with _database(database) as connection:
            queued = connection.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
            reserved = connection.execute("SELECT COUNT(*) FROM reservations").fetchone()[0]
            if queued or reserved:
                raise RuntimeError("durable admission is not idle")
        atomic_json(root / "protocol.json", {"version": 2})
    finally:
        os.close(descriptor)


def _digest(owner_id: str) -> str:
    return hashlib.sha256(owner_id.encode()).hexdigest()


def _acquire_bounded(descriptor: int, timeout_seconds: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(0.01, remaining))


def _database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=0)
    os.chmod(path, 0o600)
    connection.execute("PRAGMA journal_mode=DELETE")
    connection.execute("PRAGMA synchronous=FULL")
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version not in {0, 2}:
        connection.close()
        raise RuntimeError("unsupported durable admission schema")
    legacy_class_tables = []
    for table in ("queue", "occurrences"):
        existing = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        if existing and "'browser'" not in str(existing[0]):
            legacy_name = f"{table}_legacy_browser"
            connection.execute(f"ALTER TABLE {table} RENAME TO {legacy_name}")
            legacy_class_tables.append((table, legacy_name))
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS queue (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id TEXT NOT NULL UNIQUE,
            resource_class TEXT NOT NULL CHECK(resource_class IN ('agent','browser','deterministic'))
        );
        CREATE TABLE IF NOT EXISTS reservations (
            owner_id TEXT PRIMARY KEY,
            resource_class TEXT NOT NULL,
            sequence INTEGER NOT NULL UNIQUE,
            lease_until REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS priorities (
            owner_id TEXT PRIMARY KEY,
            admission_class TEXT NOT NULL CHECK(admission_class IN ('borrow','revenue')),
            admission_policy TEXT,
            base_priority TEXT,
            queued_at REAL
        );
        CREATE TABLE IF NOT EXISTS occurrences (
            occurrence_id TEXT PRIMARY KEY,
            owner_id TEXT NOT NULL,
            resource_class TEXT NOT NULL CHECK(resource_class IN ('agent','browser','deterministic')),
            admission_class TEXT NOT NULL CHECK(admission_class IN ('borrow','revenue')),
            base_priority TEXT NOT NULL,
            queued_at REAL NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('queued','claimed','released','cancelled')),
            sequence INTEGER
        );
        PRAGMA user_version=2;
    """)
    for table, legacy_name in legacy_class_tables:
        columns = "sequence,owner_id,resource_class" if table == "queue" else (
            "occurrence_id,owner_id,resource_class,admission_class,base_priority,"
            "queued_at,state,sequence"
        )
        connection.execute(
            f"INSERT OR IGNORE INTO {table}({columns}) SELECT {columns} FROM {legacy_name}"
        )
        connection.execute(f"DROP TABLE {legacy_name}")
    priority_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(priorities)")
    }
    if "admission_policy" not in priority_columns:
        connection.execute("ALTER TABLE priorities ADD COLUMN admission_policy TEXT")
    if "next_eligible_at" not in priority_columns:
        connection.execute(
            "ALTER TABLE priorities ADD COLUMN next_eligible_at REAL NOT NULL DEFAULT 0")
    if "base_priority" not in priority_columns:
        connection.execute("ALTER TABLE priorities ADD COLUMN base_priority TEXT")
    if "queued_at" not in priority_columns:
        connection.execute("ALTER TABLE priorities ADD COLUMN queued_at REAL")
    # Backfill old v2 rows once.  A missing timestamp is not evidence that a
    # waiter has been present forever, so use the first migration observation.
    migration_now = time.time()
    connection.execute(
        """UPDATE priorities
              SET base_priority = CASE admission_class
                  WHEN 'revenue' THEN 'revenue' ELSE 'support' END
            WHERE base_priority IS NULL"""
    )
    connection.execute(
        "UPDATE priorities SET queued_at=? WHERE queued_at IS NULL",
        (migration_now,),
    )
    return connection


def _limits(resource_class: str, admission_class: str = "borrow") -> tuple[int, int]:
    total = _capacity("LIFE_MANAGER_HOST_MAX_FINITE_RUNS", 5)
    if admission_class == "revenue":
        return total, _capacity("LIFE_MANAGER_HOST_MAX_REVENUE_RUNS", total)
    per_class = _capacity(
        "LIFE_MANAGER_HOST_MAX_AGENT_RUNS" if resource_class == "agent"
        else "LIFE_MANAGER_HOST_MAX_BROWSER_RUNS" if resource_class == "browser"
        else "LIFE_MANAGER_HOST_MAX_DETERMINISTIC_RUNS",
        1 if resource_class in {"agent", "browser"} else 2,
    )
    return total, per_class


def _revenue_floor(total: int) -> int:
    """Return capacity that borrow-only work must leave for revenue work."""
    # Older callers explicitly set the total for isolated/v1 operation and do
    # not know about the floor. New launchd plists carry the floor explicitly;
    # the default keeps an unconfigured five-run host safe during migration.
    default = (
        min(4, total)
        if "LIFE_MANAGER_HOST_MAX_FINITE_RUNS" not in os.environ else 0
    )
    requested = _capacity(
        "LIFE_MANAGER_HOST_MIN_REVENUE_RUNS", default, minimum=0)
    revenue_limit = _capacity("LIFE_MANAGER_HOST_MAX_REVENUE_RUNS", total)
    return min(total, requested, revenue_limit)


def _default_priority(admission_class: str) -> str:
    return "revenue" if admission_class == "revenue" else "support"


def _normalize_priority(priority: str | None, admission_class: str) -> str:
    value = _default_priority(admission_class) if priority is None else priority
    if value not in PRIORITY_RANK:
        raise RuntimeError("invalid queue priority")
    if value == "critical_paid" and admission_class != "revenue":
        raise RuntimeError("critical_paid requires revenue admission")
    return value


def _normalize_occurrence_id(occurrence_id: str | None) -> str | None:
    if occurrence_id is None:
        return None
    if not isinstance(occurrence_id, str) or not OCCURRENCE_ID_PATTERN.fullmatch(occurrence_id):
        raise RuntimeError("invalid occurrence identity")
    return occurrence_id


def _heartbeat_timeout_seconds() -> int:
    try:
        value = int(os.environ.get(
            "LIFE_MANAGER_CLAIM_HEARTBEAT_TIMEOUT_SECONDS",
            str(DEFAULT_HEARTBEAT_TIMEOUT_SECONDS),
        ))
    except ValueError as error:
        raise RuntimeError("invalid heartbeat timeout") from error
    if not 1 <= value <= 3600:
        raise RuntimeError("invalid heartbeat timeout")
    return value


def _heartbeat_expired(row: dict[str, object], now: float) -> bool:
    if row.get("phase") not in {"claimed", "running"}:
        return False
    heartbeat_at = row.get("heartbeat_at")
    timeout = row.get("heartbeat_timeout_seconds", DEFAULT_HEARTBEAT_TIMEOUT_SECONDS)
    if (not isinstance(heartbeat_at, (int, float)) or isinstance(heartbeat_at, bool)
            or not isinstance(timeout, (int, float)) or isinstance(timeout, bool)):
        # Legacy claims have no heartbeat contract and remain governed by
        # process identity until a compatible runner rewrites them.
        return False
    return now - float(heartbeat_at) > float(timeout)


def _record_occurrence(connection: sqlite3.Connection, occurrence_id: str,
                       owner_id: str, resource_class: str,
                       admission_class: str, priority: str, queued_at: float,
                       sequence: int) -> None:
    existing = connection.execute(
        """SELECT owner_id,resource_class,admission_class,base_priority
             FROM occurrences WHERE occurrence_id=?""",
        (occurrence_id,),
    ).fetchone()
    expected = (owner_id, resource_class, admission_class, priority)
    if existing is not None and existing != expected:
        raise RuntimeError("occurrence identity changed")
    connection.execute(
        """INSERT OR IGNORE INTO occurrences(
               occurrence_id,owner_id,resource_class,admission_class,
               base_priority,queued_at,state,sequence
           ) VALUES(?,?,?,?,?,?,?,?)""",
        (occurrence_id, owner_id, resource_class, admission_class,
         priority, queued_at, "queued", sequence),
    )


def _effective_priority(row: dict[str, object], now: float) -> int:
    priority = row.get("base_priority")
    admission_class = row.get("admission_class", "borrow")
    if not isinstance(priority, str) or priority not in PRIORITY_RANK:
        priority = _default_priority(
            admission_class if isinstance(admission_class, str) else "borrow"
        )
    rank = PRIORITY_RANK[priority]
    queued_at = row.get("queued_at")
    if not isinstance(queued_at, (int, float)) or isinstance(queued_at, bool):
        return rank
    if now - float(queued_at) >= PRIORITY_AGE_SECONDS[priority]:
        return PRIORITY_RANK["critical_paid"]
    return rank


def _durable_queue_rows(connection: sqlite3.Connection, resource_class: str,
                        now: float) -> list[dict[str, object]]:
    rows = [
        dict(zip(("owner_id", "sequence", "resource_class",
                  "admission_class", "base_priority", "queued_at"), row))
        for row in connection.execute(
            """SELECT q.owner_id,q.sequence,q.resource_class,
                      COALESCE(p.admission_class,'borrow'),p.base_priority,p.queued_at
                 FROM queue q
                 LEFT JOIN reservations r ON r.owner_id=q.owner_id
                 LEFT JOIN priorities p ON p.owner_id=q.owner_id
                WHERE q.resource_class=? AND r.owner_id IS NULL
                  AND COALESCE(p.next_eligible_at,0)<=?""",
            (resource_class, now),
        )
    ]
    rows.sort(key=lambda row: (
        _effective_priority(row, now),
        int(row["sequence"]),
        str(row["owner_id"]),
    ))
    return rows


def _next_durable_candidate(connection: sqlite3.Connection, owners: Path,
                            tickets: Path, resource_class: str, now: float,
                            starts: dict[int, str | None],
                            snapshot_started_ns: int) -> dict[str, object] | None:
    """Choose the first waiter that both wins ordering and fits capacity."""
    if _legacy_waiter_exists(tickets, resource_class, starts, snapshot_started_ns):
        return None
    for row in _durable_queue_rows(connection, resource_class, now):
        available, _ = _durable_capacity(
            connection, owners, resource_class,
            str(row.get("admission_class", "borrow")), now,
            starts, snapshot_started_ns,
        )
        if available:
            return row
    return None


def _uses_limited_capacity(row: dict[str, object], resource_class: str,
                           admission_class: str) -> bool:
    if admission_class == "revenue":
        return row.get("admission_class", "borrow") == "revenue"
    return row.get("resource_class") == resource_class


def _legacy_owner_present(occupied: list[dict[str, object]]) -> bool:
    return any(
        row.get("admission_class", "borrow") == "borrow"
        and
        row.get("admission_policy") != ADMISSION_POLICY
        for row in occupied
    )


def _capacity_available(occupied: list[dict[str, object]],
                        resource_class: str, admission_class: str) -> bool:
    total, per_class = _limits(resource_class, admission_class)
    if len(occupied) >= total:
        return False
    if (admission_class == "revenue" and _revenue_floor(total)
            and _legacy_owner_present(occupied)):
        return False
    if sum(_uses_limited_capacity(row, resource_class, admission_class)
           for row in occupied) >= per_class:
        return False
    if admission_class == "borrow":
        borrow_count = sum(
            row.get("admission_class", "borrow") == "borrow"
            for row in occupied
        )
        if borrow_count >= total - _revenue_floor(total):
            return False
    return True


def _capacity_overflow(occupied: list[dict[str, object]],
                       resource_class: str, admission_class: str) -> bool:
    total, per_class = _limits(resource_class, admission_class)
    if len(occupied) > total:
        return True
    if sum(_uses_limited_capacity(row, resource_class, admission_class)
           for row in occupied) > per_class:
        return True
    if admission_class == "borrow":
        borrow_count = sum(
            row.get("admission_class", "borrow") == "borrow"
            for row in occupied
        )
        if borrow_count > total - _revenue_floor(total):
            return True
    return False


def _identity_snapshot(*directories: Path) -> tuple[dict[int, str | None], int]:
    snapshot_started_ns = time.time_ns()
    pids = {row.get("pid") for directory in directories for _, row in (
        (path, _row(path) or {}) for path in directory.glob("*.json"))
        if isinstance(row.get("pid"), int)}
    return {pid: process_start(pid) for pid in pids}, snapshot_started_ns


def _durable_capacity(connection: sqlite3.Connection, owners: Path, resource_class: str,
                      admission_class: str,
                      now: float, starts: dict[int, str | None],
                      snapshot_started_ns: int) -> tuple[bool, list[dict[str, object]]]:
    live = []
    for path in owners.glob("*.json"):
        row = _row(path) or {}
        if (_live(path, starts, snapshot_started_ns)
                and not _heartbeat_expired(row, now)):
            live.append(row)
        else:
            if (row.get("version") == 2 and row.get("phase", "claimed") in {"claimed", "running"}
                    and isinstance(row.get("sequence"), int)
                    and not isinstance(row.get("sequence"), bool)
                    and isinstance(row.get("owner_id"), str) and row["owner_id"]
                    and row.get("resource_class") in set(RESOURCE_CLASSES)):
                connection.execute(
                    "INSERT OR IGNORE INTO queue(sequence,owner_id,resource_class) VALUES(?,?,?)",
                    (row["sequence"], row["owner_id"], row["resource_class"]))
                connection.execute(
                    """INSERT OR IGNORE INTO priorities(
                           owner_id,admission_class,admission_policy,base_priority,queued_at
                       ) VALUES(?,?,?,?,?)""",
                    (row["owner_id"], row.get("admission_class", "borrow"),
                     row.get("admission_policy"), row.get("base_priority"),
                     row.get("queued_at", now)))
                occurrence_id = row.get("occurrence_id")
                if isinstance(occurrence_id, str) and occurrence_id:
                    connection.execute(
                        "UPDATE occurrences SET state='queued' WHERE occurrence_id=?",
                        (occurrence_id,),
                    )
            path.unlink(missing_ok=True)
    connection.execute("DELETE FROM reservations WHERE lease_until <= ?", (now,))
    reserved = [dict(zip(("owner_id", "resource_class", "sequence", "lease_until",
                          "admission_class", "admission_policy"), row))
                for row in connection.execute("""
                    SELECT r.owner_id,r.resource_class,r.sequence,r.lease_until,
                           COALESCE(p.admission_class,'borrow'),p.admission_policy
                    FROM reservations r
                    LEFT JOIN priorities p ON p.owner_id=r.owner_id
                """)]
    occupied = live + reserved
    available = _capacity_available(occupied, resource_class, admission_class)
    return available, occupied


def _legacy_waiter_exists(tickets: Path, resource_class: str,
                          starts: dict[int, str | None],
                          snapshot_started_ns: int) -> bool:
    for path in tickets.glob(f"{resource_class}-*.json"):
        row = _row(path)
        if not row or row.get("version", 1) != 1:
            continue
        if _live(path, starts, snapshot_started_ns):
            return True
        path.unlink(missing_ok=True)
    return False


def enqueue_durable(resource_class: str, owner_id: str, *,
                    admission_class: str = "borrow",
                    priority: str | None = None,
                    occurrence_id: str | None = None,
                    now: float | None = None) -> tuple[Path | None, str]:
    """Persist a process-independent, priority-aware queue position."""
    if (resource_class not in set(RESOURCE_CLASSES) or not owner_id
            or admission_class not in ADMISSION_CLASSES):
        raise RuntimeError("invalid resource identity")
    priority_name = _normalize_priority(priority, admission_class)
    occurrence_name = _normalize_occurrence_id(occurrence_id)
    instant = time.time() if now is None else now
    root, owners, tickets, database = _durable_paths()
    starts, snapshot_started_ns = _identity_snapshot(owners, tickets)
    descriptor = os.open(root / "control.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if not _acquire_bounded(descriptor):
            return None, "control_busy"
        with _database(database) as connection:
            instant = time.time() if now is None else now
            available, _ = _durable_capacity(
                connection, owners, resource_class, admission_class,
                instant,
                starts, snapshot_started_ns)
            if any(item.get("owner_id") == owner_id for item in (
                    _row(path) or {} for path in owners.glob("*.json"))):
                if occurrence_name is not None:
                    connection.execute(
                        "INSERT OR IGNORE INTO queue(owner_id,resource_class) VALUES(?,?)",
                        (owner_id, resource_class),
                    )
                    connection.execute(
                        """INSERT OR IGNORE INTO priorities(
                               owner_id,admission_class,admission_policy,
                               base_priority,queued_at
                           ) VALUES(?,?,?,?,?)""",
                        (owner_id, admission_class, ADMISSION_POLICY,
                         priority_name, instant),
                    )
                    queued = connection.execute(
                        "SELECT sequence FROM queue WHERE owner_id=?",
                        (owner_id,),
                    ).fetchone()
                    if queued is None:
                        raise RuntimeError("durable occurrence queue missing")
                    _record_occurrence(
                        connection, occurrence_name, owner_id, resource_class,
                        admission_class, priority_name, instant, int(queued[0]),
                    )
                    return database, "owner_busy"
                connection.execute("DELETE FROM reservations WHERE owner_id=?", (owner_id,))
                connection.execute("DELETE FROM queue WHERE owner_id=?", (owner_id,))
                connection.execute("DELETE FROM priorities WHERE owner_id=?", (owner_id,))
                return None, "owner_busy"
            connection.execute("INSERT OR IGNORE INTO queue(owner_id,resource_class) VALUES(?,?)",
                               (owner_id, resource_class))
            connection.execute(
                """INSERT OR IGNORE INTO priorities(
                       owner_id,admission_class,admission_policy,base_priority,queued_at
                   ) VALUES(?,?,?,?,?)""",
                (owner_id, admission_class, ADMISSION_POLICY, priority_name, instant))
            connection.execute(
                """UPDATE priorities
                      SET admission_policy=?,
                          base_priority=COALESCE(base_priority,?),
                          queued_at=COALESCE(queued_at,?)
                    WHERE owner_id=?""",
                (ADMISSION_POLICY, priority_name, instant, owner_id))
            row = connection.execute("""
                SELECT q.sequence,q.resource_class,p.admission_class,
                       p.base_priority,p.queued_at
                FROM queue q JOIN priorities p ON p.owner_id=q.owner_id
                WHERE q.owner_id=?
            """, (owner_id,)).fetchone()
            if row is None or row[1:3] != (resource_class, admission_class):
                raise RuntimeError("durable owner resource class changed")
            if occurrence_name is not None:
                _record_occurrence(
                    connection, occurrence_name, owner_id, resource_class,
                    admission_class, priority_name, instant, int(row[0]),
                )
            head_rows = _durable_queue_rows(connection, resource_class, instant)
            head = head_rows[0] if head_rows else None
            ready = (available and not _legacy_waiter_exists(
                         tickets, resource_class, starts, snapshot_started_ns)
                     and head and head["owner_id"] == owner_id)
        return database, "ready" if ready else ("capacity_busy" if not available else "fifo_wait")
    finally:
        os.close(descriptor)


def claim_durable(resource_class: str, owner_id: str, *,
                  admission_class: str = "borrow",
                  now: float | None = None) -> tuple[Path | None, str]:
    """Convert this owner's queued/reserved v2 position into a live claim."""
    root, owners, tickets, database = _durable_paths()
    starts, snapshot_started_ns = _identity_snapshot(owners, tickets)
    started = process_start(os.getpid())
    if not started:
        raise RuntimeError("process identity unavailable")
    descriptor = os.open(root / "control.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None, "control_busy"
        with _database(database) as connection:
            instant = time.time() if now is None else now
            row = connection.execute("""
                SELECT q.sequence,q.resource_class,
                       COALESCE(p.admission_class,'borrow'),
                       p.base_priority,p.queued_at
                FROM queue q LEFT JOIN priorities p ON p.owner_id=q.owner_id
                WHERE q.owner_id=?
            """, (owner_id,)).fetchone()
            if row is None or row[1:3] != (resource_class, admission_class):
                return None, "ticket_missing"
            occurrence = connection.execute(
                """SELECT occurrence_id,base_priority,queued_at
                     FROM occurrences
                    WHERE owner_id=? AND state='queued'
                    ORDER BY queued_at,occurrence_id
                    LIMIT 1""",
                (owner_id,),
            ).fetchone()
            available, occupied = _durable_capacity(
                connection, owners, resource_class, admission_class, instant,
                starts, snapshot_started_ns)
            reservation = connection.execute(
                "SELECT resource_class,lease_until FROM reservations WHERE owner_id=?",
                (owner_id,)).fetchone()
            reserved = bool(reservation and reservation[0] == resource_class
                            and reservation[1] > instant)
            head = _next_durable_candidate(
                connection, owners, tickets, resource_class, instant,
                starts, snapshot_started_ns)
            if any(item.get("owner_id") == owner_id for item in (
                    _row(path) or {} for path in owners.glob("*.json"))):
                return None, "owner_busy"
            if reserved and (
                    _capacity_overflow(occupied, resource_class, admission_class)
                    or (admission_class == "revenue"
                        and _revenue_floor(_limits(resource_class, admission_class)[0])
                        and _legacy_owner_present(occupied))):
                return None, "capacity_busy"
            if not reserved and (not available or _legacy_waiter_exists(
                    tickets, resource_class, starts, snapshot_started_ns)):
                return None, "capacity_busy"
            if not reserved and (head is None or head["owner_id"] != owner_id):
                return None, "fifo_wait"
            claim = owners / f"{_digest(owner_id)}-{os.getpid()}.json"
            if occurrence is not None:
                connection.execute(
                    "UPDATE occurrences SET state='claimed' WHERE occurrence_id=?",
                    (occurrence[0],),
                )
            atomic_json(claim, {"version": 2, "pid": os.getpid(),
                        "process_start": started, "owner_id": owner_id,
                        "resource_class": resource_class, "sequence": row[0],
                        "admission_class": admission_class,
                        "admission_policy": ADMISSION_POLICY,
                        "base_priority": row[3], "queued_at": row[4],
                        "occurrence_id": occurrence[0] if occurrence else None,
                        "heartbeat_at": instant,
                        "heartbeat_timeout_seconds": _heartbeat_timeout_seconds(),
                        "phase": "claimed"})
            connection.execute("DELETE FROM reservations WHERE owner_id=?", (owner_id,))
            connection.execute("DELETE FROM queue WHERE owner_id=?", (owner_id,))
            connection.execute("DELETE FROM priorities WHERE owner_id=?", (owner_id,))
            return claim, "acquired"
    finally:
        os.close(descriptor)


def _controlled_by(value: dict[str, object], pid: int, started: str) -> bool:
    return bool(
        (value.get("pid") == pid and value.get("process_start") == started)
        or (value.get("controller_pid") == pid
            and value.get("controller_process_start") == started)
    )


def transfer_durable(claim: Path, child_pid: int) -> None:
    """Make the gated effect child, not its wrapper, the live slot owner."""
    controller_pid = os.getpid()
    controller_start = process_start(controller_pid)
    child_start = process_start(child_pid)
    if not controller_start or not child_start:
        raise RuntimeError("resource claim handoff identity unavailable")
    root, _, _, _ = _durable_paths()
    descriptor = os.open(root / "control.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if not _acquire_bounded(descriptor, timeout_seconds=0.5):
            raise RuntimeError("control_busy")
        value = _row(claim)
        if (not value or value.get("phase", "claimed") != "claimed"
                or not _controlled_by(value, controller_pid, controller_start)):
            raise RuntimeError("resource claim handoff ownership mismatch")
        atomic_json(claim, {
            **value,
            "pid": child_pid,
            "process_start": child_start,
            "controller_pid": controller_pid,
            "controller_process_start": controller_start,
            "heartbeat_at": time.time(),
            "phase": "running",
        })
    finally:
        os.close(descriptor)


def heartbeat_durable(claim: Path, *, now: float | None = None) -> bool:
    """Refresh progress for the exact live claim, without changing ownership."""
    value = _row(claim)
    started = process_start(os.getpid())
    if not value or not started or not _controlled_by(value, os.getpid(), started):
        return False
    instant = time.time() if now is None else now
    root, _, _, _ = _durable_paths()
    descriptor = os.open(root / "control.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if not _acquire_bounded(descriptor, timeout_seconds=0.5):
            return False
        current = _row(claim)
        if (not current or not _controlled_by(current, os.getpid(), started)
                or _heartbeat_expired(current, instant)):
            return False
        atomic_json(claim, {**current, "heartbeat_at": instant})
        return True
    finally:
        os.close(descriptor)


def defer_durable(owner_id: str, *, cooldown_seconds: int = 0) -> bool:
    """Return only this owner's dispatch reservation to its existing queue position."""
    if not owner_id or not isinstance(cooldown_seconds, int) or not 0 <= cooldown_seconds <= 3600:
        raise RuntimeError("invalid resource identity")
    root, _, _, database = _durable_paths()
    descriptor = os.open(root / "control.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        with _database(database) as connection:
            changed = connection.execute(
                "DELETE FROM reservations WHERE owner_id=?", (owner_id,)).rowcount
            delayed = 0
            if cooldown_seconds:
                delayed = connection.execute(
                    """UPDATE priorities SET next_eligible_at=?
                         WHERE owner_id=? AND EXISTS (
                             SELECT 1 FROM queue WHERE owner_id=?)""",
                    (time.time() + cooldown_seconds, owner_id, owner_id)).rowcount
        return bool(changed or delayed)
    finally:
        os.close(descriptor)


def cancel_durable(owner_id: str) -> bool:
    """Remove a queue entry only after the current registry proves it retired."""
    if not owner_id:
        raise RuntimeError("invalid resource identity")
    root, _, _, database = _durable_paths()
    descriptor = os.open(root / "control.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        with _database(database) as connection:
            connection.execute("DELETE FROM reservations WHERE owner_id=?", (owner_id,))
            connection.execute("DELETE FROM priorities WHERE owner_id=?", (owner_id,))
            changed = connection.execute(
                "DELETE FROM queue WHERE owner_id=?", (owner_id,)).rowcount
        return changed == 1
    finally:
        os.close(descriptor)


def _reserve_locked(connection: sqlite3.Connection, owners: Path, tickets: Path, *,
                    instant: float, lease_seconds: int,
                    starts: dict[int, str | None],
                    snapshot_started_ns: int) -> list[str]:
    dispatched = []
    while True:
        connection.execute("DELETE FROM reservations WHERE lease_until <= ?", (instant,))
        for resource_class in RESOURCE_CLASSES:
            _durable_capacity(
                connection, owners, resource_class, "borrow", instant,
                starts, snapshot_started_ns)
        candidates = []
        for resource_class in RESOURCE_CLASSES:
            candidate = _next_durable_candidate(
                connection, owners, tickets, resource_class, instant,
                starts, snapshot_started_ns)
            if candidate:
                owner_id = str(candidate["owner_id"])
                sequence = int(candidate["sequence"])
                candidates.append((
                    _effective_priority(candidate, instant),
                    sequence, owner_id, resource_class,
                ))
        if not candidates:
            break
        _, sequence, owner_id, resource_class = min(candidates)
        connection.execute(
            "INSERT INTO reservations(owner_id,resource_class,sequence,lease_until) VALUES(?,?,?,?)",
            (owner_id, resource_class, sequence, instant + lease_seconds))
        dispatched.append(owner_id)
    return dispatched


def reserve_available(*, now: float | None = None,
                      lease_seconds: int = 60) -> list[str]:
    """Reserve every currently free slot without requiring a releasing owner."""
    root, owners, tickets, database = _durable_paths()
    starts, snapshot_started_ns = _identity_snapshot(owners, tickets)
    descriptor = os.open(root / "control.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return []
        with _database(database) as connection:
            return _reserve_locked(
                connection, owners, tickets,
                instant=time.time() if now is None else now,
                lease_seconds=lease_seconds, starts=starts,
                snapshot_started_ns=snapshot_started_ns)
    finally:
        os.close(descriptor)


def release_and_reserve(claim: Path, *, requeue: bool = False,
                        reserve: bool = True, now: float | None = None,
                        lease_seconds: int = 60) -> list[str]:
    """Release one claim and reserve newly available capacity for queued owners."""
    value = _row(claim)
    started = process_start(os.getpid())
    if not value or not started or not _controlled_by(value, os.getpid(), started):
        raise RuntimeError("resource claim ownership mismatch")
    root, owners, tickets, database = _durable_paths()
    starts, snapshot_started_ns = _identity_snapshot(owners, tickets)
    descriptor = os.open(root / "control.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if not _acquire_bounded(descriptor, timeout_seconds=0.5):
            raise RuntimeError("control_busy")
        instant = time.time() if now is None else now
        with _database(database) as connection:
            if requeue and value.get("version") == 2:
                sequence = value.get("sequence")
                if not isinstance(sequence, int):
                    raise RuntimeError("durable claim sequence missing")
                connection.execute(
                    "INSERT OR IGNORE INTO queue(sequence,owner_id,resource_class) VALUES(?,?,?)",
                    (sequence, value["owner_id"], value["resource_class"]))
                connection.execute(
                    """INSERT OR IGNORE INTO priorities(
                           owner_id,admission_class,admission_policy,base_priority,queued_at
                       ) VALUES(?,?,?,?,?)""",
                    (value["owner_id"], value.get("admission_class", "borrow"),
                      value.get("admission_policy"), value.get("base_priority"),
                     value.get("queued_at", instant)))
            occurrence_id = value.get("occurrence_id")
            if isinstance(occurrence_id, str) and occurrence_id:
                connection.execute(
                    "UPDATE occurrences SET state=? WHERE occurrence_id=?",
                    ("queued" if requeue else "released", occurrence_id),
                )
            if not requeue:
                remaining = connection.execute(
                    """SELECT 1 FROM occurrences
                         WHERE owner_id=? AND state='queued' LIMIT 1""",
                    (value["owner_id"],),
                ).fetchone()
                if remaining:
                    connection.execute(
                        "INSERT OR IGNORE INTO queue(owner_id,resource_class) VALUES(?,?)",
                        (value["owner_id"], value["resource_class"]),
                    )
                    connection.execute(
                        """INSERT OR IGNORE INTO priorities(
                               owner_id,admission_class,admission_policy,
                               base_priority,queued_at
                           ) VALUES(?,?,?,?,?)""",
                        (value["owner_id"], value.get("admission_class", "borrow"),
                         value.get("admission_policy"), value.get("base_priority"),
                            value.get("queued_at", instant)),
                    )
        claim.unlink(missing_ok=True)
        if not reserve:
            return []
        with _database(database) as connection:
            return _reserve_locked(
                connection, owners, tickets, instant=instant,
                lease_seconds=lease_seconds, starts=starts,
                snapshot_started_ns=snapshot_started_ns)
    finally:
        os.close(descriptor)


def try_acquire(resource_class: str, owner_id: str, *,
                admission_class: str = "borrow",
                retain_ticket: bool = True,
                required_protocol: int | None = None) -> tuple[Path | None, str]:
    """Atomically claim a slot; live waiters are served FIFO within each class."""
    if (resource_class not in set(RESOURCE_CLASSES) or not owner_id
            or admission_class not in ADMISSION_CLASSES):
        raise RuntimeError("invalid resource identity")
    root = state_root()
    owners, tickets = root / "owners", root / "tickets"
    for path in (root, owners, tickets):
        path.mkdir(parents=True, exist_ok=True, mode=0o700); os.chmod(path, 0o700)
    descriptor = os.open(root / "control.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if not retain_ticket:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return None, "control_busy"
            fcntl.flock(descriptor, fcntl.LOCK_UN)

        snapshot_started_ns = time.time_ns()
        started = process_start(os.getpid())
        if not started:
            raise RuntimeError("process identity unavailable")
        try:
            fcntl.flock(
                descriptor,
                fcntl.LOCK_EX | (fcntl.LOCK_NB if not retain_ticket else 0),
            )
        except BlockingIOError:
            return None, "control_busy"
        observed_protocol = durable_protocol_version()
        if required_protocol is not None and observed_protocol != required_protocol:
            return None, "protocol_changed"
        live_starts: dict[int, str | None] = {os.getpid(): started}
        owner_rows = []
        for path in owners.glob("*.json"):
            if not _live(path, live_starts, snapshot_started_ns, probe_missing=True):
                path.unlink(missing_ok=True); continue
            owner_rows.append(_row(path) or {})
        if any(row.get("owner_id") == owner_id for row in owner_rows):
            return None, "owner_busy"
        reserved_rows = []
        if observed_protocol == 2:
            with _database(root / "admission-v2.sqlite3") as connection:
                connection.execute(
                    "DELETE FROM reservations WHERE lease_until <= ?", (time.time(),))
                reserved_rows = [
                    {"owner_id": row[0], "resource_class": row[1],
                     "admission_policy": row[2]}
                    for row in connection.execute(
                        """SELECT r.owner_id,r.resource_class,p.admission_policy
                           FROM reservations r
                           LEFT JOIN priorities p ON p.owner_id=r.owner_id""")
                ]
        occupied = owner_rows + reserved_rows

        digest = hashlib.sha256(owner_id.encode()).hexdigest()
        if not retain_ticket:
            if not _capacity_available(occupied, resource_class, admission_class):
                return None, "capacity_busy"
            for candidate in sorted(tickets.glob(f"{resource_class}-*.json")):
                value = _row(candidate)
                if value and value.get("version", 1) != 1:
                    continue
                if _live(candidate, live_starts, snapshot_started_ns,
                         probe_missing=True):
                    return None, "fifo_wait"
                candidate.unlink(missing_ok=True)
            claim = owners / f"{digest}-{os.getpid()}.json"
            atomic_json(claim, {"version": 1, "pid": os.getpid(),
                        "process_start": started, "owner_id": owner_id,
                        "resource_class": resource_class,
                        "admission_class": admission_class,
                        "admission_policy": ADMISSION_POLICY})
            return claim, "acquired"

        matches = [
            path for path in tickets.glob(f"{resource_class}-*-{digest}.json")
            if (_row(path) or {}).get("version", 1) == 1
        ]
        ticket = matches[0] if matches else tickets / (
            f"{resource_class}-{time.time_ns():020d}-{digest}.json")
        atomic_json(ticket, {"version": 1, "pid": os.getpid(),
                    "process_start": started, "owner_id": owner_id})

        if not _capacity_available(occupied, resource_class, admission_class):
            return None, "capacity_busy"

        head = None
        for candidate in sorted(tickets.glob(f"{resource_class}-*.json")):
            value = _row(candidate)
            if value and value.get("version", 1) != 1:
                continue
            if _live(candidate, live_starts, snapshot_started_ns, probe_missing=True):
                head = candidate
                break
            candidate.unlink(missing_ok=True)
        if head is not None and head != ticket:
            return None, "fifo_wait"

        claim = owners / f"{digest}-{os.getpid()}.json"
        atomic_json(claim, {"version": 1, "pid": os.getpid(),
                    "process_start": started, "owner_id": owner_id,
                    "resource_class": resource_class,
                    "admission_class": admission_class,
                    "admission_policy": ADMISSION_POLICY})
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
    started = process_start(os.getpid())
    if not value or not started or not _controlled_by(value, os.getpid(), started):
        raise RuntimeError("resource claim ownership mismatch")
    claim.unlink()
