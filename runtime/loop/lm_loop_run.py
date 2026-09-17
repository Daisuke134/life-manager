#!/usr/bin/env python3
"""Per-loop cleanup boundary followed by exact immutable entrypoint exec."""

from __future__ import annotations

import json
import hashlib
import os
import plistlib
import re
import signal
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

from runtime.loop.lm_loop import _apply_lock, _label_apply_lock_path, apply_live
from runtime.loop.lm_loop_apply import _loaded_arguments
from runtime.loop.loop_cleanup import remove_owned_tree
from runtime.loop.macos_loop_registry import validate_registry
from runtime.loop.runtime_event import append_runtime_event, build_runtime_event, build_runtime_start_event
from runtime.host.memory_admission import memory_free_percent
from runtime.host.resource_admission import (
    OCCURRENCE_ID_PATTERN,
    cancel_durable as cancel_durable_resource,
    claim_durable as claim_durable_resource,
    clear_no_effect_unknown as clear_no_effect_unknown_resource,
    defer_durable as defer_durable_resource,
    durable_protocol_version,
    enqueue_durable as enqueue_durable_resource,
    heartbeat_durable as heartbeat_durable_resource,
    process_start,
    release as release_resource,
    release_and_reserve as release_and_reserve_resource,
    reserve_available as reserve_available_resource,
    transfer_durable as transfer_durable_resource,
    try_acquire as try_acquire_resource,
)


EXEC_GATE = Path(__file__).resolve().parents[1] / "host/exec_gate.py"
SAFE_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SAFE_RESULT_HINT = re.compile(r"[a-z][a-z0-9_:-]{1,99}\Z")
ADMISSION_CONTROL_RETRY_ATTEMPTS = 3
ADMISSION_CONTROL_RETRY_DELAY_SECONDS = 0.05
HEARTBEAT_INTERVAL_SECONDS = 30.0
PRE_EFFECT_HINT_ENTRYPOINTS = frozenset({
    "skills/earn/crowdworks/scripts/paid-owner",
    "skills/earn/lancers/scripts/paid-owner",
    "skills/earn/mercor/scripts/application-owner",
    "skills/earn/mercor/scripts/paid-owner",
    "skills/earn/mercor/scripts/reply-owner",
    "skills/writer-agent/scripts/article-resume-pending.sh",
})


def build_loop_command(registry: dict, loop_id: str, release_root: Path) -> list[str]:
    """Validate and build argv without doing housekeeping on the wake path."""
    validate_registry(registry)
    entry = registry["loops"].get(loop_id)
    if not isinstance(entry, dict):
        raise ValueError(f"unknown loop id: {loop_id}")
    executable = release_root.resolve() / entry["entrypoint"]
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise ValueError(f"entrypoint missing or not executable: {entry['entrypoint']}")
    command = [str(executable)]
    if entry.get("adapter") == "python":
        command.insert(0, sys.executable)
    command.extend(entry.get("command", []))
    return command


