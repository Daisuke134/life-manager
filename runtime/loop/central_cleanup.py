#!/usr/bin/env python3
"""Central owner for shared immutable Life Manager release garbage collection."""

from __future__ import annotations

import asyncio
import itertools
import json
import math
import os
import pwd
import plistlib
import re
import shlex
import stat
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from xml.parsers.expat import ExpatError

from runtime.loop import host_cache_cleanup

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RECONCILE_CALL_TAIL_BYTES = 4 * 1024 * 1024
SCRATCH_GC_CANDIDATE_BUDGET = 6000
SCRATCH_GC_TIME_BUDGET_SECONDS = 60
# The 60-second budget applies to candidate evaluation. Preflight has separate
# size caps; the largest observed host has 105 roots, 76,979 candidates total,
# and 11,090 candidates in one root. Oversized inventories defer before deletion.
SCRATCH_GC_ROOT_LIMIT = 128
SCRATCH_GC_DIRECTORY_ENTRY_LIMIT = 20_000
SCRATCH_GC_ROOT_CANDIDATE_LIMIT = 20_000
SCRATCH_GC_TOTAL_CANDIDATE_LIMIT = 100_000
SCRATCH_GC_EVENT_LOG_MAX_BYTES = 20 * 1024 * 1024
SCRATCH_GC_EVENT_LINE_MAX_BYTES = 1024 * 1024
SCRATCH_GC_OWNER_MAX_BYTES = 64 * 1024
_EVENT_LOOP_ID_FIELD = re.compile(rb'"loop_id"\s*:\s*("(?:\\.|[^"\\])*")')

from runtime.loop.loop_cleanup import (
    gc_releases, remove_owned_tree, reclaim_release_source, release_is_reclaimed,
    RELEASE_NAME, _release_immutable_store_probe,
)
from runtime.host import resource_admission
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
        events_path: Path, loop_ids: set[str], *,
        candidate_keys: set[tuple[str, str]] | None = None,
        ) -> tuple[dict[tuple[str, str], tuple[str | None, str | None, str | None,
                                             str | None, str | None, str | None]],
                   str | None]:
    """Read bounded effect metadata; return a reason when coverage is incomplete."""
    observed: dict[tuple[str, str], set[tuple[str | None, str | None, str | None]]] = {}
    latest_effect: dict[tuple[str, str], tuple[str | None, str | None, str | None]] = {}
    descriptor = -1
    try:
        descriptor = os.open(
            events_path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            return {}, "event_log_untrusted"
        if info.st_size > SCRATCH_GC_EVENT_LOG_MAX_BYTES:
            return {}, "event_file_budget"
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            total_bytes = 0
            while True:
                line = handle.readline(SCRATCH_GC_EVENT_LINE_MAX_BYTES + 1)
                if not line:
                    break
                total_bytes += len(line)
                if len(line) > SCRATCH_GC_EVENT_LINE_MAX_BYTES:
                    return {}, "event_line_budget"
                if total_bytes > SCRATCH_GC_EVENT_LOG_MAX_BYTES:
                    return {}, "event_file_budget"
                if not line.strip():
                    continue
                loop_matches = []
                for match in _EVENT_LOOP_ID_FIELD.finditer(line):
                    try:
                        value = json.loads(match.group(1))
                    except (UnicodeError, json.JSONDecodeError):
                        return {}, "event_log_invalid"
                    if isinstance(value, str):
                        loop_matches.append(value)
                if not loop_matches:
                    # Valid legacy records without loop_id are irrelevant; malformed
                    # records without a parseable owner key make coverage unknown.
                    try:
                        event = json.loads(line)
                    except (UnicodeError, json.JSONDecodeError):
                        return {}, "event_log_invalid"
                    if isinstance(event, dict) and not isinstance(event.get("loop_id"), str):
                        continue
                    return {}, "event_log_invalid"
                if not any(loop_id in loop_ids for loop_id in loop_matches):
                    continue
                try:
                    event = json.loads(line)
                except (UnicodeError, json.JSONDecodeError):
                    return {}, "event_log_invalid"
                if not isinstance(event, dict):
                    return {}, "event_log_invalid"
                loop_id, run_id, effect_class, occurrence_id, release_sha = (
                    event.get("loop_id"), event.get("run_id"), event.get("effect_class"),
                    event.get("occurrence_id"), event.get("release_sha"))
                if not isinstance(loop_id, str) or loop_id not in loop_ids:
                    continue
                if not isinstance(run_id, str):
                    return {}, "event_log_invalid"
                key = (loop_id, run_id)
                if candidate_keys is not None and key not in candidate_keys:
                    continue
                values = observed.setdefault(key, set())
                values.add((
                    effect_class if isinstance(effect_class, str) else None,
                    occurrence_id if isinstance(occurrence_id, str) else None,
                    release_sha if isinstance(release_sha, str) else None,
                ))
                # Two distinct rows are enough to make a field ambiguous; keeping
                # more would grow memory with event history without changing the
                # fail-closed result.
                if len(values) > 2:
                    values.pop()
                latest_effect[key] = (
                    event.get("effect_status") if isinstance(event.get("effect_status"), str) else None,
                    event.get("provider_receipt_id") if isinstance(event.get("provider_receipt_id"), str) else None,
                    event.get("official_readback_ref") if isinstance(event.get("official_readback_ref"), str) else None,
                )
    except FileNotFoundError:
        return {}, None
    except OSError:
        return {}, "event_log_unavailable"
    finally:
        if descriptor >= 0:
            os.close(descriptor)
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
    return result, None


def _scratch_gc_directory_names(
        descriptor: int,
        ) -> tuple[list[str], str | None, int]:
    """Return a bounded, sorted directory inventory or a fail-closed reason."""
    names = []
    try:
        with os.scandir(descriptor) as entries:
            for entry in entries:
                names.append(entry.name)
                if len(names) > SCRATCH_GC_DIRECTORY_ENTRY_LIMIT:
                    return [], "directory_entry_budget", len(names)
    except OSError:
        raise
    names.sort()
    return names, None, len(names)


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


def _scratch_gc_read_cursor(path: Path | None, root_keys: set[str]):
    if path is None:
        return None
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_nlink != 1 or info.st_size > 4096
                or stat.S_IMODE(info.st_mode) != 0o600):
            return None
        payload = os.read(descriptor, 4097)
        if len(payload) > 4096:
            return None
        value = json.loads(payload)
        if not isinstance(value, dict) or not value:
            return None
        root, loop, run = value.get("root"), value.get("loop"), value.get("run")
        if (not isinstance(root, str) or root not in root_keys
                or any(not isinstance(name, str) or not name or name in {".", ".."}
                       or "/" in name for name in (loop, run))):
            return None
        return root, loop, run
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _scratch_gc_after(items: list[str], anchor: str) -> list[str]:
    """Rotate a sorted candidate list to the first item after its prior cursor."""
    index = next((index for index, item in enumerate(items) if item > anchor), None)
    if index is None:
        return items
    return items[index:] + items[:index]


