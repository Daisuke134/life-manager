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
while [ $# -gt 0 ]; do case "$1" in
  --run-dir) RUN_DIR="$2"; shift 2;;
  *) echo "FATAL: usage: prepublication-finish.sh --run-dir <run>" >&2; exit 2;;
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

current_pass() {  # <receipt> <draft>
  jq -e --arg h "$(shasum -a 256 "$2" | awk '{print $1}')" \
    '.verdict == "PASS" and .article_sha256 == $h' "$1" >/dev/null 2>&1
}

for lang in ja en; do
  md="$RUN_DIR/article-$lang.md"
  current_pass "$GATES/identity-$lang.json" "$md" && continue
  bash "$SCRIPT_DIR/identity-gate.sh" "$md" --lang "$lang" || block "identity-$lang"
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
