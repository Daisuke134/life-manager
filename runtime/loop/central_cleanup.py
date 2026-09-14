#!/usr/bin/env python3
"""Central owner for shared immutable Life Manager release garbage collection."""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.loop.loop_cleanup import gc_releases, remove_owned_tree
from runtime.host.resource_admission import process_starts


def installed_state_roots(agents_dir: Path) -> set[Path]:
    roots = set()
    for plist_path in agents_dir.glob("ai.anicca.*.plist"):
        try:
            with plist_path.open("rb") as handle:
                plist = plistlib.load(handle)
            if not isinstance(plist, dict):
                continue
            environment = plist.get("EnvironmentVariables") or {}
            if not isinstance(environment, dict):
                continue
            value = environment.get("LIFE_MANAGER_STATE_ROOT")
            if isinstance(value, str) and value:
                roots.add(Path(value).expanduser().resolve())
        except (OSError, ValueError, plistlib.InvalidFileException):
            continue
    return roots


def scratch_gc(roots: set[Path], *, snapshot_started_ns: int | None = None,
               starts: dict[int, str] | None = None) -> dict[str, int | bool]:
    """Delete only crashed per-run scratch whose process identity is provably stale."""
    started_ns = time.time_ns() if snapshot_started_ns is None else snapshot_started_ns
    identities = process_starts() if starts is None else starts
    result: dict[str, int | bool] = {
        "evaluated": 0, "removed": 0, "preserved": 0, "errors": 0,
        "identity_snapshot_available": identities is not None,
    }
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    for root in roots:
        root_fd = scratch_fd = -1
        try:
            root_fd = os.open(root.resolve(), flags)
            scratch_fd = os.open("loop-tmp", flags, dir_fd=root_fd)
            loop_names = os.listdir(scratch_fd)
        except FileNotFoundError:
            continue
        except OSError:
            result["errors"] += 1
            continue
        finally:
            if root_fd >= 0:
                os.close(root_fd)
        try:
            for loop_name in loop_names:
                loop_fd = -1
                try:
                    loop_fd = os.open(loop_name, flags, dir_fd=scratch_fd)
                    run_names = os.listdir(loop_fd)
                except OSError:
                    continue
                try:
                    for run_name in run_names:
                        run_fd = owner_fd = -1
                        try:
                            run_fd = os.open(run_name, flags, dir_fd=loop_fd)
                            owner_fd = os.open(
                                ".owner.json", os.O_RDONLY | nofollow, dir_fd=run_fd)
                        except OSError:
                            for descriptor in (owner_fd, run_fd):
                                if descriptor >= 0:
                                    os.close(descriptor)
                            continue
                        result["evaluated"] += 1
                        try:
                            try:
                                os.stat(".terminal-unrecorded", dir_fd=run_fd,
                                        follow_symlinks=False)
                            except FileNotFoundError:
                                pass
                            else:
                                result["preserved"] += 1
                                continue
                            owner_stat = os.fstat(owner_fd)
                            owner_bytes = b""
                            while chunk := os.read(owner_fd, 65536):
                                owner_bytes += chunk
                            owner = json.loads(owner_bytes)
                            if not isinstance(owner, dict):
                                raise ValueError("owner must be an object")
                            pid, expected = owner.get("pid"), owner.get("process_start")
                            if (not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0
                                    or not isinstance(expected, str) or not expected):
                                raise ValueError("invalid owner identity")
                            if identities is None or owner_stat.st_mtime_ns >= started_ns:
                                result["preserved"] += 1
                                continue
                            actual = identities.get(pid)
                            if actual is not None and actual == expected:
                                result["preserved"] += 1
                                continue
                            if remove_owned_tree(loop_fd, run_fd, run_name):
                                result["removed"] += 1
                            else:
                                result["errors"] += 1
                                result["preserved"] += 1
                        except (OSError, TypeError, ValueError, json.JSONDecodeError):
                            result["errors"] += 1
                            result["preserved"] += 1
                        finally:
                            for descriptor in (owner_fd, run_fd):
                                if descriptor >= 0:
                                    os.close(descriptor)
                finally:
                    os.close(loop_fd)
        finally:
            os.close(scratch_fd)
    return result


def host_cleanup_command(root: Path, home: Path, state_dir=None) -> list[str]:
    state_dir = state_dir or home / ".local/state/life-manager/state"
    return [sys.executable, str(root / "skills/self/disk-cleanup/disk_cleanup.py"),
            "--home", str(home), "--state-dir",
            str(state_dir)]


