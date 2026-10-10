#!/usr/bin/env python3
"""Central owner for shared immutable Life Manager release garbage collection."""

from __future__ import annotations

import json
import os
import plistlib
import re
import stat
import subprocess
import sys
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from xml.parsers.expat import ExpatError

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from runtime.loop.loop_cleanup import (
    gc_releases, remove_owned_tree, reclaim_release_source, release_is_reclaimed,
    RELEASE_NAME, _release_immutable_store_probe,
)
from runtime.host.resource_admission import process_starts

HOST_CLEANUP_RECOVERY_FLOOR_BYTES = 2 * 1024**3  # cleanup receipt target; not producer admission


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
        except (OSError, ValueError, plistlib.InvalidFileException, ExpatError):
            continue
    return roots


def no_effect_loop_ids(registry_path: Path) -> set[str]:
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return set()
    loops = registry.get("loops") if isinstance(registry, dict) else None
    if not isinstance(loops, dict):
        return set()
    return {
        loop_id for loop_id, entry in loops.items()
        if isinstance(loop_id, str) and isinstance(entry, dict)
        and entry.get("effect_class") == "none"
    }


def recorded_effect_classes(events_path: Path, loop_ids: set[str]) -> dict[tuple[str, str], str | None]:
    observed: dict[tuple[str, str], set[str | None]] = {}
    try:
        with events_path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except (UnicodeError, json.JSONDecodeError):
                    return {}
                if not isinstance(event, dict):
                    return {}
                loop_id, run_id, effect_class = (
                    event.get("loop_id"), event.get("run_id"), event.get("effect_class"))
                if not isinstance(loop_id, str) or loop_id not in loop_ids:
                    continue
                if not isinstance(run_id, str):
                    return {}
                observed.setdefault((loop_id, run_id), set()).add(
                    effect_class if isinstance(effect_class, str) else None)
    except (OSError, UnicodeError):
        return {}
    return {
        key: next(iter(classes)) if len(classes) == 1 and None not in classes else None
        for key, classes in observed.items()
    }


def _diagnostic_relay_live(run_fd: int, starts: dict | None, loop_id: str, run_id: str) -> bool:
    directory = descriptor = -1
    try:
        directory = os.open("stderr-relay", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=run_fd)
        descriptor = os.open(".stderr-relay.json", os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 4096):
            return True
        with os.fdopen(descriptor, "r", closefd=False) as handle:
            value = json.load(handle)
        binding = value["binding"]
        if (type(value["pid"]) is not int or value["pid"] <= 0
                or not isinstance(value["process_start"], str)
                or binding.get("owner_id") != loop_id or binding.get("run_id") != run_id
                or value.get("role") != "diagnostic_only" or starts is None):
            return True
        actual = starts.get(value["pid"])
        return actual is not None and " ".join(actual.split()) == " ".join(value["process_start"].split())
    except FileNotFoundError:
        return False
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return True
    finally:
        if descriptor >= 0: os.close(descriptor)
        if directory >= 0: os.close(directory)


