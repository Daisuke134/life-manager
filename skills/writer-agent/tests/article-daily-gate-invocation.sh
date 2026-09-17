#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
PROMPT_SOURCE="$ROOT/article-daily.sh"

grep -Fq 'Do not call a gate with --help' "$PROMPT_SOURCE"
grep -Fq 'usage output is not a gate verdict' "$PROMPT_SOURCE"
echo "article daily gate invocation guard: PASS"
