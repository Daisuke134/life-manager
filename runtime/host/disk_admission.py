#!/usr/bin/env python3
"""Check producer state, with a read-only capacity mode for heavy release builds."""

from __future__ import annotations

import base64
import hashlib
import json
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
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from itertools import islice
from pathlib import Path
from typing import Sequence


RECEIPT_PATH = Path("state") / "disk-headroom.json"

_PRODUCER_GATE = "life-manager-producer-preflight"
_DISK_STOP_FLAGS = (("disk-writers.stop", "disk_writers_stop"),)
_DISK_RECOVERY_OWNER = "host-disk-recovery"
_DISK_RECOVERY_REASON = "disk_headroom_low"
RECOVERY_FLOOR_BYTES = 2 * 1024**3
# Swap lives on the Data volume; below this floor the Mac froze (2026-10-14).
PRODUCER_FLOOR_BYTES = 12 * 1024**3


def _producer_floor_bytes() -> int:
    """Calibration knob for isolated tests and smaller hosts; production uses the default."""
    try:
        return max(0, int(os.environ.get("LIFE_MANAGER_PRODUCER_FLOOR_BYTES", PRODUCER_FLOOR_BYTES)))
    except ValueError:
        return PRODUCER_FLOOR_BYTES
_PRODUCER_FLOOR_REASON = "disk_floor_low"
# Revenue lanes keep running down to this lower floor, like Kubernetes evicting low-priority
# pods first: a flat 12 GiB floor stopped every revenue lane at 11 GiB (2026-10-16). 10 GiB still
# leaves the unarmed 8 GiB ballast plus the 2 GiB recovery floor as headroom for swap growth.
REVENUE_FLOOR_BYTES = 10 * 1024**3


def _is_revenue_loop(loop_id: str | None) -> bool:
    """Read the loop's admission_class from the release registry; unknown reads as not revenue."""
    if not loop_id:
        return False
    try:
        registry = json.loads((Path(os.environ["LIFE_MANAGER_REPO"]) / "config" / "loop-registry.json").read_text())
        return registry["loops"][loop_id].get("admission_class") == "revenue"
    except (KeyError, OSError, ValueError, TypeError, AttributeError):
        return False
# Cleanup, reconcile and health owners must keep running to recover space.
_CONTROL_PLANE_LOOPS = frozenset({
    "life-manager-disk-cleanup", "life-manager-disk-cleanup-15d", "lm-fence-reconciler",
    "life-manager-health-observer", "life-manager-release-reconciler", "boot-panic-evidence",
    # Recycling idle browsers frees the swap that pushes free disk under the floor (2026-10-18).
    "browser-recycle-idle",
    # Flips Hook Lab TikTok to live: a few KB of local state plus one notice (2026-10-23).
    "warmup-flip-daily",
})
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


def _floor_bytes(loop_id: str | None) -> int:
    floor = _producer_floor_bytes()
    return min(floor, REVENUE_FLOOR_BYTES) if _is_revenue_loop(loop_id) else floor


def _producer_gate(
    loop_id: str | None = None, *, check_capacity: bool = True,
) -> tuple[str, Path] | None:
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
    if check_capacity and loop_id not in _CONTROL_PLANE_LOOPS:
        available = disk_free_bytes(configured)
        floor = _floor_bytes(loop_id)
        if available is not None and available < floor:
            return _PRODUCER_FLOOR_REASON, configured
    return None


def _producer_preflight(loop_id: str | None = None) -> int:
    state_dir = _state_dir()
    if not _ensure_producer_state_dir(state_dir):
        print(json.dumps({
            "status": "failed", "failed": 1, "effect": 0, "readback": 0,
            "reason": "disk_state_unsafe", "required_bytes": 0,
        }, sort_keys=True, separators=(",", ":")))
        return 1
    gate = _producer_gate(loop_id, check_capacity=True)
    if gate is not None:
        reason, flag = gate
        available_bytes = disk_free_bytes(state_dir)
        if reason in {"disk_headroom_low", "disk_headroom_unknown", _PRODUCER_FLOOR_REASON}:
            receipt = {
                "status": "deferred", "effect": 0, "readback": 0,
                "reason": reason, "required_bytes": (
                    _floor_bytes(loop_id) if reason == _PRODUCER_FLOOR_REASON else RECOVERY_FLOOR_BYTES),
                "gate": _PRODUCER_GATE, "flag_path": str(flag),
            }
            if available_bytes is not None:
                receipt["available_bytes"] = available_bytes
            payload = _write_receipt(state_dir, receipt)
            print(payload)
            return 75
        _failure(
            reason,
            available_bytes,
            metadata={"gate": _PRODUCER_GATE, "flag_path": str(flag)},
        )
        return 1
    return 0


def disk_headroom_ok() -> bool:
    """Return whether producer control state and the free-space floor permit work."""
    return _producer_preflight(os.environ.get("LIFE_MANAGER_LOOP_ID")) == 0


