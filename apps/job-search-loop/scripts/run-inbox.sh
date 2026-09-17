#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
source "$SCRIPT_DIR/runtime-paths.sh"
source "$SCRIPT_DIR/private-env.sh"

RUN_ID="inbox-$(date +%Y%m%d-%H%M%S)-$$"
EVIDENCE="$JOB_SEARCH_STATE_ROOT/evidence/$RUN_ID"
SEEN_STATE="$JOB_SEARCH_STATE_ROOT/inbox-seen.json"
CANDIDATES="$EVIDENCE/candidates.json"
PROMPT="$EVIDENCE/prompt.md"
PREP_DATABASE="$JOB_SEARCH_STATE_ROOT/interview-prep.sqlite3"
OUTBOX_DATABASE="$JOB_SEARCH_STATE_ROOT/ledger.sqlite3"
PREP_STATUS="$EVIDENCE/prep-status.json"
TELEGRAM_OUTBOX="$JOB_SEARCH_STATE_ROOT/telegram-outbox.sqlite3"
TERMINAL_REPORT="$EVIDENCE/inbox-terminal.json"
FINAL_OUTCOME="failed"
FINAL_REASON="inbox_wake_failed"
GMAIL_ACCOUNT="${JOB_SEARCH_GMAIL_ACCOUNT:-}"
export JOB_SEARCH_MACHINE_CREDENTIALS="${XDG_DATA_HOME:-$HOME/.local/share}/anicca/credentials.json"

mkdir -p "$EVIDENCE" "$JOB_SEARCH_STATE_ROOT/logs"
chmod 700 \
  "$JOB_SEARCH_STATE_ROOT" \
  "$JOB_SEARCH_STATE_ROOT/evidence" \
  "$EVIDENCE" \
  "$JOB_SEARCH_STATE_ROOT/logs"
export PYTHONPATH="$JOB_SEARCH_APP_ROOT"
finalize() {
  local original_rc="$1"
  trap - EXIT
  set +e
  "$JOB_SEARCH_PYTHON" -m job_search_loop.application_reporting terminal \
    --ledger "$JOB_SEARCH_STATE_ROOT/ledger.sqlite3" \
    --outbox "$TELEGRAM_OUTBOX" \
    --run-id "$RUN_ID" \
    --outcome "$FINAL_OUTCOME" \
    --reason "$FINAL_REASON" \
    --output "$TERMINAL_REPORT"
  if [[ ! -f "$TERMINAL_REPORT" ]]; then
    printf '{"delivery":"delivery_unknown","event_key":"job-search-inbox:%s","outcome":"%s","reason":"%s"}\n' \
      "$RUN_ID" "$FINAL_OUTCOME" "$FINAL_REASON" >"$TERMINAL_REPORT"
  fi
  find "$EVIDENCE" -type d -exec chmod 700 {} +
  find "$EVIDENCE" -type f -exec chmod 600 {} +
  exit "$original_rc"
}
trap 'finalize $?' EXIT
job_search_load_private_env GOG_KEYRING_PASSWORD || {
  print -u2 "job-search inbox: GOG_KEYRING_PASSWORD is unavailable"
  FINAL_REASON="gmail_private_env_unavailable"
  exit 78
}
if [[ -z "$GMAIL_ACCOUNT" ]]; then
  GMAIL_ACCOUNT=$("$JOB_SEARCH_JQ" -er \
    '.candidate.application_email // empty' "$JOB_SEARCH_PROFILE")
fi
"$JOB_SEARCH_PYTHON" -m job_search_loop.interview_prep deliver \
  --database "$PREP_DATABASE" \
  --outbox "$OUTBOX_DATABASE" \
  --output "$EVIDENCE/prep-deliver-before.json"
"$JOB_SEARCH_PYTHON" -m job_search_loop.submission_confirmation reconcile \
  --account "$GMAIL_ACCOUNT" \
  --ledger "$JOB_SEARCH_STATE_ROOT/ledger.sqlite3" \
  --seen "$SEEN_STATE" \
  --output "$EVIDENCE/submission-confirmations-before.json"
"$JOB_SEARCH_PYTHON" -m job_search_loop.application_reporting deliver \
  --ledger "$JOB_SEARCH_STATE_ROOT/ledger.sqlite3" \
  --outbox "$TELEGRAM_OUTBOX" \
  --media-root "$JOB_SEARCH_TELEGRAM_MEDIA" \
  --output "$EVIDENCE/resume-deliver-before.json"
