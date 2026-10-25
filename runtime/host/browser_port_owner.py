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
from typing import Callable


_OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")


class _OwnerShutdownRequested(BaseException):
    """Interrupt the owner's wait loop so its finally block can reap the tree."""


def _process_group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _linux_process_group_has_live_member(
    pgid: int, proc_root: Path = Path("/proc"),
) -> bool | None:
    """Return whether a Linux process group has a runnable/non-zombie member.

    ``killpg(pgid, 0)`` still succeeds for a group containing only zombies.
    Container PID 1 implementations do not always reap adopted zombies
    promptly, so those dead processes must not keep a browser lease alive.
    ``None`` means /proc could not establish the group state; callers should
    fall back to the portable killpg probe in that case.
    """
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return None
    found_member = False
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            stat = (entry / "stat").read_text(encoding="utf-8")
        except OSError:
            continue
        closing_paren = stat.rfind(")")
        if closing_paren < 0:
            continue
        fields = stat[closing_paren + 2 :].split()
        if len(fields) < 3:
            continue
        try:
            member_pgid = int(fields[2])
        except ValueError:
            continue
        if member_pgid != pgid:
            continue
        found_member = True
        if fields[0] not in {"Z", "X", "x"}:
            return True
    return False if found_member else None


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
        live_member = _linux_process_group_has_live_member(pgid)
        if live_member is False or (
            live_member is None and not _process_group_exists(pgid)
        ):
            return
        time.sleep(0.02)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        return
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        live_member = _linux_process_group_has_live_member(pgid)
        if live_member is False or (
            live_member is None and not _process_group_exists(pgid)
        ):
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


