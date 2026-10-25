#!/usr/bin/env python3
"""Create, verify, or restore an isolated Manager owner-state snapshot.

Restored state is always quarantined until the production target and every
external effect are independently reconciled. A checksum is not a signature.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from manager_core.state_recovery import (
    StateRecoveryError,
    create_backup,
    restore_backup,
    verify_backup,
)

SOURCE_ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create", help="create an integrity-checked snapshot")
    create.add_argument("--state-dir", type=Path, required=True)
    create.add_argument("--destination", type=Path, required=True)

    verify = commands.add_parser("verify", help="verify an existing snapshot")
    verify.add_argument("--backup", type=Path, required=True)

    restore = commands.add_parser("restore", help="restore to a new quarantined directory")
    restore.add_argument("--backup", type=Path, required=True)
    restore.add_argument("--destination", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "create":
            result = create_backup(args.state_dir, args.destination, source_root=SOURCE_ROOT)
        elif args.command == "verify":
            result = verify_backup(args.backup)
        else:
            result = restore_backup(args.backup, args.destination, source_root=SOURCE_ROOT)
    except StateRecoveryError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