def reset_loop_scratch(state_root: Path, loop_id: str, run_id: str) -> tuple[Path, int, int]:
    """Create private per-run scratch without scanning a previous wake's tree."""
    if (not SAFE_RUN_ID.fullmatch(loop_id) or loop_id in {".", ".."}
            or not SAFE_RUN_ID.fullmatch(run_id) or run_id in {".", ".."}):
        raise ValueError("unsafe run id")
    identity = process_start(os.getpid())
    if identity is None:
        raise RuntimeError("scratch owner identity unavailable")
    state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root = state_root.resolve()
    flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    root_fd = os.open(root, flags)
    loop_tmp_fd = parent_fd = run_fd = -1
    run_created = False
    run_verified = False
    try:
        try:
            os.mkdir("loop-tmp", mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        loop_tmp_fd = os.open("loop-tmp", flags, dir_fd=root_fd)
        try:
            os.mkdir(loop_id, mode=0o700, dir_fd=loop_tmp_fd)
        except FileExistsError:
            pass
        try:
            parent_fd = os.open(loop_id, flags, dir_fd=loop_tmp_fd)
        except OSError as error:
            raise ValueError("unsafe loop scratch root") from error
        os.mkdir(run_id, mode=0o700, dir_fd=parent_fd)
        run_created = True
        created_stat = os.stat(run_id, dir_fd=parent_fd, follow_symlinks=False)
        run_fd = os.open(run_id, flags, dir_fd=parent_fd)
        opened_stat = os.fstat(run_fd)
        if ((created_stat.st_dev, created_stat.st_ino) !=
                (opened_stat.st_dev, opened_stat.st_ino)):
            raise RuntimeError("scratch inode changed during creation")
        run_verified = True
        try:
            marker_fd = os.open(
                ".terminal-unrecorded", os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=run_fd)
            os.close(marker_fd)
            owner_fd = os.open(
                ".owner.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=run_fd)
            with os.fdopen(owner_fd, "w", encoding="utf-8") as handle:
                json.dump({"pid": os.getpid(), "process_start": identity}, handle,
                          sort_keys=True, separators=(",", ":"))
                handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            os.fsync(run_fd)
        except Exception:
            raise
        scratch = root / "loop-tmp" / loop_id / run_id
        return scratch, parent_fd, run_fd
    except Exception:
        if run_created and run_verified and parent_fd >= 0 and run_fd >= 0:
            try:
                remove_owned_tree(parent_fd, run_fd, run_id)
            except OSError:
                pass
        if run_fd >= 0:
            os.close(run_fd)
        if parent_fd >= 0:
            os.close(parent_fd)
        raise
    finally:
        if loop_tmp_fd >= 0:
            os.close(loop_tmp_fd)
        os.close(root_fd)


def unprotect_loop_scratch(run_fd: int) -> None:
    """Allow cleanup only after the terminal receipt has been persisted."""
    os.unlink(".terminal-unrecorded", dir_fd=run_fd)
    os.fsync(run_fd)


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":")); handle.write("\n")
            handle.flush(); os.fsync(handle.fileno())
        os.chmod(name, 0o600); os.replace(name, path)
    finally:
        try: os.unlink(name)
        except FileNotFoundError: pass


