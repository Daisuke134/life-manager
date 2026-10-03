#!/usr/bin/env bash
# Start camofox-browser server on :9377 if not running.
#
# self-fix 2026-07-12: a bare HTTP-200-on-/health check is not enough. The server's Node wrapper
# can stay alive (200 OK) for hours after its underlying browser has died (browserConnected:false,
# e.g. after the Camoufox binaries went missing from ~/Library/Caches/camoufox/, or a health-probe
# restart got stuck) -- "already running" was true but nothing could actually open a tab, and
# nobody noticed because this script never looked past the HTTP status code. Now we parse the
# health body and force a real restart (via stop.sh, fixed the same pass -- see its header)
# whenever the wrapper is up but the browser inside it is not.
set -uo pipefail

LIFE_MANAGER_REPO="${LIFE_MANAGER_REPO:-$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$LIFE_MANAGER_REPO" ] || { echo "LIFE_MANAGER_REPO could not be resolved" >&2; exit 2; }
CAMOFOX_DIR="${CAMOFOX_DIR:-}"
if [ -z "$CAMOFOX_DIR" ]; then
  CAMOFOX_DIR="$(bash "$LIFE_MANAGER_REPO/skills/camofox-browser/fetch.sh")"
fi
LOG="/tmp/camofox.log"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_DIR="/tmp/camofox-browser-lifecycle.lock"

# start.sh and stop.sh are called by several independent loops.  Without a
# cross-script lock, two callers can both observe a dead browser; the second
# caller then stops the server that the first caller has just started.  That
# produced the misleading "healthy, then gone before POST /tabs" failure.
acquire_lock(){
  while ! mkdir "$LOCK_DIR" 2>/dev/null; do
    owner="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
    if [ -n "$owner" ] && ! kill -0 "$owner" 2>/dev/null; then
      rm -f "$LOCK_DIR/pid" 2>/dev/null || true
      rmdir "$LOCK_DIR" 2>/dev/null || true
    else
      sleep 1
    fi
  done
  echo "$$" > "$LOCK_DIR/pid"
  trap 'rm -f "$LOCK_DIR/pid" 2>/dev/null || true; rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT
}
acquire_lock

health_json(){ curl -sSf --max-time 5 http://localhost:9377/health 2>/dev/null; }
browser_ok(){ printf '%s' "$1" | python3 -c "import json,sys; d=json.load(sys.stdin); print('1' if d.get('browserConnected') else '0')" 2>/dev/null || echo 0; }

HB="$(health_json)"
if [ -n "$HB" ]; then
  if [ "$(browser_ok "$HB")" = "1" ]; then
    echo "camofox already running (browser connected)"
    echo "$HB"
    exit 0
  fi
  echo "camofox wrapper is up but browser is DOWN (browserConnected:false) -- forcing a real restart" >&2
  # We already hold the lifecycle lock; calling stop.sh here would deadlock.
  PORT_PID="$(lsof -ti :9377 2>/dev/null || true)"
  [ -n "$PORT_PID" ] && kill $PORT_PID 2>/dev/null || true
  pkill -f "node.*camofox-browser" 2>/dev/null || true
  pkill -f "Camoufox.app" 2>/dev/null || true
  sleep 1
  PORT_PID="$(lsof -ti :9377 2>/dev/null || true)"
  [ -n "$PORT_PID" ] && kill -9 $PORT_PID 2>/dev/null || true
fi

if [ ! -d "$CAMOFOX_DIR" ]; then
  echo "ERROR: verified Camofox source is unavailable at $CAMOFOX_DIR." >&2
  exit 1
fi

cd "$CAMOFOX_DIR"

# A healthy HTTP wrapper can still be unable to create tabs when the Camoufox
# payload was removed from the local cache.  Install it before starting the
# server so callers never receive a misleading browserConnected=true state.
CAMOUFOX_VERSION="$HOME/Library/Caches/camoufox/version.json"
if [ ! -f "$CAMOUFOX_VERSION" ]; then
  echo "Camoufox payload missing; fetching it before server start..." >&2
  if ! npx camoufox-js fetch >>"$LOG" 2>&1; then
    echo "ERROR: camoufox-js fetch failed; see $LOG" >&2
    tail -30 "$LOG" >&2
    exit 1
  fi
fi

# fetch.sh uses `npm ci --ignore-scripts` so a cache refresh does not execute
# package hooks.  That leaves better-sqlite3 without the Node-ABI-specific
# module required by Camoufox's persistence support.  On Node 25/macOS arm64
# there is no downloadable prebuild, so the wrapper otherwise starts but every
# browser launch fails.  Opening an in-memory database verifies the binding
# itself (a bare require does not); rebuild only when that probe fails.
NODE_BIN="$(command -v node)"
sqlite_binding_ok() {
  "$NODE_BIN" -e "const Database=require('better-sqlite3'); const db=new Database(':memory:'); db.close()" \
    >/dev/null 2>&1
}
if ! sqlite_binding_ok; then
  echo "better-sqlite3 native binding missing for $("$NODE_BIN" -v); rebuilding locally..." >&2
  if ! npm rebuild better-sqlite3 --build-from-source >>"$LOG" 2>&1 || ! sqlite_binding_ok; then
    echo "ERROR: better-sqlite3 native rebuild failed; see $LOG" >&2
    tail -30 "$LOG" >&2
    exit 1
  fi
fi

# Launch the node process directly.  `npm start` leaves an npm wrapper in the
# process group; automation runners may reap that group when this script
# exits, taking the otherwise-healthy server with it.
nohup "$NODE_BIN" "$CAMOFOX_DIR/server.js" </dev/null >"$LOG" 2>&1 &
PID=$!
echo "started camofox pid=$PID, waiting..."
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  sleep 2
  HB="$(health_json)"
  [ -z "$HB" ] && continue
  if [ "$(browser_ok "$HB")" = "1" ]; then
    echo "$HB"
    exit 0
  fi
done
echo "ERROR: camofox server started but browser never connected within 30s; see $LOG" >&2
tail -30 "$LOG" >&2
exit 1