def _browser_uuid(port: int, timeout: float = 3.0) -> str | None:
    try:
        with urllib.request.urlopen(
            f"http://localhost:{port}/json/version", timeout=timeout,
        ) as response:
            value = json.load(response)
    except Exception:
        return None
    websocket = str(value.get("webSocketDebuggerUrl") or "")
    match = re.fullmatch(r"ws://.+/devtools/browser/([A-Za-z0-9-]{8,128})", websocket)
    return match.group(1) if match else None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _pid_owns_loopback_listener(pid: int, port: int) -> bool:
    """Prove the process behind a profile lock owns this loopback CDP socket."""
    if pid <= 1 or not 1 <= port <= 65_535:
        return False
    if sys.platform.startswith("linux"):
        inodes: set[str] = set()
        loopback_addresses = {
            "tcp": {"0100007F"},
            "tcp6": {"00000000000000000000000001000000"},
        }
        for table, addresses in loopback_addresses.items():
            try:
                rows = (Path("/proc/net") / table).read_text(encoding="ascii").splitlines()[1:]
            except OSError:
                return False
            for row in rows:
                fields = row.split()
                if len(fields) < 10:
                    continue
                address, separator, raw_port = fields[1].rpartition(":")
                if (not separator or address.upper() not in addresses
                        or fields[3] != "0A" or raw_port.upper() != f"{port:04X}"):
                    continue
                if fields[9].isdigit():
                    inodes.add(fields[9])
        if not inodes:
            return False
        fd_dir = Path("/proc") / str(pid) / "fd"
        try:
            descriptors = list(fd_dir.iterdir())
        except OSError:
            return False
        for descriptor in descriptors:
            try:
                target = os.readlink(descriptor)
            except OSError:
                continue
            if target.startswith("socket:[") and target.endswith("]"):
                if target[8:-1] in inodes:
                    return True
        return False
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["/usr/sbin/lsof", "-nP", "-a", "-p", str(pid),
                 f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                capture_output=True, text=True, timeout=3, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0 and str(pid) in result.stdout.split()
    return False


def _command_line(pid: int) -> str:
    try:
        result = subprocess.run(
            ["/bin/ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout


def _live_profile_owner(profile: Path, port: int) -> int | None:
    """Return an orphan Chromium pid only when profile and CDP port both match."""
    try:
        target = os.readlink(profile / "SingletonLock")
    except OSError:
        return None
    pid_text = target.rpartition("-")[2]
    if not pid_text.isdigit():
        return None
    pid = int(pid_text)
    if pid <= 1 or not _pid_alive(pid):
        return None
    command = _command_line(pid)
    profile_marker = f"--user-data-dir={profile.resolve()}"
    port_marker = f"--remote-debugging-port={port}"
    if (profile_marker not in command or port_marker not in command
            or not _pid_owns_loopback_listener(pid, port)):
        return None
    return pid


def _wait_for_adopted_browser(pid: int, port: int, poll_interval: float = 10.0) -> int:
    """Keep the owner lease while an exact orphaned browser remains alive."""
    while _pid_alive(pid):
        if not _port_answers(port):
            return 75
        time.sleep(poll_interval)
    return 75


def _wait_for_browser(
    child: subprocess.Popen,
    *,
    port: int,
    startup_grace_seconds: float = 60.0,
    probe_interval_seconds: float = 10.0,
    max_consecutive_failures: int = 3,
    on_ready: Callable[[], bool] | None = None,
) -> int:
    """Wait for the browser, but return EX_TEMPFAIL when its CDP stays wedged."""
    startup_deadline = time.monotonic() + startup_grace_seconds
    consecutive_failures = 0
    ready_reported = False
    while True:
        try:
            return child.wait(timeout=probe_interval_seconds)
        except subprocess.TimeoutExpired:
            pass
        if _port_answers(port):
            consecutive_failures = 0
            if on_ready is not None and not ready_reported:
                ready_reported = bool(on_ready())
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
            # second browser against that live CDP/profile. If Chromium's
            # SingletonLock and command line prove that it is this exact
            # profile/port, adopt it until it exits; otherwise fail closed.
            if _port_answers(args.port):
                adopted_pid = _live_profile_owner(Path(args.profile), args.port)
                if adopted_pid is not None:
                    browser_uuid = _browser_uuid(args.port)
                    if browser_uuid is None:
                        return 75
                    payload = {
                        "owner": args.owner,
                        "pid": os.getpid(),
                        "supervisor_pid": os.getpid(),
                        "browser_root_pid": adopted_pid,
                        "listener_pid": adopted_pid,
                        "browser_uuid": browser_uuid,
                        "port": args.port,
                        "profile_name": Path(args.profile).name,
                        "adopted": True,
                    }
                    terminate_adopted = bool(getattr(args, "terminate_adopted_on_exit", False))
                    adopted_cleanup_ok = not terminate_adopted
                    shutting_down = False
                    previous = {}

                    def forward_adopted(signum: int, _frame: object) -> None:
                        nonlocal shutting_down
                        if shutting_down:
                            return
                        shutting_down = True
                        _forward_process_group_signal(adopted_pid, signum)
                        raise _OwnerShutdownRequested()

                    previous_mask = None
                    try:
                        if terminate_adopted:
                            previous_mask = signal.pthread_sigmask(
                                signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT},
                            )
                            for signum in (signal.SIGTERM, signal.SIGINT):
                                previous[signum] = signal.signal(signum, forward_adopted)
                        _write_receipt(receipt_path, payload)
                        _write_receipt(profile_receipt_path, payload)
                        if previous_mask is not None:
                            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
                        if terminate_adopted:
                            return _wait_for_adopted_browser(adopted_pid, args.port, poll_interval=0.1)
                        return _wait_for_adopted_browser(adopted_pid, args.port)
                    except _OwnerShutdownRequested:
                        return 75
                    finally:
                        shutting_down = True
                        try:
                            if terminate_adopted:
                                _terminate_process_group(adopted_pid)
                                adopted_cleanup_ok = True
                        finally:
                            for signum, handler in previous.items():
                                signal.signal(signum, handler)
                            if previous_mask is not None:
                                signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
                        if adopted_cleanup_ok:
                            for owned_receipt in (receipt_path, profile_receipt_path):
                                try:
                                    current = json.loads(owned_receipt.read_text(encoding="utf-8"))
                                except (OSError, ValueError, TypeError):
                                    current = {}
                                if (current.get("supervisor_pid") == os.getpid()
                                        and current.get("owner") == args.owner):
                                    owned_receipt.unlink(missing_ok=True)
                print(json.dumps({
                    "ok": False,
                    "reason": "browser_port_already_served",
                    "port": args.port,
                }, sort_keys=True), file=sys.stderr)
                return 75

            _clear_stale_singleton_lock(Path(args.profile))
            child = None
            previous = {}
            shutdown_requested = False

            def forward(signum: int, _frame: object) -> None:
                nonlocal shutdown_requested
                if shutdown_requested:
                    return
                shutdown_requested = True
                if child is not None:
                    _forward_process_group_signal(child.pid, signum)
                raise _OwnerShutdownRequested()

            termination_signals = {signal.SIGTERM, signal.SIGINT}
            previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, termination_signals)
            try:
                for signum in termination_signals:
                    previous[signum] = signal.signal(signum, forward)
                child = subprocess.Popen(command, start_new_session=True)
                payload = {
                    "owner": args.owner,
                    "pid": os.getpid(),
                    "supervisor_pid": os.getpid(),
                    "browser_root_pid": child.pid,
                    "port": args.port,
                    "profile_name": Path(args.profile).name,
                }

                def record_listener() -> bool:
                    listener_pid = _live_profile_owner(Path(args.profile), args.port)
                    browser_uuid = _browser_uuid(args.port)
                    if listener_pid is None or browser_uuid is None:
                        return False
                    current = {
                        **payload,
                        "listener_pid": listener_pid,
                        "browser_uuid": browser_uuid,
                    }
                    _write_receipt(receipt_path, current)
                    _write_receipt(profile_receipt_path, current)
                    return True

                # Signals received during Popen remain pending until the exact
                # child PID is stored and its cleanup handler is active.
                signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
                _write_receipt(receipt_path, payload)
                _write_receipt(profile_receipt_path, payload)
                return _wait_for_browser(
                    child, port=args.port, on_ready=record_listener,
                )
            except _OwnerShutdownRequested:
                return 75
            finally:
                shutdown_requested = True
                try:
                    if child is not None:
                        _terminate_process_group(child.pid)
                        try:
                            child.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            raise RuntimeError(f"owned browser root {child.pid} survived cleanup") from None
                finally:
                    for signum, handler in previous.items():
                        signal.signal(signum, handler)
                    signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
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
    command.add_argument("--terminate-adopted-on-exit", action="store_true")
    command.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