def _scratch_gc_write_cursor(path: Path | None, cursor) -> None:
    if path is None:
        return
    from runtime.loop.lm_loop import _atomic_private_json
    value = ({"root": cursor[0], "loop": cursor[1], "run": cursor[2]}
             if cursor is not None else {})
    _atomic_private_json(path, value)


def scratch_gc(roots: set[Path], *, snapshot_started_ns: int | None = None,
               starts: dict[int, str] | None = None,
               no_effect_loop_ids: set[str] | frozenset[str] = frozenset(),
               reconciled_occurrences: set[tuple[str, str, str]] | frozenset[tuple[str, str, str]] = frozenset(),
               cursor_path: Path | None = None,
               candidate_budget: int | None = None,
               time_budget_seconds: float | None = None,
               ) -> dict[str, int | bool | str]:
    """Delete stale scratch with bounded preflight and candidate evaluation."""
    if ((candidate_budget is not None and
         (type(candidate_budget) is not int or candidate_budget <= 0))
            or (time_budget_seconds is not None
                and (not isinstance(time_budget_seconds, (int, float))
                     or not math.isfinite(time_budget_seconds) or time_budget_seconds <= 0))
            or ((candidate_budget is not None or time_budget_seconds is not None)
                and cursor_path is None)):
        raise ValueError("bounded scratch GC requires positive budgets and a cursor path")
    started_ns = time.time_ns() if snapshot_started_ns is None else snapshot_started_ns
    scan_deadline = None
    identities = process_starts() if starts is None else starts
    result: dict[str, int | bool | str] = {
        "evaluated": 0, "removed": 0, "preserved": 0, "errors": 0,
        "scanned": 0, "preprocessed_entries": 0, "deferred": False,
        "blocking_defer": False,
        "owner_metadata_invalid": 0,
        "contents_reclaimed": 0,
        "identity_snapshot_available": identities is not None,
    }
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    root_map = {str(root.resolve()): root for root in roots}
    root_keys = sorted(root_map)
    if len(root_keys) > SCRATCH_GC_ROOT_LIMIT:
        result["deferred"] = True
        result["blocking_defer"] = True
        result["budget_reason"] = "root_budget"
        return result
    cursor = _scratch_gc_read_cursor(cursor_path, set(root_keys))
    inventories: dict[str, tuple[list[str], dict[str, list[str]]]] = {}
    candidates: list[tuple[str, str, str]] = []
    last_cursor = None
    stop_reason = None

    # Inventory candidates before deleting anything, then apply one cursor to
    # the complete ordered set so nested loop/run boundaries cannot starve.
    for root_key in root_keys:
        root = root_map[root_key]
        root_fd = scratch_fd = -1
        try:
            root_fd = os.open(root_key, flags)
            scratch_fd = os.open("loop-tmp", flags, dir_fd=root_fd)
            loop_names, inventory_reason, entry_count = _scratch_gc_directory_names(
                scratch_fd)
            result["preprocessed_entries"] += entry_count
        except FileNotFoundError:
            continue
        except OSError:
            result["errors"] += 1
            continue
        finally:
            if scratch_fd >= 0:
                os.close(scratch_fd)
            if root_fd >= 0:
                os.close(root_fd)
        if inventory_reason is not None:
            stop_reason = inventory_reason
            break

        run_names_by_loop: dict[str, list[str]] = {}
        root_candidate_count = 0
        for loop_name in loop_names:
            root_fd = scratch_fd = loop_fd = -1
            try:
                root_fd = os.open(root_key, flags)
                scratch_fd = os.open("loop-tmp", flags, dir_fd=root_fd)
                loop_fd = os.open(loop_name, flags, dir_fd=scratch_fd)
                run_names, inventory_reason, entry_count = _scratch_gc_directory_names(
                    loop_fd)
                result["preprocessed_entries"] += entry_count
            except OSError:
                continue
            finally:
                if loop_fd >= 0:
                    os.close(loop_fd)
                if scratch_fd >= 0:
                    os.close(scratch_fd)
                if root_fd >= 0:
                    os.close(root_fd)
            if inventory_reason is not None:
                stop_reason = inventory_reason
                break
            root_candidate_count += len(run_names)
            if root_candidate_count > SCRATCH_GC_ROOT_CANDIDATE_LIMIT:
                stop_reason = "root_candidate_budget"
                break
            run_names_by_loop[loop_name] = run_names

        if stop_reason is not None:
            break
        if len(candidates) + root_candidate_count > SCRATCH_GC_TOTAL_CANDIDATE_LIMIT:
            stop_reason = "total_candidate_budget"
            break
        inventories[root_key] = (loop_names, run_names_by_loop)
        candidates.extend(
            (root_key, loop_name, run_name)
            for loop_name, run_names in run_names_by_loop.items()
            for run_name in run_names
        )

    if stop_reason is None and candidates:
        candidates.sort()
        if cursor is not None:
            start_index = next(
                (index for index, candidate in enumerate(candidates)
                 if candidate > cursor),
                0,
            )
            candidates = candidates[start_index:] + candidates[:start_index]

        cursor_metadata = None
        cursor_metadata_loaded = False
        current_root_key = None
        current_root_fd = current_scratch_fd = current_loop_fd = -1
        current_loop_name = None
        event_metadata = {}

        try:
            groups = itertools.groupby(
                candidates, key=lambda candidate: (candidate[0], candidate[1]))
            for (root_key, loop_name), candidate_group in groups:
                if root_key != current_root_key:
                    for descriptor in (current_loop_fd, current_scratch_fd, current_root_fd):
                        if descriptor >= 0:
                            os.close(descriptor)
                    current_root_fd = current_scratch_fd = current_loop_fd = -1
                    current_root_key = None
                    current_loop_name = None
                    root = root_map[root_key]
                    try:
                        current_root_fd = os.open(root_key, flags)
                        current_scratch_fd = os.open(
                            "loop-tmp", flags, dir_fd=current_root_fd)
                    except FileNotFoundError:
                        for descriptor in (current_scratch_fd, current_root_fd):
                            if descriptor >= 0:
                                os.close(descriptor)
                        current_root_fd = current_scratch_fd = -1
                        continue
                    except OSError:
                        result["errors"] += 1
                        for descriptor in (current_scratch_fd, current_root_fd):
                            if descriptor >= 0:
                                os.close(descriptor)
                        current_root_fd = current_scratch_fd = -1
                        continue
                    current_root_key = root_key
                    loop_names, run_names_by_loop = inventories[root_key]
                    if (cursor is not None and root_key == cursor[0]
                            and cursor_metadata_loaded):
                        event_metadata = cursor_metadata
                    else:
                        candidate_keys = {
                            (candidate_loop, run_name)
                            for candidate_loop, run_names in run_names_by_loop.items()
                            for run_name in run_names
                        }
                        event_metadata, metadata_reason = recorded_run_metadata(
                            root / "events.jsonl", set(loop_names),
                            candidate_keys=candidate_keys)
                        if root_key == (cursor[0] if cursor is not None else None):
                            cursor_metadata = event_metadata
                            cursor_metadata_loaded = True
                        if metadata_reason is not None:
                            if metadata_reason not in {
                                "time_budget", "event_file_budget", "event_line_budget"
                            }:
                                result["errors"] += 1
                            stop_reason = metadata_reason
                            break

                if loop_name != current_loop_name:
                    if current_loop_fd >= 0:
                        os.close(current_loop_fd)
                    current_loop_fd = -1
                    current_loop_name = loop_name
                    try:
                        current_loop_fd = os.open(
                            loop_name, flags, dir_fd=current_scratch_fd)
                    except OSError:
                        continue

                for candidate_root, candidate_loop, run_name in candidate_group:
                    if current_loop_fd < 0:
                        continue
                    if (candidate_budget is not None
                            and result["scanned"] >= candidate_budget):
                        stop_reason = "candidate_budget"
                        break
                    if scan_deadline is None and time_budget_seconds is not None:
                        scan_deadline = time.monotonic() + time_budget_seconds
                    if scan_deadline is not None and time.monotonic() >= scan_deadline:
                        stop_reason = "time_budget"
                        break

                    result["scanned"] += 1
                    last_cursor = (candidate_root, candidate_loop, run_name)
                    run_fd = owner_fd = -1
                    try:
                        run_fd = os.open(run_name, flags, dir_fd=current_loop_fd)
                        owner_fd = os.open(
                            ".owner.json", os.O_RDONLY | os.O_NONBLOCK | nofollow,
                            dir_fd=run_fd)
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
                    if _diagnostic_relay_live(
                            run_fd, identities, loop_name, run_name):
                        os.close(owner_fd)
                        os.close(run_fd)
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
                        if (not stat.S_ISREG(owner_stat.st_mode)
                                or owner_stat.st_size > SCRATCH_GC_OWNER_MAX_BYTES):
                            raise ValueError("owner metadata exceeds bounded size")
                        owner_bytes = os.read(owner_fd, SCRATCH_GC_OWNER_MAX_BYTES + 1)
                        if len(owner_bytes) > SCRATCH_GC_OWNER_MAX_BYTES:
                            raise ValueError("owner metadata exceeds bounded size")
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
                            metadata if metadata is not None else
                            (None, None, None, None, None, None)
                        )
                        verified_close = (
                            isinstance(occurrence_id, str)
                            and isinstance(release_sha, str)
                            and (loop_name, occurrence_id, release_sha)
                            in reconciled_occurrences
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
                        removal = remove_owned_tree(current_loop_fd, run_fd, run_name)
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

                if stop_reason is not None:
                    break
        finally:
            for descriptor in (current_loop_fd, current_scratch_fd, current_root_fd):
                if descriptor >= 0:
                    os.close(descriptor)
    if stop_reason is not None:
        result["deferred"] = True
        result["blocking_defer"] = stop_reason not in {"candidate_budget", "time_budget"}
        result["budget_reason"] = stop_reason
        last_cursor = last_cursor or cursor
    try:
        _scratch_gc_write_cursor(cursor_path, last_cursor if stop_reason is not None else None)
    except (OSError, RuntimeError, ValueError):
        result["errors"] += 1
        result["deferred"] = True
        result["blocking_defer"] = True
        result["budget_reason"] = "cursor_write_failed"
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


def default_launch_agents_dir() -> Path:
    """The real user's LaunchAgents, never $HOME's: agent runners give children a private HOME."""
    configured = os.environ.get("LIFE_MANAGER_LAUNCH_AGENTS_DIR")
    if configured:
        return Path(configured).expanduser()
    return Path(pwd.getpwuid(os.getuid()).pw_dir) / "Library" / "LaunchAgents"


def loaded_release_roots(agents_dir: Path, releases_root: Path) -> set[Path]:
    """Releases launchd may start. Raises OSError rather than return a partial inventory.

    An empty answer from a missing, empty or unreadable directory once let keep=1 delete
    every release 116 labels still pointed at (2026-10-24).
    """
    protected = set()
    base = releases_root.resolve()
    if not agents_dir.is_dir():
        raise OSError(f"launchd agents directory is missing: {agents_dir}")
    plist_paths = list(agents_dir.glob("*.plist"))
    if not plist_paths:
        raise OSError(f"launchd agents directory has no plists: {agents_dir}")
    for plist_path in plist_paths:
        try:
            with plist_path.open("rb") as handle:
                plist = plistlib.load(handle)
        except Exception as error:
            try:
                raw = plist_path.read_bytes()
            except OSError:
                raw = None
            if raw is None or str(base).encode() in raw or b"loops/releases" in raw:
                raise OSError(f"unreadable launchd plist: {plist_path.name}") from error
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


def open_release_roots(releases_root: Path, timeout: float = 15) -> set[Path]:
    """Return release roots named by a running process command."""
    completed = subprocess.run(
        ["ps", "-axo", "command="],
        capture_output=True, text=True, timeout=timeout,
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


def _open_reference_paths(roots, timeout: float, owned_fds=(), *, uid=None) -> set[Path]:
    command = ["/usr/sbin/lsof", "-nP"]
    if uid is not None:
        command += ["-a", "-u", str(uid)]
    opened = subprocess.run(command + ["-Fpnf"], check=True, capture_output=True,
                            text=True, timeout=timeout)
    if opened.stderr:
        raise OSError("FD inventory has coverage gaps")
    prefixes = tuple(str(path) + os.sep for root in roots
                     for path in (root.expanduser(), root.resolve()))
    paths = set()
    pid = descriptor = None
    for line in opened.stdout.splitlines():
        if line.startswith("p"):
            pid, descriptor = line[1:], None
        elif line.startswith("f"):
            descriptor = line[1:]
        elif line.startswith("n/") and line[1:].startswith(prefixes):
            if (pid == str(os.getpid()) and descriptor is not None
                    and descriptor.isdecimal() and int(descriptor) in owned_fds):
                continue
            paths.add(Path(line[1:]))
    return paths


def _current_release(current: Path, releases: Path) -> Path | None:
    try:
        info = current.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISLNK(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError("invalid current selector")
    target = current.resolve(strict=True)
    if (len(target.relative_to(releases.resolve()).parts) != 1
            or not target.is_dir() or target.stat().st_uid != os.getuid()):
        raise ValueError("invalid current release")
    return target


@contextmanager
def _release_cut_lock(current: Path):
    """Borrow only our cutter parent's directory lock; never reap another owner."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent = os.open(current.parent, flags)
    descriptor = -1
    owned = False
    try:
        if os.fstat(parent).st_uid != os.getuid():
            raise RuntimeError("release root owner mismatch")
        try:
            os.mkdir(".release-cut.lock", 0o700, dir_fd=parent)
            owned = True
        except FileExistsError:
            pass
        before = os.stat(".release-cut.lock", dir_fd=parent, follow_symlinks=False)
        descriptor = os.open(".release-cut.lock", flags, dir_fd=parent)
        info = os.fstat(descriptor)
        if (info.st_uid != os.getuid() or (info.st_dev, info.st_ino) !=
                (before.st_dev, before.st_ino)):
            raise RuntimeError("release cut lock identity mismatch")
        pid_fd = os.open("pid", (os.O_WRONLY | os.O_CREAT | os.O_EXCL if owned else os.O_RDONLY)
                         | os.O_NOFOLLOW, 0o600, dir_fd=descriptor)
        try:
            pid_info = os.fstat(pid_fd)
            if (not stat.S_ISREG(pid_info.st_mode) or pid_info.st_uid != os.getuid()
                    or pid_info.st_nlink != 1):
                raise RuntimeError("release cut lock owner is unknown")
            if owned:
                os.write(pid_fd, f"{os.getpid()}\n".encode())
            elif (pid_info.st_size > 32
                  or os.read(pid_fd, 33).strip() != str(os.getppid()).encode()):
                raise RuntimeError("another process owns the release cut lock")
            now = os.stat("pid", dir_fd=descriptor, follow_symlinks=False)
            if (now.st_dev, now.st_ino) != (pid_info.st_dev, pid_info.st_ino):
                raise RuntimeError("release cut lock pid identity changed")
        finally:
            os.close(pid_fd)
        now = os.stat(".release-cut.lock", dir_fd=parent, follow_symlinks=False)
        if (now.st_dev, now.st_ino) != (info.st_dev, info.st_ino):
            raise RuntimeError("release cut lock identity changed")
        yield
    finally:
        try:
            if owned and descriptor >= 0:
                now = os.stat(".release-cut.lock", dir_fd=parent, follow_symlinks=False)
                info = os.fstat(descriptor)
                if (now.st_dev, now.st_ino) == (info.st_dev, info.st_ino):
                    try:
                        os.unlink("pid", dir_fd=descriptor)
                    except FileNotFoundError:
                        pass
                    os.rmdir(".release-cut.lock", dir_fd=parent)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            os.close(parent)


def _bundle_references(releases: Path, current: Path, agents: Path, bundles: Path,
                       deadline: float, owned_fds=()) -> tuple[set[Path], list[str]]:
    if time.monotonic() >= deadline:
        raise subprocess.TimeoutExpired("bundle references", 0)
    for root in (releases, bundles, agents):
        try:
            info = root.lstat()
        except FileNotFoundError:
            if root == bundles:
                continue
            raise
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError("reference root is untrusted")
    _current_release(current, releases)
    values = []
    protected_file = Path(os.environ.get(
        "LIFE_MANAGER_PROTECTED_RELEASES", "~/.local/state/life-manager/protected-releases.json")).expanduser()
    try:
        info = protected_file.lstat()
    except FileNotFoundError:
        info = None
    if info is not None:
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError("protected release inventory is untrusted")
        pins = json.loads(protected_file.read_text())
        if not isinstance(pins, list) or any(not isinstance(value, str) for value in pins):
            raise ValueError("protected release inventory is invalid")
        values.extend(str(Path(value).expanduser().resolve()) for value in pins)
    plist_paths = [path for path in agents.iterdir() if path.suffix == ".plist"]
    if not plist_paths:
        raise OSError("launchd inventory has no plists")
    for path in plist_paths:
        if time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired("plist references", 0)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError("plist inventory is untrusted")
        try:
            with path.open("rb") as handle:
                plist = plistlib.load(handle)
        except (ValueError, plistlib.InvalidFileException, ExpatError):
            native = subprocess.run(["/usr/bin/plutil", "-convert", "json", "-o", "-", str(path)],
                check=True, capture_output=True, text=True, timeout=min(3, max(.01, deadline-time.monotonic())))
            if native.stderr:
                raise OSError("native plist inventory has coverage gaps")
            plist = json.loads(native.stdout)
        if not isinstance(plist, dict):
            raise ValueError("plist inventory is invalid")
        pending = [plist]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                pending.extend(value.values())
            elif isinstance(value, list):
                pending.extend(value)
            elif isinstance(value, str):
                values.append(os.path.expanduser(value))
    process = subprocess.run(["ps", "-axo", "command="], check=True, capture_output=True,
        text=True, timeout=min(5, max(.01, deadline-time.monotonic())))
    if process.stderr:
        raise OSError("process inventory has coverage gaps")
    path_values = set()
    for value in values:
        if "\n" not in value:
            path_values.add(value)
        path_values.update(value.split())
    for line in process.stdout.splitlines():
        if time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired("process references", 0)
        try:
            path_values.update(shlex.split(line))
        except ValueError:
            # ps renders argv, so a literal apostrophe need not be shell syntax.
            path_values.update(line.split())
        # ps may omit quotes; each whitespace boundary can end a spaced path.
        for match in re.finditer(r"(?:^|[\s='\":])(/)", line):
            suffix = line[match.start(1):match.start(1) + 4097]
            for boundary in re.finditer(r"\s|$", suffix):
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired("process path boundaries", 0)
                path_values.add(suffix[:boundary.start()])
    resolved_paths = set()
    for word in path_values:
        if time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired("reference path resolution", 0)
        for path in word.strip("'\"").split(os.pathsep):
            if not path.startswith("/"):
                path = path.split("=", 1)[-1]
            if path.startswith("/") and len(os.fsencode(path)) <= 4096 and path not in resolved_paths:
                resolved_paths.add(path)
                values.append(str(Path(path).resolve()))
    values.append(process.stdout)
    values.extend(map(str, _open_reference_paths((releases, bundles),
        min(15, max(.01, deadline-time.monotonic())), owned_fds, uid=os.getuid())))
    protected = {path.resolve() for path in releases.iterdir()
                 if path.is_dir() and any(str(path) in value or str(path.resolve()) in value for value in values)}
    pending = [releases]
    while pending:
        if time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired("release dependency links", 0)
        # DirEntry retains the directory's type information without lstat on every leaf.
        with os.scandir(pending.pop()) as entries:
            for entry in entries:
                if time.monotonic() >= deadline:
                    raise subprocess.TimeoutExpired("release dependency links", 0)
                if entry.is_symlink():
                    values.append(str(Path(entry.path).resolve()))
                elif entry.is_dir(follow_symlinks=False):
                    pending.append(entry.path)
    if time.monotonic() >= deadline:
        raise subprocess.TimeoutExpired("release dependency links", 0)
    return protected, values


def _scan_bundle(descriptor: int, root: Path, deadline: float, *, changed=None, parts=()) -> int:
    info = os.fstat(descriptor)
    if info.st_uid != os.getuid() or info.st_mode & 0o222:
        raise ValueError("bundle is not owned and readonly")
    size = 0
    for name in os.listdir(descriptor):
        if time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired("bundle tree", 0)
        item = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if (item.st_uid != os.getuid() or name in {".lm-protected", ".terminal-unrecorded"}
                or (name == "memory" and stat.S_ISDIR(item.st_mode))
                or (name in {"memory", "state"} and stat.S_ISLNK(item.st_mode))
                or (parts and parts[-1] == "state" and name.endswith(".jsonl"))):
            raise ValueError("protected or foreign bundle entry")
        if stat.S_ISDIR(item.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            try:
                actual = os.fstat(child)
                if (actual.st_dev, actual.st_ino) != (item.st_dev, item.st_ino):
                    raise ValueError("bundle directory identity changed")
                size += _scan_bundle(child, root, deadline, changed=changed, parts=(*parts, name))
            finally:
                os.close(child)
        elif stat.S_ISLNK(item.st_mode):
            if not (root.joinpath(*parts, name).resolve(strict=True)).is_relative_to(root):
                raise ValueError("bundle link leaves its root")
        elif not stat.S_ISREG(item.st_mode) or item.st_mode & 0o222:
            raise ValueError("bundle entry is not an immutable file")
        else:
            size += item.st_size
    if changed is not None:
        changed.append((parts, info.st_dev, info.st_ino, stat.S_IMODE(info.st_mode)))
        os.fchmod(descriptor, stat.S_IMODE(info.st_mode) | 0o200)
    return size


def _restore_bundle_directories(descriptor: int, changed):
    for parts, device, inode, mode in reversed(changed):
        opened = os.dup(descriptor)
        try:
            for name in parts:
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=opened)
                os.close(opened)
                opened = child
            info = os.fstat(opened)
            if info.st_uid == os.getuid() and (info.st_dev, info.st_ino) == (device, inode):
                os.fchmod(opened, mode)
        except FileNotFoundError:
            pass
        finally:
            os.close(opened)


def _gc_dependency_bundles(releases, current, agents, bundles, deadline) -> dict:
    result = {"evaluated": 0, "removed": 0, "preserved": 0, "reclaimed_bytes": 0, "errors": 0}
    if not bundles.exists() and not bundles.is_symlink():
        return result
    parent = os.open(bundles, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if os.fstat(parent).st_uid != os.getuid():
            raise ValueError("bundle root owner mismatch")
        _held, references = _bundle_references(releases, current, agents, bundles, deadline, (parent,))
        for name in sorted(os.listdir(parent)):
            if not re.fullmatch(r"npm-[a-f0-9]{64}", name):
                continue
            result["evaluated"] += 1
            root = bundles.resolve() / name
            if any(str(root) in value or str(bundles / name) in value for value in references):
                result["preserved"] += 1
                continue
            opened = -1
            changed = []
            try:
                before = os.stat(name, dir_fd=parent, follow_symlinks=False)
                opened = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                info = os.fstat(opened)
                if (info.st_uid != os.getuid() or info.st_mode & 0o222
                        or (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino)):
                    raise ValueError("bundle identity changed")
                for required in ("package.json", "package-lock.json", ".complete"):
                    if not stat.S_ISREG(os.stat(required, dir_fd=opened, follow_symlinks=False).st_mode):
                        raise ValueError("incomplete bundle")
                modules = os.open("node_modules", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=opened)
                try:
                    if not stat.S_ISREG(os.stat(".package-lock.json", dir_fd=modules, follow_symlinks=False).st_mode):
                        raise ValueError("incomplete bundle lock")
                finally:
                    os.close(modules)
                marker_before = os.stat(".complete", dir_fd=opened, follow_symlinks=False)
                marker = os.open(".complete", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=opened)
                try:
                    marker_info = os.fstat(marker)
                    if (not stat.S_ISREG(marker_info.st_mode) or marker_info.st_uid != os.getuid()
                            or (marker_info.st_dev, marker_info.st_ino) != (marker_before.st_dev, marker_before.st_ino)
                            or marker_info.st_size > 65 or marker_info.st_mode & 0o222
                            or os.read(marker, 66) not in {name[4:].encode(), (name[4:] + "\n").encode()}):
                        raise ValueError("bundle completion key mismatch")
                finally:
                    os.close(marker)
                size = _scan_bundle(opened, root, deadline)
                _scan_bundle(opened, root, deadline, changed=changed)
                _held, references = _bundle_references(releases, current, agents, bundles,
                    deadline, (parent, opened))
                if any(str(root) in value or str(bundles / name) in value for value in references):
                    raise ValueError("bundle remains referenced")
                now = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if (now.st_dev, now.st_ino) != (info.st_dev, info.st_ino):
                    raise ValueError("bundle identity changed")
                removed = remove_owned_tree(parent, opened, name)
                if removed:
                    result["removed" if removed is True else "contents_reclaimed"] = (
                        result.get("removed" if removed is True else "contents_reclaimed", 0) + 1)
                    result["reclaimed_bytes"] += size
                else:
                    result["errors"] += 1
                    result["preserved"] += 1
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                result["preserved"] += 1
                result["errors"] += not isinstance(error, ValueError)
                result["diagnostic"] = {"error_class": type(error).__name__}
            finally:
                if opened >= 0:
                    _restore_bundle_directories(opened, changed)
                    os.close(opened)
    finally:
        os.close(parent)
    return result


def release_gc(releases: Path, current: Path, agents: Path, keep: int) -> dict:
    """Collect releases and their unreferenced immutable dependency bundles."""
    result = {"evaluated_releases": 0, "removed_releases": 0, "reclaimed_bytes": 0,
              "preserved_releases": 0, "protected_deletions": 0, "errors": 0,
              "deferred": 0}
    bundles = releases.parent / "dependency-bundles"
    # Reconcile held the admission lock for 90s; keep this wait separate from scans.
    lock_deadline = time.monotonic() + 120
    try:
        empty = True
        for root in (releases, bundles):
            try:
                info = root.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
                raise ValueError("release inventory root is untrusted")
            empty &= not any(root.iterdir())
        if empty:
            return {**result, "protected_release_count": 0, "source_reclaim": {"status": "not_needed"},
                    "dependency_bundles": {"evaluated": 0, "removed": 0, "preserved": 0,
                                           "reclaimed_bytes": 0, "errors": 0}}
        with _source_reclaim_lock(current, lock_deadline), _release_cut_lock(current):
            # Lock contention must not consume the bounded reference-census window.
            census_deadline = time.monotonic() + 30
            protected, _references = _bundle_references(
                releases, current, agents, bundles, census_deadline)
            if any(releases.iterdir()):
                protected |= loaded_release_roots(agents, releases) | open_release_roots(releases)
            pins = releases / ".pins"
            if pins.is_dir():
                protected |= {(releases / pin.name).resolve() for pin in pins.iterdir()}
            result = gc_releases(releases, current, keep=keep, protected=protected)
            result.setdefault("deferred", 0)
            result["protected_release_count"] = len(protected)
            # Bundle GC repeats the full host-reference census after release GC;
            # give that independently bounded phase its own scan window.
            bundle_deadline = time.monotonic() + 30
            bundle_result = _gc_dependency_bundles(
                releases, current, agents, bundles, bundle_deadline)
            result["dependency_bundles"] = bundle_result
            result["reclaimed_bytes"] += bundle_result["reclaimed_bytes"]
            result["errors"] += bundle_result["errors"]
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        timed_out = isinstance(error, subprocess.TimeoutExpired)
        diagnostic = {"phase": "release_reference_check"}
        if timed_out:
            timeout_phases = {
                "bundle references": "bundle_reference_deadline",
                "plist references": "plist_reference_deadline",
                "process references": "process_reference_deadline",
                "process path boundaries": "process_path_deadline",
                "reference path resolution": "reference_path_resolution",
                "release dependency links": "release_dependency_deadline",
                "bundle tree": "bundle_tree_deadline",
                "plutil": "plist_conversion_probe",
                "ps": "process_inventory_probe",
                "lsof": "open_file_reference_probe",
            }
            command = error.cmd
            if isinstance(command, str):
                diagnostic["phase"] = timeout_phases.get(command, "reference_subprocess")
            elif isinstance(command, (list, tuple)) and command:
                executable = Path(os.fsdecode(command[0])).name
                diagnostic["phase"] = timeout_phases.get(executable, "reference_subprocess")
            if (type(error.timeout) is int and error.timeout >= 0) or (
                    type(error.timeout) is float and math.isfinite(error.timeout) and error.timeout >= 0):
                diagnostic["timeout_seconds"] = error.timeout
            diagnostic["retryable"] = True
            diagnostic["next_action"] = "retry_next_scheduled_run"
        elif isinstance(error, RuntimeError):
            diagnostic["phase"] = "lock_check"
        deferred = timed_out and diagnostic["phase"] == "reference_path_resolution"
        if deferred:
            result["deferred"] += 1
        else:
            result["errors"] += 1
        result["dependency_bundles"] = {"status": "deferred" if deferred
                                        else "reference_or_lock_unavailable",
                                        "error_class": type(error).__name__,
                                        "diagnostic": diagnostic}
    source_result = {"status": "not_needed"}
    if keep > 0:
        try:
            if (_current_release(current, releases) is not None
                    and result["errors"] == 0 and result["deferred"] == 0):
                source_result = reclaim_unreferenced_source(releases, current, agents, keep)
            elif result["deferred"]:
                source_result = {"status": "deferred"}
        except (OSError, ValueError):
            source_result = {"status": "invalid_current"}
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
    """Retain stores while retiring one closed, officially reachable source snapshot."""
    result = {"removed_files": 0, "reclaimed_bytes": 0, "protected_deletions": 0,
              "errors": 0, "status": "preserved"}
    source_repo = Path(os.environ.get("LIFE_MANAGER_SOURCE_REPO", "~/Projects/life-manager-main")).expanduser()
    deadline = time.monotonic() + 15
    phase = "lifecycle_lock"
    def git(*args):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(args, 0)
        return subprocess.run(["git", "-C", str(source_repo), *args], check=True,
                              capture_output=True, text=True, timeout=min(3, remaining)).stdout.strip()
    def references(owned_fds=()):
        nonlocal phase
        previous_phase, phase = phase, "loaded_release_references"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired("ps", 0)
        held = loaded_release_roots(agents, releases) | open_release_roots(
            releases, min(5, remaining))
        phase = "current_release_reference"
        held.add(current.resolve(strict=True))
        phase = "protected_release_references"
        protected_file = Path(os.environ.get(
            "LIFE_MANAGER_PROTECTED_RELEASES", "~/.local/state/life-manager/protected-releases.json")).expanduser()
        if protected_file.exists():
            values = json.loads(protected_file.read_text())
            if not isinstance(values, list):
                raise ValueError("protected release inventory is invalid")
            held.update(Path(v).expanduser().resolve() for v in values if isinstance(v, str))
        remaining = deadline - time.monotonic()
        phase = "open_file_references"
        if remaining <= 0:
            raise subprocess.TimeoutExpired("lsof", 0)
        base = releases.resolve()
        for path in _open_reference_paths((releases,), min(4, remaining), owned_fds):
            try:
                parts = Path(path).relative_to(base).parts
                if parts:
                    held.add(base / parts[0])
            except ValueError:
                pass
        phase = previous_phase
        return held
    try:
        # This same lock excludes both per-label apply and current activation.
        with _source_reclaim_lock(current, deadline):
            phase = "remote_refs"
            official_heads = {}
            for line in git("ls-remote", "--heads", "origin").splitlines():
                fields = line.split()
                if len(fields) == 2 and fields[1].startswith("refs/heads/"):
                    official_heads[fields[1]] = fields[0]
            local_refs = {}
            for line in git("for-each-ref", "--format=%(refname) %(objectname)",
                            "refs/remotes/origin").splitlines():
                fields = line.split()
                if len(fields) == 2:
                    local_refs[fields[0]] = fields[1]
            fresh_remote_refs = {}
            for remote_ref, remote_sha in official_heads.items():
                branch = remote_ref.removeprefix("refs/heads/")
                local_ref = f"refs/remotes/origin/{branch}"
                if local_refs.get(local_ref) == remote_sha:
                    fresh_remote_refs[local_ref] = remote_sha
            if not fresh_remote_refs:
                return {**result, "status": "source_remote_refs_stale"}

            def official_source_ref(sha: str) -> str | None:
                containing = git("for-each-ref", f"--contains={sha}",
                                 "--format=%(refname)", "refs/remotes/origin").splitlines()
                witnessed = next((fresh_remote_refs[ref] for ref in containing
                                  if ref in fresh_remote_refs), None)
                if witnessed:
                    return witnessed
                # A census can outlive a branch name; keep the verified commit witness.
                for witness in dict.fromkeys(fresh_remote_refs.values()):
                    try:
                        git("merge-base", "--is-ancestor", sha, witness)
                    except subprocess.CalledProcessError as error:
                        if error.returncode == 1:
                            continue
                        raise
                    return witness
                return None

            def existing_source_pin(sha: str) -> str | None:
                pin = f"refs/life-manager/retired-release-source/{sha}"
                try:
                    value = git("rev-parse", "--verify", f"{pin}^{{commit}}")
                except subprocess.CalledProcessError:
                    return None
                return value if value == sha else "mismatch"

            def ensure_source_pin(sha: str, verified_ref: str) -> str | None:
                pin = f"refs/life-manager/retired-release-source/{sha}"
                existing = existing_source_pin(sha)
                if existing == "mismatch":
                    return None
                if existing == sha:
                    return sha
                try:
                    git("merge-base", "--is-ancestor", sha, verified_ref)
                    git("update-ref", pin, sha, "0" * 40)
                except subprocess.CalledProcessError:
                    # Another cooperating cleanup may have created the same pin.
                    existing = existing_source_pin(sha)
                    return sha if existing == sha else None
                return sha if existing_source_pin(sha) == sha else None

            phase = "lease_inventory"
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
            phase = "release_inventory"
            for path in releases.iterdir():
                if not RELEASE_NAME.fullmatch(path.name) or not path.is_dir() or path.is_symlink():
                    continue
                # Referenced roots cannot be reclaimed and need no expensive store scan.
                if path.resolve() in held:
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
                    source_ref = existing_source_pin(sha) or official_source_ref(sha)
                    if source_ref:
                        candidates.append((path.stat().st_mtime, path, sha, source_ref))
            candidates = [item for item in candidates if item[1].resolve() not in held]
            rollback = [item for item in rollback if item[1].resolve() not in held]
            keep_roots = {p for _, p in sorted(rollback, reverse=True)[:max(1, keep)]}
            counts = {}
            for _, _, sha, _ in candidates:
                counts[sha] = counts.get(sha, 0) + 1
            ordered = sorted(candidates, key=lambda item: (
                counts[item[2]] == 1 or release_is_reclaimed(item[1]),
                -item[0] if counts[item[2]] > 1 and not release_is_reclaimed(item[1]) else item[0]))
            for _, path, sha, source_ref in ordered:
                if time.monotonic() >= deadline or path in keep_roots:
                    continue
                pinned_source = ensure_source_pin(sha, source_ref)
                if pinned_source is None:
                    continue
                open_reference_snapshot = None

                def can_reclaim(owned_fds):
                    nonlocal open_reference_snapshot
                    if not owned_fds:
                        return path.resolve() not in held
                    if open_reference_snapshot is None:
                        # Refresh once after the release descriptors are open, then reuse
                        # that lock-scoped inventory for this source-file batch. Re-running
                        # full-system lsof for every leaf exhausted the 15s cleanup budget.
                        open_reference_snapshot = references(owned_fds)
                    return path.resolve() not in open_reference_snapshot

                phase = "source_reclaim"
                result = reclaim_release_source(path, source_repo,
                    can_reclaim=can_reclaim,
                    source_ref=pinned_source, deadline=deadline)
                result["release_root"] = str(path)
                result["release_sha"] = sha
                if release_is_reclaimed(path):
                    # Retired snapshot metadata rotates the next bounded pass.
                    os.utime(path, None, follow_symlinks=False)
                return result
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        result["status"] = ("lifecycle_lock_busy" if isinstance(error, RuntimeError)
                            else "reference_or_source_unavailable")
        # Record only typed metadata: exception text and subprocess output may contain secrets.
        result["diagnostic"] = {
            "phase": phase, "error_class": type(error).__name__,
            "errno": getattr(error, "errno", None),
            "exit_code": getattr(error, "returncode", None),
        }
    return result


def git_duplicate_cleanup(source_repo: Path) -> dict:
    result = {"errors": 0, "prune_packable_before": None, "prune_packable_after": None,
              "loose_bytes_before": None, "loose_bytes_after": None}
    if not (source_repo / ".git").exists():
        return {**result, "status": "not_applicable"}
    try:
        if source_repo.stat().st_uid != os.getuid():
            raise ValueError("source repository owner mismatch")
        def git(*args):
            command = ["git", "-C", str(source_repo), *args]
            environment = {**os.environ, "LC_ALL": "C"}
            if args[:2] == ("maintenance", "run"):
                from runtime.loop.lm_loop_run import _run_entrypoint
                with tempfile.TemporaryFile(mode="w+") as stdout, \
                     tempfile.TemporaryFile(mode="w+") as stderr:
                    code = _run_entrypoint(command, env=environment, timeout_seconds=15,
                        termination_grace_seconds=15, stdout_capture_fd=stdout.fileno(),
                        stderr_capture_fd=stderr.fileno())
                    stdout.seek(0)
                    stderr.seek(0)
                    completed = subprocess.CompletedProcess(command, code, stdout.read(), stderr.read())
                if code == 124:
                    raise subprocess.TimeoutExpired(command, 15,
                        output=completed.stdout, stderr=completed.stderr)
                completed.check_returncode()
                return completed
            return subprocess.run(command,
                capture_output=True, text=True, timeout=15, check=True,
                env=environment)
        def count():
            lines = git("count-objects", "-v").stdout.splitlines()
            return {name: int(next(line.partition(":")[2] for line in lines
                                  if line.startswith(f"{name}:")))
                    for name in ("prune-packable", "size")}
        before = count()
        result["prune_packable_before"] = before["prune-packable"]
        result["loose_bytes_before"] = before["size"] * 1024
        if before["prune-packable"]:
            git("prune-packed")
        # Byte pressure bypasses only the count threshold; Git keeps its batch and lock.
        auto = ("--auto",) if before["size"] < 128 * 1024 else ()
        lock = Path(git("rev-parse", "--git-path", "objects/maintenance.lock").stdout.strip())
        if not lock.is_absolute():
            lock = source_repo / lock
        maintenance = (None if lock.exists() else
                       git("maintenance", "run", "--no-quiet", *auto, "--task=loose-objects"))
        if (maintenance is None or lock.exists()
                or "skipping maintenance" in maintenance.stderr):
            result.update(status="deferred", error_class="NativeMaintenanceSkipped",
                          retryable=True, next_action="retry_next_natural_pass",
                          native_diagnostic=(maintenance.stderr[-2048:].strip()
                                             if maintenance is not None and maintenance.stderr
                                             else "maintenance lock observed; ownership unknown"))
            return result
        # Newly packed loose objects can be reclaimed in this same sweep.
        after = count()
        if after["prune-packable"]:
            git("prune-packed")
            after = count()
        result["prune_packable_after"] = after["prune-packable"]
        result["loose_bytes_after"] = after["size"] * 1024
        result["status"] = "pass"
    except subprocess.TimeoutExpired:
        result.update(status="deferred", error_class="TimeoutExpired",
                      retryable=True, next_action="retry_next_natural_pass")
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
    agents = default_launch_agents_dir()
    if sys.argv[1:] == ["--release-gc-only"]:
        try:
            result = release_gc(releases, current, agents,
                                keep=int(os.environ.get("LIFE_MANAGER_RELEASE_KEEP", "1")))
        except (OSError, ValueError) as error:
            print(json.dumps({"ok": False, "error": str(error)}, sort_keys=True)); return 1
        result["ok"] = result["errors"] == 0 and result.get("deferred", 0) == 0
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["ok"] else 1
    git_result = git_duplicate_cleanup(Path(os.environ.get(
        "LIFE_MANAGER_SOURCE_REPO", "~/Projects/life-manager-main")).expanduser())
    binding = cleanup_run_binding(dict(os.environ), ROOT)
    codex_result = (codex_history_cleanup(home) if binding and
        binding.get("owner_id") == "life-manager-disk-cleanup" else {"status": "unbound_owner"})
    try:
        queue_result = {"cancelled": resource_admission.cancel_stale_queued_occurrences()}
    except Exception as error:  # admission maintenance never fails the cleanup run
        queue_result = {"error_class": type(error).__name__}
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
        reconciled_occurrences=reconciled_occurrences,
        cursor_path=home / ".local/state/life-manager/central-cleanup-scratch-cursor.json",
        candidate_budget=SCRATCH_GC_CANDIDATE_BUDGET,
        time_budget_seconds=SCRATCH_GC_TIME_BUDGET_SECONDS)
    # AI Monk landing worktrees and oversized logs ate 10 GiB in two hours (2026-10-25/26);
    # neither owns a loop, so the five-minute cleanup shares their node_modules, drops idle
    # .next/cache and rotates the allowlisted logs on every pass.
    landing_result = host_cache_cleanup.landing_cache_cleanup(home, root=ROOT)
    log_result = host_cache_cleanup.rotate_large_logs(home)
    result["errors"] += landing_result["errors"] + log_result["errors"]
    result.update({"ok": result["errors"] == 0 and result.get("deferred", 0) == 0
                   and host_ok and scratch_result["errors"] == 0
                   and not scratch_result.get("blocking_defer", False),
                   "git_cleanup": git_result,
                   "codex_storage": codex_result,
                   "admission_queue": queue_result,
                   "host_cleanup": host_result,
                   "scratch_cleanup": scratch_result,
                   "landing_cache": landing_result,
                   "log_rotation": log_result,
                   "run_binding": binding,
                   "idle_reconcile": [],
                   "shared_cache_candidates": landing_result["examined"], "orphan_candidates": 0})
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
