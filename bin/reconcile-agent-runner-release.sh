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

provision_investment_manifest() {
  local release_root="$1"
  local provisioner="$release_root/apps/life-manager/investment-core/provision_manifest.py"
  [ -f "$provisioner" ] || return 0
  local manifest_path="${LIFE_MANAGER_INVESTMENT_MANIFEST_PATH:-$HOME/.local/state/life-manager/investment-cross-venue/inputs.json}"
  local alpaca_state_dir="${LIFE_MANAGER_INVESTMENT_ALPACA_STATE_DIR:-~/.local/state/life-manager/alpaca-investment-live}"
  if ! "$runtime_python" "$provisioner" \
      --path "$manifest_path" \
      --alpaca-state-dir "$alpaca_state_dir" \
      --available-capital-usd 0; then
    printf 'agent-runner reconcile: investment owner manifest provisioning failed\n' >&2
    return 1
  fi
}

provision_investment_selection() {
  local release_root="$1"
  local release_sha="$2"
  local configured_reports_path="${LIFE_MANAGER_INVESTMENT_VALIDATION_REPORTS_PATH:-}"
  local reports_path="${configured_reports_path:-$release_root/apps/life-manager/investment-core/reviewed-validation-reports.json}"
  if [ ! -f "$reports_path" ] && [ -z "$configured_reports_path" ]; then
    return 0
  fi
  local provisioner="$release_root/apps/life-manager/investment-core/provision_selection.py"
  if [ ! -f "$provisioner" ]; then
    printf 'agent-runner reconcile: configured investment validation reports have no selection provisioner\n' >&2
    return 1
  fi
  local live_selection_path="${LIFE_MANAGER_INVESTMENT_SELECTION_PATH:-$HOME/.local/state/life-manager/alpaca-investment-live/selected-strategy.json}"
  local paper_selection_path="${LIFE_MANAGER_INVESTMENT_PAPER_SELECTION_PATH:-$HOME/.local/state/life-manager/alpaca-investment-paper/selected-strategy.json}"
  local selection_path
  for selection_path in "$live_selection_path" "$paper_selection_path"; do
    if ! "$runtime_python" "$provisioner" \
        --path "$selection_path" \
        --reports "$reports_path" \
        --release-sha "$release_sha"; then
      printf 'agent-runner reconcile: investment strategy selection provisioning failed for %s\n' \
        "$selection_path" >&2
      return 1
    fi
  done
}

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
  local per_owner_timeout_seconds="${LIFE_MANAGER_FLEET_APPLY_PER_OWNER_TIMEOUT_SECONDS:-120}"
  local backoff_seconds="${LIFE_MANAGER_FLEET_APPLY_BACKOFF_SECONDS:-1800}"
  # Write to files, not $(...): a descendant that inherits a pipe keeps command substitution
  # waiting after apply itself exits (the first automatic run hit the 1200s timeout while the
  # same apply to a file finished in 298s). The output file is also the evidence for a failure.
  local output_path="$state_dir/fleet-apply-last-output.log"
  local owners_log_path="$state_dir/fleet-apply-owners.jsonl"
  : >"$output_path"

  # One `apply --all` call waits on every owner in one process; a single stuck owner (or the
  # reconciler's own label, which `apply --all` skips as "already owned" by itself) hangs the
  # whole fleet for the full 1200s budget with nothing applied. Apply one owner at a time instead
  # so a stuck owner only burns its own bounded timeout and every other owner still gets applied.
  local own_loop_id="${LIFE_MANAGER_LOOP_ID:-}"
  local registry_path="$release_root/config/loop-registry.json"
  local budget_deadline_epoch=$((now_epoch + apply_timeout_seconds))

  local changed=0 skipped=0 errors=0
  local already_owned=0 budget_exceeded=0
  local timed_out_owners="" apply_message=""

  # Cheap pre-check before spawning `lm-loop apply`: an owner whose loaded plist already carries
  # the target sha needs no apply at all (per-owner apply costs 5-15s even as a no-op, 60-120s for
  # mobile-publish owners with hundreds of effect_unknown fences), and every attempt restarts from
  # the top of the registry so a slow tail may never be reached. Skip those owners without spawning
  # apply, and push owners that errored or timed out on a previous attempt for this same sha to the
  # end of the queue so a repeatedly-stuck owner cannot starve the rest of the fleet.
  local plan_path
  plan_path="$(mktemp "$state_dir/.fleet-apply-plan.XXXXXX")"
  FLEET_APPLY_REGISTRY_PATH="$registry_path" FLEET_APPLY_OWNERS_LOG_PATH="$owners_log_path" \
    FLEET_APPLY_OWN_LOOP_ID="$own_loop_id" FLEET_APPLY_SHA="$release_sha" \
    "$runtime_python" - >"$plan_path" <<'PY'
