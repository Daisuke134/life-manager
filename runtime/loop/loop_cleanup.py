#!/usr/bin/env python3
"""Bounded deletion for marked loop runs and shared immutable releases."""

from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
import stat
import subprocess
import time
from contextlib import ExitStack
from pathlib import Path
from typing import Callable


PROTECTED_NAME = re.compile(r"receipt|ledger|credential|session|wallet|payment", re.I)
RELEASE_NAME = re.compile(r"\d{8}T\d{6}-[0-9a-f]{8,40}\Z")


def _clear_owned_directory(directory_fd: int) -> bool:
    """Clear entries only while each inspected inode remains at the same name."""
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    for name in os.listdir(directory_fd):
        try:
            before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISDIR(before.st_mode):
                child_fd = os.open(name, flags, dir_fd=directory_fd)
                try:
                    opened = os.fstat(child_fd)
                    if ((opened.st_dev, opened.st_ino) !=
                            (before.st_dev, before.st_ino)
                            or not _clear_owned_directory(child_fd)):
                        return False
                    current = os.stat(name, dir_fd=directory_fd,
                                      follow_symlinks=False)
                    if ((current.st_dev, current.st_ino) !=
                            (opened.st_dev, opened.st_ino)):
                        return False
                    os.rmdir(name, dir_fd=directory_fd)
                finally:
                    os.close(child_fd)
            else:
                current = os.stat(name, dir_fd=directory_fd,
                                  follow_symlinks=False)
                if ((current.st_dev, current.st_ino) !=
                        (before.st_dev, before.st_ino)):
                    return False
                os.unlink(name, dir_fd=directory_fd)
        except FileNotFoundError:
            continue
    return True


