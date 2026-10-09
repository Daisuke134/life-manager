#!/bin/sh
set -eu

HOME_DIR=${HOME:?HOME is required}
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
RELEASE_ROOT="$HOME_DIR/loops/current"
WATCHDOG="$HOME_DIR/.local/bin/disk-watchdog.sh"
[ -x "$WATCHDOG" ] || {
  printf '%s\n' "stable disk watchdog is unavailable" >&2
  exit 69
}
PYTHON_BIN=${LIFE_MANAGER_RUNTIME_PYTHON:-}
if [ -z "$PYTHON_BIN" ] && [ -f "$RELEASE_ROOT/RELEASE.json" ]; then
  PYTHON_BIN=$(/usr/bin/plutil -extract runtime_python raw -o - "$RELEASE_ROOT/RELEASE.json" 2>/dev/null || true)
fi
if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN=$(command -v python3 || true)
fi
[ -x "$PYTHON_BIN" ] || {
  printf '%s\n' "Life Manager runtime Python is unavailable" >&2
  exit 69
}

is_cleanup_lock_busy() {
  printf '%s\n' "$1" | "$PYTHON_BIN" -c '
import json, sys

def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result

def reject_constant(value):
    raise ValueError("non-standard JSON constant")

try:
    receipt = json.load(
        sys.stdin,
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )
except (ValueError, UnicodeDecodeError):
    raise SystemExit(1)
valid = (
    type(receipt) is dict
    and receipt.get("ok") is False
    and receipt.get("status") == "deferred"
    and receipt.get("reason") == "cleanup_lock_busy"
    and type(receipt.get("effect")) is int
    and receipt["effect"] == 0
    and type(receipt.get("readback")) is int
    and receipt["readback"] == 0
)
raise SystemExit(0 if valid else 1)
' >/dev/null 2>&1
}

attempt=1
while [ "$attempt" -le 3 ]; do
  if output=$("$WATCHDOG" 2>&1); then
    printf '%s\n' "$output"
    exit 0
  else
    status=$?
  fi
  printf '%s\n' "$output"
  if [ "$status" -ne 75 ] || ! is_cleanup_lock_busy "$output"; then
    exit "$status"
  fi
  [ "$attempt" -lt 3 ] || exit "$status"
  attempt=$((attempt + 1))
  sleep 5
done

exit 75