def scratch_gc(roots: set[Path], *, snapshot_started_ns: int | None = None,
               starts: dict[int, str] | None = None,
               no_effect_loop_ids: set[str] | frozenset[str] = frozenset()
               ) -> dict[str, int | bool]:
    """Delete only crashed per-run scratch whose process identity is provably stale."""
    started_ns = time.time_ns() if snapshot_started_ns is None else snapshot_started_ns
    identities = process_starts() if starts is None else starts
    result: dict[str, int | bool] = {
        "evaluated": 0, "removed": 0, "preserved": 0, "errors": 0,
        "owner_metadata_invalid": 0,
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
        event_effect_classes = recorded_effect_classes(root / "events.jsonl", set(loop_names))
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
                        except FileNotFoundError:
                            for descriptor in (owner_fd, run_fd):
                                if descriptor >= 0:
                                    os.close(descriptor)
                            continue
                        except OSError:
                            result["errors"] += 1
                            result["preserved"] += 1
                            for descriptor in (owner_fd, run_fd):
                                if descriptor >= 0:
                                    os.close(descriptor)
                            continue
                        result["evaluated"] += 1
                        if _diagnostic_relay_live(run_fd, identities, loop_name, run_name):
                            os.close(owner_fd); os.close(run_fd)
                            result["preserved"] += 1
                            continue
                        try:
                            try:
                                os.stat(".terminal-unrecorded", dir_fd=run_fd,
                                        follow_symlinks=False)
                            except FileNotFoundError:
                                has_terminal_unrecorded = False
                            else:
                                has_terminal_unrecorded = True
                            # Without this marker, lm_loop_run persisted the terminal event and
                            # ordinary stale-owner GC may reclaim the completed scratch.
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
                            if "effect_class" in owner:
                                owner_effect_class = owner["effect_class"]
                                if (not isinstance(owner_effect_class, str)
                                        or not owner_effect_class):
                                    raise ValueError("invalid owner effect class")
                            else:
                                owner_effect_class = None
                            if (has_terminal_unrecorded
                                    and loop_name not in no_effect_loop_ids):
                                result["preserved"] += 1
                                continue
                            if has_terminal_unrecorded:
                                event_key = (loop_name, run_name)
                                recorded_effect_class = event_effect_classes.get(event_key)
                                if (event_key not in event_effect_classes
                                        or recorded_effect_class != "none"
                                        or (owner_effect_class is not None
                                            and owner_effect_class != recorded_effect_class)):
                                    result["preserved"] += 1
                                    continue
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
                        except (TypeError, ValueError, json.JSONDecodeError):
                            result["owner_metadata_invalid"] += 1
                            result["preserved"] += 1
                        except OSError:
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


def _host_cleanup_capacity_status(result: object) -> str:
    free_after = result.get("free_after") if isinstance(result, dict) else None
    if (not isinstance(free_after, int) or isinstance(free_after, bool)
            or free_after < 0):
        return "unknown"
    return "met" if free_after >= HOST_CLEANUP_RECOVERY_FLOOR_BYTES else "unmet"


def cleanup_run_binding(env: dict, release_root: Path) -> dict | None:
    """Read host-owned identity; an unbound standalone sweep stays unbound."""
    run_id = env.get("LIFE_MANAGER_RUN_ID")
    occurrence_id = env.get("LIFE_MANAGER_OCCURRENCE_ID")
    try:
        sha = json.loads((release_root / "RELEASE.json").read_text())["sha"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if (not isinstance(run_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", run_id)
            or not isinstance(occurrence_id, str)
            or not occurrence_id.startswith("life-manager-disk-cleanup:")
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,255}", occurrence_id)
            or not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{40}", sha)):
        return None
    return {"owner_id": "life-manager-disk-cleanup", "run_id": run_id,
            "occurrence_id": occurrence_id, "release_sha": sha}


def host_cleanup_ok(returncode: int, result: object) -> bool:
    if not isinstance(result, dict):
        return False
    stop = result.get("disk_writers_stop")
    stop_status = stop.get("status") if isinstance(stop, dict) else None
    return (
        returncode == 0
        and result.get("errors") == 0
        and result.get("protected_deletions") == 0
        and _host_cleanup_capacity_status(result) != "unknown"
        and stop_status in {"absent", "cleared"}
    )


def host_cleanup_readback(returncode: int, stdout: str, *,
                          binding: dict | None = None) -> tuple[bool, dict]:
    """Parse the host governor's final JSON without collapsing missing output to ``{}``."""
    if not isinstance(stdout, str) or not stdout.strip():
        return False, {
            "error": "host_cleanup_result_missing",
            "returncode": returncode,
        }
    try:
        result = json.loads(stdout.splitlines()[-1])
    except (TypeError, ValueError, json.JSONDecodeError):
        return False, {
            "error": "host_cleanup_result_invalid",
            "returncode": returncode,
        }
    if not isinstance(result, dict):
        return False, {
            "error": "host_cleanup_result_invalid",
            "returncode": returncode,
        }
    if binding is not None and result.get("identity") != binding:
        return False, {"error": "host_cleanup_identity_mismatch",
                       "execution_ok": False, "capacity_recovered": None,
                       "capacity_recovery": {"status": "unknown",
                           "recovery_floor_bytes": HOST_CLEANUP_RECOVERY_FLOOR_BYTES}}
    result["capacity_recovery"] = {
        "status": _host_cleanup_capacity_status(result),
        "recovery_floor_bytes": HOST_CLEANUP_RECOVERY_FLOOR_BYTES,
    }
    ok = host_cleanup_ok(returncode, result)
    result["execution_ok"] = ok
    status = result["capacity_recovery"]["status"]
    result["capacity_recovered"] = None if status == "unknown" else status == "met"
    return ok, result


def loaded_release_roots(agents_dir: Path, releases_root: Path) -> set[Path]:
    protected = set()
    base = releases_root.resolve()
    for plist_path in agents_dir.glob("*.plist"):
        try:
            with plist_path.open("rb") as handle:
                plist = plistlib.load(handle)
        except Exception:
            continue
        if not isinstance(plist, dict):
            continue
        program_arguments = plist.get("ProgramArguments")
        if not isinstance(program_arguments, list):
            continue
        for value in map(str, program_arguments):
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
    source_result = reclaim_unreferenced_source(releases, current, agents, keep)
    result["source_reclaim"] = source_result
    result["reclaimed_bytes"] += source_result.get("reclaimed_bytes", 0)
    result["errors"] += source_result.get("errors", 0)
    return result


@contextmanager
def _source_reclaim_lock(current: Path, deadline: float):
    from runtime.loop.lm_loop import _apply_lock
    with ExitStack() as locks:
        while True:
            if time.monotonic() >= deadline:
                raise RuntimeError("reclaim lifecycle lock deadline exceeded")
            try:
                locks.enter_context(_apply_lock(current, current.parent / ".admission-protocol.lock"))
                locks.enter_context(_apply_lock(current, None))
                break
            except RuntimeError:
                locks.close()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise
                time.sleep(min(.05, remaining))
        yield


def reclaim_unreferenced_source(releases: Path, current: Path, agents: Path, keep: int) -> dict:
    """Retain stores while retiring one closed main code snapshot per occurrence."""
    result = {"removed_files": 0, "reclaimed_bytes": 0, "protected_deletions": 0,
              "errors": 0, "status": "preserved"}
    source_repo = Path(os.environ.get("LIFE_MANAGER_SOURCE_REPO", "~/Projects/life-manager-main")).expanduser()
    deadline = time.monotonic() + 15
    def git(*args):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(args, 0)
        return subprocess.run(["git", "-C", str(source_repo), *args], check=True,
                              capture_output=True, text=True, timeout=min(3, remaining)).stdout.strip()
    def references(owned_fds=()):
        held = loaded_release_roots(agents, releases) | open_release_roots(releases)
        held.add(current.resolve(strict=True))
        protected_file = Path(os.environ.get(
            "LIFE_MANAGER_PROTECTED_RELEASES", "~/.local/state/life-manager/protected-releases.json")).expanduser()
        if protected_file.exists():
            values = json.loads(protected_file.read_text())
            if not isinstance(values, list):
                raise ValueError("protected release inventory is invalid")
            held.update(Path(v).expanduser().resolve() for v in values if isinstance(v, str))
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired("lsof", 0)
        opened = subprocess.run(["lsof", "-nP", "-Fpnf"], check=True,
                                capture_output=True, text=True, timeout=min(4, remaining))
        if opened.stderr:
            raise OSError("release FD inventory has coverage gaps")
        base = releases.resolve()
        release_prefix = str(base) + os.sep
        pid = descriptor = None
        for line in opened.stdout.splitlines():
            if line.startswith("p"):
                pid, descriptor = line[1:], None
                continue
            if line.startswith("f"):
                descriptor = line[1:]
                continue
            if not line.startswith("n/"):
                continue
            if (pid == str(os.getpid()) and descriptor is not None
                    and descriptor.isdecimal() and int(descriptor) in owned_fds):
                continue
            if not line[1:].startswith(release_prefix):
                continue
            try:
                parts = Path(line[1:]).relative_to(base).parts
                if parts:
                    held.add(base / parts[0])
            except ValueError:
                pass
        return held
    try:
        # This same lock excludes both per-label apply and current activation.
        with _source_reclaim_lock(current, deadline):
            cached_main = git("rev-parse", "refs/remotes/origin/main")
            official = git("ls-remote", "origin", "refs/heads/main").split()
            if not official or official[0] != cached_main:
                return {**result, "status": "source_main_stale"}
            common = Path(git("rev-parse", "--git-common-dir"))
            if not common.is_absolute():
                common = source_repo / common
            leases = []
            for p in (common / "worktree-leases").glob("*.json"):
                if p.is_symlink() or p.stat().st_uid != os.getuid() or p.stat().st_size > 65536:
                    raise ValueError("release lease inventory is unknown")
                leases.append(json.dumps(json.loads(p.read_text())))
            held = references()
            candidates = []
            rollback = []
            for path in releases.iterdir():
                if (not RELEASE_NAME.fullmatch(path.name) or not path.is_dir() or path.is_symlink()
                        or path.resolve() in held):
                    continue
                retired = release_is_reclaimed(path)
                descriptor = path / ("RECLAIMED-RELEASE.json" if retired else "RELEASE.json")
                if not descriptor.is_file() or descriptor.is_symlink():
                    continue
                manifest = json.loads(descriptor.read_text())
                sha = manifest.get("sha")
                if not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{40}", sha):
                    continue
                if any(str(path.resolve()) in text or sha in text for text in leases):
                    continue
                if not retired:
                    rollback.append((path.stat().st_mtime, path))
                if retired or _release_immutable_store_probe(path, deadline=deadline) == "protected_descendant":
                    candidates.append((path.stat().st_mtime, path, sha))
            keep_roots = {p for _, p in sorted(rollback, reverse=True)[:max(1, keep)]}
            counts = {}
            for _, _, sha in candidates:
                counts[sha] = counts.get(sha, 0) + 1
            ordered = sorted(candidates, key=lambda item: (
                counts[item[2]] == 1 or release_is_reclaimed(item[1]),
                -item[0] if counts[item[2]] > 1 and not release_is_reclaimed(item[1]) else item[0]))
            for _, path, sha in ordered:
                if time.monotonic() >= deadline or path in keep_roots:
                    continue
                if subprocess.run(["git", "-C", str(source_repo), "merge-base", "--is-ancestor", sha, cached_main],
                                  capture_output=True, timeout=min(2, max(.01, deadline-time.monotonic()))).returncode:
                    continue
                result = reclaim_release_source(path, source_repo,
                    can_reclaim=lambda owned: path.resolve() not in references(owned), deadline=deadline)
                result["release_root"] = str(path)
                result["release_sha"] = sha
                if release_is_reclaimed(path):
                    # Retired snapshot metadata rotates the next bounded pass.
                    os.utime(path, None, follow_symlinks=False)
                return result
    except RuntimeError:
        result["status"] = "lifecycle_lock_busy"
    except (OSError, ValueError, subprocess.SubprocessError):
        result["status"] = "reference_or_source_unavailable"
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
        host_ok, host_result = host_cleanup_readback(
            host_process.returncode, host_process.stdout,
            binding=cleanup_run_binding(dict(os.environ), ROOT),
        )
        if (host_process.returncode == 75
                and host_result.get("reason") == "cleanup_lock_busy"
                and host_result.get("status") == "deferred"
                and host_result.get("effect") == 0
                and host_result.get("readback") == 0):
            # Host temp/worktree sweeping has a separate lock from release GC.
            try:
                gc_result = release_gc(releases, current, agents,
                    keep=int(os.environ.get("LIFE_MANAGER_RELEASE_KEEP", "1")))
            except (OSError, ValueError) as error:
                gc_result = {"errors": 1, "error": "release_cleanup_invocation_failed",
                             "error_class": type(error).__name__}
            print(json.dumps({**gc_result, **host_result,
                "errors": gc_result["errors"], "host_cleanup": host_result},
                sort_keys=True, separators=(",", ":")))
            return 75 if gc_result["errors"] == 0 else 1
    except subprocess.TimeoutExpired:
        host_ok, host_result = False, {"error": "host_cleanup_timeout"}
    except OSError as error:
        host_ok, host_result = False, {"error": "host_cleanup_invocation_failed",
                                       "error_class": type(error).__name__}
        if isinstance(error.errno, int):
            host_result["errno"] = error.errno
    try:
        result = release_gc(releases, current, agents,
                            keep=int(os.environ.get("LIFE_MANAGER_RELEASE_KEEP", "1")))
    except (OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True)); return 1
    snapshot_started_ns = time.time_ns()
    scratch_result = scratch_gc(
        installed_state_roots(agents), snapshot_started_ns=snapshot_started_ns,
        starts=process_starts(),
        no_effect_loop_ids=no_effect_loop_ids(ROOT / "config/loop-registry.json"))
    result.update({"ok": result["errors"] == 0 and host_ok and scratch_result["errors"] == 0,
                   "host_cleanup": host_result,
                   "scratch_cleanup": scratch_result,
                   "idle_reconcile": [],
                   "shared_cache_candidates": 0, "orphan_candidates": 0})
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