def _persist_effect_identity(sidecar: Path, state_root: Path,
                             loop_id: str, run_id: str,
                             claimed_occurrence_id: str | None = None) -> str | None:
    """Move a validated run identity out of scratch before unknown-effect cleanup."""
    if (not SAFE_RUN_ID.fullmatch(loop_id) or not SAFE_RUN_ID.fullmatch(run_id)
            or loop_id in {".", ".."} or run_id in {".", ".."}):
        raise ValueError("unsafe effect identity id")
    expected_occurrence = claimed_occurrence_id or f"{loop_id}:{run_id}"
    if not OCCURRENCE_ID_PATTERN.fullmatch(expected_occurrence):
        raise ValueError("unsafe effect identity occurrence")
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(sidecar, flags)
        try:
            info = os.fstat(descriptor)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or info.st_mode & 0o777 != 0o600):
                return None
            with os.fdopen(descriptor, "rb") as handle:
                descriptor = -1
                data = handle.read(1024 * 1024 + 1)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
    except (FileNotFoundError, OSError):
        return None
    home_prefix = str(Path.home()).encode()
    if not data.strip() or len(data) > 1024 * 1024 or (home_prefix and home_prefix in data):
        return None

    identifier = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,255}$")
    job_identifier = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
    effect_key = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,511}$")
    integration = re.compile(
        r"^integration://postiz/([a-z]+)/([A-Za-z0-9._:-]{1,200})$", re.IGNORECASE,
    )
    account = re.compile(r"^@[A-Za-z0-9._-]{1,127}$")
    hash_value = re.compile(r"^[0-9a-f]{64}$")
    allowed = {
        "schema_version", "kind", "runtime_run_id", "occurrence_id", "loop_id",
        "job_id", "effect_key", "product_id", "format_id", "form", "locale",
        "platform", "creative_id", "slot", "integration_ref", "account_id",
        "video_sha256", "caption_sha256", "media_sha256", "pack_sha256",
        "media_order_sha256",
    }
    for raw in data.splitlines():
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if (not isinstance(value, dict) or value.get("schema_version") != 1
                or value.get("kind") != "life_manager_effect_identity"
                or set(value) - allowed
                or value.get("runtime_run_id") != run_id
                or value.get("occurrence_id") != expected_occurrence
                or value.get("loop_id") != loop_id
                or not job_identifier.fullmatch(str(value.get("job_id", "")))
                or not effect_key.fullmatch(str(value.get("effect_key", "")))
                or not identifier.fullmatch(str(value.get("product_id", "")))
                or not identifier.fullmatch(str(value.get("format_id", "")))
                or not identifier.fullmatch(str(value.get("form", "")))
                or not re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", str(value.get("locale", "")))
                or value.get("platform") not in {"instagram", "tiktok", "youtube"}
                or not identifier.fullmatch(str(value.get("creative_id", "")))
                or not isinstance(value.get("slot"), str) or not value["slot"].strip()
                or not integration.fullmatch(str(value.get("integration_ref", "")))
                or not account.fullmatch(str(value.get("account_id", "")))
                or (value.get("video_sha256") is not None
                    and not hash_value.fullmatch(str(value.get("video_sha256"))))
                or not hash_value.fullmatch(str(value.get("caption_sha256", "")))):
            return None
        if "media_sha256" in value and (
                not isinstance(value["media_sha256"], list)
                or not value["media_sha256"]
                or any(not hash_value.fullmatch(str(item)) for item in value["media_sha256"])):
            return None
        for key in ("pack_sha256", "media_order_sha256"):
            if key in value and not hash_value.fullmatch(str(value[key])):
                return None
        integration_match = integration.fullmatch(str(value["integration_ref"]))
        if integration_match is None or integration_match.group(1).lower() != value["platform"]:
            return None
        video_key = re.fullmatch(
            r"marketing:video:([^:]+):(instagram|tiktok|youtube):([^:]+):([0-9a-f]{64}):([0-9a-f]{64})(?::([0-9a-f]{64}))?",
            str(value["effect_key"]),
        )
        carousel_key = re.fullmatch(
            r"marketing:carousel:([^:]+):([^:]+):([0-9a-f]{64}):([0-9a-f]{64}):([0-9a-f]{64})(?::([0-9a-f]{64}))?",
            str(value["effect_key"]),
        )
        if video_key:
            if (value["product_id"] != video_key.group(1)
                    or value["platform"] != video_key.group(2)
                    or value["creative_id"] != video_key.group(3)
                    or value["video_sha256"] != video_key.group(4)
                    or value["caption_sha256"] != video_key.group(5)
                    or (video_key.group(6) is not None
                        and video_key.group(6) != hashlib.sha256(value["slot"].encode()).hexdigest())):
                return None
        elif carousel_key:
            media_hashes = value.get("media_sha256")
            expected_media_order = (
                hashlib.sha256(json.dumps(
                    media_hashes, ensure_ascii=False, separators=(",", ":"),
                ).encode()).hexdigest()
                if isinstance(media_hashes, list) else None
            )
            if (value["product_id"] != carousel_key.group(1)
                    or value["creative_id"] != carousel_key.group(2)
                    or value.get("video_sha256") is not None
                    or not isinstance(media_hashes, list) or len(media_hashes) != 6
                    or any(not hash_value.fullmatch(str(item)) for item in media_hashes)
                    or value.get("pack_sha256") != carousel_key.group(3)
                    or value.get("media_order_sha256") != carousel_key.group(4)
                    or value.get("media_order_sha256") != expected_media_order
                    or value["caption_sha256"] != carousel_key.group(5)
                    or (carousel_key.group(6) is not None
                        and carousel_key.group(6) != hashlib.sha256(value["slot"].encode()).hexdigest())):
                return None
        else:
            return None

    root_fd = identity_fd = descriptor = -1
    temporary_name = None
    try:
        state_root = state_root.expanduser()
        state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        root_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
        root_fd = os.open(state_root, root_flags)
        root_info = os.fstat(root_fd)
        if (not stat.S_ISDIR(root_info.st_mode) or root_info.st_uid != os.getuid()
                or root_info.st_mode & 0o777 != 0o700):
            return None
        try:
            os.mkdir("effect-identities", mode=0o700, dir_fd=root_fd)
        except FileExistsError:
            pass
        identity_fd = os.open("effect-identities", root_flags, dir_fd=root_fd)
        identity_info = os.fstat(identity_fd)
        if (not stat.S_ISDIR(identity_info.st_mode) or identity_info.st_uid != os.getuid()
                or identity_info.st_mode & 0o777 != 0o700):
            return None
        write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        for attempt in range(8):
            temporary_name = f".{run_id}.{os.getpid()}.{time.time_ns()}.{attempt}.tmp"
            try:
                descriptor = os.open(
                    temporary_name, write_flags, 0o600, dir_fd=identity_fd,
                )
                break
            except FileExistsError:
                continue
        if descriptor < 0:
            return None
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(
            temporary_name, f"{run_id}.jsonl",
            src_dir_fd=identity_fd, dst_dir_fd=identity_fd,
        )
        temporary_name = None
        os.fsync(identity_fd)
        sidecar.unlink()
    except OSError:
        return None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name is not None and identity_fd >= 0:
            try:
                os.unlink(temporary_name, dir_fd=identity_fd)
            except FileNotFoundError:
                pass
        if identity_fd >= 0:
            os.close(identity_fd)
        if root_fd >= 0:
            os.close(root_fd)
    return f"lm-effect://{loop_id}/{run_id}/identity.jsonl"


