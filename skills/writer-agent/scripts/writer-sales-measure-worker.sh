#!/usr/bin/env bash
# Hourly receipt collector: external dashboards -> observations -> canonical ledger.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=writer-runtime-env.sh
source "$SCRIPT_DIR/writer-runtime-env.sh"
LOCK_DIR="$STATE_DIR/.sales-measure.lock"
LOCK_HELPER="$LIFE_MANAGER_REPO/runtime/host/owned_directory_lock.py"
BROWSER_GUARD="$LIFE_MANAGER_REPO/skills/browser/browser-guard.sh"
BROWSER_IDENTITY="interactive:dais"
BROWSER_LEASED=0
CLOAK_PYTHON="${WRITER_BROWSER_PYTHON:-$(command -v python3)}"

# The previous release records only a PID in a directory lock. During the
# rollout overlap, never reclaim that legacy lock while its process is live;
# the shared helper owns every new PID/start-identity lock after this gate.
if [ -d "$LOCK_DIR" ] && [ -f "$LOCK_DIR/pid" ]; then
  legacy_pid="$(sed -n '1p' "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [[ "$legacy_pid" =~ ^[0-9]+$ ]] && kill -0 "$legacy_pid" 2>/dev/null; then
    printf 'sales measurement legacy owner is live: pid=%s\n' "$legacy_pid" >&2
    exit 75
  fi
fi

LOCK_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(16))')"
if python3 "$LOCK_HELPER" acquire "$LOCK_DIR" "$$" "$LOCK_TOKEN"; then
  :
else
  exit "$?"
fi

release_lock() {
  if [ "$BROWSER_LEASED" -eq 1 ]; then
    AI_BROWSER_HOLDER_PID=$$ bash "$BROWSER_GUARD" release "$BROWSER_IDENTITY" >/dev/null || \
      printf 'sales measurement browser lease release failed\n' >&2
  fi
  python3 "$LOCK_HELPER" release "$LOCK_DIR" "$$" "$LOCK_TOKEN" >/dev/null
}
trap release_lock EXIT

[ -x "$CLOAK_PYTHON" ] || {
  printf 'sales measurement unavailable: cloak runtime missing\n' >&2
  exit 75
}

if BROWSER_ENDPOINT="$(AI_BROWSER_HOLDER_PID=$$ bash "$BROWSER_GUARD" acquire "$BROWSER_IDENTITY")"; then
  BROWSER_LEASED=1
else
  printf 'sales measurement browser lease unavailable: rc=%s\n' "$?" >&2
  exit 75
fi

WRITER_CDP_ENDPOINT="$BROWSER_ENDPOINT" "$CLOAK_PYTHON" "$SCRIPT_DIR/measure-sales.py" \
  --out "$STATE_DIR/sales-ledger.jsonl"
python3 "$SCRIPT_DIR/money_sync.py" \
  --state-dir "$STATE_DIR" --db "$STATE_DIR/money.sqlite3"
