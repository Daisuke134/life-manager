#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

FAKE_ROOT="$TMP/writer-agent"
STATE_DIR="$TMP/state"
RUN_DIR="$STATE_DIR/runs/daily-2026-07-29"
mkdir -p "$FAKE_ROOT/scripts" "$FAKE_ROOT/runtime" "$RUN_DIR/gates"
cp "$ROOT/scripts/article-resume-pending.sh" "$FAKE_ROOT/scripts/"
cp "$ROOT/scripts/publication_contract_resolver.py" "$FAKE_ROOT/scripts/"
cp "$ROOT/scripts/publication_contract.py" "$FAKE_ROOT/scripts/"
cp "$ROOT/scripts/article_adoption_selection.py" "$FAKE_ROOT/scripts/"
cp "$ROOT/scripts/execute-initialization-pair.py" "$FAKE_ROOT/scripts/" 2>/dev/null || true

cat >"$FAKE_ROOT/scripts/writer-runtime-env.sh" <<'SH'
ARTICLE_ROOT="${ARTICLE_ROOT:?}"
ARTICLE_SKILL_DIR="$ARTICLE_ROOT"
STATE_DIR="${ARTICLE_STATE_DIR:?}"
WRITER_STATE_DIR="$STATE_DIR"
WRITER_LOG_DIR="${ARTICLE_RESUME_LOG%/*}"
WRITER_BROWSER_PYTHON="$(command -v python3)"
WRITER_CLOAK_PYTHON="$WRITER_BROWSER_PYTHON"
LIFE_MANAGER_PYTHON="$WRITER_BROWSER_PYTHON"
export ARTICLE_ROOT ARTICLE_SKILL_DIR STATE_DIR WRITER_STATE_DIR WRITER_LOG_DIR
export WRITER_BROWSER_PYTHON WRITER_CLOAK_PYTHON LIFE_MANAGER_PYTHON
SH
cat >"$FAKE_ROOT/scripts/writer_unavailable_incident_bridge.py" <<'PY'
raise SystemExit(0)
PY

cat >"$FAKE_ROOT/scripts/article_daily_start_control.py" <<'PY'
print('{"action":"skip-pending-worker"}')
PY
cat >"$FAKE_ROOT/scripts/recover-known-unavailable.py" <<'PY'
raise SystemExit(0)
PY
cat >"$FAKE_ROOT/scripts/article_pending.py" <<PY
import json
print(json.dumps({
  "status": "READY",
  "run_id": "daily-2026-07-29",
  "run_dir": "$RUN_DIR",
  "state_path": "$RUN_DIR/gates/publication-state.json",
  "ledger_path": "$STATE_DIR/articles.jsonl",
  "initialization_pairs": ["note/ja"],
  "eligible_pairs": [],
}))
PY
cat >"$FAKE_ROOT/runtime/model-runner-support.py" <<'PY'
raise SystemExit(0)
PY
cat >"$FAKE_ROOT/runtime/model-runner.sh" <<SH
#!/usr/bin/env bash
touch "$TMP/model-was-called"
while [ "\$#" -gt 0 ]; do
  [ "\$1" = "--prompt-file" ] && cp "\$2" "$TMP/model-prompt.txt"
  shift
done
exit 0
SH
chmod +x "$FAKE_ROOT/runtime/model-runner.sh"
cat >"$FAKE_ROOT/runtime/judge-broker.sh" <<'SH'
#!/usr/bin/env bash
exit 0
SH
chmod +x "$FAKE_ROOT/runtime/judge-broker.sh"

cat >"$FAKE_ROOT/scripts/fake-note-stage.py" <<'PY'
import json, os
p = os.environ["ARTICLE_PUBLICATION_STATE"]
d = json.load(open(p))
d.setdefault("pairs", {})["note/ja"] = {
    "platform": "note", "lang": "ja", "target_kind": "note-key",
    "target": "n-test-key", "status": "intent",
}
json.dump(d, open(p, "w"))
open(os.environ["CALL_LOG"], "a").write("called\n")
PY

cat >"$RUN_DIR/gates/publication-state.json" <<JSON
{"version":1,"publication_contract":"active-six","run_id":"daily-2026-07-29","pairs":{"x-article/en":{"status":"skipped","skip_receipt":{"type":"dormant-destination","pair":"x-article/en","reason":"dormant-destination","slo":"not-applicable","recorded_at":"2026-08-05T00:00:00Z"}},"x-post/ja":{"status":"skipped","skip_receipt":{"type":"dormant-destination","pair":"x-post/ja","reason":"dormant-destination","slo":"not-applicable","recorded_at":"2026-08-05T00:00:00Z"}}}}
JSON
: >"$STATE_DIR/articles.jsonl"
# STEP 5 was killed after persisting only a sibling row: the manifest is
# non-empty but carries no note/ja row to replay.
cat >"$RUN_DIR/gates/platform-dispatch.jsonl" <<JSONL
{"platform":"substack","lang":"ja","argv":["false"],"env":{"ARTICLE_RUN_DIR":"$RUN_DIR","ARTICLE_PUBLICATION_STATE":"$RUN_DIR/gates/publication-state.json","ARTICLE_LEDGER":"$STATE_DIR/articles.jsonl"}}
JSONL
MANIFEST_SHA="$(shasum -a 256 "$RUN_DIR/gates/platform-dispatch.jsonl")"

if ! ARTICLE_ROOT="$FAKE_ROOT" \
ARTICLE_STATE_DIR="$STATE_DIR" \
ARTICLE_LOCAL_DATE="2026-07-29" \
ARTICLE_OWNER_FENCE_ACTIVE=1 \
ARTICLE_RESUME_LOG="$TMP/resume.log" \
ARTICLE_MODEL_RUNNER="$FAKE_ROOT/runtime/model-runner.sh" \
bash "$FAKE_ROOT/scripts/article-resume-pending.sh"; then
  cat "$TMP/resume.log" >&2
  exit 1
fi

# The missing staging row is typed, not "expected one row, got 0" rc=1 every
# tick, and the same-run model staging path owns the missing target (2026-10-12).
! grep -q Traceback "$TMP/resume.log"
grep -q "dispatch-row-missing" "$TMP/resume.log"
test -e "$TMP/model-was-called"
grep -q "initialization_pairs" "$TMP/model-prompt.txt"
grep -q "STEP 5 staging path for that missing pair" "$TMP/model-prompt.txt"
test "$(shasum -a 256 "$RUN_DIR/gates/platform-dispatch.jsonl")" = "$MANIFEST_SHA"
python3 - "$RUN_DIR/gates/publication-state.json" <<'PY2'
import json, sys
assert "note/ja" not in json.load(open(sys.argv[1]))["pairs"]
PY2

echo "PASS: partial dispatch manifest without note/ja routes to same-run model staging"
