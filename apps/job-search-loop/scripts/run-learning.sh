#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
source "$SCRIPT_DIR/runtime-paths.sh"

RUN_ID="learning-$(date +%Y%m%d-%H%M%S)-$$"
EVIDENCE="$JOB_SEARCH_STATE_ROOT/evidence/$RUN_ID"
REPORT="$EVIDENCE/learning-decision.json"
SUMMARY="$EVIDENCE/summary.json"
MERCOR_SOURCES="$EVIDENCE/mercor-learning-sources.json"
MERCOR_SOURCES_SUMMARY="$EVIDENCE/mercor-learning-sources-summary.json"
TELEGRAM_OUTBOX="$JOB_SEARCH_STATE_ROOT/telegram-outbox.sqlite3"

mkdir -p "$EVIDENCE" "$JOB_SEARCH_STATE_ROOT/logs"
chmod 700 \
  "$JOB_SEARCH_STATE_ROOT" \
  "$JOB_SEARCH_STATE_ROOT/evidence" \
  "$EVIDENCE" \
  "$JOB_SEARCH_STATE_ROOT/logs"
export PYTHONPATH="$JOB_SEARCH_APP_ROOT"

if [[ "${MERCOR_LEARNING_SOURCES_SKIP:-0}" == "1" ]]; then
  printf '%s\n' '{"version":1,"source_count":0,"sources":[],"income_receipts_promoted":0}' >"$MERCOR_SOURCES"
  printf '%s\n' '{"status":"skipped"}' >"$MERCOR_SOURCES_SUMMARY"
else
  set +e
  "$JOB_SEARCH_PYTHON" -m job_search_loop.mercor_learning_sources collect \
    --output "$MERCOR_SOURCES" \
    --query "${MERCOR_LEARNING_QUERY:-Mercor Japanese AI evaluator application}" \
    >"$MERCOR_SOURCES_SUMMARY"
  SOURCE_RC=$?
  set -e
  if [[ "$SOURCE_RC" -ne 0 ]]; then
    printf '%s\n' "Mercor source collection failed; strategy learning continues" >&2
  fi
fi
chmod 600 "$MERCOR_SOURCES_SUMMARY"

"$JOB_SEARCH_PYTHON" -m job_search_loop.learning run \
  --ledger "$JOB_SEARCH_STATE_ROOT/ledger.sqlite3" \
  --strategy "$JOB_SEARCH_APP_ROOT/config/strategy.default.json" \
  --replay "$JOB_SEARCH_APP_ROOT/config/learning-replay.v1.json" \
  --report "$REPORT" \
  --outbox "$TELEGRAM_OUTBOX" \
  >"$SUMMARY"
chmod 600 "$REPORT" "$SUMMARY"