def _runtime_limit(entry: dict) -> int | None:
    if entry.get("cadence") == {"keep_alive": True}:
        return None
    return entry.get("runtime_timeout_seconds", 3600)


def _resource_class(entry: dict) -> str:
    return entry.get("resource_class") or (
        "agent" if entry["provider_route"] == "shared-agent-runner" else "deterministic")


def _admission_class(entry: dict) -> str:
    """Revenue work owns capacity; every other finite wake borrows idle capacity."""
    return entry.get("admission_class", "borrow")


def _queue_priority(entry: dict) -> str | None:
    """Return an explicitly declared queue priority, if present."""
    value = entry.get("priority")
    return value if isinstance(value, str) and value else None


def _heartbeat_loop(claim: Path, stop: threading.Event) -> None:
    while not stop.wait(HEARTBEAT_INTERVAL_SECONDS):
        if not heartbeat_durable_resource(claim):
            return


def _host_admission_deferred(path: Path, started_ns: int) -> str | None:
    try:
        if path.stat().st_mtime_ns < started_ns:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    if value.get("status") != "deferred" or value.get("effect") != 0:
        return None
    reason = value.get("reason")
    prefix = "host_admission_deferred:"
    return (reason if isinstance(reason, str) and SAFE_RUN_ID.fullmatch(reason)
            and len(prefix) + len(reason) <= 128 else "unknown")


def _proven_pre_effect_failure(path: Path) -> bool:
    try:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o777 != 0o600):
            return False
        return json.loads(path.read_text(encoding="utf-8")) == {
            "status": "pre_effect_failure", "effect": 0}
    except (OSError, ValueError):
        return False


def _terminal_outcome(return_code: int, *, host_deferred: str | None = None
                      ) -> tuple[bool, bool, str | None]:
    if return_code == 0:
        return True, False, None
    if host_deferred and return_code in {75, 124, 137, 143}:
        return False, True, f"host_admission_deferred:{host_deferred}"
    return False, False, f"entrypoint_exit_{return_code}"


