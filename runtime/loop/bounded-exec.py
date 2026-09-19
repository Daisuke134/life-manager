#!/usr/bin/env python3
"""Shared portable wall-clock bound that terminates the child process group."""

from __future__ import annotations

from contextlib import suppress
import os
import signal
import subprocess
import sys
import time

STOP_PATHS_ENV = "BOUNDED_EXEC_STOP_PATHS"
POLL_INTERVAL_SECONDS, DRAIN_GRACE_SECONDS = 0.1, 1.0


def _process_table() -> dict[int, tuple[int, str]]:
    """Return pid -> (ppid, start token) for the current host snapshot."""
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,lstart="],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if result.returncode != 0:
        return {}
    table: dict[int, tuple[int, str]] = {}
    for line in result.stdout.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) != 3:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if pid > 0 and ppid >= 0 and parts[2]:
            table[pid] = (ppid, parts[2])
    return table


def _descendant_identities(root_pid: int) -> dict[int, str]:
    """Snapshot recursive descendants before terminating the owned root."""
    table = _process_table()
    descendants: dict[int, str] = {}
    parents = {root_pid}
    while parents:
        children = {
            pid for pid, (ppid, _start) in table.items()
            if ppid in parents and pid != root_pid and pid not in descendants
        }
        if not children:
            break
        for pid in children:
            descendants[pid] = table[pid][1]
        parents = children
    return descendants


def _signal_owned(pid: int, start: str, signum: int) -> bool:
    """Signal a captured descendant only if its start token is unchanged."""
    current = _process_table().get(pid)
    if current is None or current[1] != start:
        return False
    try:
        os.kill(pid, signum)
    except ProcessLookupError:
        return False
    return True


def _owned_descendants_alive(descendants: dict[int, str]) -> bool:
    if not descendants:
        return False
    table = _process_table()
    return any(table.get(pid, (None, None))[1] == start
               for pid, start in descendants.items())


def _stop_requested() -> bool:
    for path in filter(None, os.environ.get(STOP_PATHS_ENV, "").split(os.pathsep)):
        try:
            return bool(os.lstat(path))
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            return True
        return True
    return False


def _group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _terminate_group(process: subprocess.Popen[object]) -> None:
    descendants = _descendant_identities(process.pid)
    with suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    for pid, start in descendants.items():
        _signal_owned(pid, start, signal.SIGTERM)
    deadline = time.monotonic() + DRAIN_GRACE_SECONDS
    while _group_exists(process.pid) or _owned_descendants_alive(descendants):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(POLL_INTERVAL_SECONDS, remaining))
    if _group_exists(process.pid):
        with suppress(OSError):
            os.killpg(process.pid, signal.SIGKILL)
    for pid, start in descendants.items():
        _signal_owned(pid, start, signal.SIGKILL)
    process.wait()


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: bounded-exec.py <seconds> <command> [args...]", file=sys.stderr)
        return 2
    try:
        timeout = float(sys.argv[1])
    except ValueError:
        print("bounded-exec.py: seconds must be numeric", file=sys.stderr)
        return 2
    if timeout <= 0:
        print("bounded-exec.py: seconds must be positive", file=sys.stderr)
        return 2

    received_signal = [0]

    def handle_signal(signum: int, _frame: object) -> None:
        received_signal[0] = signum

    previous_sigterm = signal.signal(signal.SIGTERM, handle_signal)
    previous_sigint = signal.signal(signal.SIGINT, handle_signal)
    try:
        if received_signal[0] or _stop_requested():
            return 128 + received_signal[0] if received_signal[0] else 143
        process = subprocess.Popen(sys.argv[2:], start_new_session=True)
        deadline = time.monotonic() + timeout
        while True:
            if process.poll() is not None:
                return 128 + received_signal[0] if received_signal[0] else process.wait()
            if received_signal[0] or _stop_requested():
                _terminate_group(process)
                return 128 + received_signal[0] if received_signal[0] else 143
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate_group(process)
                return 124
            try:
                return 128 + received_signal[0] if received_signal[0] else process.wait(
                    timeout=min(POLL_INTERVAL_SECONDS, remaining)
                )
            except subprocess.TimeoutExpired:
                continue
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        signal.signal(signal.SIGINT, previous_sigint)


if __name__ == "__main__":
    raise SystemExit(main())
