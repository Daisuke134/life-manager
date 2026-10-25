"""Host caches the five-minute cleanup owns: AI Monk landing worktree caches and oversized logs.

2026-10-25/26 the Mac mini lost 10 GiB in two hours, twice. Measured sources: every new
anicca-products worktree ran `npm ci` (1.5 GB apps/landing/node_modules) and `next build`
(1.5-2.1 GB apps/landing/.next/cache, webpack packs plus `.old` copies), and ~/.tsbridge/logs
grew to 312 MB with no rotation. scripts/landing-shared-node-modules.sh and
scripts/landing-postbuild-clean.sh already do the right thing for one worktree; this module runs
them for every idle worktree on each cleanup pass and rotates the allowlisted logs.
"""
from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
LANDING_WORKTREE_ROOTS = (
    Path("Projects/anicca-products-worktrees"),
    Path("Projects/anicca-products/.worktrees"),
)
LANDING_IDLE_SECONDS = 30 * 60
LANDING_SCRIPT_TIMEOUT_SECONDS = 900
LOG_ROTATE_GLOBS = (".tsbridge/logs/*.log",)
LOG_ROTATE_BYTES = 100 * 1024 * 1024
LOG_ROTATE_KEEP = 3


def _mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def landing_cache_cleanup(home: Path, *, root: Path = ROOT, now: Callable[[], float] = time.time,
                          runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
                          idle_seconds: int = LANDING_IDLE_SECONDS) -> dict:
    """Share node_modules and drop .next/cache for every landing worktree idle for idle_seconds."""
    result = {"examined": 0, "shared": 0, "cache_removed": 0, "skipped_busy": 0, "errors": 0}
    share = root / "scripts/landing-shared-node-modules.sh"
    clean = root / "scripts/landing-postbuild-clean.sh"
    for relative in LANDING_WORKTREE_ROOTS:
        base = home / relative
        if not base.is_dir() or base.is_symlink():
            continue
        for worktree in sorted(base.iterdir()):
            if worktree.is_symlink() or not worktree.is_dir():
                continue
            landing = worktree / "apps/landing"
            node_modules = landing / "node_modules"
            cache = landing / ".next/cache"
            need_share = node_modules.is_dir() and not node_modules.is_symlink() and (landing / "package-lock.json").is_file()
            need_clean = cache.is_dir() and not cache.is_symlink()
            if not (need_share or need_clean):
                continue
            result["examined"] += 1
            newest = max(m for m in (_mtime(node_modules) if need_share else None,
                                     _mtime(cache) if need_clean else None) if m is not None)
            if now() - newest < idle_seconds:
                result["skipped_busy"] += 1
                continue
            for needed, script, key in ((need_share, share, "shared"), (need_clean, clean, "cache_removed")):
                if not needed:
                    continue
                try:
                    completed = runner(["/bin/bash", str(script), str(worktree)], capture_output=True,
                                       text=True, timeout=LANDING_SCRIPT_TIMEOUT_SECONDS, check=False)
                except (OSError, subprocess.SubprocessError):
                    result["errors"] += 1
                    continue
                if completed.returncode == 0:
                    result[key] += 1
                elif completed.returncode == 3:  # the script's own "a process has it open"
                    result["skipped_busy"] += 1
                else:
                    result["errors"] += 1
    return result


def rotate_large_logs(home: Path, *, globs: tuple[str, ...] = LOG_ROTATE_GLOBS,
                      threshold: int = LOG_ROTATE_BYTES, keep: int = LOG_ROTATE_KEEP,
                      now: Callable[[], float] = time.time) -> dict:
    """gzip a copy of any allowlisted log over threshold, truncate it in place, keep `keep` archives.

    Truncating (not renaming) keeps the writer's open append descriptor valid: with O_APPEND the
    next write lands at the new end of file.
    """
    result = {"rotated": 0, "pruned": 0, "errors": 0, "bytes_freed": 0}
    for pattern in globs:
        for path in sorted(home.glob(pattern)):
            if path.is_symlink() or not path.is_file():
                continue
            try:
                size = path.stat().st_size
            except OSError:
                result["errors"] += 1
                continue
            if size <= threshold:
                continue
            stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(now()))
            archive = path.with_name(f"{path.name}.{stamp}.gz")
            try:
                with open(path, "rb") as source, gzip.open(archive, "wb") as target:
                    shutil.copyfileobj(source, target)
                with open(path, "r+b") as handle:
                    handle.truncate(0)
            except OSError:
                result["errors"] += 1
                try:
                    archive.unlink(missing_ok=True)
                except OSError:
                    pass
                continue
            result["rotated"] += 1
            result["bytes_freed"] += size
            archives = sorted(path.parent.glob(f"{path.name}.*.gz"), key=lambda p: p.name)
            for old in archives[:-keep] if keep > 0 else archives:
                try:
                    old.unlink()
                    result["pruned"] += 1
                except OSError:
                    result["errors"] += 1
    return result