def _run_entrypoint(command: list[str], env: dict[str, str] | None = None, *,
                    timeout_seconds: float | None = None,
                    termination_grace_seconds: float = 15,
                    cancelled: Callable[[], bool] = lambda: False,
                    on_started: Callable[[int], None] = lambda _pid: None) -> int:
    watched = (signal.SIGTERM, signal.SIGINT)
    previous = {}
    process = None
    pending = []
    stopping = False

    def forward(signum, _frame):
        nonlocal stopping
        stopping = True
        if process is None:
            pending.append(signum)
        elif process.poll() is None:
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass

    for signum in watched:
        previous[signum] = signal.signal(signum, forward)
    if cancelled() or pending:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        return 75
    read_fd, write_fd = os.pipe()
    try:
        process = subprocess.Popen(
            [sys.executable, str(EXEC_GATE), str(read_fd), *command],
            start_new_session=True, env=env, pass_fds=(read_fd,))
        os.close(read_fd)
        if cancelled() or pending or stopping:
            os.close(write_fd)
            for signum in pending:
                forward(signum, None)
            process.wait()
            return 75
        try:
            on_started(process.pid)
        except BaseException:
            os.close(write_fd)
            process.wait()
            raise
        if cancelled() or pending or stopping:
            os.close(write_fd)
            for signum in pending:
                forward(signum, None)
            process.wait()
            return 75
        try:
            os.write(write_fd, b"G")
        except BrokenPipeError:
            if stopping:
                process.wait()
                return 75
            raise
        os.close(write_fd)
        try:
            return_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            forward(signal.SIGTERM, None)
            try:
                process.wait(timeout=termination_grace_seconds)
            except subprocess.TimeoutExpired:
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait()
            return 124
    finally:
        for descriptor in (read_fd, write_fd):
            try:
                os.close(descriptor)
            except OSError:
                pass
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    return return_code if return_code >= 0 else 128 - return_code