JAPAN_DAY=$(TZ=Asia/Tokyo /bin/date +%F)
"$JOB_SEARCH_PYTHON" -m job_search_loop.summary \
  --ledger "$JOB_SEARCH_STATE_ROOT/ledger.sqlite3" \
  --output "$JOB_SEARCH_STATE_ROOT/summary.v2.json" \
  --compat-output "$JOB_SEARCH_STATE_ROOT/summary.v1.json" \
  --day "$JAPAN_DAY" \
  --model-route "shared-agent-runner"
"$JOB_SEARCH_PYTHON" -m job_search_loop.inbox scan \
  --account "$GMAIL_ACCOUNT" \
  --state "$SEEN_STATE" \
  --output "$CANDIDATES" \
  --prompt-base "$JOB_SEARCH_APP_ROOT/prompts/inbox-pass.md" \
  --prompt-output "$PROMPT" \
  --summary "$EVIDENCE/summary.json"
"$JOB_SEARCH_PYTHON" -m job_search_loop.interview_prep pending \
  --database "$PREP_DATABASE" \
  --output "$PREP_STATUS"
"$JOB_SEARCH_PYTHON" -m job_search_loop.interview_prep append-prompt \
  --database "$PREP_DATABASE" \
  --prompt "$PROMPT" \
  --profile "$JOB_SEARCH_PROFILE"
NEW_COUNT=$("$JOB_SEARCH_JQ" -r '.new_count' "$CANDIDATES")
PENDING_PREP_COUNT=$("$JOB_SEARCH_JQ" -r '.pending_count' "$PREP_STATUS")
RESET_COUNT=$("$JOB_SEARCH_JQ" -r '
  [.messages[] | select(
    (.subject | contains("Reset your password for your candidate account")) and
    (.sender | ascii_downcase | contains("@otp.workday.com"))
  )] | length' "$CANDIDATES")
if [[ "$NEW_COUNT" -gt 0 && "$RESET_COUNT" == "$NEW_COUNT" ]]; then
  RESET_RECEIPTS="$EVIDENCE/workday-account-mail-receipts.jsonl"
  RESET_RESULT="$EVIDENCE/workday-account-mail-result.json"
  : >"$RESET_RECEIPTS"
  "$JOB_SEARCH_JQ" -r '.messages[] | [.thread_id,.message_id] | @tsv' "$CANDIDATES" | \
    while IFS=$'\t' read -r thread_id message_id; do
    "$JOB_SEARCH_PYTHON" -m job_search_loop.workday_account_mail \
      --account "$GMAIL_ACCOUNT" \
      --thread-id "$thread_id" \
      --message-id "$message_id" \
      --credential-store "$JOB_SEARCH_MACHINE_CREDENTIALS" \
      --database "$JOB_SEARCH_STATE_ROOT/workday-verifications.sqlite3" \
      --endpoint "http://127.0.0.1:9222" \
      >>"$RESET_RECEIPTS"
  done
  "$JOB_SEARCH_JQ" -s \
    --argjson messages "$("$JOB_SEARCH_JQ" '.message_ids' "$CANDIDATES")" \
    --argjson threads "$("$JOB_SEARCH_JQ" '.thread_ids' "$CANDIDATES")" \
    '{status:"workday_account_mail_processed",processed_threads:($threads|length),processed_thread_ids:$threads,processed_message_ids:$messages,calendar_events:[],replies:[],assessments:[],prep_packs:[],verifications:.,reports:[]}' \
    "$RESET_RECEIPTS" >"$RESET_RESULT"
  "$JOB_SEARCH_PYTHON" -m job_search_loop.inbox mark \
    --state "$SEEN_STATE" \
    --input "$CANDIDATES" \
    --result "$RESET_RESULT"
  FINAL_OUTCOME="success"
  FINAL_REASON="messages_processed"
  exit 0
fi
if [[ "$NEW_COUNT" == "0" && "$PENDING_PREP_COUNT" == "0" ]]; then
  "$JOB_SEARCH_PYTHON" -m job_search_loop.submission_confirmation reconcile \
    --account "$GMAIL_ACCOUNT" \
    --ledger "$JOB_SEARCH_STATE_ROOT/ledger.sqlite3" \
    --seen "$SEEN_STATE" \
    --output "$EVIDENCE/submission-confirmations.json"
  "$JOB_SEARCH_PYTHON" -m job_search_loop.application_reporting deliver \
    --ledger "$JOB_SEARCH_STATE_ROOT/ledger.sqlite3" \
    --outbox "$TELEGRAM_OUTBOX" \
    --media-root "$JOB_SEARCH_TELEGRAM_MEDIA" \
    --output "$EVIDENCE/resume-deliver-reconciled.json"
  FINAL_OUTCOME="no_work"
  FINAL_REASON="no_new_messages_or_preparation"
  exit 0
fi
set +e
"$JOB_SEARCH_PYTHON" "$JOB_SEARCH_RUNNER" \
  --task-class composition-agent \
  --prompt-stdin \
  --schema "$JOB_SEARCH_APP_ROOT/schemas/inbox-pass-result.v1.schema.json" \
  --evidence-dir "$EVIDENCE" \
  --task-label job-search-inbox \
  --loop job-search \
  --workdir "$JOB_SEARCH_REPO_ROOT" \
  <"$PROMPT"
RUNNER_RC=$?
set -e
if [[ "$RUNNER_RC" -ne 0 ]]; then
  FINAL_REASON="runner_failed"
  exit "$RUNNER_RC"
fi
RESULT_PATH=$("$JOB_SEARCH_JQ" -er \
  '.result_path | select(type == "string" and length > 0)' \
  "$EVIDENCE/summary.json")
case "$RESULT_PATH" in
  "$EVIDENCE"/attempt-*.result.json) ;;
  *)
    echo "inbox result path escaped current evidence directory" >&2
    FINAL_REASON="result_path_invalid"
    exit 2
    ;;
