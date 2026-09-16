#!/usr/bin/env python3
"""Per-loop cleanup boundary followed by exact immutable entrypoint exec."""

from __future__ import annotations

import json
import os
import plistlib
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable

from runtime.loop.lm_loop import _apply_lock, _label_apply_lock_path
from runtime.loop.lm_loop_apply import _loaded_arguments
from runtime.loop.loop_cleanup import remove_owned_tree
from runtime.loop.macos_loop_registry import validate_registry
from runtime.loop.runtime_event import append_runtime_event, build_runtime_event, build_runtime_start_event
from runtime.host.memory_admission import memory_free_percent
from runtime.host.resource_admission import (
    cancel_durable as cancel_durable_resource,
    claim_durable as claim_durable_resource,
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
            owner_fd = os.open(
                ".owner.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=run_fd)
            with os.fdopen(owner_fd, "w", encoding="utf-8") as handle:
                json.dump({"pid": os.getpid(), "process_start": identity}, handle,
                          sort_keys=True, separators=(",", ":"))
                handle.write("\n"); handle.flush(); os.fsync(handle.fileno())
            marker_fd = os.open(
                ".terminal-unrecorded", os.O_WRONLY | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=run_fd)
            os.close(marker_fd)
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
        if len(attempted) >= 16:
            break
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
                  receipt: Path, *, occurrence_id: str | None = None) -> int:
    limit = _runtime_limit(entry)
    if loop_id in {"life-manager-release-reconciler", "life-manager-disk-cleanup"}:
        _atomic_json(receipt, {"status": "pass", "effect": 0,
                              "reason": "control_plane_exempt"})
        return _run_entrypoint(command, env=env, timeout_seconds=limit)
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
            claim, admission_reason = (
                claim_durable_resource(
                    resource_class, loop_id, admission_class=admission_class)
                if durable else try_acquire_resource(
                    resource_class, loop_id, admission_class=admission_class,
                    retain_ticket=False, required_protocol=1)
            )
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

        return_code = _run_entrypoint(
            command, env=env, timeout_seconds=limit, cancelled=lambda: interrupted,
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
                    dispatch_after_release = release_and_reserve_resource(
                        claim, requeue=not claim_started_child,
                        reserve=claim_started_child)
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
        return_code = _run_admitted(command, entry, loop_id, {
            **os.environ, "LIFE_MANAGER_RELEASE_ROOT": str(release_root),
            "TMPDIR": f"{scratch}/", "NPM_CONFIG_CACHE": str(scratch / "npm-cache"),
        }, host_receipt, occurrence_id=f"{loop_id}:{run_id}")
        host_deferred = _host_admission_deferred(host_receipt, started_ns)
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