def _dispatch_reserved(loop_ids: list[str], *, current: Path | None = None,
                       agents_dir: Path | None = None) -> list[str]:
    """Kick only validated loaded-idle owners; reservations recover on failure."""
    root = (current or Path("~/loops/current").expanduser()).resolve()
    installed = agents_dir or Path("~/Library/LaunchAgents").expanduser()
    try:
        registry = validate_registry(json.loads(
            (root / "config/loop-registry.json").read_text(encoding="utf-8")))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    safe = root / "bin/launchctl-safe"
    started = []
    pending = list(loop_ids)
    attempted: set[str] = set()

    def cancel(loop_id: str) -> None:
        try:
            cancel_durable_resource(loop_id)
        except (OSError, RuntimeError):
            pass

    def defer(loop_id: str) -> None:
        try:
            if defer_durable_resource(loop_id, cooldown_seconds=60) is True:
                pending.extend(reserve_available_resource())
        except (OSError, RuntimeError):
            pass

    for loop_id in pending:
        if loop_id in attempted:
            continue
        attempted.add(loop_id)
        entry = registry["loops"].get(loop_id)
        if not isinstance(entry, dict) or entry.get("cadence", {}).get("keep_alive"):
            cancel(loop_id)
            continue
        label = entry["label"]
        plist = installed / f"{label}.plist"
        try:
            arguments = plistlib.loads(plist.read_bytes()).get("ProgramArguments")
        except (OSError, ValueError, plistlib.InvalidFileException):
            defer(loop_id)
            continue
        expected = [str(root / "bin/lm-loop-run"), loop_id, str(root)]
        if arguments != expected:
            try:
                applied = apply_live(
                    root, installed, safe, target=loop_id, skip_busy=True,
                    require_current=True,
                    protocol_reader=durable_protocol_version)
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
                defer(loop_id)
                continue
            if not any(result.get("ok") and result.get("loaded_arguments") == expected
                       for result in applied):
                defer(loop_id)
                continue
        service = f"gui/{os.getuid()}/{label}"
        try:
            observed = subprocess.run(
                [str(safe), "print", service], capture_output=True, text=True,
                check=False, timeout=10)
            if observed.returncode != 0 or _loaded_arguments(observed.stdout) != expected:
                defer(loop_id)
                continue
            if (re.search(r"\bstate\s*=\s*running\b", observed.stdout)
                    or re.search(r"\bpid\s*=\s*[1-9][0-9]*\b", observed.stdout)):
                continue
            if not re.search(r"\bstate\s*=\s*(?:not running|waiting)\b", observed.stdout):
                defer(loop_id)
                continue
            kicked = subprocess.run(
                [str(safe), "kickstart", service], capture_output=True, text=True,
                check=False, timeout=10)
            if kicked.returncode != 0:
                continue
            readback = subprocess.run(
                [str(safe), "print", service], capture_output=True, text=True,
                check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if readback.returncode == 0:
            started.append(loop_id)
    return started


def _run_admitted(command: list[str], entry: dict, loop_id: str, env: dict[str, str],
                  receipt: Path, *, occurrence_id: str | None = None,
                  on_claimed: Callable[[str], None] = lambda _value: None) -> int:
    limit = _runtime_limit(entry)
    if loop_id in {"life-manager-release-reconciler", "life-manager-disk-cleanup",
                   "capafy-loop-healthcheck"}:
        if entry.get("effect_class") == "none":
            try:
                clear_no_effect_unknown_resource(loop_id)
            except (OSError, RuntimeError, sqlite3.Error) as error:
                print(f"lm-loop-run: no-effect recovery deferred: {error}", file=sys.stderr)
        _atomic_json(receipt, {"status": "pass", "effect": 0,
                              "reason": "control_plane_exempt"})
        result = _run_entrypoint(command, env=env, timeout_seconds=limit)
        if result == 0 and loop_id != "capafy-loop-healthcheck":
            try:
                if durable_protocol_version() == 2:
                    reserved = reserve_available_resource()
                    if reserved:
                        _dispatch_reserved(reserved)
            except (OSError, RuntimeError, sqlite3.Error) as error:
                print(f"lm-loop-run: safety dispatch deferred: {error}", file=sys.stderr)
        return result
    if limit is None:
        _atomic_json(receipt, {"status": "pass", "effect": 0,
                              "reason": "continuous_owner_exempt"})
        return _run_entrypoint(command, env=env, timeout_seconds=None)
    try:
        minimum_free = int(os.environ.get("LIFE_MANAGER_MIN_MEMORY_FREE_PERCENT", "15"))
    except ValueError:
        return 64
    if not 1 <= minimum_free <= 100:
        return 64
    claim = None
    claim_started_child = False
    heartbeat_stop = threading.Event()
    heartbeat_thread: threading.Thread | None = None
    durable = False
    dispatch_after_release: list[str] = []
    interrupted = False
    return_code: int | None = None
    previous = {}

    def interrupt_wait(_signum, _frame):
        nonlocal interrupted
        interrupted = True

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, interrupt_wait)
        resource_class = _resource_class(entry)
        admission_class = _admission_class(entry)
        queue_priority = _queue_priority(entry)
        try:
            durable = durable_protocol_version() == 2
            enqueue_kwargs = {"admission_class": admission_class}
            if queue_priority is not None:
                enqueue_kwargs["priority"] = queue_priority
            if occurrence_id is not None:
                enqueue_kwargs["occurrence_id"] = occurrence_id
            if entry.get("coalesce_queued_wakes") is True:
                enqueue_kwargs["coalesce_reserved"] = True
            if entry.get("effect_class") == "none":
                enqueue_kwargs["allow_no_effect_recovery"] = True
            ticket, admission_reason = (
                enqueue_durable_resource(
                    resource_class, loop_id, **enqueue_kwargs)
                if durable else (None, "legacy")
            )
        except (OSError, RuntimeError):
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": "resource_admission_unavailable"})
            return 75
        if durable and ticket is None:
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": f"resource_{admission_reason}"})
            return 75
        available = memory_free_percent()
        if interrupted:
            if durable:
                try:
                    defer_durable_resource(loop_id)
                except (OSError, RuntimeError):
                    pass
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": "resource_admission_interrupted"})
            return 75
        if available is None or available < minimum_free:
            if durable:
                try:
                    defer_durable_resource(loop_id)
                except (OSError, RuntimeError):
                    pass
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                         "reason": "memory_headroom_unavailable" if available is None
                         else "memory_headroom_low"})
            return 75
        try:
            claim = None
            admission_reason = None
            claim_kwargs = {"admission_class": admission_class}
            if durable and entry.get("coalesce_queued_wakes") is True and occurrence_id is not None:
                claim_kwargs["coalesced_occurrence_id"] = occurrence_id
            for attempt in range(ADMISSION_CONTROL_RETRY_ATTEMPTS):
                if interrupted:
                    break
                claim, admission_reason = (
                    claim_durable_resource(
                        resource_class, loop_id, **claim_kwargs)
                    if durable else try_acquire_resource(
                        resource_class, loop_id, admission_class=admission_class,
                        retain_ticket=False, required_protocol=1)
                )
                if claim is not None or admission_reason != "control_busy":
                    break
                if attempt + 1 < ADMISSION_CONTROL_RETRY_ATTEMPTS:
                    time.sleep(ADMISSION_CONTROL_RETRY_DELAY_SECONDS * (attempt + 1))
        except (OSError, RuntimeError):
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": "resource_admission_unavailable"})
            return 75
        if claim is None:
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": f"resource_{admission_reason}"})
            if durable and not interrupted:
                _dispatch_reserved(reserve_available_resource())
            return 75
        claimed_occurrence_id = occurrence_id
        if durable and occurrence_id is not None:
            try:
                claimed_occurrence_id = json.loads(claim.read_text(encoding="utf-8")).get(
                    "occurrence_id")
                if (not isinstance(claimed_occurrence_id, str)
                        or not OCCURRENCE_ID_PATTERN.fullmatch(claimed_occurrence_id)
                        or not claimed_occurrence_id.startswith(f"{loop_id}:")):
                    raise ValueError("invalid claimed occurrence")
            except (OSError, ValueError, AttributeError):
                _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                      "reason": "resource_claim_identity_invalid"})
                return 75
            on_claimed(claimed_occurrence_id)
        available = memory_free_percent()
        if interrupted:
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": "resource_admission_interrupted"})
            return 75
        if available is None or available < minimum_free:
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                         "reason": "memory_headroom_unavailable" if available is None
                         else "memory_headroom_low"})
            return 75
        _atomic_json(receipt, {"status": "pass", "effect": 0,
                              "reason": "resource_slot_acquired",
                              "resource_class": resource_class})
        if interrupted:
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": "resource_admission_interrupted"})
            return 75

        def transfer_claim(child_pid: int) -> None:
            nonlocal claim_started_child, heartbeat_thread
            transfer_durable_resource(claim, child_pid)
            claim_started_child = True
            if durable:
                heartbeat_thread = threading.Thread(
                    target=_heartbeat_loop, args=(claim, heartbeat_stop),
                    name=f"lm-heartbeat-{loop_id}", daemon=True,
                )
                heartbeat_thread.start()

        hint_allowed = entry.get("entrypoint") in PRE_EFFECT_HINT_ENTRYPOINTS
        child_env = {key: value for key, value in env.items()
                     if key not in {"LIFE_MANAGER_OCCURRENCE_ID", "LIFE_MANAGER_RESULT_HINT_PATH"}}
        if hint_allowed:
            child_env["LIFE_MANAGER_RESULT_HINT_PATH"] = str(
                receipt.parent / "entrypoint-result.json")
        if claimed_occurrence_id is not None:
            child_env["LIFE_MANAGER_OCCURRENCE_ID"] = claimed_occurrence_id
        return_code = _run_entrypoint(
            command, env=child_env, timeout_seconds=limit, cancelled=lambda: interrupted,
            on_started=transfer_claim)
        if return_code == 75 and interrupted:
            _atomic_json(receipt, {"status": "deferred", "effect": 0,
                                  "reason": "resource_admission_interrupted"})
        return return_code
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=1)
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        if claim is not None:
            try:
                if durable:
                    release_options = {"requeue": not claim_started_child,
                                       "reserve": claim_started_child}
                    if (claim_started_child and return_code != 0
                            and entry.get("effect_class") != "none"
                            and not (hint_allowed and _proven_pre_effect_failure(
                                receipt.parent / "entrypoint-result.json"))):
                        release_options["effect_unknown"] = True
                    dispatch_after_release = release_and_reserve_resource(claim, **release_options)
                else:
                    release_resource(claim)
            except (OSError, RuntimeError) as error:
                print(f"lm-loop-run: resource release deferred to stale recovery: {error}",
                      file=sys.stderr)
        if dispatch_after_release:
            _dispatch_reserved(dispatch_after_release)


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if len(args) != 2:
        print("usage: lm-loop-run <loop-id> <release-root>", file=sys.stderr); return 64
    loop_id, release_value = args
    release_root = Path(release_value).resolve()
    try:
        registry = json.loads((release_root / "config/loop-registry.json").read_text())
        manifest = json.loads((release_root / "RELEASE.json").read_text())
        if not isinstance(manifest.get("sha"), str) or len(manifest["sha"]) != 40:
            raise ValueError("invalid release manifest SHA")
        entry = registry.get("loops", {}).get(loop_id)
        if not isinstance(entry, dict):
            raise ValueError(f"unknown loop id: {loop_id}")
        loop_state_root = Path(os.path.expanduser(
            os.environ.get("LIFE_MANAGER_STATE_ROOT", entry["state_root"])))
        current = Path("~/loops/current").expanduser()
        item_lock = _label_apply_lock_path(current, entry["label"])
        with _apply_lock(current, item_lock):
            command = build_loop_command(registry, loop_id, release_root)
            run_id = os.environ.get("LIFE_MANAGER_RUN_ID") or f"{time.time_ns():x}-{os.getpid()}"
            event_path = loop_state_root / "events.jsonl"
            scratch, scratch_parent_fd, scratch_fd = reset_loop_scratch(
                loop_state_root, loop_id, run_id)
            try:
                append_runtime_event(event_path, build_runtime_start_event(
                    loop_id=loop_id, domain=entry["domain"], run_id=run_id,
                    release_sha=manifest["sha"], provider=entry["provider_route"],
                    profile_alias=None, effect_class=entry["effect_class"],
                ))
            except (OSError, ValueError) as error:
                print(f"lm-loop-run: start event failed: {error}", file=sys.stderr)
        host_receipt = scratch / "host-admission.json"
        started_ns = time.time_ns()
        claimed_occurrence_id = None
        def record_claimed(value: str) -> None:
            nonlocal claimed_occurrence_id
            claimed_occurrence_id = value
        return_code = _run_admitted(command, entry, loop_id, {
            **os.environ, "LIFE_MANAGER_RELEASE_ROOT": str(release_root),
            "LIFE_MANAGER_RUN_ID": run_id,
            "LIFE_MANAGER_EFFECT_IDENTITY_PATH": str(scratch / "effect-identity.jsonl"),
            "TMPDIR": f"{scratch}/", "NPM_CONFIG_CACHE": str(scratch / "npm-cache"),
        }, host_receipt, occurrence_id=f"{loop_id}:{run_id}", on_claimed=record_claimed)
        host_deferred = _host_admission_deferred(host_receipt, started_ns)
        effect_identity_ref = None
        if entry.get("effect_class") != "none" and return_code != 0:
            try:
                effect_identity_ref = _persist_effect_identity(
                    scratch / "effect-identity.jsonl", loop_state_root, loop_id, run_id,
                    claimed_occurrence_id,
                )
            except (OSError, ValueError) as error:
                print(f"lm-loop-run: effect identity preservation deferred: {error}", file=sys.stderr)
        terminal_saved = False
        try:
            succeeded, deferred, blocker = _terminal_outcome(
                return_code, host_deferred=host_deferred)
            event = build_runtime_event(
                loop_id=loop_id, domain=entry["domain"], run_id=run_id,
                release_sha=manifest["sha"], provider=entry["provider_route"],
                profile_alias=None, effect_class=entry["effect_class"],
                succeeded=succeeded, deferred=deferred, blocker=blocker,
                evidence_scheme="lm-loop",
                claimed_occurrence_id=claimed_occurrence_id,
                effect_identity_ref=effect_identity_ref,
            )
            append_runtime_event(event_path, event)
            terminal_saved = True
        except (OSError, ValueError) as error:
            print(f"lm-loop-run: terminal event failed: {error}", file=sys.stderr)
        try:
            if terminal_saved:
                unprotect_loop_scratch(scratch_fd)
                remove_owned_tree(scratch_parent_fd, scratch_fd, run_id)
        finally:
            os.close(scratch_fd)
            os.close(scratch_parent_fd)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"lm-loop-run: {error}", file=sys.stderr); return 78
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
