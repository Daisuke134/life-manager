#!/usr/bin/env bash
# Run 20261017-033711: the agent revised EN, then ended its turn while identity-en and
# conscience were still running, so a staged continuous-policy package never reached
# publication init. prepublication-finish.sh must finish identity -> quality assess ->
# conscience -> init deterministically, and never override a strict or blocked run.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FINISH="$ROOT/scripts/prepublication-finish.sh"
TMP="$(cd "$(mktemp -d)" && pwd -P)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin" "$TMP/logs"

cat >"$TMP/bin/model-runner" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
prompt="$(cat)"
case "$prompt" in
  *"identity/honesty reviewer"*)
    printf 'identity\n' >>"$FAKE_MODEL_CALLS"
    printf '%s\n' '{"verdict":"PASS","violations":[]}' ;;
  *"publication conscience reviewer"*)
    printf 'conscience\n' >>"$FAKE_MODEL_CALLS"
    if [ "${FAKE_CONSCIENCE:-ALLOW}" = BLOCK ]; then
      printf '%s\n' '{"verdict":"BLOCK","reasons":["names a private person"]}'
    else
      printf '%s\n' '{"verdict":"ALLOW","reasons":[]}'
    fi ;;
  *) printf 'unexpected\n' >>"$FAKE_MODEL_CALLS"; exit 9 ;;
esac
EOF
cat >"$TMP/bin/publication_resume.py" <<'EOF'
import json, os, sys
with open(os.environ["FAKE_INIT_ARGS"], "w", encoding="utf-8") as handle:
    json.dump(sys.argv[1:], handle)
state = sys.argv[sys.argv.index("--state") + 1]
with open(state, "w", encoding="utf-8") as handle:
    json.dump({"publication_contract": "active-four"}, handle)
EOF
chmod +x "$TMP/bin/model-runner"

export ARTICLE_MODEL_RUNNER="$TMP/bin/model-runner"
export ARTICLE_PUBLICATION_RESUME="$TMP/bin/publication_resume.py"
export ARTICLE_GATES_LOG="$TMP/logs/gates.log"
export WRITER_LOG_DIR="$TMP/logs" WRITER_STATE_DIR="$TMP" LIFE_MANAGER_ENV_FILE=/dev/null
export FAKE_MODEL_CALLS="$TMP/model-calls" FAKE_INIT_ARGS="$TMP/init-args.json"
export ARTICLE_LEDGER="$TMP/articles.jsonl"
unset ARTICLE_RUN_DIR

# `a && b` does not trip set -e when a fails; every compound assertion ends in fail.
fail() { echo "assertion failed at line $1" >&2; exit 1; }

sha() { shasum -a 256 "$1" | awk '{print $1}'; }

make_run() {
  local run="$TMP/runs/$1"
  rm -rf "$run"
  mkdir -p "$run/gates"
  printf '# 日本語\n\n本文。\n' >"$run/article-ja.md"
  printf '# English\n\nRevised body with sourced figures.\n' >"$run/article-en.md"
  printf 'post\n' >"$run/x-post-ja.txt"
  printf 'png\n' >"$run/headline-image.png"
  printf 'png\n' >"$run/body-diagram.png"
  printf '%s\n' '{"topic_id":"paid-demand:abc","editorial_form":"how-to"}' >"$run/gates/topic-route.json"
  printf '{"verdict":"PASS","fixes":[],"strengths":[],"article_sha256":"%s"}\n' \
    "$(sha "$run/article-ja.md")" >"$run/gates/editorial-ja.json"
  # The EN receipt is the pre-revision FAIL: bound to bytes that no longer exist.
  printf '{"verdict":"FAIL","fixes":["cite"],"strengths":[],"article_sha256":"%s"}\n' \
    "$(printf 'old' | shasum -a 256 | awk '{print $1}')" >"$run/gates/editorial-en.json"
  printf '{"verdict":"PASS","violations":[],"article_sha256":"%s"}\n' \
    "$(sha "$run/article-ja.md")" >"$run/gates/identity-ja.json"
  : >"$FAKE_MODEL_CALLS"
  rm -f "$FAKE_INIT_ARGS"
  : >"$ARTICLE_LEDGER"
  printf '%s' "$run"
}

# 1. Continuous policy: stale EN editorial FAIL is advisory; the package reaches init.
RUN="$(make_run 20261017-033711)"
ARTICLE_PUBLICATION_POLICY=continuous bash "$FINISH" --run-dir "$RUN" >"$TMP/out1" 2>&1 \
  || { cat "$TMP/out1"; exit 1; }
