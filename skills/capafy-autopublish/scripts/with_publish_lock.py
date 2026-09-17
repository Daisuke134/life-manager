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
        print("Capafy publisher account is already in use", file=sys.stderr)
        os.close(descriptor)
        return 75
    os.set_inheritable(descriptor, True)
    environment = dict(os.environ)
    environment["CAPAFY_PUBLISH_LOCK_HELD"] = "1"
    os.execvpe("bash", ["bash", *sys.argv[1:]], environment)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
