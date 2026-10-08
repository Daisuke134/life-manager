"""Bounded, read-only host inventory for the Life Manager disk governor."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable


SCHEMA_VERSION = "life-manager-host-inventory-v1"
# Full census is hourly and runs behind the governor's outer 120-second bound.
# A 3-second probe systematically missed otherwise bounded repository roots
# (measured 5–9s on the Mac mini), leaving their size unattributed. Ten seconds
# keeps the probe bounded while allowing those roots to be measured.
DU_TIMEOUT_SECONDS = 10
BUILD_TOOL_DU_TIMEOUT_SECONDS = 30
FULL_INVENTORY_BUDGET_SECONDS = 90
MAX_CHILDREN_PER_ROOT = 512

# These are observation families, not deletion roots.  A missing or unreadable
# family is recorded as a coverage gap instead of being silently skipped.
ROOT_FAMILIES = (
    ("user-home", "{home}"),
    ("repository-worktree", "{home}/Projects"),
    ("repository-worktree", "{home}/Projects/life-manager-main"),
    ("repository-worktree", "{home}/anicca-project"),
    ("repository-worktree", "{home}/anicca"),
    ("repository-worktree", "{home}/anicca-docs-tools"),
    ("repository-worktree", "{home}/anicca-portfolio-self-improve"),
    ("repository-worktree", "{home}/anicca-rtdash"),
    ("repository-worktree", "{home}/life-manager-repo-v0-retire"),
    ("repository-worktree", "{home}/.codex-worktrees"),
    ("gig-deliverable", "{home}/gig"),
    ("agent-runtime", "{home}/.openclaw"),
    ("agent-session", "{home}/.claude"),
    ("agent-session", "{home}/.codex"),
    ("browser-identity", "{home}/.cloak"),
    ("user-library", "{home}/Library"),
    ("downloads-trash", "{home}/Downloads"),
    ("downloads-trash", "{home}/.Trash"),
    ("system-library", "/Library"),
    ("system-temp", "/private/tmp"),
    ("system-temp", "/private/var/folders"),
    ("volume", "/Volumes"),
    ("build-tool", "/opt/homebrew"),
)

PERMISSION_OWNER_BOUNDARIES = (
    ("user-library", "{home}/Library/Application Support/com.apple.TCC"),
    ("downloads-trash", "{home}/.Trash"),
    ("system-temp", "/private/tmp"),
    ("system-temp", "/private/var/folders"),
)
REQUIRED_OWNER_FAMILIES = tuple(sorted({family for family, _ in ROOT_FAMILIES}))

SIZE_PROBE_FAMILIES = {
    "repository-worktree",
    "gig-deliverable",
    "agent-runtime",
    "user-library",
    "system-temp",
    "build-tool",
}


def _run(argv: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _normalize_mount_path(path: str) -> str:
    """Decode the octal escapes emitted by BSD mount/df for path names."""

    return (
        path.strip()
        .replace(r"\040", " ")
        .replace(r"\011", "\t")
        .replace(r"\134", "\\")
    )


def _normalize_mount_options(options: str) -> list[str]:
    """Return deterministic, de-duplicated mount options."""

    return sorted({option.strip().lower() for option in options.split(",") if option.strip()})


def _parse_mount(output: str) -> dict[str, dict[str, Any]]:
    """Parse macOS ``mount`` records, retaining paths that contain spaces."""

    metadata: dict[str, dict[str, Any]] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^(?P<prefix>.+) \((?P<options>[^()]*)\)$", line)
        if match is None:
            continue
        prefix = match.group("prefix")
        if " on " not in prefix:
            continue
        filesystem, mount = prefix.split(" on ", 1)
        filesystem = filesystem.strip()
        mount = _normalize_mount_path(mount)
        if not filesystem or not mount.startswith("/"):
            continue
        mount_options = _normalize_mount_options(match.group("options"))
        metadata[mount] = {
            "filesystem": filesystem,
            "mount": mount,
            "mount_options": mount_options,
        }
    return metadata


def _parse_df(
    output: str,
    mount_metadata: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    mounts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in output.splitlines()[1:]:
        fields = line.split(maxsplit=5)
        if len(fields) < 6:
            continue
        filesystem, total, used, available, capacity = fields[:5]
        mount = _normalize_mount_path(fields[5])
        if not mount.startswith("/") or mount in seen:
            continue
        try:
            values = {
                "total_bytes": int(total) * 1024,
                "used_bytes": int(used) * 1024,
                "available_bytes": int(available) * 1024,
            }
        except ValueError:
            continue
        seen.add(mount)
        metadata = (mount_metadata or {}).get(mount)
        options = metadata["mount_options"] if metadata is not None else None
        mounts.append(
            {
                "filesystem": filesystem,
                "mount": mount,
                "capacity": capacity,
                "local": None if metadata is None else "local" in options,
                "writable": None if metadata is None else "read-only" not in options,
                "mount_options": options,
                **values,
            }
        )
    return mounts


def _mounts(
    run: Runner = _run,
    *,
    timeout: float = 5,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[list[dict[str, Any]], list[str], list[str] | None]:
    gaps: list[str] = []
    metadata: dict[str, dict[str, Any]] = {}
    metadata_available = False
    df_timeout = timeout
    if deadline is not None:
        df_remaining = deadline - clock()
        df_timeout = min(timeout, df_remaining) if df_remaining > 0 else None
    if df_timeout is None:
        gaps.append("mount-census:budget-exhausted")
        df_result = None
    else:
        try:
            df_result = run(["/bin/df", "-kP"], timeout=df_timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            gaps.append(f"mount-census:{type(exc).__name__}")
            df_result = None
    if df_result is not None and df_result.returncode != 0:
        gaps.append(f"mount-census:rc-{df_result.returncode}")
    df_output = df_result.stdout if df_result is not None else ""
    mounts = _parse_df(df_output)
    if not mounts:
        gaps.append("mount-census:no-readable-mounts")

    mount_timeout = timeout
    if deadline is not None:
        mount_remaining = deadline - clock()
        mount_timeout = min(timeout, mount_remaining) if mount_remaining > 0 else None
    if mount_timeout is None:
        gaps.append("mount-metadata:budget-exhausted")
    else:
        try:
            mount_result = run(["/sbin/mount"], timeout=mount_timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            gaps.append(f"mount-metadata:{type(exc).__name__}")
        else:
            if mount_result.returncode != 0:
                gaps.append(f"mount-metadata:rc-{mount_result.returncode}")
            else:
                metadata = _parse_mount(mount_result.stdout)
                if not metadata:
                    gaps.append("mount-metadata:no-readable-mounts")
                else:
                    metadata_available = True

    missing_metadata_mounts = sorted(
        mount["mount"]
        for mount in mounts
        if mount["filesystem"].startswith("/dev/") and mount["mount"] not in metadata
    )
    for mount in missing_metadata_mounts:
        gaps.append(f"mount-metadata:missing:{mount}")
    if missing_metadata_mounts:
        metadata_available = False

    if metadata:
        mounts = _parse_df(
            df_output,
            metadata,
        )
    local_writable_mounts = (
        sorted(
            mount
            for mount, record in metadata.items()
            if record["filesystem"].startswith("/dev/")
            and "local" in record["mount_options"]
            and "read-only" not in record["mount_options"]
        )
        if metadata_available
        else None
    )
    return mounts, gaps, local_writable_mounts


def _children(path: Path) -> tuple[dict[str, Any], list[str]]:
    gaps: list[str] = []
    record: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists() or path.is_symlink(),
        "symlink": path.is_symlink(),
        "measurement": "metadata-only",
        "children_seen": 0,
        "files_seen": 0,
        "directories_seen": 0,
        "symlinks_seen": 0,
    }
    if not record["exists"]:
        gaps.append(f"missing:{path}")
        return record, gaps
    if record["symlink"]:
        gaps.append(f"symlink-root:{path}")
        return record, gaps
    try:
        with os.scandir(path) as entries:
            for index, entry in enumerate(entries):
                if index >= MAX_CHILDREN_PER_ROOT:
                    record["truncated"] = True
                    gaps.append(f"child-limit:{path}")
                    break
                record["children_seen"] += 1
                try:
                    if entry.is_symlink():
                        record["symlinks_seen"] += 1
                    elif entry.is_dir(follow_symlinks=False):
                        record["directories_seen"] += 1
                    else:
                        record["files_seen"] += 1
                except OSError:
                    gaps.append(f"stat-error:{entry.path}")
    except PermissionError:
        gaps.append(f"permission-limited:{path}")
    except OSError as exc:
        gaps.append(f"scan-error:{path}:{type(exc).__name__}")
    return record, gaps


def _permission_owner_receipt(path: Path, owner_family: str) -> dict[str, Any]:
    """Observe a protected boundary without enumerating or retaining children."""

    receipt: dict[str, Any] = {
        "path": str(path),
        "owner_family": owner_family,
        "exists": False,
        "symlink": False,
        "access": "missing",
        "reclaim_eligible": False,
    }
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return receipt
    except PermissionError:
        receipt["exists"] = None
        receipt["symlink"] = None
        receipt["access"] = "permission-error"
        return receipt
    except OSError:
        receipt["exists"] = None
        receipt["symlink"] = None
        receipt["access"] = "scan-error"
        return receipt

    receipt["exists"] = True
    receipt["symlink"] = stat.S_ISLNK(metadata.st_mode)
    if receipt["symlink"]:
        receipt["access"] = "symlink"
        return receipt
    try:
        with os.scandir(path):
            pass
    except FileNotFoundError:
        receipt["exists"] = False
        receipt["symlink"] = False
        receipt["access"] = "missing"
    except PermissionError:
        receipt["access"] = "permission-error"
    except OSError:
        receipt["access"] = "scan-error"
    else:
        receipt["access"] = "readable"
    return receipt


def _bounded_size(
    path: Path,
    run: Runner = _run,
    *,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[int | None, str, str | None]:
    timeout = BUILD_TOOL_DU_TIMEOUT_SECONDS if path == Path("/opt/homebrew") else DU_TIMEOUT_SECONDS
    if deadline is not None:
        remaining = deadline - clock()
        if remaining <= 0:
            return None, "budget-exhausted", "size-budget-exhausted"
        timeout = min(timeout, remaining)
    try:
        result = run(["/usr/bin/du", "-x", "-sk", str(path)], timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "timeout", "size-timeout"
    except OSError as exc:
        return None, "error", f"size-error:{type(exc).__name__}"
    fields = result.stdout.split()
    parsed_size: int | None = None
    if fields:
        try:
            parsed_size = int(fields[0]) * 1024
        except ValueError:
            parsed_size = None
    if result.returncode != 0:
        if parsed_size is not None:
            error_text = (result.stderr or "").lower()
            gap = (
                "size-permission-partial"
                if "permission" in error_text or "not permitted" in error_text
                else f"size-partial-rc-{result.returncode}"
            )
            return parsed_size, "bounded-du-partial", gap
        return None, "error", f"size-rc-{result.returncode}"
    if parsed_size is None:
        return None, "error", "size-empty" if not fields else "size-invalid"
    return parsed_size, "bounded-du", None


def collect_host_inventory(
    *,
    home: Path,
    state_dir: Path,
    full: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    clock: Callable[[], float] = time.monotonic,
    budget_seconds: float | None = None,
) -> dict[str, Any]:
    """Collect and atomically persist a read-only, bounded host census."""

    run = runner or _run
    if full:
        budget = FULL_INVENTORY_BUDGET_SECONDS if budget_seconds is None else max(0.0, budget_seconds)
        deadline = clock() + budget
    else:
        deadline = None
    if full and deadline is not None:
        mount_remaining = deadline - clock()
        if mount_remaining <= 0:
            mounts, gaps, local_writable_mounts = [], ["inventory-budget-exhausted"], None
        else:
            mounts, gaps, local_writable_mounts = _mounts(
                run,
                timeout=min(5, mount_remaining),
                deadline=deadline,
                clock=clock,
            )
    else:
        mounts, gaps, local_writable_mounts = _mounts(run)
    if local_writable_mounts is None:
        local_writable_mount_count = None
        missing_local_writable_mounts = None
    else:
        local_writable_mount_count = len(local_writable_mounts)
        df_mount_paths = {mount["mount"] for mount in mounts}
        missing_local_writable_mounts = sorted(
            mount for mount in local_writable_mounts if mount not in df_mount_paths
        )
    roots: list[dict[str, Any]] = []
    root_gaps = list(gaps)
    for family, template in ROOT_FAMILIES:
        path = Path(template.format(home=home))
        record, record_gaps = _children(path)
        record["owner_family"] = family
        if full and family in SIZE_PROBE_FAMILIES and record["exists"] and not record["symlink"]:
            size, measurement, size_gap = _bounded_size(path, run, deadline=deadline, clock=clock)
            record["size_bytes"] = size
            record["measurement"] = measurement
            if size_gap:
                record_gaps.append(f"{size_gap}:{path}")
        else:
            record["size_bytes"] = None
            if family in SIZE_PROBE_FAMILIES:
                record_gaps.append(f"size-deferred:{path}")
        roots.append(record)
        root_gaps.extend(record_gaps)

    permission_owner_receipts = [
        _permission_owner_receipt(Path(template.format(home=home)), family)
        for family, template in PERMISSION_OWNER_BOUNDARIES
    ]

    present_owner_families = sorted({root["owner_family"] for root in roots if root["exists"]})
    missing_owner_families = sorted(
        set(REQUIRED_OWNER_FAMILIES) - set(present_owner_families)
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "policy_version": "cleanup-control-v1",
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "full" if full else "fast",
        "mounts": mounts,
        "roots": roots,
        "permission_owner_receipts": permission_owner_receipts,
        "coverage": {
            "mount_count": len(mounts),
            "local_writable_mounts": local_writable_mounts,
            "local_writable_mount_count": local_writable_mount_count,
            "missing_local_writable_mounts": missing_local_writable_mounts,
            "root_count": len(roots),
            "required_owner_families": list(REQUIRED_OWNER_FAMILIES),
            "owner_families": present_owner_families,
            "missing_owner_families": missing_owner_families,
            "gaps": sorted(set(root_gaps)),
            "unattributed_size_bytes": None,
            "complete": not root_gaps,
        },
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    payload["inventory_sha256"] = hashlib.sha256(encoded).hexdigest()
    state_dir.mkdir(parents=True, exist_ok=True)
    target = state_dir / ("host-inventory-full.json" if full else "host-inventory.json")
    for orphan in state_dir.glob(".host-inventory.*"):
        try:
            metadata = os.lstat(orphan)
            if stat.S_ISREG(metadata.st_mode) and time.time() - metadata.st_mtime > FULL_INVENTORY_BUDGET_SECONDS:
                orphan.unlink()
        except OSError:
            pass
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=state_dir, prefix=".host-inventory.", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    payload["path"] = str(target)
    return payload