[ "$(cat "$FAKE_MODEL_CALLS")" = "$(printf 'identity\nconscience\nconscience')" ]
jq -e '.action == "force_publish_advisory"' "$RUN/gates/quality-self-heal.json" >/dev/null
jq -e --arg h "$(sha "$RUN/article-en.md")" \
  '.article_sha256 == $h and .editorial_gate == "ADVISORY" and .safety_gate == "ALLOW"' \
  "$RUN/gates/quality-terminal-en.json" >/dev/null
jq -e --arg run "$RUN" --arg ledger "$ARTICLE_LEDGER" '
  (index("init") as $i | $i != null)
  and (.[index("--state") + 1] == ($run + "/gates/publication-state.json"))
  and (.[index("--ledger") + 1] == $ledger)
  and (.[index("--run-id") + 1] == "20261017-033711")
  and (.[index("--topic-id") + 1] == "paid-demand:abc")
  and (.[index("--safety") + 1] == "ALLOW")
  and (.[index("--body-asset") + 1] == ($run + "/body-diagram.png"))
  and (index("--require-quality") != null)' "$FAKE_INIT_ARGS" >/dev/null

# 1b. Re-run after a failed init reuses the bound quality decision (no attempt 2).
rm -f "$RUN/gates/publication-state.json" "$FAKE_INIT_ARGS"; : >"$FAKE_MODEL_CALLS"
ARTICLE_PUBLICATION_POLICY=continuous bash "$FINISH" --run-dir "$RUN" >"$TMP/out1b" 2>&1 \
  || { cat "$TMP/out1b"; exit 1; }
{ [ ! -s "$FAKE_MODEL_CALLS" ] && [ -e "$FAKE_INIT_ARGS" ]; } || fail "$LINENO"
[ ! -e "$RUN/gates/quality-self-heal-attempt-2.json" ]

# 2. Existing publication state: the agent already crossed init; do nothing.
: >"$FAKE_MODEL_CALLS"; rm -f "$FAKE_INIT_ARGS"
ARTICLE_PUBLICATION_POLICY=continuous bash "$FINISH" --run-dir "$RUN" >"$TMP/out2" 2>&1
{ [ ! -s "$FAKE_MODEL_CALLS" ] && [ ! -e "$FAKE_INIT_ARGS" ]; } || fail "$LINENO"

# 3. Strict policy never forces publication.
RUN="$(make_run 20261017-040000)"
ARTICLE_PUBLICATION_POLICY=strict bash "$FINISH" --run-dir "$RUN" >"$TMP/out3" 2>&1
{ [ ! -s "$FAKE_MODEL_CALLS" ] && [ ! -e "$FAKE_INIT_ARGS" ]; } || fail "$LINENO"
[ ! -e "$RUN/gates/quality-self-heal.json" ]

# 4. A ledger row for the run means the agent already decided (e.g. carry-over); do nothing.
RUN="$(make_run 20261017-050000)"
printf '{"run_id":"20261017-050000","published":false,"state":"carry-over:conscience-block:x"}\n' >"$ARTICLE_LEDGER"
ARTICLE_PUBLICATION_POLICY=continuous bash "$FINISH" --run-dir "$RUN" >"$TMP/out4" 2>&1
{ [ ! -s "$FAKE_MODEL_CALLS" ] && [ ! -e "$FAKE_INIT_ARGS" ]; } || fail "$LINENO"

# 5. Conscience BLOCK stays blocking: no init, non-zero exit.
RUN="$(make_run 20261017-060000)"
set +e
FAKE_CONSCIENCE=BLOCK ARTICLE_PUBLICATION_POLICY=continuous bash "$FINISH" --run-dir "$RUN" >"$TMP/out5" 2>&1
rc=$?
set -e
[ "$rc" -ne 0 ]
{ [ ! -e "$FAKE_INIT_ARGS" ] && [ ! -e "$RUN/gates/publication-state.json" ]; } || fail "$LINENO"

# 5b. The BLOCK is persisted hash-bound and is final for the same bytes: no re-judge to ALLOW.
jq -e --arg h "$(sha "$RUN/article-ja.md")" '.verdict == "BLOCK" and .article_sha256 == $h' \
  "$RUN/gates/conscience-ja.json" >/dev/null
