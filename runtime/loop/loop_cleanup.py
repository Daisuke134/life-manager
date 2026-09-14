#!/usr/bin/env python3
"""Bounded deletion for marked loop runs and shared immutable releases."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import time
from pathlib import Path


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


def _tree_bytes(path: Path) -> int:
    total = 0
    for current, directories, files in os.walk(path, followlinks=False):
        os.chmod(current, 0o700)
        directories[:] = [name for name in directories
                           if not (Path(current) / name).is_symlink()]
        for name in files:
            item = Path(current) / name
            try:
                if not item.is_symlink(): total += item.stat().st_size
            except OSError:
                pass
    return total


def _contains_protected(path: Path) -> bool:
    if (path / ".lm-protected").exists():
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
                     now: float | None = None) -> dict[str, int]:
    result = {"evaluated_runs": 0, "removed_runs": 0, "reclaimed_bytes": 0,
              "preserved_runs": 0, "protected_deletions": 0, "errors": 0}
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
    return result


def _valid_release(path: Path) -> bool:
    if not RELEASE_NAME.fullmatch(path.name) or not path.is_dir() or path.is_symlink():
        return False
    try:
        value = json.loads((path / "RELEASE.json").read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(value.get("sha"), str) and bool(re.fullmatch(r"[0-9a-f]{40}", value["sha"]))


def gc_releases(releases_root: Path, current: Path, *, keep: int,
                protected: set[Path]) -> dict[str, int]:
    result = {"evaluated_releases": 0, "removed_releases": 0, "reclaimed_bytes": 0,
              "preserved_releases": 0, "protected_deletions": 0, "errors": 0}
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
    return result
