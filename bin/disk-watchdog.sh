#!/bin/sh
set -eu

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
# HostDiskGovernor keeps minute sweeps fast and runs a bounded full census when due.
export LIFE_MANAGER_DISK_WATCHDOG=1
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
# Ballast: swap lives on the Data volume, so a full disk froze the Mac (2026-10-14).
# Hold real allocated space while healthy and release it the moment free space is critical.
BALLAST="$HOME/.local/state/life-manager/disk-ballast"
FREE_KB=${LIFE_MANAGER_DISK_FREE_KB:-$(df -k "$HOME" 2>/dev/null | awk 'NR==2 {print $4}')}
case "$FREE_KB" in
  ''|*[!0-9]*) ;;
  *)
    if [ -f "$BALLAST" ] && [ "$FREE_KB" -lt 3145728 ]; then
      rm -f "$BALLAST" && printf '%s\n' "disk-watchdog: ballast released free_kb=$FREE_KB" >&2
    elif [ ! -e "$BALLAST" ] && [ "$FREE_KB" -gt 26214400 ] && [ -d "${BALLAST%/*}" ]; then
      /usr/sbin/mkfile "${LIFE_MANAGER_BALLAST_SIZE:-8g}" "$BALLAST" || rm -f "$BALLAST"
    fi ;;
esac

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