def dependency_manifest_matches(left: bytes, right: bytes) -> bool:
    """Ignore only scripts, which the cached npm-ci command never executes."""
    try:
        manifests = [json.loads(payload) for payload in (left, right)]
        for manifest in manifests:
            if not isinstance(manifest, dict):
                return False
            if "scripts" in manifest and not isinstance(manifest["scripts"], dict):
                return False
            manifest.pop("scripts", None)
        return json.dumps(manifests[0], sort_keys=True) == json.dumps(manifests[1], sort_keys=True)
    except (ValueError, TypeError, UnicodeError):
        return False


def dependency_bundle_is_reusable(node_modules: Path, bundle_root: Path) -> bool:
    """Accept only a complete read-only content-addressed bundle under the shared root."""
    try:
        if not node_modules.is_symlink():
            return False
        modules = node_modules.resolve(strict=True)
        bundle = modules.parent
        key = bundle.name.removeprefix("npm-")
        marker = bundle / ".complete"
        return (
            modules == (bundle / "node_modules").resolve(strict=True)
            and bundle.parent.resolve(strict=True) == bundle_root.resolve(strict=True)
            and len(key) == 64
            and all(char in "0123456789abcdef" for char in key)
            and not bundle.stat().st_mode & 0o222
            and not marker.is_symlink()
            and stat.S_ISREG(marker.lstat().st_mode)
            and marker.read_text(encoding="utf-8").strip() == key
            and (modules / ".package-lock.json").is_file()
        )
    except (OSError, UnicodeError, ValueError, RuntimeError):
        return False


def release_capacity_bytes(repo: Path, sha: str, loops: Path, node: str, npm: str) -> int:
    """Measure the source export, bytecode, and serial temporary write budget."""
    return release_capacity(repo, sha, loops, node, npm)[0]


