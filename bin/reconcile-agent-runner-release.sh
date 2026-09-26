#!/usr/bin/env bash
# Keep managed runners on one complete pushed-main release without interrupting active loops.
set -euo pipefail

SOURCE_REPO="${LIFE_MANAGER_SOURCE_REPO:-$HOME/Projects/life-manager-main}"
LOOPS_ROOT="${LOOPS_ROOT:-$HOME/loops}"
CURRENT="$LOOPS_ROOT/current"
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

# The unattended merge guard freezes this reconciler on a bound recovery PR (see
# apps/life-manager/lib/dev-merge-guard.js's acquirePromotionHold): from the moment such a PR
# merges until its loop-runtime promotion has a verdict, this reconciler cutting+activating
# whatever is on origin/main every 60s would fleet-activate an unvalidated merge in under a
# minute, regardless of what the promotion's own canary/health/rollback decide.
#
# A non-expired hold means "do nothing this cycle". An EXPIRED hold is NOT automatically treated as
# released: if the guard crashed mid-promotion, nothing ever cleared it, and silently "ignoring" it
# once its TTL passed would let this reconciler cut+activate an unverified merge fleet-wide -- the
# exact blocker this hold exists to prevent, just delayed by the TTL instead of skipped entirely.
# An expired hold only stops blocking once a terminal row for its recorded sha actually exists in
# the promotions ledger (ok:true, or rolled_back:true meaning the main revert landed too) -- proof
# the promotion genuinely finished, not just that a clock ran out. Recovering an orphan with no such
# row is apps/life-manager/lib/self-build-daily.js's job (next pass, before it picks a PR); this
# script never mutates the hold, it only ever decides whether to freeze this one cycle.
PROMOTION_HOLD_PATH="${LIFE_MANAGER_PROMOTION_HOLD_PATH:-$LOOPS_ROOT/.promotion-hold}"
PROMOTIONS_LEDGER_PATH="${LIFE_MANAGER_PROMOTIONS_LEDGER_PATH:-$HOME/.local/state/life-manager/recovery/promotions.jsonl}"
if [ -f "$PROMOTION_HOLD_PATH" ]; then
  hold_json="$(python3 -c '
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as handle:
        value = json.load(handle)
    print(json.dumps({
        "expires_at": value.get("expires_at") if isinstance(value.get("expires_at"), str) else "",
        "sha": value.get("sha") if isinstance(value.get("sha"), str) else "",
        "pr": value.get("pr", ""),
    }))
except (OSError, ValueError, TypeError, AttributeError):
    print(json.dumps({"expires_at": "", "sha": "", "pr": ""}))
' "$PROMOTION_HOLD_PATH" 2>/dev/null || printf '{"expires_at":"","sha":"","pr":""}')"
  hold_expires_at="$(printf '%s' "$hold_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("expires_at",""))' 2>/dev/null || true)"
  hold_sha="$(printf '%s' "$hold_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("sha",""))' 2>/dev/null || true)"
  hold_pr="$(printf '%s' "$hold_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("pr",""))' 2>/dev/null || true)"
  hold_active=0
  if [ -n "$hold_expires_at" ]; then
    if python3 -c '
import datetime, sys
try:
    expires = datetime.datetime.fromisoformat(sys.argv[1].replace("Z", "+00:00"))
except ValueError:
    sys.exit(1)
sys.exit(0 if expires > datetime.datetime.now(datetime.timezone.utc) else 1)
' "$hold_expires_at" 2>/dev/null; then
      hold_active=1
    fi
  fi
  if [ "$hold_active" -eq 1 ]; then
    printf 'agent-runner reconcile: promotion hold active at %s (expires %s); skipping cut/advance of current this cycle\n' \
      "$PROMOTION_HOLD_PATH" "$hold_expires_at" >&2
    exit 0
  fi
  resolved=0
  if [ -n "$hold_sha" ] && [ -f "$PROMOTIONS_LEDGER_PATH" ]; then
    if python3 -c '
import json, sys
sha = sys.argv[1]
try:
    with open(sys.argv[2], encoding="utf-8") as handle:
        lines = handle.readlines()
except OSError:
    sys.exit(1)
