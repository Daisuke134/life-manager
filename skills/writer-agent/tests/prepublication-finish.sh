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

# 9. 7cd0d0e486 keeps the proxy key out of the model sandbox: the agent writes the headline
#    prompt/alt but cannot call the image API (run 20261023-004552: missing-headline-image.png).
#    The finisher creates the headline once with the proxy key, then finishes as usual.
RUN="$(make_run 20261023-004552)"
rm -f "$RUN/headline-image.png"
printf 'a calm desk\n' >"$RUN/gates/headline-image-prompt.txt"
printf 'a desk\n' >"$RUN/gates/headline-image-alt.txt"
printf 'api-keys:\n  - "proxy-fixture-key"\n' >"$TMP/cliproxy.conf"
cat >"$TMP/bin/headline.py" <<'PY'
import os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_HEADLINE_CALLS"], "a", encoding="utf-8") as handle:
    handle.write(args[0] + " key=" + os.environ.get("CLIPROXY_API_KEY", "") + "\n")
if args[0] == "generate":
    open(args[args.index("--candidate") + 1], "wb").write(b"png")
    open(args[args.index("--intent") + 1], "w").write("{}")
    open(args[args.index("--receipt") + 1], "w").write("{}")
PY
cat >"$TMP/bin/media.py" <<'PY'
import os, shutil, sys
args = sys.argv[1:]
with open(os.environ["FAKE_HEADLINE_CALLS"], "a", encoding="utf-8") as handle:
    handle.write("commit " + args[args.index("--kind") + 1] + "\n")
shutil.copyfile(args[args.index("--candidate") + 1], args[args.index("--destination") + 1])
PY
export FAKE_HEADLINE_CALLS="$TMP/headline-calls"; : >"$FAKE_HEADLINE_CALLS"
ARTICLE_PUBLICATION_POLICY=continuous ARTICLE_CLIPROXY_CONFIG="$TMP/cliproxy.conf" \
  ARTICLE_HEADLINE_IMAGE_GENERATOR="$TMP/bin/headline.py" ARTICLE_MEDIA_CREATE_ONCE="$TMP/bin/media.py" \
  bash "$FINISH" --run-dir "$RUN" >"$TMP/out9" 2>&1 || { cat "$TMP/out9"; exit 1; }
[ "$(cat "$FAKE_HEADLINE_CALLS")" = "$(printf 'generate key=proxy-fixture-key\ncommit headline\nverify key=')" ] \
  || { cat "$FAKE_HEADLINE_CALLS"; fail "$LINENO"; }
[ -f "$RUN/headline-image.png" ] && [ -f "$FAKE_INIT_ARGS" ] || fail "$LINENO"

# 9b. An unknown-outcome intent is never resent: the finisher blocks with its status.
RUN="$(make_run 20261023-010000)"
rm -f "$RUN/headline-image.png"
printf 'p\n' >"$RUN/gates/headline-image-prompt.txt"; printf 'a\n' >"$RUN/gates/headline-image-alt.txt"
printf '{"status":"delivery_unknown"}' >"$RUN/gates/headline-image-api-intent.json"
: >"$FAKE_HEADLINE_CALLS"
if ARTICLE_PUBLICATION_POLICY=continuous ARTICLE_CLIPROXY_CONFIG="$TMP/cliproxy.conf" \
  ARTICLE_HEADLINE_IMAGE_GENERATOR="$TMP/bin/headline.py" ARTICLE_MEDIA_CREATE_ONCE="$TMP/bin/media.py" \
  bash "$FINISH" --run-dir "$RUN" >"$TMP/out9b" 2>&1; then cat "$TMP/out9b"; fail "$LINENO"; fi
[ ! -s "$FAKE_HEADLINE_CALLS" ] && grep -q "reason=headline-image-intent-delivery_unknown" "$TMP/out9b" \
  || fail "$LINENO"

