#!/usr/bin/env bash
# Shared provider-agnostic boundary for revenue-loop judgment work.
# Consumers choose only a task class; provider/model routing lives in
# runtime/agent-runner/config.json (or AGENT_RUNNER_CONFIG).
set -euo pipefail

TASK_CLASS=""
EVIDENCE_DIR=""
TASK_LABEL=""
LOOP=""
SCHEMA=""
ESCALATION_REASON=""
WORKDIR="${AGENT_RUNNER_WORKDIR:-$HOME}"
PRINT_RESULT=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --task-class) TASK_CLASS="${2:-}"; shift 2 ;;
    --evidence-dir) EVIDENCE_DIR="${2:-}"; shift 2 ;;
    --task-label) TASK_LABEL="${2:-}"; shift 2 ;;
    --loop) LOOP="${2:-}"; shift 2 ;;
    --schema) SCHEMA="${2:-}"; shift 2 ;;
    --escalation-reason) ESCALATION_REASON="${2:-}"; shift 2 ;;
    --workdir) WORKDIR="${2:-}"; shift 2 ;;
    --print-result) PRINT_RESULT=1; shift ;;
    *) echo "run_agent.sh: unknown argument: $1" >&2; exit 2 ;;
  esac
done

case "$TASK_CLASS" in
  # Keep this in sync with runtime/agent-runner/config.json.  Capafy's CP1/CP2/CP3
  # browser flow deliberately uses application-lane-agent (3600s); rejecting it
  # here made the bounded drainer fail before the provider could start.
  repeatable-agent|tool-agent|browser-lane-agent|application-lane-agent|application-intent-planner|marketing-agent|high-value-agent|self-heal-code-agent) ;;
  *) echo "run_agent.sh: invalid or missing --task-class" >&2; exit 2 ;;
esac
[ -n "$EVIDENCE_DIR" ] || { echo "run_agent.sh: missing --evidence-dir" >&2; exit 2; }
[ -n "$TASK_LABEL" ] || { echo "run_agent.sh: missing --task-label" >&2; exit 2; }
[ -n "$LOOP" ] || { echo "run_agent.sh: missing --loop" >&2; exit 2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RUNNER="${AGENT_RUNNER_BIN:-$REPO_ROOT/runtime/agent-runner/agent_runner.py}"
SCHEMA="${SCHEMA:-$SCRIPT_DIR/schemas/loop_pass.schema.json}"

# Read and vet the caller's prompt BEFORE anything else can fail, because the
# FINAL CONTRACT appended below is ~180 chars: an empty caller prompt would
# otherwise sail past the runner's own floor and buy a paid greeting. Loop
# prompts are thousands of characters, so anything at this floor means the
# caller built it wrong (unset variable, failed heredoc) and must not be paid
# for. Floor matches agent_runner.MIN_PROMPT_CHARS on purpose.
PROMPT_FILE="$(mktemp "${TMPDIR:-/tmp}/marketing-agent-prompt.XXXXXX")"
trap 'rm -f "$PROMPT_FILE"' EXIT
cat >"$PROMPT_FILE"
MIN_PROMPT_CHARS="${RUN_AGENT_MIN_PROMPT_CHARS:-16}"
PROMPT_CHARS="$(tr -d '[:space:]' <"$PROMPT_FILE" | wc -c | tr -d ' ')"
if [ "$PROMPT_CHARS" -lt "$MIN_PROMPT_CHARS" ]; then
  echo "run_agent.sh: refusing to spend on an empty/trivial prompt (${PROMPT_CHARS} chars < ${MIN_PROMPT_CHARS})" >&2
  exit 2
fi

[ -f "$RUNNER" ] || { echo "run_agent.sh: runner not found: $RUNNER" >&2; exit 2; }
[ -f "$SCHEMA" ] || { echo "run_agent.sh: schema not found: $SCHEMA" >&2; exit 2; }

mkdir -p "$EVIDENCE_DIR"
cat >>"$PROMPT_FILE" <<'EOF'

FINAL CONTRACT: after completing the bounded work, return only JSON that satisfies the supplied output schema. Never claim an action without concrete evidence in the evidence array.
EOF

RUNNER_STDOUT="$EVIDENCE_DIR/runner.stdout.log"
PROMPT_ARGS=(--prompt-file "$PROMPT_FILE")
[ "$TASK_CLASS" = "application-intent-planner" ] && PROMPT_ARGS=(--prompt-stdin)
set +e
/usr/bin/python3 "$RUNNER" \
  --task-class "$TASK_CLASS" \
  --escalation-reason "$ESCALATION_REASON" \
  "${PROMPT_ARGS[@]}" \
  --schema "$SCHEMA" \
  --evidence-dir "$EVIDENCE_DIR" \
  --task-label "$TASK_LABEL" \
  --loop "$LOOP" \
  --workdir "$WORKDIR" <"$PROMPT_FILE" >"$RUNNER_STDOUT"
RC=$?
set -e

if [ "$RC" -ne 0 ]; then
  cat "$RUNNER_STDOUT" >&2
  exit "$RC"
fi

if [ "$PRINT_RESULT" -eq 1 ]; then
  /usr/bin/python3 - "$EVIDENCE_DIR/summary.json" <<'PY'
import json, pathlib, sys
summary = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
result = summary.get("result_path")
if not result:
    raise SystemExit("run_agent.sh: successful summary has no result_path")
print(pathlib.Path(result).read_text(encoding="utf-8"), end="")
PY
else
  cat "$RUNNER_STDOUT"
fi
