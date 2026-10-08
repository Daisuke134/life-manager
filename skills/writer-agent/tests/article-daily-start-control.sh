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
grep -F 'writer_capacity_preflight' "$WRAPPER" >/dev/null
grep -F 'disk-writers.stop' "$WRAPPER" >/dev/null
grep -F 'WRITER_DISK_CONTROL_DIR="$WRITER_CANONICAL_HOME/.local/state/life-manager/state"' "$WRAPPER" >/dev/null
! grep -F 'LIFE_MANAGER_HOST_STATE_DIR:-' "$WRAPPER" >/dev/null
! grep -E 'CANONICAL_DISK_HEADROOM|DISK_MIN_FREE_BYTES|DISK_LOW_THRESHOLD|disk floor blocked|disk-pressure\.block' "$WRAPPER" >/dev/null
! grep -E 'CANONICAL_DISK_HEADROOM|DISK_MIN_FREE_BYTES|disk floor blocked|writer_capacity_floor' "$ROOT/skills/writer-agent/scripts/article-resume-pending.sh" >/dev/null
grep -F 'ARTICLE_PROVIDER="${ARTICLE_PROVIDER:-codex}"' "$ROOT/skills/writer-agent/scripts/article-resume-pending.sh" >/dev/null
grep -F 'PRE_START_REASON" = "no-same-jst-day-run"' "$ROOT/skills/writer-agent/scripts/article-resume-pending.sh" >/dev/null

echo 'PASS: low disk no longer blocks Writer; explicit hard stop remains'
