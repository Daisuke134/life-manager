#!/usr/bin/env bash
# Verify the latest exact8 run and any due both-lane experiment application.
set -euo pipefail

SKILL_DIR="${ARTICLE_SKILL_DIR:-${ARTICLE_ROOT:-$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)}}"
STATE_DIR="${ARTICLE_STATE_DIR:-${WRITER_STATE_DIR:-$SKILL_DIR/state}}"
exec python3 "$SKILL_DIR/scripts/self_improve_control.py" verify \
  --skill-dir "$SKILL_DIR" --state-dir "$STATE_DIR"
