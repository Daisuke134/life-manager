#!/usr/bin/env bash
# Usage: scripts/ledger-check.sh <key>
#   exit 0 = FREE (ledger fresh, key absent), exit 1 = BUSY (key already claimed by any owner/account, do NOT apply),
#   exit 3 = UNKNOWN (pull or read failed: never treat as free), exit 2 = usage.
# key = platform:id (e.g. lancers:5620321), matched exactly in the key column whatever the owner or account.
# A row whose status is unknown/sending also blocks until someone reconciles it.
set -euo pipefail
[ $# -ge 1 ] || { echo "usage: $0 <key>" >&2; exit 2; }
cd "$(dirname "$0")/.."
LEDGER=ledger/APPLICATIONS.md
if ! git pull -q --rebase 2>/dev/null; then
  echo "UNKNOWN: git pull failed — ledger freshness unknown, do not apply" >&2
  exit 3
fi
[ -r "$LEDGER" ] || { echo "UNKNOWN: $LEDGER unreadable — do not apply" >&2; exit 3; }
key=$(printf '%s' "$1" | tr 'A-Z' 'a-z' | sed -E 's#^https?://##; s#^www\.##; s#/+$##')
hit=$(awk -F'|' -v k="$key" '
  { c=$5; gsub(/^[ \t]+|[ \t]+$/, "", c); if (tolower(c) == k) print $0 }' "$LEDGER") || {
  echo "UNKNOWN: ledger read failed — do not apply" >&2; exit 3; }
if [ -n "$hit" ]; then
  printf '%s\n' "$hit"
  echo "BUSY: $key already in ledger (any owner/account) — do not apply" >&2
  exit 1
fi
echo "FREE: $key — add a 'claimed' row, commit+push to main, confirm it reached main, then apply"
