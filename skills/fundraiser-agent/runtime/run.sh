#!/bin/bash
set -uo pipefail

REPO_ROOT="${LIFE_MANAGER_REPO:-$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$REPO_ROOT" ] || { echo "fundraiser: repository unavailable" >&2; exit 2; }
STATE_ROOT="${FUNDRAISER_STATE_ROOT:-$HOME/.local/state/life-manager/fundraiser}"
LOCK_DIR="$STATE_ROOT/run.lock"
LOCK_HELPER="$REPO_ROOT/skills/fundraiser-agent/runtime/run-lock.sh"
LOG="$STATE_ROOT/fundraiser.log"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
EVIDENCE_DIR="$STATE_ROOT/evidence/$RUN_ID"
OCCURRENCE_ID="${LIFE_MANAGER_OCCURRENCE_ID:-fundraiser:$RUN_ID}"
case "$OCCURRENCE_ID" in
  fundraiser:*) OCCURRENCE_KEY="${OCCURRENCE_ID#fundraiser:}" ;;
  *) echo "fundraiser: invalid occurrence identity" >&2; exit 2 ;;
esac
if ! [[ "$OCCURRENCE_KEY" =~ ^[A-Za-z0-9._:-]{1,127}$ ]]; then
  echo "fundraiser: invalid occurrence identity" >&2
  exit 2
fi
MARKERS_ROOT="$STATE_ROOT/effect-markers"
MARKER_PATH="$MARKERS_ROOT/$OCCURRENCE_KEY.json"
RUN_AGENT="$REPO_ROOT/skills/earn/marketing-engine/run_agent.sh"
PROMPT="$REPO_ROOT/skills/fundraiser-agent/prompts/daily.md"
SCHEMA="$REPO_ROOT/skills/fundraiser-agent/runtime/pass-result.schema.json"
SENDER="$REPO_ROOT/skills/_shared/send-telegram.sh"
PHOTO_SENDER="$REPO_ROOT/skills/_shared/send-telegram-photo.sh"
LOOP_CLI="${LIFE_MANAGER_LOOP_CLI:-$REPO_ROOT/bin/lm-loop}"
MIN_FREE_KIB=$((1536 * 1024))
PRESSURE_FREE_KIB=$((2 * 1024 * 1024))
# Use the registered daily-driver identity and a task-owned browser context.
# The profile guard protects endpoint recovery when available; a held profile
# is resolved read-only so another owner can keep working in its own context.
BROWSER_GUARD="${LIFE_MANAGER_BROWSER_GUARD:-$REPO_ROOT/skills/browser/browser-guard.sh}"
BROWSER_FOUNDATION="${LIFE_MANAGER_BROWSER_FOUNDATION:-$REPO_ROOT/skills/browser/ensure_browser.sh}"
BROWSER_IDENTITY="${LIFE_MANAGER_BROWSER_IDENTITY:-interactive:dais}"
BROWSER_CONTEXT_LEASE="${LIFE_MANAGER_BROWSER_CONTEXT_LEASE:-$REPO_ROOT/skills/browser/scripts/cdp_context_lease.py}"
BROWSER_CONTEXT_HELPER="${LIFE_MANAGER_BROWSER_CONTEXT_HELPER:-$REPO_ROOT/skills/browser/browser-context-lease.sh}"
BROWSER_RESOLVER="${LIFE_MANAGER_BROWSER_RESOLVER:-$REPO_ROOT/skills/browser/resolve_cdp_endpoint.py}"
BROWSER_REGISTRY="${AI_BROWSER_REGISTRY:-$HOME/.config/ai/registry/browsers.toml}"
export CLOAK_BROWSER_OWNER="${LIFE_MANAGER_BROWSER_TARGET_OWNER:-fundraiser}"
export CLOAK_CONTEXT_COOKIE_DOMAINS="${FUNDRAISER_CONTEXT_COOKIE_DOMAINS:-x.com,twitter.com}"
source "$BROWSER_CONTEXT_HELPER"

