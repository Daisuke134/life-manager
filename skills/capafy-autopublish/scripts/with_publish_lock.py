#!/usr/bin/env python3
"""Run one Capafy publisher entrypoint under the account's OS file lock."""

import fcntl
import os
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        return 2
    state = Path(os.environ.get("CAPAFY_PUBLISHER_STATE_HOME") or
                 Path.home() / ".local/state/life-manager/runtime/capafy-publisher")
    locks = state / "locks"
    locks.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(locks / "publisher.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # Name the holder (same idea as skills/earn/gig/scripts/cdp_lock.sh's owner meta):
        # the fd is inherited, so a surviving child can keep the lock after its script exits.
        holder = os.pread(descriptor, 512, 0).decode("utf-8", "replace").strip()
        print(f"Capafy publisher account is already in use (holder: {holder or 'unknown'})", file=sys.stderr)
        os.close(descriptor)
        return 75
    import time
    os.ftruncate(descriptor, 0)
    os.pwrite(descriptor, f"pid={os.getpid()} since={time.strftime('%Y-%m-%dT%H:%M:%S')} cmd={' '.join(sys.argv[1:3])}".encode(), 0)
    os.set_inheritable(descriptor, True)
    environment = dict(os.environ)
    environment["CAPAFY_PUBLISH_LOCK_HELD"] = "1"
    os.execvpe("bash", ["bash", *sys.argv[1:]], environment)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