import json, os, plistlib
from pathlib import Path

registry_path = os.environ["FLEET_APPLY_REGISTRY_PATH"]
owners_log_path = os.environ["FLEET_APPLY_OWNERS_LOG_PATH"]
own_loop_id = os.environ.get("FLEET_APPLY_OWN_LOOP_ID", "")
release_sha = os.environ["FLEET_APPLY_SHA"]
agents_dir = Path(os.environ.get(
    "LIFE_MANAGER_LAUNCH_AGENTS_DIR", "~/Library/LaunchAgents")).expanduser()

try:
    with open(registry_path, encoding="utf-8") as handle:
        registry = json.load(handle)
except (OSError, ValueError):
    registry = {}
loops = registry.get("loops") or {}
if not isinstance(loops, dict):
    loops = {}

# The most recent owners-log row per loop_id for this exact sha decides whether that owner
# errored or timed out last time; a later successful retry for the same sha must not still be
# pushed to the back.
last_for_sha = {}
try:
    with open(owners_log_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("sha") != release_sha:
                continue
            loop_id = row.get("loop_id")
            if isinstance(loop_id, str):
                last_for_sha[loop_id] = row
except OSError:
    pass
prev_failed = {
    loop_id for loop_id, row in last_for_sha.items()
    if row.get("rc") not in (0, None)
}

def apply_order(loop_id):
    entry = loops[loop_id] if isinstance(loops.get(loop_id), dict) else {}
    # Revenue/contract owners must not starve behind slow growth publishers when the bounded
    # fleet budget is exhausted. Keep deterministic ordering inside each class.
    domain_rank = {"earn": 0, "financial": 1, "growth": 2, "system": 3}.get(
        entry.get("domain"), 4
    )
    priority_rank = {"critical_paid": 0, "revenue": 1, "support": 2}.get(
        entry.get("priority"), 3
    )
    admission_rank = {"revenue": 0, "borrow": 1}.get(entry.get("admission_class"), 2)
    return domain_rank, priority_rank, admission_rank, loop_id

skip_current, clean, failed_last = [], [], []
for loop_id in sorted(loops.keys(), key=apply_order):
    if loop_id == own_loop_id:
        continue
    entry = loops[loop_id] if isinstance(loops.get(loop_id), dict) else {}
    label = entry.get("label")
    installed_sha = None
    if isinstance(label, str) and label:
        plist_path = agents_dir / f"{label}.plist"
        try:
            with plist_path.open("rb") as handle:
                plist = plistlib.load(handle)
            installed_sha = (plist.get("EnvironmentVariables") or {}).get(
                "LIFE_MANAGER_RELEASE_SHA")
        except Exception:
            installed_sha = None
    if installed_sha == release_sha:
        skip_current.append(loop_id)
    elif loop_id in prev_failed:
        failed_last.append(loop_id)
    else:
        clean.append(loop_id)

# Guarded retirement is a validated lm-loop target, not a registry loop id.
# Reconcile it before normal owners so a bounded fleet pass cannot starve it.
for label in sorted(registry.get("guarded_retired_labels", {})):
    print(f"retire\t{label}")

for loop_id in skip_current:
    print(f"current\t{loop_id}")
for loop_id in clean + failed_last:
    print(f"apply\t{loop_id}")
PY

  local plan_action loop_id
  while IFS=$'\t' read -r plan_action loop_id; do
    [ -z "$loop_id" ] && continue
    if [ "$plan_action" = "current" ]; then
      skipped=$((skipped + 1))
      FLEET_APPLY_OWNERS_LOG_PATH="$owners_log_path" FLEET_APPLY_SHA="$release_sha" \
        FLEET_APPLY_OWNER_LOOP_ID="$loop_id" \
        "$runtime_python" - <<'PY'
import json, os
record = {
    "sha": os.environ["FLEET_APPLY_SHA"],
    "loop_id": os.environ["FLEET_APPLY_OWNER_LOOP_ID"],
    "rc": 0,
    "seconds": 0,
    "changed": 0,
    "skipped": 1,
    "reason": "current",
}
with open(os.environ["FLEET_APPLY_OWNERS_LOG_PATH"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
PY
      continue
    fi
    local remaining_budget_seconds
    remaining_budget_seconds=$((budget_deadline_epoch - $(date -u +%s)))
    if [ "$remaining_budget_seconds" -le 0 ]; then
      budget_exceeded=1
      break
    fi
    # Do not start another owner when the remaining fleet budget cannot cover its full bounded
    # timeout. Starting it anyway lets the per-owner timeout (and its grace period) overrun the
    # fleet deadline, which was observed as 1225s for a 1200s budget. If configuration gives an
    # owner timeout larger than the fleet budget, fail closed before starting any owner rather than
    # violating the fleet bound.
    if [ "$remaining_budget_seconds" -lt "$per_owner_timeout_seconds" ]; then
      budget_exceeded=1
      break
    fi

    local owner_output_path owner_started owner_rc owner_output owner_seconds
    owner_output_path="$(mktemp "$state_dir/.fleet-apply-owner-output.XXXXXX")"
    owner_started="$(date -u +%s)"
    owner_rc=0
    LIFE_MANAGER_RELEASE_ROOT="$release_root" LIFE_MANAGER_APPLY_TARGET="$loop_id" \
      "$runtime_python" "$timeout_runner" --grace-seconds 15 "$per_owner_timeout_seconds" \
      "$release_root/bin/lm-loop" apply >"$owner_output_path" 2>&1 </dev/null || owner_rc=$?
    owner_output="$(cat "$owner_output_path")"
    owner_seconds=$(( $(date -u +%s) - owner_started ))
    {
      printf '=== owner %s (rc=%s, %ss) ===\n' "$loop_id" "$owner_rc" "$owner_seconds"
      cat "$owner_output_path"
    } >>"$output_path"
    rm -f "$owner_output_path"

    local owner_changed=0 owner_skipped=0 owner_errors=0
    if [ "$owner_rc" -eq 0 ]; then
      read -r owner_changed owner_skipped owner_errors < <(printf '%s' "$owner_output" | "$runtime_python" -c '
import json, sys
try:
    rows = json.load(sys.stdin)
    if not isinstance(rows, list):
        rows = []
except ValueError:
    rows = []
if sys.argv[1] == "retire":
    row = rows[0] if len(rows) == 1 and isinstance(rows[0], dict) else {}
    if not (row.get("ok") is True and row.get("retired") is True
            and row.get("label") == sys.argv[2]
            and isinstance(row.get("was_loaded"), bool)
            and isinstance(row.get("removed_plist"), bool)):
        print("0 0 1")
        sys.exit(0)
changed = sum(1 for r in rows if isinstance(r, dict) and (
    r.get("changed") or (r.get("retired") is True and (
        r.get("was_loaded") is True or r.get("removed_plist") is True))))
skipped = sum(1 for r in rows if isinstance(r, dict) and (
    r.get("skipped") or (r.get("retired") is True
        and r.get("was_loaded") is False and r.get("removed_plist") is False)))
errors = sum(1 for r in rows if isinstance(r, dict) and r.get("ok") is False)
print(changed, skipped, errors)
' "$plan_action" "$loop_id" 2>/dev/null || printf '0 0 1')
      changed=$((changed + owner_changed))
      skipped=$((skipped + owner_skipped))
      errors=$((errors + owner_errors))
    elif printf '%s' "$owner_output" | grep -q "production apply is already owned"; then
      # Another apply (a human running `lm-loop apply --all`, or this reconciler's own next-tick
      # retry racing a slow prior run) already owns the fleet apply lock. This is lock contention,
      # not a broken release -- stop this cycle and retry on the very next tick.
      already_owned=1
      apply_message="production apply is already owned"
    elif [ "$owner_rc" -eq 124 ]; then
      errors=$((errors + 1))
      timed_out_owners="${timed_out_owners:+$timed_out_owners,}$loop_id"
    else
      errors=$((errors + 1))
    fi

    FLEET_APPLY_OWNERS_LOG_PATH="$owners_log_path" FLEET_APPLY_SHA="$release_sha" \
      FLEET_APPLY_OWNER_LOOP_ID="$loop_id" FLEET_APPLY_OWNER_RC="$owner_rc" \
      FLEET_APPLY_OWNER_SECONDS="$owner_seconds" FLEET_APPLY_OWNER_CHANGED="$owner_changed" \
      FLEET_APPLY_OWNER_SKIPPED="$owner_skipped" \
      "$runtime_python" - <<'PY'
import json, os
record = {
    "sha": os.environ["FLEET_APPLY_SHA"],
    "loop_id": os.environ["FLEET_APPLY_OWNER_LOOP_ID"],
    "rc": int(os.environ["FLEET_APPLY_OWNER_RC"]),
    "seconds": int(os.environ["FLEET_APPLY_OWNER_SECONDS"]),
    "changed": int(os.environ["FLEET_APPLY_OWNER_CHANGED"]),
    "skipped": int(os.environ["FLEET_APPLY_OWNER_SKIPPED"]),
}
with open(os.environ["FLEET_APPLY_OWNERS_LOG_PATH"], "a", encoding="utf-8") as handle:
    handle.write(json.dumps(record, sort_keys=True) + "\n")
PY

    [ "$already_owned" -eq 1 ] && break
  done <"$plan_path"
  rm -f "$plan_path"

  local status message
  if [ "$already_owned" -eq 1 ]; then
    status="skip"
    message="$apply_message"
  elif [ -n "$timed_out_owners" ] || [ "$budget_exceeded" -eq 1 ]; then
    # A stuck or slow owner (or an overrun budget) must not be silently swallowed into "ok" --
    # record it as partial so it still backs off, and name exactly which owner(s) hung.
    status="partial"
    message="timed out owners: ${timed_out_owners:-none}${budget_exceeded:+; budget exceeded}"
  elif [ "$errors" -gt 0 ]; then
    status="error"
    message="one or more owner applies failed"
  else
    status="ok"
    message=""
  fi

  local next_retry_epoch=0
  { [ "$status" = "error" ] || [ "$status" = "partial" ]; } && next_retry_epoch=$((now_epoch + backoff_seconds))
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

  { [ "$status" = "error" ] || [ "$status" = "partial" ]; } && return 1
  return 0
}

schedule_self_handoff() {
  local release_root="$1" release_sha="$2"
  local state_dir="${LIFE_MANAGER_RELEASE_RECONCILER_STATE_ROOT:-$HOME/.local/state/life-manager/release-reconciler}"
  local handoff_dir="$state_dir/self-handoff"
  local helper_label="ai.anicca.life-manager-release-reconciler-self-handoff"
  local helper_plist="$handoff_dir/helper.plist"
  local target_plist_tmp="$handoff_dir/reconciler-target.plist.tmp"
  local installed_plist="${LIFE_MANAGER_LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}/ai.anicca.life-manager-release-reconciler.plist"
  local receipt_path="$handoff_dir/receipt.json"
  local helper_script="$release_root/bin/reconcile-agent-self-handoff.sh"
  local launchctl_safe="$release_root/bin/launchctl-safe"
  [ -x "$helper_script" ] || { printf 'agent-runner self-handoff: helper missing in release\n' >&2; return 1; }
  [ -x "$launchctl_safe" ] || { printf 'agent-runner self-handoff: launchctl-safe missing in release\n' >&2; return 1; }
  mkdir -p "$handoff_dir"
  chmod 700 "$handoff_dir"
  mkdir -p "$(dirname "$installed_plist")"

  LIFE_MANAGER_RUNTIME_PYTHON="$runtime_python" PYTHONPATH="$release_root" \
    "$runtime_python" - "$release_root" "$target_plist_tmp" "$installed_plist" \
    "$helper_plist" "$helper_script" "$launchctl_safe" "$receipt_path" "$helper_label" "$$" <<'PY'
import json, os, plistlib, sys, tempfile
from pathlib import Path
from runtime.loop.lm_loop_apply import _plist, _preserve_operational_attributes

release_root = Path(sys.argv[1]).resolve(strict=True)
target_path = Path(sys.argv[2])
installed_path = Path(sys.argv[3])
helper_path = Path(sys.argv[4])
helper_script = sys.argv[5]
launchctl_safe = sys.argv[6]
receipt_path = sys.argv[7]
helper_label = sys.argv[8]
parent_pid = sys.argv[9]
manifest = json.loads((release_root / "RELEASE.json").read_text(encoding="utf-8"))
registry = json.loads((release_root / "config/loop-registry.json").read_text(encoding="utf-8"))
loop_id = "life-manager-release-reconciler"
entry = registry["loops"][loop_id]
new_bytes = _plist(loop_id, entry, release_root, manifest["sha"])
old_bytes = installed_path.read_bytes() if installed_path.is_file() else None
new_bytes = _preserve_operational_attributes(
    new_bytes, old_bytes, retired_environment_keys=("LIFE_MANAGER_SOURCE_REPO",))
target_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
fd, temporary = tempfile.mkstemp(prefix=f".{target_path.name}.", dir=str(target_path.parent))
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(new_bytes)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target_path)
finally:
    Path(temporary).unlink(missing_ok=True)
helper = {
    "Label": helper_label,
    "ProgramArguments": [
        helper_script, "--parent-pid", parent_pid,
        "--old-service", "ai.anicca.life-manager-release-reconciler",
        "--helper-service", helper_label,
        "--target-plist", str(target_path),
        "--installed-plist", str(installed_path),
        "--handoff-plist", str(helper_path),
        "--receipt", receipt_path,
        "--launchctl", launchctl_safe,
    ],
    "ProcessType": "Background",
    "RunAtLoad": True,
    "ThrottleInterval": 60,
    "EnvironmentVariables": {
        "LIFE_MANAGER_RUNTIME_PYTHON": os.environ.get("LIFE_MANAGER_RUNTIME_PYTHON", sys.executable),
    },
}
helper_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
fd, temporary = tempfile.mkstemp(prefix=f".{helper_path.name}.", dir=str(helper_path.parent))
try:
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(plistlib.dumps(helper, fmt=plistlib.FMT_XML, sort_keys=True))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, helper_path)
finally:
    Path(temporary).unlink(missing_ok=True)
PY

  if "$SCRIPT_ROOT/bin/launchctl-safe" print "gui/$(id -u)/$helper_label" >/dev/null 2>&1; then
    printf 'agent-runner self-handoff: helper already loaded for release %s\n' "$release_sha" >&2
    return 0
  fi
  "$SCRIPT_ROOT/bin/launchctl-safe" bootstrap "gui/$(id -u)" "$helper_plist"
  printf 'agent-runner self-handoff: scheduled release %s after parent exit\n' "$release_sha" >&2
}

if [ "${LIFE_MANAGER_RECONCILER_HANDOFF_ONLY:-0}" = "1" ]; then
  handoff_release_root="$(cd "$CURRENT" 2>/dev/null && pwd -P || true)"
  handoff_release_sha=""
  if [ -n "$handoff_release_root" ]; then
    handoff_release_sha="$("$runtime_python" - "$handoff_release_root/RELEASE.json" <<'PY'
import json, sys
try:
    print(json.loads(open(sys.argv[1], encoding="utf-8").read()).get("sha", ""))
except (OSError, ValueError, json.JSONDecodeError):
    print("")
PY
    )"
  fi
  installed_reconciler_plist="${LIFE_MANAGER_LAUNCH_AGENTS_DIR:-$HOME/Library/LaunchAgents}/ai.anicca.life-manager-release-reconciler.plist"
  installed_reconciler_sha="$("$runtime_python" - "$installed_reconciler_plist" <<'PY'