write_boundary_marker() {
  local phase="$1" effect="$2" temporary
  temporary="$MARKER_PATH.tmp.$$"
  mkdir -p "$MARKERS_ROOT" || return 1
  chmod 700 "$STATE_ROOT" "$MARKERS_ROOT" || return 1
  if [ -e "$MARKER_PATH" ]; then
    [ ! -L "$MARKER_PATH" ] || return 1
    [ "$(sed -n 's/.*"phase":"\([^"]*\)".*/\1/p' "$MARKER_PATH" 2>/dev/null)" = "pre_effect" ] || return 1
  fi
  if ! (umask 077; printf '{"schema_version":1,"owner_id":"fundraiser","occurrence_id":"%s","phase":"%s","effect":%s,"updated_at":"%s"}\n' \
      "$OCCURRENCE_ID" "$phase" "$effect" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >"$temporary"); then
    rm -f "$temporary"
    return 1
  fi
  chmod 600 "$temporary" && mv -f "$temporary" "$MARKER_PATH"
}

# This is the durable owner-side boundary. It is written before disk/browser
# preflight, so a later read-only replay can distinguish no-submit from an
# armed application without trusting a missing evidence directory.
write_boundary_marker pre_effect 0 || {
  echo "fundraiser: effect boundary marker unavailable" >&2
  exit 75
}

available_kib() {
  df -Pk "$STATE_ROOT" 2>/dev/null | awk 'NR==2 {print $4}'
}

BROWSER_LEASED=0
BROWSER_ENDPOINT=""

release_browser() {
  browser_context_lease_release >/dev/null 2>&1 || true
  if [ "$BROWSER_LEASED" -eq 1 ]; then
    "$BROWSER_GUARD" release "$BROWSER_IDENTITY" >/dev/null 2>&1 || true
    BROWSER_LEASED=0
  fi
}

# An application browser pass temporarily needs close to 1 GiB. Starting below this floor
# repeatedly ended with ENOSPC before the runner could persist its summary or proof.
# Keep launchd enabled, ask the existing disk owner to reclaim only classified
# regenerable artifacts, and let the next scheduled wake retry naturally.
FREE_KIB="$(available_kib)"
if [ -z "$FREE_KIB" ] || ! [[ "$FREE_KIB" =~ ^[0-9]+$ ]]; then
  echo "fundraiser: disk preflight unavailable" >&2
  exit 2
fi
if [ "$FREE_KIB" -lt "$PRESSURE_FREE_KIB" ]; then
  "$LOOP_CLI" restart life-manager-disk-cleanup >/dev/null 2>&1 || true
  echo "fundraiser: deferred disk policy available_kib=$FREE_KIB required_kib=$PRESSURE_FREE_KIB" >>"$LOG"
  exit 75
fi

[ -x "$BROWSER_GUARD" ] || {
  echo "fundraiser: browser foundation unavailable" >>"$LOG"
  exit 2
}
if BROWSER_ENDPOINT="$(AI_BROWSER_HOLDER_PID=$$ "$BROWSER_GUARD" acquire "$BROWSER_IDENTITY" 2>&1)"; then
  BROWSER_LEASED=1
else
  BROWSER_RC=$?
  if [ "$BROWSER_RC" -eq 9 ]; then
    BROWSER_ENDPOINT="$(browser_context_resolve_registered_endpoint \
      "$BROWSER_IDENTITY" "$BROWSER_RESOLVER" "$BROWSER_REGISTRY")" || {
      echo "fundraiser: deferred registered browser unavailable while another owner holds profile" >>"$LOG"
      exit 75
    }
  elif [ "$BROWSER_RC" -eq 10 ] && [ -x "$BROWSER_FOUNDATION" ]; then
    # Identity mismatch or unreachable: ask the registered owner to recover the
    # daily-driver profile (same recovery path life-manager-connector-native
    # uses), then take one more lease attempt before giving up this wake.
    BROWSER_STATUS="$(CLOAK_BROWSER_OWNER="$CLOAK_BROWSER_OWNER" bash "$BROWSER_FOUNDATION" 2>&1 | tail -n 1)" || BROWSER_STATUS="FAILED"
    case "$BROWSER_STATUS" in
      ALIVE|RECOVERED) ;;
      *)
        echo "fundraiser: deferred browser foundation unavailable: ${BROWSER_STATUS:-EMPTY}" >>"$LOG"
        exit 75
        ;;
    esac
    if BROWSER_ENDPOINT="$(AI_BROWSER_HOLDER_PID=$$ "$BROWSER_GUARD" acquire "$BROWSER_IDENTITY" 2>&1)"; then
      BROWSER_LEASED=1
    else
      BROWSER_RC=$?
      if [ "$BROWSER_RC" -eq 9 ]; then
        BROWSER_ENDPOINT="$(browser_context_resolve_registered_endpoint \
          "$BROWSER_IDENTITY" "$BROWSER_RESOLVER" "$BROWSER_REGISTRY")" || {
          echo "fundraiser: deferred registered browser unavailable after recovery" >>"$LOG"
          exit 75
        }
      else
        echo "fundraiser: deferred browser lease unavailable after recovery" >>"$LOG"
        exit 75
      fi
    fi
  else
    # Unknown guard failures do not justify attaching to or recovering a browser.
    echo "fundraiser: deferred browser lease unavailable rc=$BROWSER_RC: $BROWSER_ENDPOINT" >>"$LOG"
    exit 75
  fi
fi
case "$BROWSER_ENDPOINT" in
  http://127.0.0.1:*|http://localhost:*|http://\[::1\]:*) ;;
  *)
    echo "fundraiser: deferred browser endpoint invalid: $BROWSER_ENDPOINT" >>"$LOG"
    release_browser
    exit 75
    ;;
