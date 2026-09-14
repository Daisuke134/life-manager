#!/usr/bin/env bash
# Supervise the single launchd-owned Capafy daily pass. Do not create a second
# tmux/Claude scheduler: ai.anicca.capafy-loop-daily is the only execution owner.
set -uo pipefail

LABEL="ai.anicca.capafy-loop-daily"
LOOP_ID="capafy-loop-daily"
DOMAIN="gui/$(id -u)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RELEASE_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
LIFE_MANAGER_STATE_HOME="${LIFE_MANAGER_STATE_HOME:-$HOME/.local/state/life-manager}"
MARK="$LIFE_MANAGER_STATE_HOME/state/capafy-autopublish/.capafy-healthy-pass"
LOG="$LIFE_MANAGER_STATE_HOME/logs/capafy-loop-healthcheck.log"
EVIDENCE_ROOT="$LIFE_MANAGER_STATE_HOME/state/agent-runner-evidence/capafy-marketplace"
OFFLINE_EVIDENCE_ROOT="$LIFE_MANAGER_STATE_HOME/state/agent-runner-evidence/capafy-offline-build"
BACKOFF="$LIFE_MANAGER_STATE_HOME/state/capafy-provider-backoff.json"
EVENTS="$LIFE_MANAGER_STATE_HOME/events.jsonl"
STALE_SECONDS=$((30 * 60 * 60))
ATTEMPT_GRACE_SECONDS=$((2 * 60 * 60))
mkdir -p "$(dirname "$LOG")"

# Provider admission is checked on every five-minute wake, independently of
# scheduler freshness. The gate performs a bounded per-key limit repair and
# verifies it with a live request; provider failure must not restart the owner.
KEY_GATE="$RELEASE_ROOT/skills/capafy-autopublish/scripts/key_health_gate.sh"
if ! KEY_HEALTH="$(bash "$KEY_GATE" 2>&1)"; then
  echo "$(date '+%F %T') provider admission unhealthy; no owner restart; $KEY_HEALTH" >>"$LOG"
  exit 0
fi
case "$KEY_HEALTH" in
  *KEY_SELF_HEAL=OK*) echo "$(date '+%F %T') provider admission self-healed; $KEY_HEALTH" >>"$LOG" ;;
esac

OWNER_STATUS="$(launchctl print "$DOMAIN/$LABEL" 2>/dev/null)" || OWNER_STATUS=""

now="$(date +%s)"
mtime="$(stat -f %m "$MARK" 2>/dev/null || echo 0)"
age=$((now - mtime))
if [ "$mtime" -gt 0 ] && [ "$age" -lt "$STALE_SECONDS" ]; then
  exit 0
fi

# A recent attempt proves launchd is scheduling the owner. Let the hourly
# cadence retry it; the five-minute monitor must not overlap or amplify it.
LATEST_START="$({
  find "$EVIDENCE_ROOT" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; 2>/dev/null
  find "$OFFLINE_EVIDENCE_ROOT" -mindepth 1 -maxdepth 1 -type d -exec basename {} \; 2>/dev/null
} | cut -d- -f1 | sort -n | tail -1)"
case "$LATEST_START" in
  ''|*[!0-9]*) ;;
  *)
    if [ $((now - LATEST_START)) -lt "$ATTEMPT_GRACE_SECONDS" ]; then
      exit 0
    fi
    ;;
esac

# A fresh successful owner terminal is stronger truth than the legacy healthy
# marker. Do not restart a healthy hourly owner merely because that marker is old.
if [ -n "$OWNER_STATUS" ] && printf '%s\n' "$OWNER_STATUS" | grep -q 'last exit code = 0' \
  && python3 - "$EVENTS" "$now" "$STALE_SECONDS" <<'PY'
import datetime as dt
import json
import sys

path, now, stale = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
latest = None
try:
    for line in open(path, encoding="utf-8"):
        row = json.loads(line)
        if row.get("loop_id") == "capafy-loop-daily" and row.get("phase") == "report":
            latest = row
except (OSError, ValueError, TypeError):
    raise SystemExit(1)
if not latest or latest.get("status") != "pass":
    raise SystemExit(1)
stamp = str(latest.get("timestamp") or "").replace("Z", "+00:00")
try:
    observed = int(dt.datetime.fromisoformat(stamp).timestamp())
except ValueError:
    raise SystemExit(1)
raise SystemExit(0 if now - observed < stale else 1)
PY
then
  exit 0
fi

# Provider quota is not a dead scheduler. The hourly owner will try again on
# its normal cadence; a five-minute kickstart here only amplifies the outage.
LATEST_SUMMARY="$(find "$EVIDENCE_ROOT" -mindepth 2 -maxdepth 2 -type f -name summary.json 2>/dev/null | sort | tail -1)"
LATEST="${LATEST_SUMMARY%/summary.json}"
if [ -n "$LATEST" ] && python3 - "$LATEST/summary.json" "$LATEST/attempts.jsonl" <<'PY'
import json
import sys

try:
    summary = json.load(open(sys.argv[1], encoding="utf-8"))
    attempts = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8") if line.strip()]
except (OSError, ValueError, TypeError):
    raise SystemExit(1)
raise SystemExit(0 if summary.get("status") == "failed" and attempts
                 and all(row.get("error_class") == "transient_quota" for row in attempts) else 1)
PY
then
  next_eligible=$((now + 60 * 60))
  mkdir -p "$(dirname "$BACKOFF")"
  python3 - "$BACKOFF" "$now" "$next_eligible" <<'PY'
import json
import os
import sys
import tempfile

target, observed, eligible = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
fd, temporary = tempfile.mkstemp(prefix=".capafy-provider-backoff.", dir=os.path.dirname(target))
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"error_class": "transient_quota", "observed_at_epoch": observed,
                   "next_eligible_at_epoch": eligible}, handle, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY
  echo "$(date '+%F %T') provider quota; hourly owner backoff until epoch $next_eligible; no kickstart" >>"$LOG"
  exit 0
fi

# A stale/missing terminal receipt means the real launchd loop needs a pass.
# Delegate lifecycle mutation to the release-local control plane; never spawn a
# parallel executor or mutate launchd directly here.
if "$RELEASE_ROOT/bin/lm-loop" restart "$LOOP_ID"; then
  echo "$(date '+%F %T') stale healthy-pass (${age}s); restarted $LABEL" >>"$LOG"
  exit 0
fi

echo "$(date '+%F %T') failed to restart $LABEL" >>"$LOG"
exit 1
