#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="${0:A:h}"
source "$SCRIPT_DIR/runtime-paths.sh"
export PYTHONPATH="$JOB_SEARCH_APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"

CURRENT_RUN=""
if [[ "${1:-}" == "--current-run" ]]; then
  CURRENT_RUN="${2:?missing current run path}"
  shift 2
fi
if (( $# != 0 )); then
  print -u2 "retain-evidence: unsupported arguments"
  exit 2
fi

if [[ "${JOB_SEARCH_EVIDENCE_RETENTION_DISABLE:-0}" == "1" ]]; then
  exit 0
fi

ARGS=(
  -m job_search_loop.evidence_retention
  --root "$JOB_SEARCH_STATE_ROOT/evidence"
  --receipt "$JOB_SEARCH_STATE_ROOT/evidence-retention/last.json"
  --min-age-seconds "${JOB_SEARCH_EVIDENCE_RETENTION_MIN_AGE_SECONDS:-604800}"
  --min-free-bytes "${JOB_SEARCH_EVIDENCE_RETENTION_MIN_FREE_BYTES:-536870912}"
  --max-evidence-bytes "${JOB_SEARCH_EVIDENCE_RETENTION_MAX_BYTES:-2147483648}"
)
if [[ -n "$CURRENT_RUN" ]]; then
  ARGS+=(--current-run "$CURRENT_RUN")
fi
exec "$JOB_SEARCH_PYTHON" "${ARGS[@]}"