for line in reversed(lines):
    line = line.strip()
    if not line:
        continue
    try:
        row = json.loads(line)
    except ValueError:
        continue
    if row.get("record_type") == "recovery_promotion_terminal" and row.get("merged_sha") == sha:
        sys.exit(0 if (row.get("ok") is True or row.get("rolled_back") is True) else 1)
sys.exit(1)
' "$hold_sha" "$PROMOTIONS_LEDGER_PATH" 2>/dev/null; then
      resolved=1
    fi
  fi
  if [ "$resolved" -eq 1 ]; then
    printf 'agent-runner reconcile: promotion hold at %s is expired but sha=%s has a terminal ledger row; treating as released\n' \
      "$PROMOTION_HOLD_PATH" "$hold_sha" >&2
  else
    orphan_line="promotion_hold_orphaned sha=${hold_sha:-<none>} pr=${hold_pr:-<none>}"
    printf '%s\n' "$orphan_line" >&2
    # Alert once per hold so a frozen fleet is not silent until the next self-build pass.
    alerted_marker="$PROMOTION_HOLD_PATH.alerted"
    if [ "$(cat "$alerted_marker" 2>/dev/null)" != "${hold_sha:-none}:${hold_pr:-none}" ] \
      && [ -n "${LM_TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${LM_ADMIN_TELEGRAM_CHAT_ID:-}" ]; then
      if curl -sS -m 15 -o /dev/null "https://api.telegram.org/bot${LM_TELEGRAM_BOT_TOKEN}/sendMessage" \
        --data-urlencode "chat_id=${LM_ADMIN_TELEGRAM_CHAT_ID}" \
        --data-urlencode "text=⚠️ release-reconciler frozen: ${orphan_line}" >/dev/null 2>&1; then
        printf '%s' "${hold_sha:-none}:${hold_pr:-none}" > "$alerted_marker"
      fi
    fi
    exit 0
  fi
fi

fetch_timeout_seconds="${LIFE_MANAGER_RELEASE_FETCH_TIMEOUT_SECONDS:-600}"
case "$fetch_timeout_seconds" in
  ''|*[!0-9]*)
    printf 'agent-runner reconcile refused: invalid fetch timeout\n' >&2
    exit 64
    ;;
esac
if [ "$fetch_timeout_seconds" -lt 1 ]; then
  printf 'agent-runner reconcile refused: invalid fetch timeout\n' >&2
  exit 64
fi
reconcile_timeout_seconds="${LIFE_MANAGER_RECONCILE_TIMEOUT_SECONDS:-300}"
case "$reconcile_timeout_seconds" in
  ''|*[!0-9]*)
    printf 'agent-runner reconcile refused: invalid reconcile timeout\n' >&2
    exit 64
    ;;
esac
if [ "$reconcile_timeout_seconds" -lt 1 ]; then
  printf 'agent-runner reconcile refused: invalid reconcile timeout\n' >&2
  exit 64
fi
runtime_python="${LIFE_MANAGER_RUNTIME_PYTHON:-$(command -v python3 || true)}"
timeout_runner="$SCRIPT_ROOT/runtime/run-with-timeout.py"
if [ -z "$runtime_python" ] || [ ! -f "$timeout_runner" ]; then
  printf 'agent-runner reconcile refused: portable timeout unavailable\n' >&2
  exit 69
fi

run_reconcile() {
  local release_root="$1"
  shift
  LIFE_MANAGER_RELEASE_ROOT="$release_root" "$runtime_python" "$timeout_runner" \
    --grace-seconds 15 "$reconcile_timeout_seconds" "$release_root/bin/lm-loop" "$@"
}