# 9c. Generated and committed at the API but died before the local commit: replay commit+verify only.
RUN="$(make_run 20261023-020000)"
rm -f "$RUN/headline-image.png"
printf 'p\n' >"$RUN/gates/headline-image-prompt.txt"; printf 'a\n' >"$RUN/gates/headline-image-alt.txt"
printf '{"status":"committed"}' >"$RUN/gates/headline-image-api-intent.json"
mkdir -p "$RUN/gates/media-candidates"; printf 'png' >"$RUN/gates/media-candidates/headline-gpt-image-2.png"
: >"$FAKE_HEADLINE_CALLS"
ARTICLE_PUBLICATION_POLICY=continuous ARTICLE_CLIPROXY_CONFIG="$TMP/cliproxy.conf" \
  ARTICLE_HEADLINE_IMAGE_GENERATOR="$TMP/bin/headline.py" ARTICLE_MEDIA_CREATE_ONCE="$TMP/bin/media.py" \
  bash "$FINISH" --run-dir "$RUN" >"$TMP/out9c" 2>&1 || { cat "$TMP/out9c"; exit 1; }
[ "$(cat "$FAKE_HEADLINE_CALLS")" = "$(printf 'commit headline\nverify key=')" ] \
  && [ -f "$RUN/headline-image.png" ] || { cat "$FAKE_HEADLINE_CALLS"; fail "$LINENO"; }

# 10. The model sandbox cannot reach kroki/mermaid.ink, so the agent writes body-diagram.mmd
#     but never a PNG (runs 20261024-150602 and 20261025-040107: missing-body-diagram.png).
#     The finisher renders it once and commits it as the body asset, then finishes as usual.
RUN="$(make_run 20261025-040107)"
rm -f "$RUN/body-diagram.png"
printf 'flowchart TD\n  A-->B\n' >"$RUN/body-diagram.mmd"
cat >"$TMP/bin/render.py" <<'PY'
import os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_HEADLINE_CALLS"], "a", encoding="utf-8") as handle:
    handle.write("render " + os.path.basename(args[args.index("--in") + 1]) + "\n")
open(args[args.index("--out") + 1], "wb").write(b"png")
PY
: >"$FAKE_HEADLINE_CALLS"; rm -f "$FAKE_INIT_ARGS"
ARTICLE_PUBLICATION_POLICY=continuous ARTICLE_BODY_DIAGRAM_RENDERER="$TMP/bin/render.py" \
  ARTICLE_MEDIA_CREATE_ONCE="$TMP/bin/media.py" \
  bash "$FINISH" --run-dir "$RUN" >"$TMP/out10" 2>&1 || { cat "$TMP/out10"; exit 1; }
[ "$(cat "$FAKE_HEADLINE_CALLS")" = "$(printf 'render body-diagram.mmd\ncommit body')" ] \
  || { cat "$FAKE_HEADLINE_CALLS"; fail "$LINENO"; }
[ -f "$RUN/body-diagram.png" ] && [ -f "$FAKE_INIT_ARGS" ] || fail "$LINENO"

# 10b. A body commit receipt without the PNG is never re-rendered: a different second
#      candidate would be refused, so the run stays skipped for the reconciler.
RUN="$(make_run 20261025-050000)"
rm -f "$RUN/body-diagram.png"
printf 'flowchart TD\n  A-->B\n' >"$RUN/body-diagram.mmd"
printf '{}' >"$RUN/gates/body-diagram-create.json"
: >"$FAKE_HEADLINE_CALLS"
ARTICLE_PUBLICATION_POLICY=continuous ARTICLE_BODY_DIAGRAM_RENDERER="$TMP/bin/render.py" \
  ARTICLE_MEDIA_CREATE_ONCE="$TMP/bin/media.py" \
  bash "$FINISH" --run-dir "$RUN" >"$TMP/out10b" 2>&1 || { cat "$TMP/out10b"; exit 1; }
[ ! -s "$FAKE_HEADLINE_CALLS" ] && grep -q "reason=missing-body-diagram.png" "$TMP/out10b" || fail "$LINENO"

echo "prepublication-finish: PASS"
