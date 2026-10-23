#!/usr/bin/env bash
# Usage: scripts/ledger-check.sh <key>   exit 0 = free to claim, exit 1 = already in ledger (do NOT apply)
set -euo pipefail
[ $# -ge 1 ] || { echo "usage: $0 <key>" >&2; exit 2; }
cd "$(dirname "$0")/.."
git pull -q --rebase 2>/dev/null || true
key=$(printf '%s' "$1" | tr 'A-Z' 'a-z' | sed -E 's#^https?://##; s#^www\.##; s#/+$##')
if grep -iF -- "$key" ledger/APPLICATIONS.md; then echo "DUPLICATE: $key already in ledger — do not apply" >&2; exit 1; fi
echo "FREE: $key — add a 'claimed' row, commit+push, then apply"