def _fresh_dependency_bytes(package_manifests: list, block: int) -> int:
    """Measure locked production packages without installing or caching artifacts."""
    packages = {}
    for _relative, manifests in package_manifests:
        manifest, lock = (json.loads(payload) for payload in manifests)
        if (not isinstance(manifest, dict) or not isinstance(lock, dict)
                or lock.get("lockfileVersion") not in (2, 3)
                or not isinstance(lock.get("packages"), dict)):
            raise ValueError("locked dependency sizes unavailable")
        for path, entry in lock["packages"].items():
            if not isinstance(path, str) or not isinstance(entry, dict):
                raise ValueError("invalid locked dependency")
            if not path or entry.get("dev") is True:
                continue
            name = entry.get("name") or path.rsplit("node_modules/", 1)[-1]
            version, url, integrity = (entry.get(key) for key in ("version", "resolved", "integrity"))
            if ("node_modules/" not in path or not isinstance(name, str) or not name
                    or not isinstance(version, str) or not version
                    or not isinstance(url, str) or not isinstance(integrity, str)
                    or any(entry.get(key) for key in ("link", "inBundle", "bundled"))):
                raise ValueError("unsupported locked dependency")
            parsed = urllib.parse.urlsplit(url)
            if (parsed.scheme != "https" or parsed.netloc != "registry.npmjs.org"
                    or parsed.query or parsed.fragment or not parsed.path.endswith(".tgz")
                    or not integrity.startswith("sha512-")
                    or len(base64.b64decode(integrity[7:], validate=True)) != 64):
                raise ValueError("unverified locked dependency")
            identity = (name, version, integrity)
            if url in packages and packages[url][0] != identity:
                raise ValueError("conflicting locked dependency")
            packages[url] = (identity, packages.get(url, (identity, 0))[1] + 1)

    def measure(url):
        (name, version, integrity), count = packages[url]
        metadata_url = ("https://registry.npmjs.org/" + urllib.parse.quote(name, safe="")
                        + "/" + urllib.parse.quote(version, safe=""))
        with urllib.request.urlopen(metadata_url, timeout=15) as response:
            metadata = json.load(response)
        if not isinstance(metadata, dict) or not isinstance(metadata.get("dist"), dict):
            raise ValueError("invalid package metadata")
        dist = metadata["dist"]
        if (metadata.get("name") != name or metadata.get("version") != version
                or dist.get("tarball") != url or dist.get("integrity") != integrity):
            raise ValueError("metadata differs from locked dependency")
        size, files = dist.get("unpackedSize"), dist.get("fileCount")
        if ((size is not None and (type(size) is not int or size < 0))
                or (files is not None and (type(files) is not int or files <= 0))):
            raise ValueError("invalid package size metadata")
        rounded = lambda value: ((value + block - 1) // block) * block
        if size is not None and files is not None:
            # Per-file rounding and directory overhead are absent from unpackedSize.
            allocation = rounded(size) + 2 * files * block
        else:
            # Older publications omit sizes. Inspect verified bytes without extracting them.
            digest = hashlib.sha512()
            with urllib.request.urlopen(url, timeout=15) as response:
                class HashingReader:
                    def read(self, size):
                        chunk = response.read(size)
                        digest.update(chunk)
                        return chunk
                reader = HashingReader()
                with tarfile.open(fileobj=reader, mode="r|gz") as entries:
                    allocation = sum(block + rounded(entry.size) for entry in entries)
                while reader.read(1024 * 1024):
                    pass
            if digest.digest() != base64.b64decode(integrity[7:], validate=True):
                raise ValueError("locked tarball integrity mismatch")
            if allocation <= 0:
                raise ValueError("dependency install size unknown")
        return count * allocation

    # Cache by locked tarball across all seven roots; requests overlap without writing a cache.
    tree = 0
    urls = iter(packages)
    with ThreadPoolExecutor(max_workers=8) as pool:
        while batch := list(islice(urls, 8)):
            tree += sum(pool.map(measure, batch))
    return tree + tree // 2  # Existing npm cache/temporary budget.


def release_capacity(repo: Path, sha: str, loops: Path, node: str, npm: str) -> tuple[int, bool]:
    """Return (bytes, fresh_install_budgeted); the flag lets cut-loop-release run npm ci."""
    roots = ("", "runtime/compute-proxy", "runtime/agentmail", "apps/life-manager",
             "skills/earn/taskmarket", "skills/earn/x402-sell", "services/x402-endpoint")
    package_manifests = []
    for relative in roots:
        prefix = relative + "/" if relative else ""
        manifests = []
        for name in ("package.json", "package-lock.json"):
            result = subprocess.run(["git","-C",str(repo),"show",f"{sha}:{prefix}{name}"],capture_output=True)
            manifests.append(result.stdout if result.returncode == 0 else None)
        if None in manifests:
            continue

        package_manifests.append((relative, manifests))

    block = os.statvfs(loops).f_frsize
    if block <= 0:
        raise ValueError("filesystem allocation unknown")
    bootstrap = bool(package_manifests) and not os.path.lexists(loops / "current")
    donors = []
    candidates = []
    if package_manifests:
        candidates = (sorted((loops / "releases").glob("*")) if bootstrap else
                      [(loops / "current").resolve()])
    for donor in candidates:
        try:
            descriptor = json.loads((donor / "RELEASE.json").read_text())
            if (not isinstance(descriptor, dict)
                    or descriptor.get("release_paths") != "ALL"
                    or descriptor.get("provenance") != "ancestor-of-origin-main"
                    or Path(str(descriptor.get("runtime_python"))).resolve() != Path(sys.executable).resolve()
                    or descriptor.get("runtime_python_cache_tag") != sys.implementation.cache_tag
                    or donor.stat().st_mode & 0o222
                    or os.path.lexists(donor / "RECLAIMED-RELEASE.json")):
                raise ValueError("donor is not a complete immutable runtime")
            subprocess.run(["git","-C",str(repo),"merge-base","--is-ancestor",descriptor["sha"],"origin/main"],check=True,capture_output=True)
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
            if not bootstrap:
                raise
            continue
        donors.append(donor)
    fresh_install = 0
    unmatched = []
    for relative, manifests in package_manifests:
        for donor in donors:
            directory = donor / relative
            try:
                donor_manifests = [(directory / name).read_bytes()
                                   for name in ("package.json", "package-lock.json")]
                if (donor_manifests[1] != manifests[1]
                        or not dependency_manifest_matches(donor_manifests[0], manifests[0])):
                    if bootstrap:
                        continue
                    # ponytail: assumes a changed lock installs about as much as the old one (+50%).
                    tree = 0
                    for root, _dirs, files in os.walk((directory / "node_modules").resolve()):
                        for name in files:
                            try:
                                tree += os.lstat(os.path.join(root, name)).st_size + 4096
                            except OSError:
                                pass
                    if tree <= 0:
                        raise ValueError("dependency install size unknown")
                    fresh_install += tree + tree // 2  # npm ci cache and temporaries
                elif not dependency_bundle_is_reusable(directory / "node_modules", loops / "dependency-bundles"):
                    raise ValueError("dependency bundle unavailable")
            except (OSError, ValueError):
                if not bootstrap:
                    raise
                continue
            break
        else:
            unmatched.append((relative, manifests))
    if unmatched:
        fresh_install += _fresh_dependency_bytes(unmatched, block)
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
    return budget + largest_temporary + fresh_install, bool(unmatched) or fresh_install > 0


def main(argv: Sequence[str] | None = None) -> int:
    remaining = list(sys.argv[1:] if argv is None else argv)
    if remaining[:1] == ["--release-capacity"]:
        if len(remaining) != 6:
            return 2
        try:
            required, install = release_capacity(Path(remaining[1]),remaining[2],Path(remaining[3]),remaining[4],remaining[5])
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, tarfile.TarError, SyntaxError, EOFError) as exc:
            print(json.dumps({
                "status": "failed",
                "effect": 0,
                "readback": 0,
                "reason": "release_capacity_measurement_failed",
                "error_class": type(exc).__name__,
            }, sort_keys=True, separators=(",", ":")), file=sys.stderr)
            return 1
        print(f"{required} install" if install else required)
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
    preflight = _producer_preflight(os.environ.get("LIFE_MANAGER_LOOP_ID"))
    if preflight:
        return preflight
    os.execvpe(remaining[0], remaining, os.environ)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
