#!/usr/bin/env bash
# Recover the persistent browser through its canonical launchd owner.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

CDP="${CLOAK_CDP_BASE_URL:-http://127.0.0.1:9222}"
CDP_PORT="${CDP_DAILY_DRIVER_PORT:-${CDP##*:}}"
LOG="${CDP_GUARD_LOG:-${LIFE_MANAGER_HOME:-${XDG_STATE_HOME:-$HOME/.local/state}/life-manager}/logs/cdp-daily-driver-guard.log}"
GUARD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../earn/gig/scripts/cdp_daily_driver_guard.sh"
export CDP_DAILY_DRIVER_PORT="$CDP_PORT"
export SESSION_VAULT_PORT="${SESSION_VAULT_PORT:-$CDP_PORT}"

alive() { curl -s --max-time 4 "$CDP/json/version" >/dev/null 2>&1; }
wait_for_alive() {
  local waited=0
  while [ "$waited" -lt 45 ]; do
    alive && return 0
    sleep 1
    waited=$((waited + 1))
  done
  return 1
}
post_recovery() {
  python3 "$(dirname "${BASH_SOURCE[0]}")/scripts/session_vault.py" restore >> "$LOG" 2>&1 || true
  if [ -n "${CLOAK_BROWSER_OWNER:-}" ]; then
    python3 "$(dirname "${BASH_SOURCE[0]}")/scripts/cdp_tab_gc.py" --owner "$CLOAK_BROWSER_OWNER" >> "$LOG" 2>&1 || true
  fi
  # Only the already-alive fast path (below) used to run this; a lane that woke into a
  # crashed browser and recovered it here got no lease reap at all until the next lucky
  # already-alive wake. acquire() now self-reclaims a dead-pid holder of its own task on
  # every call, but a task nobody has re-acquired since its holder died still leaks its
  # context until something calls gc -- so recovery wakes need this backstop too.
  start_context_gc
}

# Context disposal is maintenance, not part of browser admission. A stale ledger can
# contain many rows and every CDP disposal has its own bounded network deadline. Waiting
# for all of them here made unrelated marketplace wakes time out, kill only this shell,
# and leave the reaper behind. The reaper itself is single-flight per ledger, so callers
# launch it detached and continue as soon as the browser is known alive.
start_context_gc() {
  mkdir -p "$(dirname "$LOG")"
  python3 "$(dirname "${BASH_SOURCE[0]}")/scripts/cdp_context_lease.py" gc --idle-min 45 \
    >> "$LOG" 2>&1 </dev/null &
}

if alive; then
  start_context_gc
  echo "ALIVE"
  exit 0
fi

mkdir -p "$(dirname "$LOG")"
echo "$(date '+%F %T') ensure_browser: :$CDP_PORT dead -> managed recovery" >> "$LOG"
if [ -n "${CLOAK_BROWSER_LAUNCHD_LABEL:-}" ]; then
  case "$CLOAK_BROWSER_LAUNCHD_LABEL" in
    *[!A-Za-z0-9._-]*) echo "FAILED: invalid browser launchd label"; exit 1 ;;
  esac
  if launchctl kickstart -k "gui/$(id -u)/$CLOAK_BROWSER_LAUNCHD_LABEL" \
      >> "$LOG" 2>&1 && wait_for_alive; then
    post_recovery
    echo "$(date '+%F %T') ensure_browser: RECOVERED by launchd owner $CLOAK_BROWSER_LAUNCHD_LABEL" >> "$LOG"
    echo "RECOVERED"
    exit 0
  fi
  echo "$(date '+%F %T') ensure_browser: FAILED launchd-owner recovery" >> "$LOG"
  echo "FAILED"
  exit 1
fi

if [ ! -f "$GUARD" ]; then
  echo "FAILED: persistent browser guard missing"
  exit 1
fi

source "$GUARD"
if cdp_guard_ensure_healthy 4 45; then
  post_recovery
  echo "$(date '+%F %T') ensure_browser: RECOVERED by persistent owner" >> "$LOG"
  echo "RECOVERED"
  exit 0
fi

echo "$(date '+%F %T') ensure_browser: FAILED to recover" >> "$LOG"
echo "FAILED"
exit 1
