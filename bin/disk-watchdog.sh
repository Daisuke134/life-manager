#!/bin/sh
set -eu

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
RELEASE_ROOT="$HOME/loops/current"
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

exec "$PYTHON_BIN" "$GOVERNOR" --home "$HOME" --state-dir "$STATE_DIR"
