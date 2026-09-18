#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
WRAPPER="$ROOT/skills/writer-agent/article-daily.sh"

grep -F 'article_daily_start_control.py' "$WRAPPER" >/dev/null
grep -F 'skip-complete' "$WRAPPER" >/dev/null
grep -F 'skip-pending-worker' "$WRAPPER" >/dev/null
grep -F 'completed prior run released a new run' "$WRAPPER" >/dev/null
grep -F 'allocate_new_run_id' "$WRAPPER" >/dev/null
grep -F 'START_REASON' "$WRAPPER" >/dev/null
! grep -F 'no second article' "$WRAPPER" >/dev/null
! grep -F 'RESUME_EXISTING=' "$WRAPPER" >/dev/null
grep -F 'disk floor blocked after preflight' "$WRAPPER" >/dev/null
grep -F 'POST_PREFLIGHT_FREE_BYTES' "$WRAPPER" >/dev/null
grep -F 'CANONICAL_DISK_HEADROOM_KIB=524288' "$WRAPPER" >/dev/null
grep -F 'GIG_DISK_HEADROOM_KIB="${GIG_DISK_HEADROOM_KIB:-$CANONICAL_DISK_HEADROOM_KIB}"' "$WRAPPER" >/dev/null
grep -F 'DISK_LOW_THRESHOLD_BYTES="${ARTICLE_DISK_MIN_FREE_BYTES:-$((GIG_DISK_HEADROOM_KIB * 1024))}"' "$WRAPPER" >/dev/null
grep -F 'writer_capacity_preflight' "$WRAPPER" >/dev/null
grep -F 'Life Manager ${required_kib}KiB floor' "$WRAPPER" >/dev/null
grep -F 'disk-writers.stop' "$WRAPPER" >/dev/null
grep -F 'disk-pressure.block' "$WRAPPER" >/dev/null
grep -F 'GIG_IGNORE_DISK_PRESSURE_BLOCK' "$WRAPPER" >/dev/null
grep -F 'DISK_MIN_FREE_BYTES="${ARTICLE_RESUME_MIN_FREE_BYTES:-${ARTICLE_DISK_MIN_FREE_BYTES:-$((GIG_DISK_HEADROOM_KIB * 1024))}}"' "$ROOT/skills/writer-agent/scripts/article-resume-pending.sh" >/dev/null
grep -F 'CANONICAL_DISK_HEADROOM_KIB=524288' "$ROOT/skills/writer-agent/scripts/article-resume-pending.sh" >/dev/null
grep -F 'ARTICLE_PROVIDER="${ARTICLE_PROVIDER:-codex}"' "$ROOT/skills/writer-agent/scripts/article-resume-pending.sh" >/dev/null
grep -F 'PRE_START_REASON" = "no-same-jst-day-run"' "$ROOT/skills/writer-agent/scripts/article-resume-pending.sh" >/dev/null

echo 'PASS: wrapper creates only a new daily run and leaves saved work to durable workers'
