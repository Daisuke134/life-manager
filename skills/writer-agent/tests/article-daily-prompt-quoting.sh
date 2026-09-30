#!/usr/bin/env bash
# Regression for 2026-09-29 production incident: a literal apostrophe inside the
# single-quoted PROMPT='...' literal in article-daily.sh (STEP 3, added by #6110)
# prematurely closed the bash string. Everything after it ("angle in the buyer
# problem...") was re-parsed as a separate shell command instead of prompt text,
# so STEP 4 through STEP 10 (including the STEP 4.9 export of ARTICLE_RUN_DIR /
# ARTICLE_PUBLICATION_STATE / ARTICLE_LEDGER) never made it into the prompt the
# model received. In ARMED mode the model got only the STEP 11-20 publish
# addendum with zero run context and correctly refused to proceed.
#
# This test extracts the real PROMPT='...' assignment (lines up to its closing
# quote after STEP 10) from article-daily.sh and executes it in a throwaway
# bash subprocess, then asserts the resulting PROMPT variable is not corrupted:
# it must be non-empty, must not trip an "unexpected token" / "command not
# found" parse error, and must contain the STEP 10 closing sentence.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
SOURCE_SH="$ROOT/article-daily.sh"

START_LINE="$(grep -n "^PROMPT='Run ONE daily Writer Agent article pass" "$SOURCE_SH" | head -1 | cut -d: -f1)"
END_LINE="$(grep -n "^STEP 10 (FINISH -- HONEST DELIVERY)" "$SOURCE_SH" | head -1 | cut -d: -f1)"
if [ -z "$START_LINE" ] || [ -z "$END_LINE" ]; then
  echo "article daily prompt quoting: FAIL (could not locate PROMPT literal bounds)" >&2
  exit 1
fi

TMP_SNIPPET="$(mktemp)"
trap 'rm -f "$TMP_SNIPPET"' EXIT
sed -n "${START_LINE},${END_LINE}p" "$SOURCE_SH" > "$TMP_SNIPPET"
{
  echo 'echo "PROMPT_LEN=${#PROMPT}"'
  echo 'case "$PROMPT" in'
  echo '  *"never equate foreground exit with shipped."*) echo "PROMPT_HAS_STEP10=yes" ;;'
  echo '  *) echo "PROMPT_HAS_STEP10=no" ;;'
  echo 'esac'
} >> "$TMP_SNIPPET"

OUTPUT="$(bash "$TMP_SNIPPET" 2>&1)"

echo "$OUTPUT" | grep -Fq "command not found" && {
  echo "article daily prompt quoting: FAIL (a fragment of the prompt text executed as a shell command -- likely an unescaped apostrophe inside PROMPT='...')" >&2
  echo "$OUTPUT" >&2
  exit 1
}

echo "$OUTPUT" | grep -q "^PROMPT_HAS_STEP10=yes" || {
  echo "article daily prompt quoting: FAIL (PROMPT did not retain STEP 10 text -- the single-quoted literal was truncated early)" >&2
  echo "$OUTPUT" >&2
  exit 1
}

PROMPT_LEN="$(echo "$OUTPUT" | sed -n 's/^PROMPT_LEN=//p')"
if [ -z "$PROMPT_LEN" ] || [ "$PROMPT_LEN" -lt 20000 ]; then
  echo "article daily prompt quoting: FAIL (PROMPT suspiciously short: len=$PROMPT_LEN)" >&2
  exit 1
fi

echo "article daily prompt quoting: PASS (len=$PROMPT_LEN)"
