#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d /tmp/article-resume-pre-effect-hint.XXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
mkdir -p "$TMP/article/scripts" "$TMP/state/runs"
cp "$ROOT/scripts/article-resume-pending.sh" "$TMP/article/scripts/"
cat >"$TMP/article/scripts/writer-runtime-env.sh" <<ENV
ARTICLE_ROOT="$TMP/article"
STATE_DIR="$TMP/state"
WRITER_LOG_DIR="$TMP/state/logs"
ARTICLE_OWNER_FENCE_ACTIVE=1
ENV

set +e
ARTICLE_ROOT="$TMP/article" \
STATE_DIR="$TMP/state" \
WRITER_LOG_DIR="$TMP/state/logs" \
LIFE_MANAGER_RESULT_HINT_PATH="$TMP/hint.json" \
GIG_DISK_HEADROOM_KIB=not-a-number \
bash "$TMP/article/scripts/article-resume-pending.sh"
rc=$?
set -e

test "$rc" -eq 1
test -f "$TMP/hint.json"
test "$(stat -f '%Lp' "$TMP/hint.json")" = 600
test "$(cat "$TMP/hint.json")" = '{"status":"pre_effect_failure","effect":0}'
echo "PASS: article-resume records a hash-free pre-effect failure hint before disk-floor refusal"
