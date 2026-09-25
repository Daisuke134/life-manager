#!/usr/bin/env bash
# Canonical bounded Connector pass. This script owns only local lifecycle state;
# the worker owns no global schedule or completion claim.
set -eu
umask 077

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$HERE/../.." && pwd -P)"
[ -f "$REPO_ROOT/apps/life-manager/lib/connector-minimal-production.js" ] || {
  printf 'Connector native repository unavailable\n' >&2
  exit 2
}

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export CLOAK_CDP_BASE_URL="${CLOAK_CDP_BASE_URL:-}"
export CLOAK_BROWSER_OWNER="${LIFE_MANAGER_BROWSER_TARGET_OWNER:-}"
LIFE_MANAGER_STATE_HOME="${LIFE_MANAGER_STATE_HOME:-${XDG_STATE_HOME:-$HOME/.local/state}/life-manager}"
LM_CONNECTOR_SHARED_ENV_FILE="${LM_CONNECTOR_SHARED_ENV_FILE:-$LIFE_MANAGER_STATE_HOME/.env}"
export LM_CONNECTOR_SHARED_ENV_FILE

STATE_DIR="${LM_CONNECTOR_STATE_DIR:-$LIFE_MANAGER_STATE_HOME/connector-native}"
case "$STATE_DIR" in
  /*) ;;
  *) printf 'Connector native state directory unavailable\n' >&2; exit 2 ;;
esac
NODE_BIN="${NODE_BIN:-$(command -v node || true)}"
[ -n "$NODE_BIN" ] && [ -x "$NODE_BIN" ] || {
  printf 'Connector native node unavailable\n' >&2
  exit 2
}
"$NODE_BIN" "$HERE/lib/load-connector-env.js" "$LM_CONNECTOR_SHARED_ENV_FILE" || exit 2
LOCK_STALE_MS="${LM_CONNECTOR_LOCK_STALE_MS:-900000}"
OWNER_TOKEN="$($NODE_BIN "$HERE/lib/native-state.js" token)" || {
  printf 'Connector native owner unavailable\n' >&2
  exit 2
}

release_lock() {
  "$NODE_BIN" "$HERE/lib/native-state.js" release "$STATE_DIR" "$OWNER_TOKEN" >/dev/null 2>&1 || true
}

BROWSER_GUARD="$REPO_ROOT/skills/browser/browser-guard.sh"
BROWSER_FOUNDATION="$REPO_ROOT/skills/browser/ensure_browser.sh"
BROWSER_TAB_GC="$REPO_ROOT/skills/browser/scripts/cdp_tab_gc.py"
BROWSER_IDENTITY="${LIFE_MANAGER_BROWSER_IDENTITY:-}"
if [ -z "$BROWSER_IDENTITY" ] || [ -z "$CLOAK_BROWSER_OWNER" ]; then
  BROWSER_JOIN="$(python3 - "$REPO_ROOT/config/loop-registry.json" <<'PY'
import json, sys
try:
    value = json.load(open(sys.argv[1], encoding="utf-8"))
    row = value["loops"]["life-manager-connector-native"]
    print(row["browser_identity"], row["browser_target_owner"])
except (OSError, KeyError, TypeError, ValueError):
    raise SystemExit(1)
PY
)" || {
  printf 'Connector browser identity unavailable\n' >&2
  exit 2
}
  if [ -z "$BROWSER_IDENTITY" ]; then BROWSER_IDENTITY="${BROWSER_JOIN%% *}"; fi
  if [ -z "$CLOAK_BROWSER_OWNER" ]; then CLOAK_BROWSER_OWNER="${BROWSER_JOIN#* }"; fi
fi
[ -n "$BROWSER_IDENTITY" ] && [ -n "$CLOAK_BROWSER_OWNER" ] || {
  printf 'Connector browser join unavailable\n' >&2
  exit 2
}
export CLOAK_BROWSER_OWNER

BROWSER_LEASED=0
release_browser() {
  [ "$BROWSER_LEASED" -eq 1 ] || return 0
  "$BROWSER_GUARD" release "$BROWSER_IDENTITY" >/dev/null 2>&1 || true
  BROWSER_LEASED=0
}
release_all() {
  release_browser
  release_lock
}

LOCK_RESULT="$($NODE_BIN "$HERE/lib/native-state.js" acquire "$STATE_DIR" "$OWNER_TOKEN" "$$" "$LOCK_STALE_MS")" || {
  printf 'Connector native lock unavailable\n' >&2
  exit 2
}
case "$LOCK_RESULT" in
  '{"status":"acquired"}') ;;
  '{"status":"busy"}') exit 75 ;;
  *) printf 'Connector native lock unavailable\n' >&2; exit 2 ;;
esac
trap release_all EXIT

"$NODE_BIN" "$HERE/lib/native-state.js" heartbeat "$STATE_DIR" "$OWNER_TOKEN" native_started >/dev/null || exit 2

# Resolve the browser identity from the canonical browser registry before any provider
# page work. The guard selects the live host/port by profile ownership, so a proxy or an
# IPv4/IPv6 port collision cannot be mistaken for the daily-driver.
[ -x "$BROWSER_GUARD" ] || {
  printf 'Connector browser foundation unavailable: %s\n' "$BROWSER_GUARD" >&2
  "$NODE_BIN" "$HERE/lib/native-state.js" heartbeat "$STATE_DIR" "$OWNER_TOKEN" browser_foundation_missing >/dev/null 2>&1 || true
  exit 2
}
BROWSER_ENDPOINT=""
if BROWSER_ENDPOINT="$(AI_BROWSER_HOLDER_PID=$$ bash "$BROWSER_GUARD" acquire "$BROWSER_IDENTITY" 2>&1)"; then
  BROWSER_LEASED=1
else
  BROWSER_RC=$?
  if [ "$BROWSER_RC" -eq 10 ] && [ -x "$BROWSER_FOUNDATION" ]; then
    # Recovery is still owned by the existing daily-driver supervisor. Its probe is
    # forced to IPv6 because this host currently has an unrelated IPv4 :9222 listener.
    BROWSER_PORT="${CDP_DAILY_DRIVER_PORT:-9222}"
    BROWSER_BASE="http://[::1]:$BROWSER_PORT"
    BROWSER_STATUS="$(CLOAK_CDP_BASE_URL="$BROWSER_BASE" CDP_DAILY_DRIVER_PORT="$BROWSER_PORT" \
      CLOAK_BROWSER_OWNER="$CLOAK_BROWSER_OWNER" bash "$BROWSER_FOUNDATION" 2>&1 | tail -n 1)" || BROWSER_STATUS="FAILED"
    case "$BROWSER_STATUS" in
      ALIVE|RECOVERED) ;;
      *)
        printf 'Connector browser foundation unavailable: %s\n' "${BROWSER_STATUS:-EMPTY}" >&2
        "$NODE_BIN" "$HERE/lib/native-state.js" heartbeat "$STATE_DIR" "$OWNER_TOKEN" browser_foundation_failed >/dev/null 2>&1 || true
        exit 75
        ;;
    esac
    BROWSER_ENDPOINT="$(AI_BROWSER_HOLDER_PID=$$ bash "$BROWSER_GUARD" acquire "$BROWSER_IDENTITY" 2>&1)" || {
      printf 'Connector browser lease unavailable after recovery: %s\n' "$BROWSER_ENDPOINT" >&2
      "$NODE_BIN" "$HERE/lib/native-state.js" heartbeat "$STATE_DIR" "$OWNER_TOKEN" browser_lease_failed >/dev/null 2>&1 || true
      exit 75
    }
    BROWSER_LEASED=1
  else
    printf 'Connector browser lease unavailable: %s\n' "$BROWSER_ENDPOINT" >&2
    "$NODE_BIN" "$HERE/lib/native-state.js" heartbeat "$STATE_DIR" "$OWNER_TOKEN" browser_lease_failed >/dev/null 2>&1 || true
    exit 75
  fi
fi
case "$BROWSER_ENDPOINT" in
  http://127.0.0.1:*|http://localhost:*|http://\[::1\]:*) ;;
  *)
    printf 'Connector browser endpoint invalid: %s\n' "$BROWSER_ENDPOINT" >&2
    exit 75
    ;;
esac
export CLOAK_CDP_BASE_URL="$BROWSER_ENDPOINT"
if ! python3 "$BROWSER_TAB_GC" --owner "$CLOAK_BROWSER_OWNER" >/dev/null 2>&1; then
  printf 'Connector browser tab GC failed; continuing with provider readback fence\n' >&2
fi

if "$NODE_BIN" "$HERE/native-pass.js" \
  --repo-root "$REPO_ROOT" \
  --state-dir "$STATE_DIR" \
  --owner-token "$OWNER_TOKEN"; then
  "$NODE_BIN" "$HERE/lib/native-state.js" heartbeat "$STATE_DIR" "$OWNER_TOKEN" worker_finished >/dev/null || exit 2
  exit 0
else
  EXIT_CODE=$?
  if [ "$EXIT_CODE" -ge 128 ]; then
    OBSERVER_ID="${OWNER_TOKEN:0:24}"
    "$NODE_BIN" "$HERE/lib/observer-envelope.js" process-crash \
      "$STATE_DIR/observer-replay.jsonl" \
      "wake:$OBSERVER_ID" "run:$OBSERVER_ID" \
      "${LM_CONNECTOR_CODE_COMMIT:-unknown}" || exit 2
    "$NODE_BIN" "$HERE/minimal-crash-report.js" \
      --repo-root "$REPO_ROOT" \
      --state-dir "$STATE_DIR" \
      --owner-token "$OWNER_TOKEN" || exit 2
  fi
  "$NODE_BIN" "$HERE/lib/native-state.js" heartbeat "$STATE_DIR" "$OWNER_TOKEN" worker_failed >/dev/null 2>&1 || true
  exit "$EXIT_CODE"
fi
