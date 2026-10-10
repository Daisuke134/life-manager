#!/bin/sh
set -eu

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
# The managed five-minute owner retains the full census; keep this hot pass light.
export LIFE_MANAGER_DISK_INVENTORY_FAST=1
RELEASE_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
GOVERNOR="$RELEASE_ROOT/skills/self/disk-cleanup/disk_cleanup.py"
STATE_DIR="$HOME/.local/state/life-manager/state"
PYTHON_BIN=${LIFE_MANAGER_RUNTIME_PYTHON:-}

if [ -z "$PYTHON_BIN" ] && [ -f "$RELEASE_ROOT/RELEASE.json" ]; then
  PYTHON_BIN=$(/usr/bin/plutil -extract runtime_python raw -o - "$RELEASE_ROOT/RELEASE.json" 2>/dev/null || true)
fi
if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN=$(command -v python3 || true)
fi
[ -x "$PYTHON_BIN" ] || { printf '%s\n' "Life Manager runtime Python is unavailable" >&2; exit 69; }
[ -f "$GOVERNOR" ] || { printf '%s\n' "Life Manager disk cleanup governor is unavailable" >&2; exit 69; }

exec "$PYTHON_BIN" -B -c '
from contextlib import ExitStack
from pathlib import Path
import runpy
import sys

release, home, state_dir = map(Path, sys.argv[1:])
governor = release / "skills/self/disk-cleanup/disk_cleanup.py"
sys.path[:0] = [str(release), str(governor.parent)]
sys.argv = [str(governor), "--home", str(home), "--state-dir", str(state_dir)]
with ExitStack() as stack:
    try:
        from runtime.host.bounded_output import bounded_launchd_output
        from runtime.host.storage_policy import load_storage_policy
        policy = load_storage_policy(release / "config/storage-policy.json", "life-manager-disk-cleanup")
        if policy is None:
            raise ValueError("cleanup storage owner is missing")
        stack.enter_context(bounded_launchd_output(
            home / ".local/state/life-manager/life-manager-disk-cleanup/logs", policy))
    except (ImportError, OSError, ValueError) as error:
        print(f"disk-watchdog: diagnostic capture unavailable: {type(error).__name__}", file=sys.stderr)
    runpy.run_path(str(governor), run_name="__main__")
' "$RELEASE_ROOT" "$HOME" "$STATE_DIR"
