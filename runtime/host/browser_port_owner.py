#!/usr/bin/env python3
"""Hold one host-wide CDP port lease for one browser process tree."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


_OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


def _process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _forward_process_group_signal(pgid: int, signum: int) -> None:
    try:
        os.killpg(pgid, signum)
    except (ProcessLookupError, PermissionError):
        pass


def _terminate_process_group(pgid: int, grace_seconds: float = 2.0) -> None:
    """Best-effort: make sure the process group we spawned is gone.

    macOS can raise EPERM signalling a process group whose session leader has
    already exited -- an orphaned group -- even though every member is
    already dead. That observed EPERM is evidence the group is gone from
    under us, not a real permission conflict, so it ends cleanup here instead
    of crashing the supervisor. A group we still cannot verify as dead is
    left alone rather than force-killed, since it may not be ours to kill.
    """
    if not _process_group_exists(pgid):
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not _process_group_exists(pgid):
            return
        time.sleep(0.02)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        return
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not _process_group_exists(pgid):
            return
        time.sleep(0.02)
    raise RuntimeError(f"owned process group {pgid} survived SIGKILL")


def _port_answers(port: int, timeout: float = 3.0) -> bool:
    """True when something is serving CDP on the port right now.

    Probes "localhost", not the literal 127.0.0.1: on this host an unrelated
    process can (and did, 2026-09-27) occupy 127.0.0.1:<port> and 404 every
    request, while the browser this owner spawned only binds the IPv6 loopback
    (::1) on the same numeric port. browser-guard.sh already probes via
    "localhost" for the same reason (commit de022c0); a probe hardcoded to the
    IPv4 literal here saw only the unrelated occupant, always failed, and
    killed a healthy browser every ~90s.
    """
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=timeout):
            return True
    except Exception:
        return False


def _wait_for_browser(
    child: subprocess.Popen,
    *,
    port: int,
    startup_grace_seconds: float = 60.0,
    probe_interval_seconds: float = 10.0,
    max_consecutive_failures: int = 3,
) -> int:
    """Wait for the browser, but return EX_TEMPFAIL when its CDP stays wedged."""
    startup_deadline = time.monotonic() + startup_grace_seconds
    consecutive_failures = 0
    while True:
        try:
            return child.wait(timeout=probe_interval_seconds)
        except subprocess.TimeoutExpired:
            pass
        if _port_answers(port):
            consecutive_failures = 0
            continue
        if time.monotonic() < startup_deadline:
            continue
        consecutive_failures += 1
        if consecutive_failures >= max_consecutive_failures:
            print(json.dumps({
                "ok": False,
                "reason": "owned_browser_cdp_unhealthy",
                "port": port,
                "browser_root_pid": child.pid,
                "consecutive_failures": consecutive_failures,
            }, sort_keys=True), file=sys.stderr)
            return 75


def _clear_stale_singleton_lock(profile: Path) -> None:
    """Remove a profile's SingletonLock left behind by a browser that died.

    Chromium's SingletonLock is a symlink named "<hostname>-<pid>". A browser
    that dies without cleaning up leaves it in place, and every later launch
    against that profile treats it as already open and refuses to start (or
    exits immediately with a wedged, unreachable CDP). This is called only
    while we hold the profile's own flock exclusively, so no supervised
    launch can be racing us for it -- a lock still pointing at a live pid is
    a real external conflict and is left untouched.
    """
    lock = profile / "SingletonLock"
    try:
        target = os.readlink(lock)
    except OSError:
        return
    pid_text = target.rpartition("-")[2]
    if not pid_text.isdigit():
        return
    pid = int(pid_text)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pass
    except PermissionError:
        return
    else:
        return
    try:
        lock.unlink()
    except OSError:
        pass


def _reclaim_wedged_owner(receipt_path: Path, *, owner: str, port: int) -> bool:
    """Take the lock back from our own supervisor when it is alive but serving nothing.

    Measured 2026-09-07: a Chromium stayed up for two and a half hours without ever binding its
    debugging port, after the volume filled underneath it. Its supervisor therefore stayed up too,
    holding the flock, so every relaunch returned EX_TEMPFAIL -- five runs, then indefinitely. The
    locks are correct: flock releases when a process dies, and this process had not died. Nothing
    in the chain asked whether it was doing its job, so launchd retried forever and the lane it
    serves applied to nothing until a human killed the browser by hand.

    Only our own owner is reclaimed. A different owner holding the profile is a real conflict and
    is left alone, because killing another lane's browser to start ours is not recovery.
    """
    if _port_answers(port):
        return False
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    if str(receipt.get("owner") or "") != owner or int(receipt.get("port") or 0) != port:
        return False
    reclaimed = False
    for key in ("browser_root_pid", "supervisor_pid"):
        pid = receipt.get(key)
        if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 1:
            continue
        try:
            _terminate_process_group(pid)
            reclaimed = True
        except Exception:
            continue
    if reclaimed:
        print(json.dumps({"ok": False, "reason": "reclaimed_wedged_browser",
                          "owner": owner, "port": port}, sort_keys=True), file=sys.stderr)
    return reclaimed


def _default_state_dir() -> Path:
    import pwd

    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    return home / ".local/state/life-manager/browser-ports"


def _write_receipt(path: Path, payload: dict[str, object]) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        Path(temporary).unlink(missing_ok=True)
        raise


def run(args: argparse.Namespace) -> int:
    state_dir = args.state_dir or _default_state_dir()
    if not state_dir.is_absolute() or not Path(args.profile).is_absolute():
        return 64
    if not 1 <= args.port <= 65_535 or not _OWNER.fullmatch(args.owner):
        return 64
    command = list(args.command)
    if command and command[0] == "--":
        command.pop(0)
    if not command:
        return 64

    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state_dir, 0o700)
    profile_digest = hashlib.sha256(
        str(Path(args.profile).resolve()).encode("utf-8")
    ).hexdigest()
    profile_lock_path = state_dir / f"profile-{profile_digest}.lock"
    profile_receipt_path = state_dir / f"profile-{profile_digest}.json"
    lock_path = state_dir / f"{args.port}.lock"
    receipt_path = state_dir / f"{args.port}.json"
    with profile_lock_path.open("a+", encoding="utf-8") as profile_lock:
        os.chmod(profile_lock_path, 0o600)
        try:
            fcntl.flock(profile_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            current_owner = "unknown"
            try:
                current = json.loads(profile_receipt_path.read_text(encoding="utf-8"))
                if _OWNER.fullmatch(str(current.get("owner", ""))):
                    current_owner = str(current["owner"])
            except (OSError, ValueError, TypeError):
                pass
            if _reclaim_wedged_owner(profile_receipt_path, owner=args.owner, port=args.port):
                # launchd relaunches in a moment; the lock is free by then.
                return 75
            print(json.dumps({
                "ok": False,
                "reason": "browser_profile_owned",
                "current_owner": current_owner,
            }, sort_keys=True), file=sys.stderr)
            return 75
        with lock_path.open("a+", encoding="utf-8") as lock:
            os.chmod(lock_path, 0o600)
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                current_owner = "unknown"
                try:
                    current = json.loads(receipt_path.read_text(encoding="utf-8"))
                    if _OWNER.fullmatch(str(current.get("owner", ""))):
                        current_owner = str(current["owner"])
                except (OSError, ValueError, TypeError):
                    pass
                if _reclaim_wedged_owner(receipt_path, owner=args.owner, port=args.port):
                    return 75
                print(json.dumps({
                    "ok": False,
                    "reason": "browser_port_owned",
                    "port": args.port,
                    "current_owner": current_owner,
                }, sort_keys=True), file=sys.stderr)
                return 75

            # A previous supervisor can die after its lock is released while
            # its Chromium child keeps serving the port.  Do not spawn a
            # second browser against that live CDP/profile; fail closed and
            # let the owner-scoped recovery path reconcile the orphan.
            if _port_answers(args.port):
                print(json.dumps({
                    "ok": False,
                    "reason": "browser_port_already_served",
                    "port": args.port,
                }, sort_keys=True), file=sys.stderr)
                return 75

            _clear_stale_singleton_lock(Path(args.profile))
            child = subprocess.Popen(command, start_new_session=True)
            payload = {
                "owner": args.owner,
                "pid": os.getpid(),
                "supervisor_pid": os.getpid(),
                "browser_root_pid": child.pid,
                "port": args.port,
                "profile_name": Path(args.profile).name,
            }
            _write_receipt(receipt_path, payload)
            _write_receipt(profile_receipt_path, payload)

            def forward(signum: int, _frame: object) -> None:
                _forward_process_group_signal(child.pid, signum)

            previous = {}
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous[signum] = signal.signal(signum, forward)
            try:
                return _wait_for_browser(child, port=args.port)
            finally:
                _terminate_process_group(child.pid)
                for signum, handler in previous.items():
                    signal.signal(signum, handler)
                for owned_receipt in (receipt_path, profile_receipt_path):
                    try:
                        current = json.loads(owned_receipt.read_text(encoding="utf-8"))
                    except (OSError, ValueError, TypeError):
                        current = {}
                    if (current.get("supervisor_pid") == os.getpid()
                            and current.get("owner") == args.owner):
                        owned_receipt.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)
    command = subparsers.add_parser("run")
    command.add_argument("--state-dir", type=Path)
    command.add_argument("--port", type=int, required=True)
    command.add_argument("--profile", required=True)
    command.add_argument("--owner", required=True)
    command.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