reconcile_release() {
  local release_root="$1"
  local status=0
  if ! run_reconcile "$release_root" reconcile shared-agent-runner --loaded-idle-only --max-owners 4; then
    status=1
  fi
  if ! run_reconcile "$release_root" reconcile deterministic --loaded-idle-only --max-owners 4; then
    status=1
  fi
  local recovery_queue="${LIFE_MANAGER_RECOVERY_INTENTS_PATH:-$HOME/.local/state/life-manager/recovery/intents.jsonl}"
  local recovery_journal="${LIFE_MANAGER_RECOVERY_SUPERVISOR_JOURNAL_PATH:-$HOME/.local/state/life-manager/recovery/supervisor.jsonl}"
  if [ -f "$recovery_queue" ]; then
    if [ ! -x "$release_root/bin/lm-recovery-supervise" ]; then
      printf 'agent-runner reconcile: recovery supervisor unavailable in release\n' >&2
      status=1
    elif ! LIFE_MANAGER_RELEASE_ROOT="$release_root" \
      LIFE_MANAGER_RECOVERY_INTENTS_PATH="$recovery_queue" \
      LIFE_MANAGER_RECOVERY_SUPERVISOR_JOURNAL_PATH="$recovery_journal" \
      "$release_root/bin/lm-recovery-supervise" \
      --queue "$recovery_queue" --journal "$recovery_journal" --release-root "$release_root"; then
      status=1
    fi
  fi
  local admission_root="${LIFE_MANAGER_RESOURCE_ADMISSION_ROOT:-$HOME/.local/state/life-manager/host-admission/resources}"
  if [ ! -f "$admission_root/protocol.json" ] && \
    ! LIFE_MANAGER_RELEASE_ROOT="$release_root" "$release_root/bin/lm-loop" admission-v2-enable; then
    status=1
  fi
  return "$status"
}

"$runtime_python" "$timeout_runner" --grace-seconds 15 "$fetch_timeout_seconds" \
  git -C "$SOURCE_REPO" fetch --quiet --no-tags --no-auto-maintenance \
    --negotiation-tip=refs/remotes/origin/main origin main
main_sha="$(git -C "$SOURCE_REPO" rev-parse origin/main)"
initial_release_root="$(cd "$CURRENT" 2>/dev/null && pwd -P || true)"
current_sha=""
current_paths=""
if [ -n "$initial_release_root" ]; then
  current_sha="$(jq -r '.sha // ""' "$initial_release_root/RELEASE.json" 2>/dev/null || true)"
  current_paths="$(jq -r '.release_paths // ""' "$initial_release_root/RELEASE.json" 2>/dev/null || true)"
fi
current_complete=0
[ "$current_paths" = "ALL" ] && current_complete=1
release_sha_target="$main_sha"

# The public specs and the Gig progress ledger are not runtime inputs. Re-exporting the complete
# tree for a progress-only main commit consumes about a GiB while changing no runnable byte.
# Keep reconciling stale target labels to the existing complete release; cut a new release as soon
# as any other path differs. A missing/non-ancestor current SHA fails closed into a cut.
if [ "$current_complete" -eq 1 ] && [ -n "$current_sha" ] \
  && git -C "$SOURCE_REPO" merge-base --is-ancestor "$current_sha" "$main_sha" 2>/dev/null \
  && git -C "$SOURCE_REPO" diff --quiet "$current_sha" "$main_sha" -- . \
    ':(exclude)docs/**' ':(exclude)skills/earn/gig/TODO.md'; then
  release_sha_target="$current_sha"
fi

if [ "$release_sha_target" != "$current_sha" ] || [ "$current_complete" -ne 1 ]; then
  cutter="$CURRENT/bin/cut-loop-release.sh"
  [ -x "$cutter" ] || cutter="$SOURCE_REPO/bin/cut-loop-release.sh"
  LIFE_MANAGER_SOURCE_REPO="$SOURCE_REPO" LOOPS_ROOT="$LOOPS_ROOT" LOOPS_RELEASE_PATHS= \
    bash "$cutter" "$main_sha"
fi

RELEASE_ROOT="$(cd "$CURRENT" && pwd -P)"
release_sha="$(jq -r '.sha // ""' "$RELEASE_ROOT/RELEASE.json")"
release_paths="$(jq -r '.release_paths // ""' "$RELEASE_ROOT/RELEASE.json")"
if [ "$release_sha" != "$release_sha_target" ] || [ "$release_paths" != "ALL" ]; then
  printf 'agent-runner reconcile refused: release is not the full pushed-main build\n' >&2
  exit 1
fi

reconcile_release "$RELEASE_ROOT"
