#!/usr/bin/env bash
# skills/earn/promptbase/daily.sh — ship one Capafy catalog skill to
# PromptBase per day, no human in the loop.
#
# Flow: readback first (refresh ledger status/sales for every tracked row)
# -> read the authoritative Capafy publish-list -> pick the next online,
# not-yet-shipped catalog skill (select_next.py; reels-hook-lab preferred) ->
# publish.py --confirm once -> record the outcome.
#
# CAPTCHA policy (strict, per task spec): never solve/bypass/outsource a
# challenge. publish.py itself never attempts to solve one -- it raises
# recaptcha_requires_human_verification and stops closed. This script's only
# job on that outcome is to record status=captcha_challenge_deferred in the
# ledger and exit 0 (no Telegram ask, no retry loop here); tomorrow's run
# tries again because ledger.already_listed treats that status as retryable.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd)"
SCRIPTS="$HERE/scripts"
PY="${PY:-/opt/homebrew/bin/python3}"
command -v "$PY" >/dev/null 2>&1 || PY=python3

BROWSER_GUARD="/Users/anicca/.config/ai/bin/browser-guard.sh"
BROWSER_IDENTITY="interactive:dais"

ENV_FILE="$HOME/.local/state/life-manager/.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE" >/dev/null 2>&1 || true
  set +a
fi

PUBLISHER_DIR="$REPO_ROOT/skills/capafy-autopublish/vendor/capafy-publisher"
CAPAFY_PUBLISHER_STATE_HOME_VALUE="$HOME/.local/state/life-manager/runtime/capafy-publisher"
CAPAFY_PUBLISHER_HOME_VALUE="$HOME/.local/state/life-manager/runtime/capafy-publisher-home"

LEDGER_PATH="${PROMPTBASE_LEDGER_PATH:-$HOME/.local/state/life-manager/state/promptbase-listings.jsonl}"
CATALOG_DIR="$REPO_ROOT/skills/capafy/catalog"
FENCE_RECONCILE_TOOL="$SCRIPTS/promptbase_fence_reconcile.py"

log() { echo "[promptbase-daily] $*"; }

ENDPOINT="$("$BROWSER_GUARD" acquire "$BROWSER_IDENTITY")"
ACQUIRE_RC=$?
if [ "$ACQUIRE_RC" -ne 0 ]; then
  log "browser lease unavailable (rc=$ACQUIRE_RC) -- skip this run, next wake retries"
  exit 0
fi
TMP_CAPAFY_JSON="$(mktemp)"
cleanup() {
  rm -f "$TMP_CAPAFY_JSON"
  "$BROWSER_GUARD" release "$BROWSER_IDENTITY" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# 1. Readback first: refresh ledger status/sales for every tracked row from
#    the PromptBase seller dashboard. Non-fatal -- a stale ledger just means
#    selection below works off slightly older status data.
log "readback: refreshing ledger from PromptBase dashboard"
"$PY" "$SCRIPTS/readback.py" --endpoint "$ENDPOINT" || log "readback failed (non-fatal, continuing)"

# 2. Authoritative Capafy online/shipped state.
log "reading Capafy publish-list"
if ! CAPAFY_LIST_JSON="$(cd "$PUBLISHER_DIR" && CAPAFY_PUBLISHER_STATE_HOME="$CAPAFY_PUBLISHER_STATE_HOME_VALUE" HOME="$CAPAFY_PUBLISHER_HOME_VALUE" "$PY" packager.py publish-list)"; then
  log "publish-list failed -- cannot select a candidate, exit clean"
  exit 0
fi
printf '%s' "$CAPAFY_LIST_JSON" >"$TMP_CAPAFY_JSON"

# 3. Pick the next slug: pure selection logic, no browser (testable in isolation).
SELECTION_JSON="$("$PY" "$SCRIPTS/select_next.py" \
  --catalog-dir "$CATALOG_DIR" \
  --ledger-path "$LEDGER_PATH" \
  --capafy-list-file "$TMP_CAPAFY_JSON")"
log "selection: $SELECTION_JSON"

SLUG="$(printf '%s' "$SELECTION_JSON" | "$PY" -c 'import json,sys; print((json.load(sys.stdin).get("slug") or ""))')"
TITLE="$(printf '%s' "$SELECTION_JSON" | "$PY" -c 'import json,sys; print((json.load(sys.stdin).get("title") or ""))')"

if [ -z "$SLUG" ]; then
  log "no publishable candidate today"
  if [ -n "${LIFE_MANAGER_OCCURRENCE_ID:-}" ]; then
    "$PY" "$FENCE_RECONCILE_TOOL" --occurrence "$LIFE_MANAGER_OCCURRENCE_ID" \
      --record-snapshot >/dev/null 2>&1 || true
  fi
  exit 0
fi
log "selected slug=$SLUG title=$TITLE"

# Durable pre-dispatch snapshot for the fence reconciler: record the exact
# slug/title this occurrence is about to submit, before the one
# PromptBase-mutating call below runs. Best-effort -- a write failure here
# never blocks the run; the reconciler falls back to "no candidate" (safe:
# no PromptBase-mutating step could have run without a snapshot naming one).
if [ -n "${LIFE_MANAGER_OCCURRENCE_ID:-}" ]; then
  "$PY" "$FENCE_RECONCILE_TOOL" --occurrence "$LIFE_MANAGER_OCCURRENCE_ID" \
    --record-snapshot --slug "$SLUG" --title "$TITLE" >/dev/null 2>&1 || true
fi

EVIDENCE_DIR="$HOME/.local/state/life-manager/state/promptbase-evidence/$(date -u +%Y%m%dT%H%M%SZ)-$SLUG"
PUBLISH_OUTPUT="$("$PY" "$SCRIPTS/publish.py" \
  --catalog-dir "$CATALOG_DIR/$SLUG" \
  --endpoint "$ENDPOINT" \
  --confirm \
  --evidence-dir "$EVIDENCE_DIR" 2>&1)"
PUBLISH_RC=$?
echo "$PUBLISH_OUTPUT"

if [ "$PUBLISH_RC" -eq 0 ]; then
  log "submitted ok: $SLUG"
  exit 0
fi

if printf '%s' "$PUBLISH_OUTPUT" | /usr/bin/grep -qE "already_in_ledger|already_visible_in_dashboard"; then
  log "publish.py found $SLUG already listed (race with a concurrent run) -- no-op, not a failure"
  exit 0
fi

if printf '%s' "$PUBLISH_OUTPUT" | /usr/bin/grep -q "recaptcha_requires_human_verification"; then
  log "reCAPTCHA escalated to an image challenge for $SLUG -- deferring (never solving it)"
  "$PY" "$SCRIPTS/ledger.py" record-captcha-deferred \
    --slug "$SLUG" --title "$TITLE" --evidence-dir "$EVIDENCE_DIR" --ledger-path "$LEDGER_PATH" \
    >/dev/null 2>&1 || true
  exit 0
fi

log "publish failed for an unexpected reason: $PUBLISH_OUTPUT"
exit 1
