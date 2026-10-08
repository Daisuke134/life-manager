#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DAILY="$ROOT/skills/writer-agent/article-daily.sh"
RESUME="$ROOT/skills/writer-agent/scripts/article-resume-pending.sh"
GUARD="$ROOT/skills/writer-agent/scripts/publication-guard.py"

if rg -n 'CANONICAL_DISK_HEADROOM|ARTICLE_DISK_MIN_FREE_BYTES|ARTICLE_RESUME_MIN_FREE_BYTES|DISK_MIN_FREE_BYTES|disk_headroom_low|disk floor blocked|writer_capacity_floor' \
  "$DAILY" "$RESUME" "$GUARD"; then
  echo 'Writer still has a numeric disk admission gate' >&2
  exit 1
fi
grep -F 'disk-writers.stop' "$DAILY" >/dev/null
! grep -F 'disk-pressure.block' "$DAILY" >/dev/null

echo 'PASS: Writer capacity numbers no longer defer generation or publication'
