#!/usr/bin/env python3
"""Fail closed before a managed launchd bootout would discard pending admission."""

import fcntl
import json
import os
import pwd
import sqlite3
import sys
from pathlib import Path


def check_service(registry_path: Path, service: str) -> int:
    prefix = f"gui/{os.getuid()}/"
    if not service.startswith(prefix):
        return 0
    label = service[len(prefix):]
    if not label.startswith("ai.anicca.") or "/" in label:
        return 0
    try:
        loops = json.loads(registry_path.read_text())["loops"]
        matches = [loop_id for loop_id, row in loops.items()
                   if row.get("label") == label]
        if len(matches) != 1:
            return 0 if not matches else 1
        owner_id = matches[0]
        home = Path(pwd.getpwuid(os.getuid()).pw_dir)
        root = Path(os.environ.get("LIFE_MANAGER_RESOURCE_ADMISSION_ROOT",
                                   home / ".local/state/life-manager/host-admission/resources")).expanduser()
        database = root / "admission-v2.sqlite3"
        try:
            database.stat()
        except FileNotFoundError:
            return 0
        descriptor = os.open(root / "control.lock", os.O_RDWR | os.O_CREAT, 0o600)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro",
                                 uri=True, timeout=0.5) as connection:
                pending = connection.execute(
                    """SELECT 1 FROM occurrences WHERE owner_id=? AND state='claimed'
                       UNION
                       SELECT 1 FROM occurrences o JOIN queue q ON q.owner_id=o.owner_id
                        WHERE o.owner_id=? AND o.state='queued' AND o.effect_unknown=0
                       LIMIT 1""", (owner_id, owner_id)).fetchone()
            return 75 if pending else 0
        finally:
            os.close(descriptor)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        return 1


def main() -> int:
    if len(sys.argv) != 3:
        return 2
    status = check_service(Path(sys.argv[1]), sys.argv[2])
    if status == 75:
        print("launchctl-safe: pending admission owner; bootout deferred", file=sys.stderr)
    elif status:
        print("launchctl-safe: admission guard unavailable; bootout deferred", file=sys.stderr)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
