#!/usr/bin/env python3
"""Check producer state, with a read-only capacity mode for heavy release builds."""

from __future__ import annotations

import json
import hashlib
import marshal
import platform
import subprocess
import tarfile
import os
import pwd
import shutil
import stat
import sys
import tempfile
from pathlib import Path
from typing import Sequence


RECEIPT_PATH = Path("state") / "disk-headroom.json"

_PRODUCER_GATE = "life-manager-producer-preflight"
_DISK_STOP_FLAGS = (("disk-writers.stop", "disk_writers_stop"),)
_DISK_RECOVERY_OWNER = "host-disk-recovery"
_DISK_RECOVERY_REASON = "disk_headroom_low"
RECOVERY_FLOOR_BYTES = 2 * 1024**3
_DISK_RECOVERY_ACTION = "restore_capacity_and_install_shared_disk_gate"


def is_cleanup_disk_recovery_signal(path: Path | str) -> bool:
    """Identify only the cleanup-owned low-space record, not operator stops."""
    descriptor = -1
    try:
        descriptor = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
            or info.st_size > 4096
        ):
            return False
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            raw = handle.read(4097)
    except (OSError, UnicodeError, ValueError):
        return False
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(raw) > 4096:
        return False
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return False
    return (
        isinstance(value, dict)
        and value.get("owner_id") == _DISK_RECOVERY_OWNER
        and value.get("reason") == _DISK_RECOVERY_REASON
        and value.get("required_bytes") == RECOVERY_FLOOR_BYTES
        and value.get("next_action") == _DISK_RECOVERY_ACTION
    )


def disk_free_bytes(path: Path | str) -> int | None:
    """Return validated free bytes for the filesystem containing ``path``."""
    try:
        usage = shutil.disk_usage(path)
    except (OSError, TypeError, ValueError):
        return None
    available = getattr(usage, "free", None)
    if isinstance(available, bool) or not isinstance(available, int) or available < 0:
        return None
    return available


