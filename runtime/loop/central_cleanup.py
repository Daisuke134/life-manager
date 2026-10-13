#!/usr/bin/env python3
"""Central owner for shared immutable Life Manager release garbage collection."""

from __future__ import annotations

import asyncio
import json
import os
import plistlib
import re
import stat
import shutil
import subprocess
import sys
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from xml.parsers.expat import ExpatError

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RECONCILE_CALL_TAIL_BYTES = 4 * 1024 * 1024

from runtime.loop.loop_cleanup import (
    gc_releases, remove_owned_tree, reclaim_release_source, release_is_reclaimed,
    RELEASE_NAME, _release_immutable_store_probe,
)
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


def recorded_run_metadata(
        events_path: Path, loop_ids: set[str]
        ) -> dict[tuple[str, str], tuple[str | None, str | None, str | None,
                                        str | None, str | None, str | None]]:
    observed: dict[tuple[str, str], set[tuple[str | None, str | None, str | None]]] = {}
    latest_effect: dict[tuple[str, str], tuple[str | None, str | None, str | None]] = {}
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
                loop_id, run_id, effect_class, occurrence_id, release_sha = (
                    event.get("loop_id"), event.get("run_id"), event.get("effect_class"),
                    event.get("occurrence_id"), event.get("release_sha"))
                if not isinstance(loop_id, str) or loop_id not in loop_ids:
                    continue
                if not isinstance(run_id, str):
                    return {}
                key = (loop_id, run_id)
                observed.setdefault(key, set()).add((
                    effect_class if isinstance(effect_class, str) else None,
                    occurrence_id if isinstance(occurrence_id, str) else None,
                    release_sha if isinstance(release_sha, str) else None,
                ))
                latest_effect[key] = (
                    event.get("effect_status") if isinstance(event.get("effect_status"), str) else None,
                    event.get("provider_receipt_id") if isinstance(event.get("provider_receipt_id"), str) else None,
                    event.get("official_readback_ref") if isinstance(event.get("official_readback_ref"), str) else None,
                )
    except (OSError, UnicodeError):
        return {}
    result: dict[tuple[str, str], tuple[str | None, str | None, str | None,
                                        str | None, str | None, str | None]] = {}
    for key, values in observed.items():
        classes, occurrences, releases = ({value[index] for value in values}
                                           for index in range(3))
        result[key] = (
            next(iter(classes)) if len(classes) == 1 and None not in classes else None,
            next(iter(occurrences)) if len(occurrences) == 1 and None not in occurrences else None,
            next(iter(releases)) if len(releases) == 1 and None not in releases else None,
            *latest_effect.get(key, (None, None, None)),
        )
    return result


