#!/usr/bin/env bash
# prepublication-finish.sh — deterministic STEP 4.6 -> 4.75 -> 4.8 -> 4.9 for a staged run.
# Usage: prepublication-finish.sh --run-dir <run>   (needs ARTICLE_LEDGER)
#
# Continuous policy only. When the foreground agent stops after staging drafts but before
# publication init (run 20261017-033711 ended its turn while identity-en/conscience were
# still running), finish the same immutable package without a model decision:
# identity (missing/stale only) -> quality_self_heal assess -> conscience -> init.
# Identity FAIL, conscience BLOCK, or any gate error stays blocking (non-zero, no init).
# No-op when policy is strict, publication-state exists, the ledger already has a row for
# this run (the agent recorded its own decision), or the package is incomplete.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR=""
KEEP_PID=""
while [ $# -gt 0 ]; do case "$1" in
  --run-dir) RUN_DIR="$2"; shift 2;;
  --keep-pid) KEEP_PID="$2"; shift 2;;
  *) echo "FATAL: usage: prepublication-finish.sh --run-dir <run> [--keep-pid <broker>]" >&2; exit 2;;
esac; done
[ -d "$RUN_DIR" ] || { echo "FATAL: run dir missing" >&2; exit 2; }
: "${ARTICLE_LEDGER:?ARTICLE_LEDGER is required}"
RUN_DIR="$(cd "$RUN_DIR" && pwd -P)"
RUN_ID="$(basename "$RUN_DIR")"
GATES="$RUN_DIR/gates"
STATE="$GATES/publication-state.json"
PUBLICATION_RESUME="${ARTICLE_PUBLICATION_RESUME:-$SCRIPT_DIR/publication_resume.py}"
export ARTICLE_RUN_DIR="$RUN_DIR"

skip() { echo "prepublication-finish: skip run=$RUN_ID reason=$1"; exit 0; }
block() { echo "prepublication-finish: blocked run=$RUN_ID reason=$1" >&2; exit 1; }

[ "${ARTICLE_PUBLICATION_POLICY:-strict}" = "continuous" ] || skip "policy-not-continuous"
[ -e "$STATE" ] && skip "publication-state-present"
if [ -f "$ARTICLE_LEDGER" ] && jq -e --arg run "$RUN_ID" 'select(.run_id == $run)' \
  "$ARTICLE_LEDGER" 2>/dev/null | grep -q .; then
  skip "ledger-row-present"
fi
for f in article-ja.md article-en.md x-post-ja.txt headline-image.png body-diagram.png; do
  [ -f "$RUN_DIR/$f" ] || skip "missing-$f"
done
TOPIC_ID="$(jq -r '.topic_id // empty' "$GATES/topic-route.json" 2>/dev/null)"
[ -n "$TOPIC_ID" ] || skip "missing-topic-id"

descendants() {  # <pid>: the pid and every descendant
  local child
  echo "$1"
  for child in $(pgrep -P "$1" 2>/dev/null); do descendants "$child"; done
}

# The agent can end its turn while gates it launched for this run still run (codex left
# identity/conscience in progress on 20261017-033711). Stop every process naming this run,
# except this finisher and the kept judge broker tree, so no stale gate races our verdicts.
stop_run_leftovers() {
  local keep pid tries=0 found candidates
  while :; do
    # Recompute every pass, after the scan: the broker forks handlers (argv names this
    # run) at any time, and a handler seen by pgrep must already be in the keep set.
    candidates="$(pgrep -f -- "$RUN_DIR" 2>/dev/null)"
    keep=" $$ $PPID $( [ -n "$KEEP_PID" ] && descendants "$KEEP_PID" | tr '\n' ' ') "
    found=""
    for pid in $candidates; do
      case "$keep" in *" $pid "*) ;; *) found="$found $pid";; esac
    done
    [ -n "$found" ] || return 0
    if [ "$tries" -lt 50 ]; then kill -TERM $found 2>/dev/null; else kill -KILL $found 2>/dev/null; fi
    [ "$tries" -lt 100 ] || block "run-leftovers-survive:$found"
    tries=$((tries + 1))
    sleep 0.1
  done
}
stop_run_leftovers

verdict_for_current() {  # <receipt> <draft>: prints the verdict bound to the current bytes
  jq -r --arg h "$(shasum -a 256 "$2" | awk '{print $1}')" \
    'select(.article_sha256 == $h) | .verdict // empty' "$1" 2>/dev/null
}

# Negative verdicts are final for the same bytes: never re-judge them.
for lang in ja en; do
  md="$RUN_DIR/article-$lang.md"
  case "$(verdict_for_current "$GATES/identity-$lang.json" "$md")" in
    PASS) continue ;;
    "") bash "$SCRIPT_DIR/identity-gate.sh" "$md" --lang "$lang" || block "identity-$lang" ;;
    *) block "identity-$lang-final" ;;
  esac
done
for lang in ja en; do
  [ "$(verdict_for_current "$GATES/conscience-$lang.json" "$RUN_DIR/article-$lang.md")" = BLOCK ] \
    && block "conscience-$lang-final"
done

# Reuse a decision already bound to these exact drafts (a re-run must not open attempt 2).
ASSESS="$(jq -c --arg ja "$(shasum -a 256 "$RUN_DIR/article-ja.md" | awk '{print $1}')" \
  --arg en "$(shasum -a 256 "$RUN_DIR/article-en.md" | awk '{print $1}')" \
  'select(.quality.ja.article_sha256 == $ja and .quality.en.article_sha256 == $en)' \
  "$GATES/quality-self-heal.json" 2>/dev/null)"
[ -n "$ASSESS" ] || ASSESS="$(python3 "$SCRIPT_DIR/quality_self_heal.py" assess --run-dir "$RUN_DIR" \
  --draft-ja "$RUN_DIR/article-ja.md" --draft-en "$RUN_DIR/article-en.md")"
case "$(printf '%s' "$ASSESS" | jq -r '.action // empty' 2>/dev/null)" in
  force_publish_advisory|ready_to_freeze) ;;
  *) block "quality-assess:${ASSESS:-error}" ;;
esac

for lang in ja en; do
  md="$RUN_DIR/article-$lang.md"
  python3 "$SCRIPT_DIR/quality-phase-terminal.py" check --run-dir "$RUN_DIR" \
    --lang "$lang" --markdown-file "$md" >/dev/null && continue
  # conscience-gate.sh writes the hash-bound quality-terminal marker only on ALLOW.
  bash "$SCRIPT_DIR/conscience-gate.sh" "$md" --lang "$lang" || block "conscience-$lang"
done

python3 "$PUBLICATION_RESUME" --state "$STATE" --ledger "$ARTICLE_LEDGER" init \
  --run-id "$RUN_ID" --run-dir "$RUN_DIR" --topic-id "$TOPIC_ID" \
  --draft-ja "$RUN_DIR/article-ja.md" --draft-en "$RUN_DIR/article-en.md" \
  --x-post-ja "$RUN_DIR/x-post-ja.txt" --headline-image "$RUN_DIR/headline-image.png" \
  --body-asset "$RUN_DIR/body-diagram.png" --safety ALLOW --max-resume-attempts 2 \
  --require-quality || block "publication-init"
echo "prepublication-finish: initialized run=$RUN_ID"