esac
MENTAL_OUTCOME_OUTPUT="$EVIDENCE/mental-outcomes.json"
MENTAL_OUTCOME_ARGS=(
  --ledger "$JOB_SEARCH_STATE_ROOT/ledger.sqlite3"
  --candidates "$CANDIDATES"
  --result "$RESULT_PATH"
  --output "$MENTAL_OUTCOME_OUTPUT"
)
if [[ -n "${LIFE_MANAGER_MENTAL_OUTCOME_ENDPOINT:-}" ]]; then
  MENTAL_OUTCOME_ARGS+=(
    --endpoint "$LIFE_MANAGER_MENTAL_OUTCOME_ENDPOINT"
    --secret "${LIFE_MANAGER_MENTAL_OUTCOME_SECRET:-}"
  )
fi
"$JOB_SEARCH_PYTHON" -m job_search_loop.mental_outcome_projection "${MENTAL_OUTCOME_ARGS[@]}"
"$JOB_SEARCH_PYTHON" -m job_search_loop.inbox mark \
  --state "$SEEN_STATE" \
  --input "$CANDIDATES" \
  --result "$RESULT_PATH"
"$JOB_SEARCH_PYTHON" -m job_search_loop.submission_confirmation reconcile \
  --account "$GMAIL_ACCOUNT" \
  --ledger "$JOB_SEARCH_STATE_ROOT/ledger.sqlite3" \
  --seen "$SEEN_STATE" \
  --output "$EVIDENCE/submission-confirmations.json"
"$JOB_SEARCH_PYTHON" -m job_search_loop.application_reporting deliver \
  --ledger "$JOB_SEARCH_STATE_ROOT/ledger.sqlite3" \
  --outbox "$TELEGRAM_OUTBOX" \
  --media-root "$JOB_SEARCH_TELEGRAM_MEDIA" \
  --output "$EVIDENCE/resume-deliver-reconciled.json"
"$JOB_SEARCH_PYTHON" -m job_search_loop.summary \
  --ledger "$JOB_SEARCH_STATE_ROOT/ledger.sqlite3" \
  --output "$JOB_SEARCH_STATE_ROOT/summary.v2.json" \
  --compat-output "$JOB_SEARCH_STATE_ROOT/summary.v1.json" \
  --day "$JAPAN_DAY" \
  --model-route "shared-agent-runner"
"$JOB_SEARCH_PYTHON" -m job_search_loop.interview_prep deliver \
  --database "$PREP_DATABASE" \
  --outbox "$OUTBOX_DATABASE" \
  --output "$EVIDENCE/prep-deliver-after.json"
FINAL_OUTCOME="success"
FINAL_REASON="processed"
