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

# `reconcile_release` above only ever touches loaded-and-idle owners on the shared-agent-runner and
# deterministic provider routes, four at a time. It never installs a brand-new label or repoints a
# loaded owner that never idles long enough to be picked up: measured 2026-09-27, only 53/172 loaded
# owners were on the current release (81 sat on a 10h-old one) until a human ran
# `lm-loop apply --all` by hand. This runs that same fleet apply automatically, but only once per
# newly *activated* release sha (never every 60s tick) and never while a release was cut as a
# non-activated candidate (RELEASE_ROOT below is only ever the `current` symlink target, and
# `cut-loop-release.sh` refuses to activate `current` for anything but a complete origin/main
# ancestor -- see its LOOPS_ACTIVATE_CURRENT handling), and never while the promotion hold above is
# active (this function is only reached after the hold's early `exit 0`).
run_fleet_apply() {
  local release_root="$1"
  local release_sha="$2"
  local state_dir="${LIFE_MANAGER_RELEASE_RECONCILER_STATE_ROOT:-$HOME/.local/state/life-manager/release-reconciler}"
  local state_path="$state_dir/fleet-apply-state.json"
  local log_path="$state_dir/fleet-apply.jsonl"
  mkdir -p "$state_dir"

  local last_sha last_status last_next_retry last_ok_epoch
  IFS=$'\t' read -r last_sha last_status last_next_retry last_ok_epoch < <(
    FLEET_APPLY_STATE_PATH="$state_path" "$runtime_python" - <<'PY'
import json, os
path = os.environ["FLEET_APPLY_STATE_PATH"]
try:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
except (OSError, ValueError):
    data = {}
sha = data.get("sha", "")
status = data.get("status", "")
sha = sha if isinstance(sha, str) else ""
status = status if isinstance(status, str) else ""
try:
    next_retry = int(data.get("next_retry_epoch", 0) or 0)
except (TypeError, ValueError):
    next_retry = 0
try:
    last_ok_epoch = int(data.get("last_ok_epoch", 0) or 0)
except (TypeError, ValueError):
    last_ok_epoch = 0
print(f"{sha}\t{status}\t{next_retry}\t{last_ok_epoch}")
PY
  )

  local now_epoch
  now_epoch="$(date -u +%s)"
  local min_interval_seconds="${LIFE_MANAGER_FLEET_APPLY_MIN_INTERVAL_SECONDS:-1800}"
  if [ "$last_status" = "ok" ]; then
    if [ "$last_sha" = "$release_sha" ]; then
      printf 'agent-runner fleet-apply: release %s already applied; skipping\n' "$release_sha" >&2
      return 0
    fi
    # Releases are cut on every merge -- one every ~20 minutes during a busy night -- and each
    # apply re-bootstraps ~150 idle launchd owners, which loads the host (measured cause of the
    # Mac mini's WindowServer kernel panics under load). Coalesce: a new sha within the min
    # interval since the last *successful* apply is not applied yet; once the interval elapses,
    # apply once against whatever is current then, never an intermediate sha from the gap.
    if [ -n "${last_ok_epoch:-}" ] && [ "$now_epoch" -lt "$((last_ok_epoch + min_interval_seconds))" ]; then
      printf 'agent-runner fleet-apply: release %s coalesced; last success at epoch %s, min interval %ss\n' \
        "$release_sha" "$last_ok_epoch" "$min_interval_seconds" >&2
      return 0
    fi
  fi
  if [ "$last_sha" = "$release_sha" ] && [ "$last_status" = "error" ] \
    && [ "$now_epoch" -lt "${last_next_retry:-0}" ]; then
    printf 'agent-runner fleet-apply: release %s failed previously; backoff until epoch %s\n' \
      "$release_sha" "$last_next_retry" >&2
    return 0
  fi

  local apply_timeout_seconds="${LIFE_MANAGER_FLEET_APPLY_TIMEOUT_SECONDS:-1200}"
  local backoff_seconds="${LIFE_MANAGER_FLEET_APPLY_BACKOFF_SECONDS:-1800}"
  local apply_output apply_rc=0
  apply_output="$(LIFE_MANAGER_RELEASE_ROOT="$release_root" "$runtime_python" "$timeout_runner" \
    --grace-seconds 15 "$apply_timeout_seconds" "$release_root/bin/lm-loop" apply --all 2>&1)" \
    || apply_rc=$?

  local status changed=0 skipped=0 errors=0 message=""
  if [ "$apply_rc" -eq 0 ]; then
    status="ok"
    read -r changed skipped errors < <(printf '%s' "$apply_output" | "$runtime_python" -c '
import json, sys
try:
    rows = json.load(sys.stdin)
    if not isinstance(rows, list):
        rows = []
except ValueError:
    rows = []
changed = sum(1 for r in rows if isinstance(r, dict) and r.get("changed"))
skipped = sum(1 for r in rows if isinstance(r, dict) and r.get("skipped"))
errors = sum(1 for r in rows if isinstance(r, dict) and r.get("ok") is False)
print(changed, skipped, errors)
' 2>/dev/null || printf '0 0 0')
  elif printf '%s' "$apply_output" | grep -q "production apply is already owned"; then
    # Another apply (a human running `lm-loop apply --all`, or this reconciler's own next-tick
    # retry racing a slow prior run) already owns the fleet apply lock. This is lock contention,
    # not a broken release -- retry on the very next tick instead of the error backoff.
    status="skip"
    message="production apply is already owned"
  elif [ "$apply_rc" -eq 124 ]; then
    status="error"
    message="apply --all timed out after ${apply_timeout_seconds}s"
  else
    status="error"
    message="apply --all exited ${apply_rc}"
  fi

  local next_retry_epoch=0
  [ "$status" = "error" ] && next_retry_epoch=$((now_epoch + backoff_seconds))
  local new_last_ok_epoch="${last_ok_epoch:-0}"
  [ "$status" = "ok" ] && new_last_ok_epoch="$now_epoch"

  FLEET_APPLY_STATE_PATH="$state_path" FLEET_APPLY_LOG_PATH="$log_path" \
    FLEET_APPLY_SHA="$release_sha" FLEET_APPLY_STATUS="$status" \
    FLEET_APPLY_CHANGED="$changed" FLEET_APPLY_SKIPPED="$skipped" FLEET_APPLY_ERRORS="$errors" \
    FLEET_APPLY_MESSAGE="$message" FLEET_APPLY_NEXT_RETRY="$next_retry_epoch" \
    FLEET_APPLY_LAST_OK_EPOCH="$new_last_ok_epoch" \
    "$runtime_python" - <<'PY'
import json, os, time
record = {
    "sha": os.environ["FLEET_APPLY_SHA"],
    "status": os.environ["FLEET_APPLY_STATUS"],
    "changed": int(os.environ["FLEET_APPLY_CHANGED"]),
    "skipped": int(os.environ["FLEET_APPLY_SKIPPED"]),
    "errors": int(os.environ["FLEET_APPLY_ERRORS"]),
    "message": os.environ["FLEET_APPLY_MESSAGE"],
    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "next_retry_epoch": int(os.environ["FLEET_APPLY_NEXT_RETRY"]),
    "last_ok_epoch": int(os.environ["FLEET_APPLY_LAST_OK_EPOCH"]),
}
state_path = os.environ["FLEET_APPLY_STATE_PATH"]
tmp = state_path + ".tmp"
with open(tmp, "w", encoding="utf-8") as handle:
    json.dump(record, handle, sort_keys=True)
os.replace(tmp, state_path)
with open(os.environ["FLEET_APPLY_LOG_PATH"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
PY

  printf 'agent-runner fleet-apply: release %s status=%s changed=%s skipped=%s errors=%s%s\n' \
    "$release_sha" "$status" "$changed" "$skipped" "$errors" \
    "${message:+ message=\"$message\"}" >&2

  [ "$status" = "error" ] && return 1
  return 0
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

reconcile_status=0
reconcile_release "$RELEASE_ROOT" || reconcile_status=1
fleet_apply_status=0
run_fleet_apply "$RELEASE_ROOT" "$release_sha" || fleet_apply_status=1
if [ "$reconcile_status" -ne 0 ] || [ "$fleet_apply_status" -ne 0 ]; then
  exit 1
fi
exit 0