def host_cleanup_ok(returncode: int, result: object) -> bool:
    return (returncode == 0 and isinstance(result, dict)
            and result.get("errors") == 0 and result.get("protected_deletions") == 0)


def loaded_release_roots(agents_dir: Path, releases_root: Path) -> set[Path]:
    protected = set()
    base = releases_root.resolve()
    for plist_path in agents_dir.glob("ai.anicca.*.plist"):
        try:
            with plist_path.open("rb") as handle:
                plist = plistlib.load(handle)
        except Exception:
            continue
        for value in map(str, plist.get("ProgramArguments") or []):
            candidate = Path(os.path.expanduser(value))
            try:
                resolved = candidate.resolve(strict=True)
                relative = resolved.relative_to(base)
            except (OSError, ValueError):
                continue
            if relative.parts:
                release = base / relative.parts[0]
                if release.is_dir(): protected.add(release.resolve())
    return protected


def open_release_roots(releases_root: Path) -> set[Path]:
    """Return release roots named by a running process command."""
    completed = subprocess.run(
        ["ps", "-axo", "command="],
        capture_output=True, text=True, timeout=120,
    )
    if completed.returncode != 0:
        raise OSError(f"release process inventory failed: {completed.returncode}")
    requested_base = releases_root.expanduser()
    base = requested_base.resolve()
    commands = completed.stdout
    return {
        release.resolve()
        for release in base.iterdir()
        if release.is_dir() and any(
            candidate in commands
            for candidate in (str(release.resolve()), str(requested_base / release.name))
        )
    }


def release_gc(releases: Path, current: Path, agents: Path, keep: int) -> dict:
    """Collect releases while pinning every generation referenced by launchd."""
    protected = loaded_release_roots(agents, releases) | open_release_roots(releases)
    protected_file = Path(os.environ.get(
        "LIFE_MANAGER_PROTECTED_RELEASES", "~/.local/state/life-manager/protected-releases.json")).expanduser()
    try:
        values = json.loads(protected_file.read_text())
        if isinstance(values, list):
            protected.update(Path(value).expanduser().resolve() for value in values if isinstance(value, str))
    except (OSError, json.JSONDecodeError):
        pass
    result = gc_releases(releases, current, keep=keep, protected=protected)
    result["protected_release_count"] = len(protected)
    return result


def main() -> int:
    home = Path.home()
    loops_root = Path(os.environ.get("LOOPS_ROOT", "~/loops")).expanduser()
    releases = loops_root / "releases"
    current = loops_root / "current"
    agents = Path(os.environ.get(
        "LIFE_MANAGER_LAUNCH_AGENTS_DIR", "~/Library/LaunchAgents")).expanduser()
    if sys.argv[1:] == ["--release-gc-only"]:
        try:
            result = release_gc(releases, current, agents,
                                keep=int(os.environ.get("LIFE_MANAGER_RELEASE_KEEP", "1")))
        except (OSError, ValueError) as error:
            print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True)); return 1
        result["ok"] = result["errors"] == 0
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["ok"] else 1
    try:
        cleanup_state = Path(os.environ.get(
            "LIFE_MANAGER_HOST_STATE_DIR",
            home / ".local/state/life-manager/state",
        )).expanduser()
        host_process = subprocess.run(
            host_cleanup_command(ROOT, home, cleanup_state),
            capture_output=True, text=True, timeout=240,
        )
        host_result = json.loads(host_process.stdout.splitlines()[-1]) if host_process.stdout.strip() else {}
        host_ok = host_cleanup_ok(host_process.returncode, host_result)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, IndexError) as error:
        host_ok, host_result = False, {"error": str(error)}
    try:
        result = release_gc(releases, current, agents,
                            keep=int(os.environ.get("LIFE_MANAGER_RELEASE_KEEP", "1")))
    except (OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True)); return 1
    snapshot_started_ns = time.time_ns()
    scratch_result = scratch_gc(
        installed_state_roots(agents), snapshot_started_ns=snapshot_started_ns,
        starts=process_starts())
    result.update({"ok": result["errors"] == 0 and host_ok and scratch_result["errors"] == 0,
                   "host_cleanup": host_result,
                   "scratch_cleanup": scratch_result,
                   "idle_reconcile": [],
                   "shared_cache_candidates": 0, "orphan_candidates": 0})
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