def closed_reconcile_occurrences(path: Path, *, max_bytes: int = RECONCILE_CALL_TAIL_BYTES
                                 ) -> set[tuple[str, str, str]]:
    """Read exact structured closures bound to the target runtime release."""
    try:
        size = path.stat().st_size
        offset = max(0, size - max_bytes)
        with path.open("rb") as handle:
            handle.seek(offset)
            payload = handle.read(max_bytes)
    except OSError:
        return set()
    lines = payload.splitlines()
    if offset and lines:
        lines = lines[1:]  # first line may begin before the bounded tail
    closed: set[tuple[str, str, str]] = set()
    for line in lines:
        try:
            record = json.loads(line)
        except (UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(record, dict) or record.get("closed") is not True \
                or record.get("exit_code") != 0:
            continue
        owner_id, occurrence_id, release_sha = (
            record.get("owner_id"), record.get("occurrence_id"), record.get("release_sha"))
        proof = record.get("closure_proof")
        if not (isinstance(owner_id, str) and owner_id
                and isinstance(occurrence_id, str) and occurrence_id
                and isinstance(release_sha, str)
                and re.fullmatch(r"[a-f0-9]{40}", release_sha)
                and isinstance(proof, dict)):
            continue
        receipt_ref = proof.get("receipt_ref")
        if (proof.get("proof_type") == "effect_reconcile_closure.v1"
                and proof.get("owner_id") == owner_id
                and proof.get("occurrence_id") == occurrence_id
                and proof.get("release_sha") == release_sha
                and proof.get("verified") is True
                and isinstance(receipt_ref, str) and receipt_ref.strip()):
            closed.add((owner_id, occurrence_id, release_sha))
    return closed


def _browser_profiles_live(run_path: Path) -> bool | None:
    """Return whether a process still names a run-owned ephemeral Chromium profile."""
    try:
        profiles = []
        for path in run_path.iterdir():
            if not path.name.startswith("agent-browser-profile-"):
                continue
            if path.is_symlink() or not path.is_dir() or path.stat().st_uid != os.getuid():
                return None
            profiles.append(str(path.resolve()))
    except OSError:
        return None
    if not profiles:
        return False
    try:
        result = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True,
                                text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or parts[0] == str(os.getpid()):
            continue
        if any(profile in parts[1] for profile in profiles):
            return True
    return False


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
               no_effect_loop_ids: set[str] | frozenset[str] = frozenset(),
               reconciled_occurrences: set[tuple[str, str, str]] | frozenset[tuple[str, str, str]] = frozenset(),
               ) -> dict[str, int | bool]:
    """Delete only crashed per-run scratch whose process identity is provably stale."""
    started_ns = time.time_ns() if snapshot_started_ns is None else snapshot_started_ns
    identities = process_starts() if starts is None else starts
    result: dict[str, int | bool] = {
        "evaluated": 0, "removed": 0, "preserved": 0, "errors": 0,
        "owner_metadata_invalid": 0,
        "contents_reclaimed": 0,
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
        event_metadata = recorded_run_metadata(root / "events.jsonl", set(loop_names))
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
                        except (FileNotFoundError, NotADirectoryError):
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
                            event_key = (loop_name, run_name)
                            metadata = event_metadata.get(event_key)
                            (recorded_effect_class, occurrence_id, release_sha, effect_status,
                             provider_receipt_id, official_readback_ref) = (
                                metadata if metadata is not None else (None, None, None, None, None, None)
                            )
                            verified_close = (
                                isinstance(occurrence_id, str)
                                and isinstance(release_sha, str)
                                and (loop_name, occurrence_id, release_sha) in reconciled_occurrences
                            )
                            no_effect_without_reconcile = (
                                recorded_effect_class == "none"
                                and loop_name in no_effect_loop_ids
                            )
                            if has_terminal_unrecorded:
                                if (event_key not in event_metadata
                                        or recorded_effect_class is None
                                        or (not no_effect_without_reconcile and not verified_close)
                                        or (owner_effect_class is not None
                                            and owner_effect_class != recorded_effect_class)):
                                    result["preserved"] += 1
                                    continue
                            if metadata is not None:
                                effect_is_closed = (
                                    verified_close
                                    or no_effect_without_reconcile
                                    or (recorded_effect_class not in {None, "none"}
                                        and effect_status == "not_applicable"
                                        and not provider_receipt_id and not official_readback_ref)
                                    or (recorded_effect_class not in {None, "none"}
                                        and effect_status in {"verified", "reconciled"}
                                        and provider_receipt_id and official_readback_ref)
                                )
                                if not effect_is_closed:
                                    result["preserved"] += 1
                                    continue
                            if identities is None or owner_stat.st_mtime_ns >= started_ns:
                                result["preserved"] += 1
                                continue
                            actual = identities.get(pid)
                            if actual is not None and actual == expected:
                                result["preserved"] += 1
                                continue
                            browser_live = _browser_profiles_live(
                                root / "loop-tmp" / loop_name / run_name)
                            if browser_live is not False:
                                result["preserved"] += 1
                                continue
                            removal = remove_owned_tree(loop_fd, run_fd, run_name)
                            if removal is True:
                                result["removed"] += 1
                            elif removal == "contents_reclaimed":
                                result["contents_reclaimed"] += 1
                                result["preserved"] += 1
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
        capture_output=True, text=True, timeout=5,
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


def git_duplicate_cleanup(source_repo: Path) -> dict:
    result = {"errors": 0, "prune_packable_before": None, "prune_packable_after": None}
    if not (source_repo / ".git").exists():
        return {**result, "status": "not_applicable"}
    try:
        if source_repo.stat().st_uid != os.getuid():
            raise ValueError("source repository owner mismatch")
        def git(*args):
            return subprocess.run(["git", "-C", str(source_repo), *args],
                capture_output=True, text=True, timeout=15, check=True).stdout
        def count():
            return int(next(line.partition(":")[2] for line in git("count-objects", "-v").splitlines()
                            if line.startswith("prune-packable:")))
        result["prune_packable_before"] = count()
        # Git owns the auto threshold, bounded loose-object batches and maintenance lock.
        # This never runs full gc or expires unreachable history.
        git("maintenance", "run", "--auto", "--task=loose-objects")
        # Newly packed loose objects can be reclaimed in this same sweep.
        if count():
            git("prune-packed")
            result["prune_packable_after"] = count()
        else:
            result["prune_packable_after"] = 0
        result["status"] = "pass"
    except (OSError, ValueError, StopIteration, subprocess.SubprocessError) as error:
        result.update(errors=1, status="failed", error_class=type(error).__name__)
    return result



def codex_history_cleanup(home: Path, *, connect=None) -> dict:
    """Request vendor-owned lossless maintenance; never rewrite a rollout ourselves."""
    root = home / ".codex-acct2"
    result = {"status": "deferred", "completion": "unknown"}
    if not root.exists():
        return {"status": "not_applicable"}
    try:
        if root.is_symlink() or root.stat().st_uid != os.getuid():
            return {**result, "reason": "untrusted_home"}
        marker = root / ".tmp/rollout-compression.lock"
        if marker.parent.is_symlink() or marker.is_symlink():
            return {**result, "reason": "untrusted_marker"}
        if marker.exists():
            info = marker.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                return {**result, "reason": "untrusted_marker"}
            if time.time() - info.st_mtime < 6 * 3600:
                return {"status": "recent_native_maintenance", "completion": "unknown"}
        sizes = []; cold = 0; deadline = time.monotonic() + 5
        for folder in (root / "sessions", root / "archived_sessions"):
            if not folder.exists():
                continue
            if folder.is_symlink() or folder.stat().st_uid != os.getuid():
                return {**result, "reason": "untrusted_history_root"}
            for path in folder.rglob("*"):
                if time.monotonic() >= deadline:
                    return {**result, "reason": "scan_budget"}
                parts = {part.lower() for part in path.relative_to(folder).parts}
                if (path.is_symlink() or parts.intersection({"memory", ".cloak", ".config", ".codex", ".claude"})
                        or (path.parent.name == "state" and path.suffix == ".jsonl")
                        or path.suffix == ".tmp"
                        or any(token in path.name.lower() for token in ("credential", "wallet", "receipt", "ledger", "effect_unknown"))):
                    return {**result, "reason": "protected_or_unknown_history_entry"}
                info = path.stat()
                if info.st_uid != os.getuid():
                    return {**result, "reason": "history_owner_mismatch"}
                if not stat.S_ISREG(info.st_mode) or path.suffix != ".jsonl":
                    continue
                if info.st_nlink != 1:
                    return {**result, "reason": "history_hardlink"}
                age = time.time() - info.st_mtime
                cold += age >= 7 * 86400
                # Include files that can become cold during the vendor's five-hour bound.
                if age >= 7 * 86400 - 5 * 3600:
                    sizes.append(info.st_size)
        if not cold:
            return {"status": "no_cold_rollouts"}
        required = sum(sorted(sizes, reverse=True)[:2]) * 102 // 100 + 64 * 1024**2
        if shutil.disk_usage(root).free < required:
            return {**result, "reason": "native_staging_capacity", "required_bytes": required}
        socket_path = root / "app-server-control/app-server-control.sock"
        info = socket_path.stat()
        if (not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600):
            return {**result, "reason": "untrusted_control_socket"}

        async def request():
            connector = connect
            if connector is None:
                from websockets.asyncio.client import unix_connect
                connector = unix_connect
            async with connector(str(socket_path), uri="ws://localhost/", open_timeout=5,
                                 max_size=2 * 1024**2) as websocket:
                async def call(identifier, method, params):
                    await websocket.send(json.dumps({"jsonrpc": "2.0", "id": identifier,
                                                     "method": method, "params": params}))
                    while True:
                        response = json.loads(await websocket.recv())
                        if response.get("id") == identifier:
                            if "error" in response or "result" not in response:
                                raise ValueError("native_request_rejected")
                            return response["result"]
                initialized = await call(1, "initialize", {
                    "clientInfo": {"name": "life-manager-storage-maintenance", "version": "1"},
                    "capabilities": {"experimentalApi": True}})
                if (Path(initialized.get("codexHome", "")).resolve() != root.resolve()
                        or re.search(r"/0\.160\.0(?:[ (;]|$)", initialized.get("userAgent", "")) is None):
                    raise ValueError("unsupported_native_identity")
                await websocket.send(json.dumps({"jsonrpc": "2.0", "method": "initialized"}))
                await call(2, "rollout/compress", None)
            return {"status": "requested", "completion": "unknown", "cold_files": cold,
                    "required_bytes": required}
        async def bounded_request():
            return await asyncio.wait_for(request(), timeout=10)
        return asyncio.run(bounded_request())
    except Exception as error:
        # Optional vendor maintenance must not suppress the existing host sweep.
        return {**result, "reason": "native_maintenance_unavailable",
                "error_class": type(error).__name__}


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
    git_result = git_duplicate_cleanup(Path(os.environ.get(
        "LIFE_MANAGER_SOURCE_REPO", "~/Projects/life-manager-main")).expanduser())
    binding = cleanup_run_binding(dict(os.environ), ROOT)
    codex_result = (codex_history_cleanup(home) if binding and
        binding.get("owner_id") == "life-manager-disk-cleanup" else {"status": "unbound_owner"})
    # The 60-second watchdog is the sole HostDiskGovernor owner. This five-minute
    # service performs maintenance and release/scratch GC without contending on
    # the watchdog's host-sweep lock.
    host_ok = True
    host_result = {"status": "delegated", "owner_id": "com.anicca.disk-watchdog"}
    try:
        result = release_gc(releases, current, agents,
                            keep=int(os.environ.get("LIFE_MANAGER_RELEASE_KEEP", "1")))
    except (OSError, ValueError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True)); return 1
    result["errors"] += git_result["errors"]
    snapshot_started_ns = time.time_ns()
    reconciled_occurrences = closed_reconcile_occurrences(
        home / ".local/state/life-manager/lm-fence-reconciler/reconcile-calls.jsonl")
    scratch_result = scratch_gc(
        installed_state_roots(agents), snapshot_started_ns=snapshot_started_ns,
        starts=process_starts(),
        no_effect_loop_ids=no_effect_loop_ids(ROOT / "config/loop-registry.json"),
        reconciled_occurrences=reconciled_occurrences)
    result.update({"ok": result["errors"] == 0 and host_ok and scratch_result["errors"] == 0,
                   "git_cleanup": git_result,
                   "codex_storage": codex_result,
                   "host_cleanup": host_result,
                   "scratch_cleanup": scratch_result,
                   "idle_reconcile": [],
                   "shared_cache_candidates": 0, "orphan_candidates": 0})
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
