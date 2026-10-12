#!/usr/bin/env python3
"""Own a headed CloakBrowser context for the lifetime of the process."""

from __future__ import annotations

import argparse
import json
import os
import pwd
import signal
import stat
import subprocess
import sys
import time
from contextlib import nullcontext
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
from runtime.host.bounded_output import bounded_launchd_output  # noqa: E402
from runtime.host.memory_admission import memory_free_percent  # noqa: E402
from runtime.host.storage_policy import load_storage_policy  # noqa: E402

_GUARD = _REPO_ROOT / "runtime/host/disk_admission.py"
_READABLE = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
_REMOVED_ENV = (
    "BROWSER_DISK_HEADROOM_KIB", "GIG_DISK_HEADROOM_KIB",
    "LIFE_MANAGER_DISK_HEADROOM_KIB",
    "LIFE_MANAGER_HOST_STATE_DIR",
    "LIFE_MANAGER_PRODUCER_STATE_DIR",
    "LIFE_MANAGER_IGNORE_DISK_WRITERS_STOP",
    "GIG_HOST_STATE_DIR", "GIG_STATE_DIR",
    "GIG_IGNORE_DISK_WRITERS_STOP",
    "DISK_CONTROL_STATE_DIR", "OPENCLAW_STATE_DIR",
)


def _canonical_home() -> Path | None:
    try:
        home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (KeyError, OSError):
        return None
    return home if home.is_absolute() and home.is_dir() else None


def _disk_preflight(home: Path | None = None, guard: Path | None = None) -> bool:
    home = _canonical_home() if home is None else home
    if home is None or not home.is_absolute() or not home.is_dir():
        return False
    guard = _GUARD if guard is None else guard
    try:
        if (
            guard.is_symlink()
            or not guard.is_file()
            or not guard.stat().st_mode & _READABLE
        ):
            return False
        child_env = os.environ.copy()
        for key in _REMOVED_ENV:
            child_env.pop(key, None)
        child_env.update(
            {
                "HOME": str(home),
                "LIFE_MANAGER_HOST_STATE_DIR": str(home / ".local/state/life-manager/state"),
                "LIFE_MANAGER_PRODUCER_STATE_DIR": str(home / ".local/state/life-manager/browser-provision"),
            }
        )
        result = subprocess.run(
            ["/usr/bin/python3", "-I", str(guard), "/usr/bin/true"],
            env=child_env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return getattr(result, "returncode", 1) == 0


def _memory_preflight() -> str | None:
    try:
        minimum = int(os.environ.get("LIFE_MANAGER_MIN_MEMORY_FREE_PERCENT", "15"))
    except ValueError:
        return "memory_headroom_policy_invalid"
    if not 1 <= minimum <= 100:
        return "memory_headroom_policy_invalid"
    available = memory_free_percent()
    if available is None:
        return "memory_headroom_unavailable"
    if available < minimum:
        return "memory_headroom_low"
    return None


def _owner_output_context(owner_id: str | None):
    if not owner_id:
        return nullcontext()
    policy_path = _REPO_ROOT / "config/storage-policy.json"
    policy = load_storage_policy(policy_path, owner_id)
    if policy is None:
        raise ValueError("browser_owner_storage_policy_missing")
    registry_path = _REPO_ROOT / "config/loop-registry.json"
    if registry_path.is_symlink():
        raise ValueError("browser_owner_loop_registry_symlink")
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    owner = (registry.get("loops") or {}).get(owner_id)
    log_root = owner.get("log_root") if isinstance(owner, dict) else None
    if not isinstance(log_root, str) or not log_root.strip():
        raise ValueError("browser_owner_log_root_missing")
    return bounded_launchd_output(Path(log_root).expanduser(), policy)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _command_line(pid: int) -> str:
    try:
        result = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                                capture_output=True, text=True, check=False, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout


def _live_profile_owner(profile: str) -> int | None:
    """Return the live Chromium pid that already holds this profile, if any."""
    try:
        target = os.readlink(Path(profile) / "SingletonLock")
    except OSError:
        return None
    pid_text = target.rpartition("-")[2]
    if not pid_text.isdigit():
        return None
    pid = int(pid_text)
    if not _pid_alive(pid):
        return None
    marker = f"--user-data-dir={os.path.realpath(profile)}"
    return pid if marker in _command_line(pid) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--renderer-limit", default="24")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--owner-id")
    parser.add_argument("--extension", action="append", default=[], help="unpacked extension dir (repeatable)")
    args = parser.parse_args(argv)
    try:
        port = int(args.port)
        renderer_limit = int(args.renderer_limit)
    except (TypeError, ValueError):
        return 1
    if not 0 <= port <= 65_535 or not 1 <= renderer_limit <= 64 or not _disk_preflight():
        return 1
    if args.owner_id:
        memory_defer = _memory_preflight()
        if memory_defer:
            print(f"browser_memory_preflight_deferred:{memory_defer}", file=sys.stderr)
            return 75
    if args.preflight_only:
        return 0
    try:
        with _owner_output_context(args.owner_id):
            owner = _live_profile_owner(args.profile)
            if owner is not None:
                # Adopt the existing profile owner. Never launch a second Chromium.
                print(f"adopted live profile owner pid={owner}", flush=True)
                while _pid_alive(owner):
                    time.sleep(5)
                return 1
            from cloakbrowser import launch_persistent_context

            context = launch_persistent_context(
                args.profile,
                headless=False,
                humanize=True,
                extension_paths=[os.path.expanduser(path) for path in args.extension] or None,
                args=[
                    f"--remote-debugging-port={port}",
                    # Use Chromium's default loopback bind and resolve the port
                    # from the profile's DevToolsActivePort file.
                    "--remote-allow-origins=*",
                    "--disable-features=MacAppCodeSignClone",
                    f"--renderer-process-limit={renderer_limit}",
                    "--disk-cache-size=67108864",
                    "--media-cache-size=33554432",
                    f"--disk-cache-dir={_canonical_home() / '.cache' / 'life-manager-daily-driver'}",
                ],
            )
            stopping = False

            def stop(_signum, _frame):
                nonlocal stopping
                stopping = True

            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
            print(f"persistent context alive on 127.0.0.1:{port}", flush=True)
            try:
                while not stopping:
                    time.sleep(1)
            finally:
                context.close()
    except (OSError, ValueError) as error:
        print(f"browser_context_owner_bounds_failed:{type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
