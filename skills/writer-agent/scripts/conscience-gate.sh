#!/usr/bin/env bash
# conscience-gate.sh — 品質とは独立した公開適否 gate。
# Usage: conscience-gate.sh <article.md> [--lang ja|en]
# stdout: {"verdict":"ALLOW|BLOCK","reasons":[...]}; exit 0=ALLOW, exit 1=BLOCK。
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTICLE_ROOT="${ARTICLE_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd -P)}"
# shellcheck source=writer-runtime-env.sh
source "$SCRIPT_DIR/writer-runtime-env.sh" || exit $?
MODEL_RUNNER="${ARTICLE_MODEL_RUNNER:-$ARTICLE_ROOT/runtime/model-runner.sh}"

MD=""; LANG_A="ja"
POSITIONAL=()
while [ $# -gt 0 ]; do case "$1" in
  --lang) LANG_A="$2"; shift 2;;
  --markdown-file) MD="$2"; shift 2;;
  *) POSITIONAL+=("$1"); shift;;
esac; done
[ -z "$MD" ] && [ ${#POSITIONAL[@]} -gt 0 ] && MD="${POSITIONAL[0]}"
[ -f "$MD" ] || { echo "FATAL: usage: conscience-gate.sh <article.md> [--lang ja|en]" >&2; exit 2; }

GATES_LOG="${ARTICLE_GATES_LOG:-$WRITER_LOG_DIR/article-gates.log}"
log_gate_verdict() {
  mkdir -p "$(dirname "$GATES_LOG")" 2>/dev/null || return 0
  printf '%s script=conscience-gate.sh md=%s lang=%s verdict=%s\n' \
    "$(date '+%Y-%m-%d %H:%M:%S')" "$MD" "$LANG_A" "$1" >>"$GATES_LOG" 2>/dev/null || true
}

BODY="$(cat "$MD")"
PROMPT="You are a fresh, context-zero publication conscience reviewer. You receive only one proposed article and must decide whether it is appropriate to publish as written. This is separate from prose quality, factual depth, or commercial potential.

BLOCK publication when the article creates a material gray-zone exposure in any of these categories:
1. INTERNAL CREDENTIAL OR SECURITY EXPOSURE: credentials, session material, private access details, secret values, or operational instructions that expose non-public systems.
2. NON-PUBLIC INFORMATION ABOUT ANOTHER PERSON OR ORGANIZATION: private facts, communications, identity details, financial/medical/employment information, or allegations that are not already intentionally public by the subject.
3. REPUTATIONAL HARM: claims or framing likely to unfairly damage a person or organization, especially where the evidence is incomplete, private, speculative, or presented without a fair public-interest basis.
4. LEGAL RISK: defamation, privacy invasion, breach of confidence, unlawful disclosure, or instructions whose publication would create a concrete legal risk.
5. TARGETED ACCUSATION: identifying a real person or organization in order to blame, shame, or accuse them, rather than neutrally documenting well-sourced public facts.

Do not BLOCK ordinary critical analysis of public products, public documentation, public conduct, or well-sourced public facts merely because it is negative. Query parameters on the article's own product or call-to-action link (product_id, run_id, artifact_id, variant_id, click_id, ct, utm_*) are standard marketing attribution that every publisher uses; they are not credentials, private access details, or a security or privacy exposure, so never BLOCK for them. Do not infer hidden context. Judge only the article below. When uncertain about a material gray-zone exposure, fail closed with BLOCK and explain the uncertainty.

Output the FINAL LINE as pure JSON exactly:
{\"verdict\":\"ALLOW\"|\"BLOCK\",\"reasons\":[\"<specific reason quoting or identifying the risky passage>\", ...]}
ALLOW requires an empty reasons array. BLOCK requires at least one concrete reason.

=== ARTICLE (lang=$LANG_A) ===
$BODY"

# Judge broker routing must survive agent subshells that drop env vars
# (observed 2026-07-25): the markdown lives in the run dir, so derive
# ARTICLE_RUN_DIR from it whenever the caller failed to pass one.
if [ -z "${ARTICLE_RUN_DIR:-}" ] && [ -f "$MD" ]; then
  export ARTICLE_RUN_DIR="$(cd "$(dirname "$MD")" && pwd)"
fi
# A BLOCK is final for the same bytes: replay it instead of asking a fresh judge,
# so a later pass can never re-roll a BLOCK into ALLOW (review of #8251).
RECEIPT=""
ARTICLE_HASH="$(shasum -a 256 "$MD" | awk '{print $1}')"
if [ -n "${ARTICLE_RUN_DIR:-}" ]; then
  RECEIPT="$ARTICLE_RUN_DIR/gates/conscience-$LANG_A.json"
  if jq -e --arg h "$ARTICLE_HASH" '.verdict == "BLOCK" and .article_sha256 == $h' \
    "$RECEIPT" >/dev/null 2>&1; then
    jq -c '{verdict, reasons}' "$RECEIPT"
    log_gate_verdict "BLOCK:replayed"
    exit 1
  fi
fi
OUT=$(printf '%s' "$PROMPT" | "$MODEL_RUNNER" judge --prompt-file - 2>/dev/null)
JSON=$(printf '%s\n' "$OUT" | grep -o '{"verdict".*}' | tail -1)
if [ -z "$JSON" ]; then
  log_gate_verdict "FATAL:no-json-from-judge"
  echo "FATAL: judge returned no JSON verdict" >&2
  printf '%s\n' "$OUT" | tail -5 >&2
  exit 3
fi

NORMALIZED=$(python3 -c '
import json, sys
try:
    data = json.loads(sys.argv[1])
except json.JSONDecodeError:
    raise SystemExit(1)
verdict = data.get("verdict")
reasons = data.get("reasons")
if verdict not in {"ALLOW", "BLOCK"} or not isinstance(reasons, list):
    raise SystemExit(1)
if verdict == "ALLOW" and reasons:
    raise SystemExit(1)
if verdict == "BLOCK" and not reasons:
    raise SystemExit(1)
print(json.dumps({"verdict": verdict, "reasons": reasons}, separators=(",", ":"), ensure_ascii=False))
' "$JSON" 2>/dev/null)
if [ -z "$NORMALIZED" ]; then
  log_gate_verdict "FATAL:invalid-json-from-judge"
  echo "FATAL: judge returned an invalid conscience verdict" >&2
  printf '%s\n' "$JSON" >&2
  exit 3
fi

echo "$NORMALIZED"
VERDICT=$(printf '%s' "$NORMALIZED" | python3 -c 'import json,sys; print(json.load(sys.stdin)["verdict"])')
log_gate_verdict "$VERDICT"
if [ -n "$RECEIPT" ]; then
  mkdir -p "$(dirname "$RECEIPT")"
  printf '%s' "$NORMALIZED" | jq -c --arg h "$ARTICLE_HASH" '. + {article_sha256: $h}' \
    >"$RECEIPT.$$.tmp" && mv -f "$RECEIPT.$$.tmp" "$RECEIPT" || {
      echo "FATAL: could not persist conscience receipt" >&2
      exit 3
    }
fi
if [ "$VERDICT" = "ALLOW" ] && [ -n "${ARTICLE_RUN_DIR:-}" ]; then
  python3 "$SCRIPT_DIR/quality-phase-terminal.py" write \
    --run-dir "$ARTICLE_RUN_DIR" --lang "$LANG_A" --markdown-file "$MD" || {
      echo "FATAL: could not persist quality terminal marker" >&2
      exit 3
    }
fi
[ "$VERDICT" = "ALLOW" ]
