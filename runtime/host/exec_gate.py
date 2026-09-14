"""Wait for the parent start byte, then replace this process with its command."""

from __future__ import annotations

import os
import sys


def main() -> int:
    if len(sys.argv) < 3:
        return 64
    descriptor = int(sys.argv[1])
    command = sys.argv[2:]
    try:
        allowed = os.read(descriptor, 1) == b"G"
    finally:
        os.close(descriptor)
    if not allowed:
        return 75
    os.execvpe(command[0], command, os.environ)
    return 70


if __name__ == "__main__":
    raise SystemExit(main())