esac

if ! browser_context_lease_acquire \
    "$BROWSER_ENDPOINT" "$CLOAK_BROWSER_OWNER" "$CLOAK_CONTEXT_COOKIE_DOMAINS" "$BROWSER_CONTEXT_LEASE"; then
  echo "fundraiser: deferred task browser context unavailable" >>"$LOG"
  release_browser
  exit 75
fi
# The task context is isolated now; release any short identity lease before the run.
if [ "$BROWSER_LEASED" -eq 1 ]; then
  "$BROWSER_GUARD" release "$BROWSER_IDENTITY" >/dev/null 2>&1 || true
  BROWSER_LEASED=0
fi

mkdir -p "$STATE_ROOT/evidence" "$EVIDENCE_DIR"
chmod 700 "$STATE_ROOT" "$STATE_ROOT/evidence" "$EVIDENCE_DIR"
source "$LOCK_HELPER"
if ! acquire_run_lock "$LOCK_DIR"; then
  echo "fundraiser: prior pass still owns the loop" >>"$LOG"
  release_browser
  exit 0
fi
trap 'release_run_lock "$LOCK_DIR"; release_browser' EXIT

export PATH="/opt/homebrew/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export LIFE_MANAGER_REPO="$REPO_ROOT"
export FUNDRAISER_RUN_ID="$RUN_ID"
export FUNDRAISER_OCCURRENCE_ID="$OCCURRENCE_ID"
export FUNDRAISER_EFFECT_MARKER="$MARKER_PATH"
export FUNDRAISER_STATE_ROOT="$STATE_ROOT"
export FUNDRAISER_EVIDENCE_DIR="$EVIDENCE_DIR"
export FUNDRAISER_RECEIPTS="$STATE_ROOT/application-receipts.jsonl"
export FUNDRAISER_TARGET_INTENTS="$STATE_ROOT/target-intents.jsonl"
export FUNDRAISER_APPLICATIONS_DIR="$STATE_ROOT/applications"
export FUNDRAISER_RECORD_APPLICATION="$REPO_ROOT/skills/fundraiser-agent/runtime/record-application.py"
export FUNDRAISER_CURSOR="$STATE_ROOT/cursor.json"
export CLOAK_CDP_BASE_URL="$BROWSER_ENDPOINT"
# Raw nav/eval and owned-tab helpers must share the leased browser endpoint.
export CDP="$BROWSER_ENDPOINT"
# Recovery belongs to the next owner preflight, never an effectful pass helper.
export CLOAK_BROWSER_RECOVERY_SCRIPT=/dev/null
export LIFE_MANAGER_DISK_CLEANUP_SCRIPT=/dev/null
export FUNDRAISER_CDP_ENDPOINT="$BROWSER_ENDPOINT"
export FUNDRAISER_X_CDP_ENDPOINT="$BROWSER_ENDPOINT"
export FUNDRAISER_TELEGRAM_SENDER="$SENDER"
export FUNDRAISER_TELEGRAM_PHOTO_SENDER="$PHOTO_SENDER"
export FUNDRAISER_CAPTCHA_MODE="existing-capsolver-only"

CONTEXT_META="$(node --input-type=module - "$REPO_ROOT" <<'NODE'
import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

const root = process.argv[2];
const context = JSON.parse(await readFile(`${root}/.agents/startup-context.json`, "utf8"));
const { contextDigest } = await import(pathToFileURL(`${root}/scripts/startup-context/lib.mjs`));
process.stdout.write(`${context.context_version}\n${contextDigest(context)}\n`);
NODE
)" || { echo "fundraiser: canonical context preflight failed" >>"$LOG"; exit 2; }
export FUNDRAISER_CONTEXT_VERSION="$(printf '%s\n' "$CONTEXT_META" | sed -n '1p')"
export FUNDRAISER_CONTEXT_DIGEST="$(printf '%s\n' "$CONTEXT_META" | sed -n '2p')"
[ -n "$FUNDRAISER_CONTEXT_VERSION" ] && [ -n "$FUNDRAISER_CONTEXT_DIGEST" ] || {
  echo "fundraiser: canonical context metadata unavailable" >>"$LOG"
  exit 2
}

