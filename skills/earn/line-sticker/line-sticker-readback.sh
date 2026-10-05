#!/usr/bin/env bash
# Sealed releases do not contain .git; derive the root from this script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)" || SCRIPT_DIR=""
LIFE_MANAGER_REPO="${LIFE_MANAGER_REPO:-$(cd "$SCRIPT_DIR/../../.." 2>/dev/null && pwd -P)}"
if [ -z "$LIFE_MANAGER_REPO" ] || [ ! -f "$LIFE_MANAGER_REPO/skills/earn/line-sticker/creators_readback.py" ]; then
  echo "LIFE_MANAGER_REPO could not be resolved" >&2
  exit 2
fi
export LIFE_MANAGER_REPO
# Hourly read-only readback of every submitted LINE sticker set (review state, public store page).
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin:$PATH"
set -uo pipefail
PY="${LIFE_MANAGER_PYTHON:-$HOME/.local/share/life-manager/venv/bin/python}"
[ -x "$PY" ] || { echo "python with playwright is required" >&2; exit 2; }
STATE="${LIFE_MANAGER_STATE_HOME:-$HOME/.local/state/life-manager}/line-sticker"
status=0
for item in "$STATE"/set-*/creators-item.json; do
  [ -f "$item" ] || continue
  "$PY" "$LIFE_MANAGER_REPO/skills/earn/line-sticker/creators_readback.py" --item-file "$item" || status=1
done
exit "$status"
