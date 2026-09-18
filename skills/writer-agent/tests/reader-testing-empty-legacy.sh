#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
TMP="$(mktemp -d /tmp/article-reader-empty-legacy.XXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/run/gates"

cat >"$TMP/bin/model-runner" <<'FAKE'
#!/usr/bin/env bash
set -euo pipefail
test "$1" = judge
test "$2" = --prompt-file
test "$3" = -
prompt="$(cat)"
printf 'CALL\n' >>"$FAKE_CALLS"
if [[ "$prompt" == *"generating a reader-testing question set"* ]]; then
  printf '%s\n' '{"questions":["Q1?","Q2?","Q3?","Q4?","Q5?"]}'
else
  printf '%s\n' '{"unanswered_questions":[]}'
fi
FAKE
chmod +x "$TMP/bin/model-runner"
printf '# Title\n\nBody.\n' >"$TMP/article.md"
: >"$TMP/run/gates/reader-testing-gate-ja.json"

export ARTICLE_MODEL_RUNNER="$TMP/bin/model-runner"
export FAKE_CALLS="$TMP/calls"
export ARTICLE_RUN_DIR="$TMP/run"

bash "$ROOT/skills/writer-agent/scripts/reader-testing-gate.sh" \
  "$TMP/article.md" --lang ja --questions-file "$TMP/run/gates/questions-ja.json" \
  >"$TMP/result.json"

test "$(grep -c '^CALL$' "$TMP/calls")" -eq 2
jq -e '.verdict == "PASS" and .status == "pass"' "$TMP/result.json" >/dev/null

# A model-led caller may redirect stdout directly to the canonical terminal path.
# Shell truncation happens before gate-attempt-control.py begin runs; an empty
# terminal file must be treated as absent at begin, then replaced by the strict
# hash-bound terminal receipt at finish.
mkdir -p "$TMP/run-terminal/gates"
: >"$TMP/run-terminal/gates/reader-testing-gate-en.terminal.json"
ARTICLE_RUN_DIR="$TMP/run-terminal" bash "$ROOT/skills/writer-agent/scripts/reader-testing-gate.sh" \
  "$TMP/article.md" --lang en --questions-file "$TMP/run-terminal/gates/questions-en.json" \
  >"$TMP/run-terminal/gates/reader-testing-gate-en.terminal.json"

test "$(grep -c '^CALL$' "$TMP/calls")" -eq 4
jq -e '.gate == "reader-testing-gate" and .lang == "en" and .status == "pass"' \
  "$TMP/run-terminal/gates/reader-testing-gate-en.terminal.json" >/dev/null
echo 'PASS: empty legacy and redirected terminal reader evidence are treated as absent at begin'