export FUNDRAISER_VERIFIED_DECK="$REPO_ROOT/fundraising/application-kit/deck.pdf"
node "$REPO_ROOT/skills/fundraiser-agent/runtime/verify-deck.mjs" \
  "$REPO_ROOT/.agents/startup-context.json" \
  "$REPO_ROOT/fundraising/application-kit/assets.json" \
  "$REPO_ROOT/fundraising/application-kit/deck.pdf.receipt.json" \
  "$FUNDRAISER_VERIFIED_DECK" >>"$LOG" 2>&1 || {
    echo "fundraiser: verified pitch deck preflight failed" >>"$LOG"
    exit 2
  }

RUNTIME_PROMPT="$EVIDENCE_DIR/runtime-prompt.md"
{
  cat "$PROMPT"
  cat <<EOF

## Concrete local runtime

- Continue both eligible program applications and introductions to new VCs or AI/AGI lab founders. Verify the recipient's current role and business contact route on an official organization page. Use startup-context facts to describe Life Manager as a manager that completes delegated real-world work and reports evidence; invite one public business recipient to one podcast, Zoom, or in-person discussion. For an in-person meeting, say I can travel if useful. Do not guess addresses, use private contacts, attach or send private data, or buy travel, lodging, or paid tickets. Outreach uses no attachment.
- The legacy DeepScale.Ventures unknown is permanently blocked. Do not rediscover or resend it under another name, cohort, purpose, contact route, digest, or occurrence.
- The target-intent recorder protocol supersedes older prepare/send directions. Process targets sequentially. Before each target, create a mode-600 final draft and run \`python3 "$REPO_ROOT/skills/fundraiser-agent/runtime/record-application.py" --prepare --occurrence "$FUNDRAISER_OCCURRENCE_ID" --draft <draft> --ledger "$FUNDRAISER_RECEIPTS" --applications-dir "$FUNDRAISER_APPLICATIONS_DIR" --expected-context-version "$FUNDRAISER_CONTEXT_VERSION" --expected-context-digest "$FUNDRAISER_CONTEXT_DIGEST"\`. This durably appends the target identity, occurrence, and digest.
  After final review, call the same recorder with \`--claim-effect --occurrence "$FUNDRAISER_OCCURRENCE_ID"\` and the same draft arguments immediately before the one Submit or email send. It records per-target \`effect_attempted\` before the external action; do not send if the claim command fails.
  After verified provider/Sent readback and Telegram photo receipt, finalize through the recorder. Prepare the next target only after the prior one is \`submitted_verified\` or \`verified_pre_effect_failure\`. For an unclaimed target with direct proof that no request was dispatched, the owner marker may be \`pre_effect\` before the first success or \`post_effect_verified\` after earlier success; leave it unchanged.
  If a target reaches \`effect_attempted\` or \`submit_unknown\` without a verified outcome, stop external effects for this occurrence and preserve its held marker. Never relabel an unknown as \`pre_effect\`. A later natural occurrence may work other targets while the exact unresolved target remains fenced. Never write terminal receipt rows directly.

- This is real run \`$RUN_ID\`, owned by \`ai.anicca.fundraiser\`.
- Work in \`$REPO_ROOT\`; use the registered CDP endpoint \`$FUNDRAISER_CDP_ENDPOINT\` and this run's seeded context \`$CLOAK_BROWSER_CONTEXT_ID\`. The existing CDP helper restricts page targets to that context. Never attach to another context or Dais's personal Chrome.
- Search both the live Web and rendered authenticated X UI. X is discovery only; verify on the official program website before applying.
- Use existing browser helpers under \`skills/browser/\`; do not launch or kill a browser.
- If the leased browser transport fails during this pass, do not acquire another lease, restart the browser, or continue provider actions. Preserve all existing receipts and return a non-success result with the transport observation. If any Submit or outbound request may have started, record submit_unknown and retain its exact identity fence; otherwise record the observation failure without claiming a provider effect. The next natural wake owns browser foundation recovery and fresh endpoint binding before dispatch.
- Read private founder values only from \`~/.config/anicca/job-search/profile.json\` and \`~/.local/share/anicca/credentials.json\`; never print or report their values.
- The only attachable pitch deck is the deterministic preflight-verified file \`$FUNDRAISER_VERIFIED_DECK\`; never attach another deck path.
- For draft preparation, the immediate effect claim, terminal status, and final receipt, use the target-intent recorder sequence above. Never write receipt rows directly.
- Write the durable next discovery cursor atomically to \`$STATE_ROOT/cursor.json\`.
- Immediately after every candidate terminal, execute \`bash $SENDER "Codex::: Fundraiser: <program, truthful status, non-secret readback, running counts>"\` and require \`TELEGRAM_SENT=true\`.
- An application is verified only after its official form completion page or exact Gmail Sent message is captured as a PNG, visually readable, sent with \`bash $PHOTO_SENDER "<png>" "Codex::: Fundraiser proof: <program>"\`, and the output contains \`TELEGRAM_PHOTO_SENT=true MSGID=<id>\`. Save them as exact top-level receipt keys \`"completion_png":"<absolute path>"\` and \`"telegram_photo_message_id":<integer>\`; mentioning them only inside \`readback_reference\` is invalid.
- First click a visible ordinary reCAPTCHA checkbox once through the rendered UI and observe. If it produces an image/audio challenge, use only the already-installed CapSolver/tier-a-bypass route found locally. Never weaken, evade, or disable provider security. If unavailable, checkpoint that candidate and continue to the next one.
- Spend this pass applying, not editing product code. Continue after the first submission. Return status=failure when submitted=0.
EOF
} >"$RUNTIME_PROMPT"
chmod 600 "$RUNTIME_PROMPT"

echo "=== fundraiser $RUN_ID start ===" >>"$LOG"
set +e
cat "$RUNTIME_PROMPT" | "$RUN_AGENT" \
  --task-class fundraiser-agent \
  --escalation-reason "Fundraiser program discovery and public VC or AI lab introductions with official readback" \
  --schema "$SCHEMA" \
  --evidence-dir "$EVIDENCE_DIR" \
  --task-label fundraiser-continuous \
  --loop fundraiser \
  --workdir "$REPO_ROOT" >>"$LOG" 2>&1
RC=$?
set -e

SUMMARY_STATUS="runner_failure"
COUNTS="submitted=0 unknown=0 checkpoints=0"
if [ "$RC" -eq 0 ] && [ -f "$EVIDENCE_DIR/summary.json" ]; then
  READBACK="$(python3 - "$EVIDENCE_DIR/summary.json" <<'PY'
import json, pathlib, sys
summary = json.loads(pathlib.Path(sys.argv[1]).read_text())
if (summary.get("selected_provider") != "codex"
        or summary.get("selected_model") != "gpt-6-luna"
        or summary.get("selected_effort") != "max"):
    raise SystemExit("fundraiser selected an unexpected model route")
result = json.loads(pathlib.Path(summary["result_path"]).read_text())
print(result["status"])
print(f'submitted={result["submitted"]} unknown={result["submit_unknown"]} checkpoints={result["checkpoints"]}')
PY
)" || RC=1
  SUMMARY_STATUS="$(printf '%s\n' "$READBACK" | sed -n '1p')"
  COUNTS="$(printf '%s\n' "$READBACK" | sed -n '2p')"
fi

if [ -f "$FUNDRAISER_RECEIPTS" ]; then
  LEDGER_COUNTS="$(python3 - "$FUNDRAISER_RECEIPTS" "$RUN_ID" <<'PY'
import json, pathlib, sys

submitted = unknown = checkpoints = 0
for line in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    try:
        receipt = json.loads(line)
    except json.JSONDecodeError:
        continue
    if receipt.get("run_id") != sys.argv[2]:
        continue
    status = receipt.get("status")
    submitted += status == "submitted_verified"
    unknown += status == "submit_unknown"
    checkpoints += status == "human_checkpoint"
print(f"submitted={submitted} unknown={unknown} checkpoints={checkpoints}")
PY
)" || true
  [ -n "$LEDGER_COUNTS" ] && COUNTS="$LEDGER_COUNTS"
fi

CHECKPOINTS="$(printf '%s\n' "$COUNTS" | sed -n 's/.*checkpoints=\([0-9][0-9]*\).*/\1/p')"
CURRENT_PHASE="$(sed -n 's/.*"phase":"\([^"]*\)".*/\1/p' "$MARKER_PATH" 2>/dev/null || true)"
if [ "$CURRENT_PHASE" = "pre_effect" ] \
    && { [ "${CHECKPOINTS:-0}" -gt 0 ] || [ "$SUMMARY_STATUS" = "human_required" ]; }; then
  write_boundary_marker human_required 0 || true
fi

REPORT="Codex::: Fundraiser wake $RUN_ID finished: status=$SUMMARY_STATUS, $COUNTS. Evidence: $EVIDENCE_DIR"
"$SENDER" "$REPORT" >>"$LOG" 2>&1 || RC=1
echo "=== fundraiser $RUN_ID end rc=$RC status=$SUMMARY_STATUS $COUNTS ===" >>"$LOG"
exit "$RC"