import plistlib, sys
try:
    env = plistlib.loads(open(sys.argv[1], "rb").read()).get("EnvironmentVariables") or {}
    print(env.get("LIFE_MANAGER_RELEASE_SHA", ""))
except (OSError, ValueError, plistlib.InvalidFileException):
    print("")
PY
  )"
  if [ -n "$handoff_release_sha" ] && [ "$installed_reconciler_sha" != "$handoff_release_sha" ]; then
    schedule_self_handoff "$handoff_release_root" "$handoff_release_sha"
  fi
  exit 0
fi

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

if ! provision_investment_manifest "$RELEASE_ROOT"; then
  printf 'agent-runner reconcile refused: investment owner manifest is not provisioned\n' >&2
  exit 1
fi
if ! provision_investment_selection "$RELEASE_ROOT" "$release_sha"; then
  printf 'agent-runner reconcile refused: investment strategy selection is not provisioned\n' >&2
  exit 1
fi
reconcile_status=0
reconcile_release "$RELEASE_ROOT" || reconcile_status=1
fleet_apply_status=0
run_fleet_apply "$RELEASE_ROOT" "$release_sha" || fleet_apply_status=1
self_handoff_status=0
script_sha="$(jq -r '.sha // ""' "$SCRIPT_ROOT/RELEASE.json" 2>/dev/null || true)"
if [ -n "$script_sha" ] && [ "$release_sha" != "$script_sha" ]; then
  schedule_self_handoff "$RELEASE_ROOT" "$release_sha" || self_handoff_status=1
fi
if [ "$reconcile_status" -ne 0 ] || [ "$fleet_apply_status" -ne 0 ] \
  || [ "$self_handoff_status" -ne 0 ]; then
  exit 1
fi
exit 0
