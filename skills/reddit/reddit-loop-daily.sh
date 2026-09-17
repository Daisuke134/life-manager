#!/usr/bin/env bash
# reddit-loop-daily.sh — DETERMINISTIC daily trigger for the Reddit demand-gen loop (self-fix
# 2026-07-12: found via live audit that the tmux STARTUP prompt's self-registered `CronCreate
# "0 10 * * *"` never actually persisted a recurring pass — the always-on tmux session
# (anicca-reddit-loop) ran ONE real pass at its Jul 10 09:55 startup (commit 0f6dca06, posted to
# r/IMadeThis) then sat idle for 2+ days with zero subsequent activity; posts.jsonl went stale for
# 30h+ and the healthcheck's output-freshness guard kept escalating to self-fix, which repeatedly
# spawned fixer sessions (many of which themselves hung) instead of fixing the actual scheduling
# gap. Root cause: an in-session model/tmux process is not a real
# OS/gateway scheduler — CronCreate jobs are session-scoped, in-memory, and gone once the session
# ends or (per the tool's own docs) simply never a durable trigger to begin with. This is the exact
# bug already found+fixed for capafy-loop (commit 41938abe) and life-manager/connector before it;
# same fix here: copy the proven connector_fill_gaps.sh / capafy-loop-daily.sh pattern — a launchd
# StartCalendarInterval job calls THIS script directly, once a day, bounded + timeout-guarded, no
# reliance on the LLM self-scheduling itself.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin:$PATH"
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
RUN_AGENT="${RUN_AGENT_BIN:-$REPO_ROOT/skills/earn/marketing-engine/run_agent.sh}"
if [ "${AGENT_WIRING_PROBE_ONLY:-0}" = "1" ]; then
  printf '{"task_class":"tool-agent","runner":"%s"}\n' "$RUN_AGENT"
  exit 0
fi
STATE_ROOT="${REDDIT_STATE_ROOT:-$HOME/.local/state/life-manager/reddit}"
STATE="${REDDIT_STATE_DIR:-$STATE_ROOT/state}"
LOG="${REDDIT_LOG_FILE:-$STATE_ROOT/logs/reddit-loop-daily.log}"
mkdir -p "$(dirname "$LOG")"
mkdir -p "$STATE"
export LIFE_MANAGER_REPO="${LIFE_MANAGER_REPO:-$REPO_ROOT}"
export REDDIT_STATE_DIR="$STATE"
set -a
. "${LIFE_MANAGER_ENV_FILE:-$HOME/.local/state/life-manager/.env}" 2>/dev/null || true
set +a
echo "=== reddit-loop-daily run $(date '+%F %T %Z') ===" >>"$LOG"

# Camofox auth is isolated by (userId, sessionKey). Reuse the account's stored
# session instead of silently falling back to the anonymous `anicca/default`
# profile, which makes Reddit look unavailable and prevents verified posting.
if [ -z "${CF_USER:-}" ] || [ -z "${CF_SESSION:-}" ]; then
  ACCOUNT_SESSION_FILE="${RD_ACCOUNTS:-$HOME/.cloak/reddit-accounts.json}"
  SESSION_FIELDS="$(${PYTHON:-python3} - "$ACCOUNT_SESSION_FILE" <<'PY' 2>/dev/null
import json, sys
try:
    value = json.load(open(sys.argv[1], encoding="utf-8"))
    accounts = value if isinstance(value, list) else value.get("accounts", [])
    session = next(
        (row.get("camofox_session") for row in accounts
         if isinstance(row, dict) and isinstance(row.get("camofox_session"), dict)),
        {},
    )
    print("\t".join((str(session.get("userId") or ""), str(session.get("sessionKey") or ""))))
except (OSError, TypeError, ValueError, json.JSONDecodeError):
    print("\t")
PY
  )"
  IFS=$'\t' read -r STORED_CF_USER STORED_CF_SESSION <<<"$SESSION_FIELDS"
  [ -n "${CF_USER:-}" ] || CF_USER="$STORED_CF_USER"
  [ -n "${CF_SESSION:-}" ] || CF_SESSION="$STORED_CF_SESSION"
  export CF_USER CF_SESSION
fi

# launchd does not provide PROMPT. Preserve an injected prompt when present, but
# keep the deterministic trigger runnable under `set -u` when it is absent.
PROMPT="${PROMPT:-} Perform one full Reddit loop pass now. Run $REPO_ROOT/skills/reddit/loop.sh to measure canonical state, heal Camofox through $REPO_ROOT/skills/camofox-browser when needed, then make exactly one honest disclosed contribution when the account is active and the ledger is stale. Verify the real Reddit URL in a fresh browser navigation and append only verified evidence to $STATE/posts.jsonl. Code is read from the Life Manager repository; runtime ledgers belong only in $STATE and must never be committed. If a snapshot after a successful action is empty or times out, keep the same tab, use cf_screenshot or the last successful refs, and do not retry snapshot repeatedly; preserve the bounded ACT attempt and verify the result before logging it. This is a bounded pass: if browser navigation or posting has not produced a verified success within 120 seconds, stop the ACT attempt, record the precise blocker, touch $STATE/.reddit-loop-last-pass, and return a failure result so the supervisor can retry later; never hang until the outer runner timeout. Report a meaningful result through $REPO_ROOT/skills/report/loop-report.sh."

EVIDENCE_DIR="$STATE/agent-runner-evidence/reddit-daily/$(date +%s)-$$"
printf '%s\n' "$PROMPT" | "$RUN_AGENT" --task-class tool-agent \
  --loop reddit \
  --evidence-dir "$EVIDENCE_DIR" --task-label reddit-loop-daily --workdir "$REPO_ROOT" >>"$LOG" 2>&1
RC=$?
echo "=== reddit-loop-daily done rc=$RC $(date '+%F %T %Z') ===" >>"$LOG"
touch "$STATE/.reddit-loop-last-pass" 2>/dev/null || true
exit 0
