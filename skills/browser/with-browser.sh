#!/usr/bin/env bash
# Hold one registered browser identity for exactly one command lifetime.
set -uo pipefail

IDENTITY="${1:-}"
shift || true
[ "${1:-}" = "--" ] && shift

if [ -z "$IDENTITY" ] || [ "$#" -eq 0 ]; then
  echo "usage: with-browser.sh IDENTITY -- command..." >&2
  exit 64
fi

# Target IDs are unique only within one CDP endpoint. Keep each registered browser's
# ownership ledger separate so a GC reading another endpoint cannot prune this command's tab.
IDENTITY_KEY="$(printf '%s' "$IDENTITY" | shasum -a 256 | awk '{print $1}')"
export CLOAK_TARGET_OWNERS_FILE="$HOME/.cloak/vault/target-owners/$IDENTITY_KEY.json"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD="${AI_BROWSER_GUARD:-$HERE/browser-guard.sh}"
ENSURE="${AI_ENSURE_PROVISION_BROWSER:-$HERE/ensure_provision_browser.sh}"
WAIT_SECONDS="${BROWSER_WAIT_SECONDS:-300}"
CDP=""
deadline=$(( $(date +%s) + WAIT_SECONDS ))
ensure_attempted=0

while :; do
  # Command substitution runs acquire in a short-lived shell. Bind the lease to this wrapper,
  # which remains alive until the browser command and its official readback have both exited.
  CDP="$(AI_BROWSER_HOLDER_PID=$$ "$GUARD" acquire "$IDENTITY" 2>/dev/null)"
  acquire_status=$?
  [ "$acquire_status" -eq 0 ] && break
  # Exit 10 is identity-unreachable, not BUSY. Provision only through the guarded shared
  # launcher, and bind the launcher's lease to this same wrapper so there is no lease gap.
  # Exit 9 remains a genuine live-owner collision and continues to wait without interference.
  if [ "$acquire_status" -eq 10 ] && [ "$ensure_attempted" -eq 0 ] && [ -x "$ENSURE" ]; then
    ensure_attempted=1
    CDP="$(AI_BROWSER_HOLDER_PID=$$ bash "$ENSURE" "$IDENTITY" 2>/dev/null)" && break
  fi
  if [ "$(date +%s)" -ge "$deadline" ]; then
    if [ "$acquire_status" -eq 10 ]; then
      echo "with-browser: $IDENTITY unreachable after guarded startup attempt" >&2
      exit 10
    fi
    echo "with-browser: $IDENTITY busy for ${WAIT_SECONDS}s" >&2
    exit 75
  fi
  sleep 10
done

released=0
child=0
release_once() {
  [ "$released" -eq 1 ] && return
  released=1
  [ "$child" -ne 0 ] && kill -TERM "$child" 2>/dev/null || true
  "$GUARD" release "$IDENTITY" >/dev/null 2>&1 || true
}
trap release_once EXIT INT TERM HUP

# The caller may inherit a launchd/static endpoint (for example the shared :9223
# daily-driver).  The guard's resolved endpoint is authoritative for this identity;
# pass it through both names so Python adapters cannot accidentally reconnect to the
# inherited port, especially inside a sandbox that intentionally denies that port.
CDP_PORT="${CDP##*:}"
CDP_PORT="${CDP_PORT%%/*}"
case "$CDP_PORT" in
  ''|*[!0-9]*)
    echo "with-browser: resolved endpoint has no valid port: $CDP" >&2
    exit 10
    ;;
esac
export CLOAK_CDP_BASE_URL="$CDP"
export CDP
# These are compatibility variables consumed by older gig adapters.  Keep them
# derived from the leased endpoint so a dynamic DevToolsActivePort cannot leave a
# stale :9223/:9222 sandbox or health probe behind.
export CDP_DAILY_DRIVER_PORT="$CDP_PORT"
export SESSION_VAULT_PORT="$CDP_PORT"
export GIG_CDP_HEALTH_URL="${CDP%/}/json/version"
"$@" &
child=$!
wait "$child"
status=$?
release_once
exit "$status"
