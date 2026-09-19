#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d /tmp/article-resume-owner-fence-hint.XXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
mkdir -p "$TMP/article/scripts" "$TMP/state/runs" "$TMP/state/owner-fence"
cp "$ROOT/scripts/article-resume-pending.sh" "$TMP/article/scripts/"
cp "$ROOT/scripts/writer_owner_fence.py" "$TMP/article/scripts/"
cat >"$TMP/article/scripts/writer-runtime-env.sh" <<ENV
ARTICLE_ROOT="$TMP/article"
STATE_DIR="$TMP/state"
WRITER_LOG_DIR="$TMP/state/logs"
ARTICLE_OWNER_FENCE_DIR="$TMP/state/owner-fence"
ENV

START="$(ps -p $$ -o lstart= | sed 's/^ *//;s/ *$//')"
python3 - "$TMP/state/owner-fence/owner.json" "$START" <<'PY'
import json
import os
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps({
    "version": 1,
    "token": "held-token",
    "pid": os.getppid(),
    "start": sys.argv[2],
    "owner": "article-resume",
    "root": "/tmp/article",
    "state": "/tmp/state",
    "run_id": "held-run",
}) + "\n", encoding="utf-8")
PY

set +e
ARTICLE_ROOT="$TMP/article" \
STATE_DIR="$TMP/state" \
WRITER_LOG_DIR="$TMP/state/logs" \
ARTICLE_OWNER_FENCE_DIR="$TMP/state/owner-fence" \
ARTICLE_OWNER_FENCE_ACTIVE=0 \
LIFE_MANAGER_RESULT_HINT_PATH="$TMP/hint.json" \
bash "$TMP/article/scripts/article-resume-pending.sh"
rc=$?
set -e

test "$rc" -eq 75
test -f "$TMP/hint.json"
test "$(stat -f '%Lp' "$TMP/hint.json")" = 600
test "$(cat "$TMP/hint.json")" = '{"status":"pre_effect_failure","effect":0}'
echo "PASS: owner-fence refusal records a pre-effect failure hint"
