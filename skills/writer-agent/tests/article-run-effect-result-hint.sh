#!/usr/bin/env bash
# The loop runtime trusts entrypoint-result.json as a verified Writer effect, so it may be
# written only when the armed run's active destinations all have live reality-PASS rows.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
GATE="$ROOT/skills/writer-agent/scripts/article-run-complete.py"
TMP="$(mktemp -d /tmp/article-run-effect-hint.XXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
LEDGER="$TMP/articles.jsonl"
RUN=20261017-001933
STATE="$TMP/runs/$RUN/gates/publication-state.json"
SCRATCH="$TMP/scratch"
HINT="$SCRATCH/entrypoint-result.json"
OCC="article-daily:18df31ffadbf0bb8-90384"
mkdir -p "$(dirname "$STATE")" "$SCRATCH"
chmod 700 "$SCRATCH"
printf '%s\n' "{\"version\":1,\"publication_contract\":\"active-four\",\"run_id\":\"$RUN\"}" >"$STATE"
: >"$LEDGER"

emit() {
  printf '{"run_id":"%s","topic_id":"t1","platform":"%s","lang":"%s","live_url":"https://%s.example.test/%s","published":true,"reality_gate":"PASS"}\n' \
    "$RUN" "$1" "$2" "$1" "$2" >>"$LEDGER"
}
hint() {
  python3 "$GATE" --ledger "$LEDGER" --run-id "$RUN" --armed "$1" --publication-state "$STATE" \
    --effect-result-hint "$HINT" --occurrence-id "$2"
}

# Partial publication: no hint, so the runtime keeps effect unknown.
emit note ja
emit substack ja
! hint 1 "$OCC"
test ! -e "$HINT"

# Unarmed staging rows are never a publication effect.
emit substack en
! hint 0 "$OCC"
test ! -e "$HINT"

# A foreign occurrence is refused.
! hint 1 "other-loop:run"
test ! -e "$HINT"

# All active destinations live with reality PASS: exact private hint.
hint 1 "$OCC"
test "$(stat -f '%Lp' "$HINT" 2>/dev/null || stat -c '%a' "$HINT")" = 600
python3 - "$HINT" "$OCC" "$RUN" <<'PY'
import json, sys
value = json.load(open(sys.argv[1]))
assert value == {
    "schema_version": 1, "kind": "life_manager_effect_result", "status": "verified_effect",
    "effect": 1, "owner_id": "article-daily", "occurrence_id": sys.argv[2],
    "provider": "writer", "provider_receipt_id": sys.argv[3], "effect_status": "verified",
    "live_urls": [
        "https://note.example.test/ja",
        "https://substack.example.test/en",
        "https://substack.example.test/ja",
    ],
}, value
PY

# An existing hint is never overwritten.
! hint 1 "$OCC"
echo 'PASS: Writer verified effect hint requires armed complete live reality-PASS set'