def _state_dir() -> Path:
    configured = os.environ.get("LIFE_MANAGER_PRODUCER_STATE_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".local" / "state" / "life-manager"


def _ensure_producer_state_dir(state_dir: Path) -> bool:
    """Prepare the receipt/filesystem root before measuring a fresh instance."""
    try:
        if not state_dir.exists():
            state_dir.mkdir(parents=True, mode=0o700)
            state_dir.chmod(0o700)
        entry = state_dir.lstat()
        return (
            stat.S_ISDIR(entry.st_mode)
            and not state_dir.is_symlink()
            and entry.st_uid == os.getuid()
            and not entry.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        )
    except OSError:
        return False


def _host_state_dir() -> Path:
    configured = os.environ.get("LIFE_MANAGER_HOST_STATE_DIR")
    if configured:
        return Path(configured).expanduser()
    return _canonical_host_state_dirs()[0]


def _canonical_host_state_dirs() -> tuple[Path, Path]:
    owner_home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    return (
        owner_home / ".local" / "state" / "life-manager" / "state",
        owner_home / ".openclaw" / "state",
    )


def _ensure_host_state_dir(host_state: Path) -> bool:
    """Create a fresh private control root, rejecting unsafe existing paths."""
    try:
        if not host_state.exists():
            host_state.mkdir(parents=True, mode=0o700)
            host_state.chmod(0o700)
        entry = host_state.lstat()
        return (
            stat.S_ISDIR(entry.st_mode)
            and not host_state.is_symlink()
            and entry.st_uid == os.getuid()
            and not entry.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
        )
    except OSError:
        return False


def _fsync_directory(directory: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    directory_fd = os.open(str(directory), flags)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _write_receipt(state_dir: Path, receipt: dict[str, object]) -> str:
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
    except Exception as exc:
        print(f"disk_admission: could not persist receipt: {exc}", file=sys.stderr)
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
        "required_bytes": 0,
    }
    if available_bytes is not None:
        receipt["available_bytes"] = available_bytes
    if metadata:
        receipt.update(metadata)
    payload = _write_receipt(_state_dir(), receipt)
    print(payload)
    return 1


def _producer_gate() -> tuple[str, Path] | None:
    try:
        configured = _host_state_dir()
        candidates = (*_canonical_host_state_dirs(), configured)
    except (KeyError, OSError):
        return "disk_policy_unavailable", (
            Path.home() / ".local" / "state" / "life-manager" / "state"
        )
    host_states = tuple(dict.fromkeys(candidates))
    for host_state in host_states:
        required = host_state == configured
        if required:
            if not _ensure_host_state_dir(host_state):
                return "disk_policy_unavailable", host_state
        else:
            try:
                entry = host_state.lstat()
            except FileNotFoundError:
                continue
            except OSError:
                return "disk_policy_unavailable", host_state
            if (
                not stat.S_ISDIR(entry.st_mode)
                or host_state.is_symlink()
                or entry.st_uid != os.getuid()
                or entry.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
            ):
                return "disk_policy_unavailable", host_state
            try:
                next(iter(host_state.iterdir()), None)
            except OSError:
                return "disk_policy_unavailable", host_state
        for filename, reason in _DISK_STOP_FLAGS:
            flag = host_state / filename
            try:
                entry = flag.lstat()
            except FileNotFoundError:
                continue
            except OSError:
                return "disk_policy_unavailable", flag
            if not stat.S_ISREG(entry.st_mode):
                return "disk_policy_unavailable", flag
            if is_cleanup_disk_recovery_signal(flag):
                continue
            return reason, flag
    return None


def disk_headroom_ok() -> bool:
    """Validate state; ignore cleanup low-space signals but honor operator stops."""
    state_dir = _state_dir()
    if not _ensure_producer_state_dir(state_dir):
        print(json.dumps({
            "status": "failed", "failed": 1, "effect": 0, "readback": 0,
            "reason": "disk_state_unsafe", "required_bytes": 0,
        }, sort_keys=True, separators=(",", ":")))
        return False
    gate = _producer_gate()
    if gate is not None:
        reason, flag = gate
        available_bytes = disk_free_bytes(state_dir)
        _failure(
            reason,
            available_bytes,
            metadata={"gate": _PRODUCER_GATE, "flag_path": str(flag)},
        )
        return False
    return True


def release_capacity_bytes(repo: Path, sha: str, loops: Path, node: str, npm: str) -> int:
    """Measure a complete source export only when all dependency bundles are reusable."""
    donor = (loops / "current").resolve()
    descriptor = json.loads((donor / "RELEASE.json").read_text())
    if (descriptor.get("release_paths") != "ALL"
            or descriptor.get("provenance") != "ancestor-of-origin-main"
            or descriptor.get("runtime_python") != str(Path(sys.executable).resolve())
            or descriptor.get("runtime_python_cache_tag") != sys.implementation.cache_tag
            or donor.stat().st_mode & 0o222
            or os.path.lexists(donor / "RECLAIMED-RELEASE.json")):
        raise ValueError("donor is not a complete immutable runtime")
    subprocess.run(["git","-C",str(repo),"merge-base","--is-ancestor",descriptor["sha"],"origin/main"],check=True,capture_output=True)
    roots = ("", "runtime/compute-proxy", "runtime/agentmail", "apps/life-manager",
             "skills/earn/taskmarket", "skills/earn/x402-sell", "services/x402-endpoint")
    for relative in roots:
        prefix = relative + "/" if relative else ""
        manifests = []
        for name in ("package.json", "package-lock.json"):
            result = subprocess.run(["git","-C",str(repo),"show",f"{sha}:{prefix}{name}"],capture_output=True)
            manifests.append(result.stdout if result.returncode == 0 else None)
        if None in manifests:
            continue
        directory = donor / relative
        if any((directory / name).read_bytes() != payload for name,payload in zip(("package.json","package-lock.json"),manifests)):
            raise ValueError("dependency manifests changed")
        header = "\0".join(("command","npm-ci --omit=dev --ignore-scripts","os",platform.system(),"arch",platform.machine(),"node",node,"npm",npm)) + "\0"
        key_data = header.encode()
        for label,payload in zip(("package-json","package-lock"),manifests):
            key_data += label.encode() + b"\0" + (hashlib.sha256(payload).hexdigest() + "  -\n").encode()
        key = hashlib.sha256(key_data).hexdigest()
        bundle = loops / "dependency-bundles" / ("npm-" + key)
        if (not (directory / "node_modules").is_symlink()
                or (directory / "node_modules").resolve() != (bundle / "node_modules").resolve()
                or bundle.stat().st_mode & 0o222
                or (bundle / ".complete").read_text().strip() != key
                or not (bundle / "node_modules/.package-lock.json").is_file()):
            raise ValueError("dependency bundle unavailable")
    block = os.statvfs(loops).f_frsize
    if block <= 0:
        raise ValueError("filesystem allocation unknown")
    rounded = lambda size: ((size + block - 1) // block) * block
    # No clone savings assumed: one full export and one serial file temporary.
    # Bytecode retains its conservative allocation plus atomic-write budget.
    budget = 64 * 1024**2
    largest_temporary = 0
    with subprocess.Popen(["git","-C",str(repo),"archive","--format=tar",sha],stdout=subprocess.PIPE) as archive:
        with tarfile.open(fileobj=archive.stdout,mode="r|") as entries:
            for entry in entries:
                allocation = rounded(entry.size)
                budget += block + allocation
                largest_temporary = max(largest_temporary, allocation)
                if entry.isfile() and entry.name.startswith("runtime/") and entry.name.endswith(".py"):
                    code = compile(entries.extractfile(entry).read(),entry.name,"exec")
                    budget += 2 * (block + rounded(16 + len(marshal.dumps(code))))
        if archive.wait() != 0:
            raise ValueError("Git export measurement failed")
    return budget + largest_temporary


def main(argv: Sequence[str] | None = None) -> int:
    remaining = list(sys.argv[1:] if argv is None else argv)
    if remaining[:1] == ["--release-capacity"]:
        if len(remaining) != 6:
            return 2
        try:
            required = release_capacity_bytes(Path(remaining[1]),remaining[2],Path(remaining[3]),remaining[4],remaining[5])
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, tarfile.TarError, SyntaxError):
            required = RECOVERY_FLOOR_BYTES
        print(required)
        return 0
    if remaining[:1] == ["--check-free-space"]:
        if len(remaining) not in (2,3):
            return 2
        try:
            required = int(remaining[2]) if len(remaining) == 3 else RECOVERY_FLOOR_BYTES
        except ValueError:
            return 2
        if required <= 0:
            return 2
        path = Path(remaining[1]).expanduser()
        probe = next((p for p in (path, *path.parents) if p.exists()), None)
        available = disk_free_bytes(probe) if probe is not None else None
        if available is not None and available >= required:
            return 0
        print(json.dumps({"status": "deferred", "effect": 0, "readback": 0,
            "reason": "disk_headroom_low" if available is not None else "disk_headroom_unknown",
            "available_bytes": available, "required_bytes": required},
            sort_keys=True, separators=(",", ":")))
        return 75
    if not remaining:
        print("disk_admission: missing child argv", file=sys.stderr)
        return 2
    if not disk_headroom_ok():
        return 1
    os.execvpe(remaining[0], remaining, os.environ)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
