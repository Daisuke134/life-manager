#!/usr/bin/env bash
# Read PromptBase's official seller dashboard and Sales page once per hourly wake.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd -P)"
PY="${PY:-/opt/homebrew/bin/python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python3
BROWSER_GUARD="${AI_BROWSER_GUARD:-$REPO_ROOT/skills/browser/browser-guard.sh}"
BROWSER_IDENTITY="promptbase:dais"

log() { echo "[promptbase-hourly-readback] $*"; }

ENDPOINT="$(AI_BROWSER_HOLDER_PID=$$ "$BROWSER_GUARD" acquire "$BROWSER_IDENTITY" 2>/dev/null)"
ACQUIRE_RC=$?
if [ "$ACQUIRE_RC" -ne 0 ]; then
  log "browser lease unavailable (rc=$ACQUIRE_RC) -- skip this wake; next hour retries"
  exit 75
fi

cleanup() {
  AI_BROWSER_HOLDER_PID=$$ "$BROWSER_GUARD" release "$BROWSER_IDENTITY" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM HUP

log "reading the official PromptBase Sales page"
"$PY" "$REPO_ROOT/skills/earn/promptbase/scripts/readback.py" --endpoint "$ENDPOINT" --sales-only