: >"$FAKE_MODEL_CALLS"
set +e
ARTICLE_PUBLICATION_POLICY=continuous bash "$FINISH" --run-dir "$RUN" >"$TMP/out5b" 2>&1
rc=$?
set -e
{ [ "$rc" -ne 0 ] && ! grep -q conscience "$FAKE_MODEL_CALLS"; } || fail "$LINENO"
{ [ ! -e "$FAKE_INIT_ARGS" ] && [ ! -e "$RUN/gates/publication-state.json" ]; } || fail "$LINENO"
# The gate itself also replays the stored BLOCK instead of asking the judge again.
set +e
ARTICLE_RUN_DIR="$RUN" bash "$ROOT/scripts/conscience-gate.sh" "$RUN/article-ja.md" --lang ja >"$TMP/out5c" 2>&1
rc=$?
set -e
{ [ "$rc" -eq 1 ] && ! grep -q conscience "$FAKE_MODEL_CALLS" && grep -q '"BLOCK"' "$TMP/out5c"; } || fail "$LINENO"

# 7. A current-hash identity FAIL is final: never re-judged, never initialized.
RUN="$(make_run 20261017-070000)"
printf '{"verdict":"FAIL","violations":["C: Dais"],"article_sha256":"%s"}\n' \
  "$(sha "$RUN/article-en.md")" >"$RUN/gates/identity-en.json"
set +e
ARTICLE_PUBLICATION_POLICY=continuous bash "$FINISH" --run-dir "$RUN" >"$TMP/out7" 2>&1
rc=$?
set -e
{ [ "$rc" -ne 0 ] && [ ! -s "$FAKE_MODEL_CALLS" ] && [ ! -e "$FAKE_INIT_ARGS" ]; } || fail "$LINENO"

# 8. Gates the agent left running for this run are stopped before the finisher judges;
#    the kept (broker) pid survives.
RUN="$(make_run 20261017-080000)"
python3 -c 'import time; time.sleep(300)' "$RUN/article-en.md" &
LEFTOVER=$!
python3 -c 'import time; time.sleep(300)' "$RUN" &
KEPT=$!
sleep 0.3
ARTICLE_PUBLICATION_POLICY=continuous bash "$FINISH" --run-dir "$RUN" --keep-pid "$KEPT" >"$TMP/out8" 2>&1 \
  || { cat "$TMP/out8"; exit 1; }
alive_leftover=0; kill -0 "$LEFTOVER" 2>/dev/null && alive_leftover=1
alive_kept=0; kill -0 "$KEPT" 2>/dev/null && alive_kept=1
kill "$LEFTOVER" "$KEPT" 2>/dev/null || true
wait "$LEFTOVER" "$KEPT" 2>/dev/null || true
{ [ "$alive_leftover" -eq 0 ] && [ "$alive_kept" -eq 1 ] && [ -e "$FAKE_INIT_ARGS" ]; } || fail "$LINENO"

# 8b. A broker handler forked after the scan started is still kept (keep set is live).
#     The leftover ignores TERM so the stop loop keeps iterating until KILL.
RUN="$(make_run 20261017-090000)"
python3 -c 'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(300)' \
  "$RUN/article-en.md" &
LEFTOVER=$!
bash -c 'sleep 1; python3 -c "import os,sys,time; open(sys.argv[2],\"w\").write(str(os.getpid())); time.sleep(300)" "$1" "$2" & wait' \
  broker "$RUN" "$TMP/handler.pid" &
KEPT=$!
sleep 0.3
ARTICLE_PUBLICATION_POLICY=continuous bash "$FINISH" --run-dir "$RUN" --keep-pid "$KEPT" >"$TMP/out8b" 2>&1 \
  || { cat "$TMP/out8b"; exit 1; }
HANDLER="$(cat "$TMP/handler.pid" 2>/dev/null || true)"
alive_handler=0; [ -n "$HANDLER" ] && kill -0 "$HANDLER" 2>/dev/null && alive_handler=1
alive_leftover=0; kill -0 "$LEFTOVER" 2>/dev/null && alive_leftover=1
kill -KILL "$LEFTOVER" "$KEPT" ${HANDLER:+"$HANDLER"} 2>/dev/null || true
wait "$LEFTOVER" "$KEPT" 2>/dev/null || true
{ [ "$alive_handler" -eq 1 ] && [ "$alive_leftover" -eq 0 ]; } || fail "$LINENO"

# 6. The daily wrapper calls the finisher after the model pass, before the broker drains.
awk '/^run_model_pass$/{m=1} m&&/prepublication-finish\.sh/{f=1} m&&/^drain_generation_workers$/{print (f?"ok":"missing"); exit}' \
  "$ROOT/article-daily.sh" | grep -qx ok
grep -Fq -- '--keep-pid "$JUDGE_BROKER_PID"' "$ROOT/article-daily.sh"

echo "prepublication-finish: PASS"