def remove_owned_tree(parent_fd: int, opened_fd: int, name: str) -> bool:
    """Rename and remove only the directory inode already opened by its owner."""
    expected = os.fstat(opened_fd)
    trash = f"{name}.gc-trash.{os.getpid()}.{time.time_ns():x}"
    os.replace(name, trash, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    trash_fd = os.open(trash, flags, dir_fd=parent_fd)
    try:
        actual = os.fstat(trash_fd)
        if ((actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino)
                or not _clear_owned_directory(trash_fd)):
            return False
        current = os.stat(trash, dir_fd=parent_fd, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino):
            return False
        os.rmdir(trash, dir_fd=parent_fd)
        return True
    finally:
        os.close(trash_fd)


def _tree_bytes(path: Path, *, prepare_delete: bool = True) -> int:
    total = 0
    for current, directories, files in os.walk(path, followlinks=False):
        if prepare_delete:
            os.chmod(current, 0o700)
        directories[:] = [name for name in directories
                           if not (Path(current) / name).is_symlink()]
        for name in files:
            item = Path(current) / name
            try:
                if not item.is_symlink(): total += item.stat().st_size
            except OSError:
                if not prepare_delete:
                    raise
    return total


def _contains_protected(path: Path) -> bool:
    if (path / ".lm-protected").exists():
        return True
    if _release_immutable_store_probe(path) is not None:
        return True
    try:
        return any(PROTECTED_NAME.search(item.name) for item in path.rglob("*") if not item.is_symlink())
    except OSError:
        return True


def _remove_marked(path: Path) -> int:
    size = _tree_bytes(path)
    trash = path.with_name(f"{path.name}.gc-trash.{os.getpid()}")
    os.replace(path, trash)
    shutil.rmtree(trash)
    return size


def cleanup_run_root(root: Path, contract: dict, active_run_ids: set[str], *,
                     now: float | None = None, managed_bytes: int | None = None,
                     closed_run_ids: set[str] | None = None) -> dict[str, int]:
    result = {"evaluated_runs": 0, "removed_runs": 0, "reclaimed_bytes": 0,
              "preserved_runs": 0, "protected_deletions": 0, "errors": 0}
    if managed_bytes is not None and (type(managed_bytes) is not int or managed_bytes < 0):
        raise ValueError("invalid managed byte budget")
    runs = root.expanduser() / "runs"
    if not runs.is_dir() or runs.is_symlink():
        return result
    now = time.time() if now is None else now
    max_runs = max(0, int(contract["max_runs"]))
    max_age = max(0, int(contract["max_age_days"])) * 86400
    candidates = []
    for path in runs.iterdir():
        if (not path.is_dir() or path.is_symlink()
                or not (path / ".lm-regenerable").is_file()
                or not (path / "summary.json").is_file()):
            continue
        result["evaluated_runs"] += 1
        if path.name in active_run_ids or _contains_protected(path):
            result["preserved_runs"] += 1
            continue
        try:
            candidates.append((path.stat().st_mtime, path))
        except OSError:
            result["errors"] += 1
    ordered = sorted(candidates, reverse=True)
    keep = {path for _, path in ordered[:max_runs]}
    for modified, path in reversed(ordered):
        if path in keep and now - modified <= max_age:
            result["preserved_runs"] += 1
            continue
        try:
            result["reclaimed_bytes"] += _remove_marked(path)
            result["removed_runs"] += 1
        except OSError:
            result["errors"] += 1
    if managed_bytes is not None:
        if type(managed_bytes) is not int or managed_bytes < 0:
            raise ValueError("invalid managed byte budget")
        retained = []
        for path in runs.iterdir():
            if not path.is_dir() or path.is_symlink():
                continue
            try:
                size = _tree_bytes(path, prepare_delete=False)
                retained.append((path.stat().st_mtime, path, size))
            except OSError:
                result["errors"] += 1
        eligible = []
        unavailable = 0
        for modified, path, size in retained:
            if (path.name in active_run_ids or path.name not in (closed_run_ids or set())
                    or _contains_protected(path) or not (path / ".lm-regenerable").is_file()
                    or not (path / "summary.json").is_file()):
                unavailable += size
                continue
            eligible.append((modified, path, size))
        total = sum(size for _, _, size in eligible)
        for _, path, size in sorted(eligible):
            if total <= managed_bytes:
                break
            try:
                result["reclaimed_bytes"] += _remove_marked(path)
                result["removed_runs"] += 1
                total -= size
            except OSError:
                result["errors"] += 1
        result["unrecoverable_bytes"] = unavailable + max(0, total - managed_bytes)
    return result


def release_is_reclaimed(path: Path) -> bool:
    """Reject selection unless the reclaimed descriptor is definitely absent."""
    try:
        (path / "RECLAIMED-RELEASE.json").lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def reclaim_release_source(path: Path, source_repo: Path, *,
                           can_reclaim: Callable[[tuple[int, ...]], bool],
                           max_bytes: int = 64 * 1024**2, max_files: int = 256,
                           deadline: float | None = None) -> dict:
    """Reclaim matching Git code leaves; retain stores and unknown files in place."""
    result = {"removed_files": 0, "removed_source_bytes": 0, "reclaimed_bytes": 0,
              "protected_deletions": 0, "errors": 0, "status": "preserved"}
    deadline = time.monotonic() + 15 if deadline is None else deadline
    if max_bytes < 1 or max_files < 1 or time.monotonic() >= deadline:
        return result
    directories = {"bin", "runtime", "apps", "skills", "lib", "scripts", "services",
                   "templates", "plugins", "adapters", "integrations"}
    suffixes = {".py", ".js", ".cjs", ".mjs", ".sh", ".ts", ".tsx", ".jsx",
                ".css", ".html", ".svg", ".png", ".jpg", ".webp"}
    sensitive = re.compile(r"credential|secret|cookie|passkey|recovery|auth|session|wallet|payment|receipt|ledger", re.I)
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    root_fd = None
    root_mode = None
    def git(*args):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(args, 0)
        return subprocess.run(["git", "-C", str(source_repo), *args], check=True,
                              capture_output=True, timeout=min(3, remaining)).stdout
    def identity(info):
        return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    try:
        if can_reclaim(()) is not True:
            return result
        if (path / ".lm-protected").exists() or (path / ".lm-protected").is_symlink():
            return result
        before = path.lstat()
        if not stat.S_ISDIR(before.st_mode) or before.st_uid != os.getuid():
            return result
        root_fd = os.open(path, flags)
        root = os.fstat(root_fd)
        if (root.st_dev, root.st_ino) != (before.st_dev, before.st_ino):
            return result
        root_mode = stat.S_IMODE(root.st_mode)
        descriptor = "RECLAIMED-RELEASE.json" if release_is_reclaimed(path) else "RELEASE.json"
        desc_fd = os.open(descriptor, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
        try:
            desc_info = os.fstat(desc_fd)
            if (not stat.S_ISREG(desc_info.st_mode) or desc_info.st_uid != os.getuid()
                    or desc_info.st_size > 65536):
                return result
            manifest = json.loads(os.read(desc_fd, 65537))
        finally:
            os.close(desc_fd)
        sha = manifest.get("sha")
        if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{40}", sha):
            return result
        try:
            git("merge-base", "--is-ancestor", sha, "refs/remotes/origin/main")
        except subprocess.CalledProcessError:
            return result
        entries = []
        for entry in git("ls-tree", "-r", "-l", "-z", sha).split(b"\0"):
            if not entry:
                continue
            header, relative = entry.split(b"\t", 1)
            mode, kind, oid, size = header.split()
            name = relative.decode("utf-8")
            parts = Path(name).parts
            if (mode not in (b"100644", b"100755") or kind != b"blob"
                    or not parts or parts[0] not in directories
                    or Path(name).suffix not in suffixes
                    or any(p in {"memory", "state", "private", "identity", ".cloak", "node_modules", ".git"}
                           or p.startswith(".env") or sensitive.search(p) for p in parts)):
                continue
            entries.append((int(size), name, oid.decode()))
        for size, name, oid in sorted(entries, reverse=True):
            if time.monotonic() >= deadline or result["removed_files"] >= max_files:
                break
            if size > max_bytes - result["removed_source_bytes"]:
                continue
            parts = Path(name).parts
            with ExitStack() as stack:
                parent_fd = root_fd
                parents = []
                try:
                    for part in parts[:-1]:
                        child = os.open(part, flags, dir_fd=parent_fd)
                        stack.callback(os.close, child)
                        child_info = os.fstat(child)
                        if child_info.st_uid != os.getuid():
                            raise PermissionError("source parent UID mismatch")
                        parents.append((parent_fd, part, child_info))
                        parent_fd = child
                    leaf_fd = os.open(parts[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd)
                    stack.callback(os.close, leaf_fd)
                    info = os.fstat(leaf_fd)
                    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                            or info.st_size != size or info.st_nlink != 1):
                        continue
                    if info.st_blocks * 512 > max_bytes - result["reclaimed_bytes"]:
                        continue
                    git("cat-file", "-e", oid + "^{blob}")
                    digest = hashlib.sha1(f"blob {size}\0".encode())
                    while chunk := os.read(leaf_fd, 512 * 1024):
                        if time.monotonic() >= deadline:
                            return result
                        digest.update(chunk)
                    if digest.hexdigest() != oid or identity(os.fstat(leaf_fd)) != identity(info):
                        continue
                    owned_fds = (root_fd, parent_fd, leaf_fd, *(p[0] for p in parents))
                    if (can_reclaim(owned_fds) is not True or time.monotonic() >= deadline
                            or (path.lstat().st_dev, path.lstat().st_ino) != (root.st_dev, root.st_ino)):
                        return result
                    for ancestor_fd, component, opened in parents:
                        named = os.stat(component, dir_fd=ancestor_fd, follow_symlinks=False)
                        if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
                            return result
                    if descriptor == "RELEASE.json":
                        if identity(os.stat(descriptor, dir_fd=root_fd, follow_symlinks=False)) != identity(desc_info):
                            return result
                        if release_is_reclaimed(path):
                            return result
                        os.fchmod(root_fd, root_mode | stat.S_IWUSR)
                        os.rename(descriptor, "RECLAIMED-RELEASE.json", src_dir_fd=root_fd, dst_dir_fd=root_fd)
                        os.fsync(root_fd)
                        descriptor = "RECLAIMED-RELEASE.json"
                    now = os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)
                    if identity(now) != identity(info):
                        continue
                    mode = stat.S_IMODE(os.fstat(parent_fd).st_mode)
                    os.fchmod(parent_fd, mode | stat.S_IWUSR)
                    try:
                        for ancestor_fd, component, opened in parents:
                            named = os.stat(component, dir_fd=ancestor_fd, follow_symlinks=False)
                            if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
                                return result
                        if identity(os.stat(parts[-1], dir_fd=parent_fd, follow_symlinks=False)) != identity(info):
                            continue
                        os.unlink(parts[-1], dir_fd=parent_fd)
                        result["removed_files"] += 1
                        result["removed_source_bytes"] += size
                        result["reclaimed_bytes"] += info.st_blocks * 512
                        result["status"] = "reclaimed"
                    finally:
                        os.fchmod(parent_fd, mode)
                except OSError:
                    # Missing, linked, unreadable and changed leaves remain untouched.
                    continue
    except subprocess.TimeoutExpired:
        result["budget_exhausted"] = True
    except (OSError, ValueError, subprocess.SubprocessError):
        result["errors"] += 1
    finally:
        if root_fd is not None:
            if root_mode is not None:
                os.fchmod(root_fd, root_mode)
            os.close(root_fd)
    return result


def _valid_release(path: Path) -> bool:
    if (not RELEASE_NAME.fullmatch(path.name) or not path.is_dir() or path.is_symlink()
            or release_is_reclaimed(path)):
        return False
    try:
        value = json.loads((path / "RELEASE.json").read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(value.get("sha"), str) and bool(re.fullmatch(r"[0-9a-f]{40}", value["sha"]))


def _release_immutable_store_probe(
    path: Path,
    *,
    deadline: float | None = None,
    clock: Callable[[], float] | None = None,
) -> str | None:
    """Preserve memory/state JSONL paths; fail closed on probe errors or deadlines."""
    clock = clock or time.monotonic
    errors: list[OSError] = []
    try:
        for current, directories, files in os.walk(
            path, topdown=True, followlinks=False, onerror=errors.append
        ):
            if errors:
                return "descendant_probe_error"
            if deadline is not None and clock() >= deadline:
                return "probe-budget-exhausted"
            current_path = Path(current)
            if current_path.name == "memory" or "memory" in directories:
                return "protected_descendant"
            if current_path.name == "state" and any(name.endswith(".jsonl") for name in files):
                return "protected_descendant"
            for name in directories + files:
                if deadline is not None and clock() >= deadline:
                    return "probe-budget-exhausted"
                if name not in {"memory", "state"}:
                    continue
                try:
                    info = (current_path / name).lstat()
                except OSError:
                    return "descendant_probe_error"
                if stat.S_ISLNK(info.st_mode):
                    return "protected_descendant"
    except OSError:
        return "descendant_probe_error"
    return "descendant_probe_error" if errors else None


def gc_releases(releases_root: Path, current: Path, *, keep: int,
                protected: set[Path], managed_bytes: int | None = None,
                closed_releases: set[Path] | None = None) -> dict[str, int]:
    result = {"evaluated_releases": 0, "removed_releases": 0, "reclaimed_bytes": 0,
              "preserved_releases": 0, "protected_deletions": 0, "errors": 0}
    if managed_bytes is not None and (type(managed_bytes) is not int or managed_bytes < 0):
        raise ValueError("invalid managed release byte budget")
    if not releases_root.is_dir() or releases_root.is_symlink():
        return result
    protected = {path.resolve() for path in protected}
    try:
        protected.add(current.resolve(strict=True))
    except OSError:
        pass
    candidates = []
    for path in releases_root.iterdir():
        if not _valid_release(path):
            continue
        result["evaluated_releases"] += 1
        if path.resolve() in protected:
            result["preserved_releases"] += 1
            continue
        store_state = _release_immutable_store_probe(path)
        if store_state is not None:
            result["preserved_releases"] += 1
            result["errors"] += store_state == "descendant_probe_error"
            continue
        try:
            candidates.append((path.stat().st_mtime, path))
        except OSError:
            result["errors"] += 1
    ordered = sorted(candidates, reverse=True)
    for _, path in ordered[:max(0, keep)]:
        result["preserved_releases"] += 1
    for _, path in reversed(ordered[max(0, keep):]):
        try:
            result["reclaimed_bytes"] += _remove_marked(path)
            result["removed_releases"] += 1
        except OSError:
            result["errors"] += 1
    if managed_bytes is not None:
        closed = {p.resolve() for p in (closed_releases or set())}
        retained = []
        unavailable = 0
        for modified, path in ordered[:max(0, keep)]:
            if not path.exists():
                continue
            try:
                size = _tree_bytes(path, prepare_delete=False)
                if path.resolve() not in closed:
                    unavailable += size
                else:
                    retained.append((modified, path, size))
            except OSError:
                result["errors"] += 1
        total = sum(size for _, _, size in retained)
        for _, path, size in sorted(retained):
            if total <= managed_bytes:
                break
            if path.resolve() in protected or _release_immutable_store_probe(path) is not None:
                unavailable += size
                continue
            try:
                result["reclaimed_bytes"] += _remove_marked(path)
                result["removed_releases"] += 1
                total -= size
            except OSError:
                result["errors"] += 1
        result["unrecoverable_bytes"] = unavailable + max(0, total - managed_bytes)
    return result
