#!/usr/bin/env bash
# capafy-reel-daily.sh — one voiced Hook Lab reel per day on X and Instagram (SSOT D2, $0).
# Schedules the reel for TARGET_DATE = today (JST) + 7 so the Postiz queue always holds a week.
# Effect: Postiz schedule on two integrations; fenced by capafy_reel_fence_reconcile.py.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin:$PATH"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
LIFE_MANAGER_REPO="${LIFE_MANAGER_REPO:-$(cd "$SCRIPT_DIR/../../.." && pwd -P)}"
export LIFE_MANAGER_REPO
if [ "${LIFE_MANAGER_LOOP_ID:-}" != "capafy-reel-daily" ] \
    || [ -z "${LIFE_MANAGER_RUN_ID:-}" ] \
    || [ "${LIFE_MANAGER_OCCURRENCE_ID:-}" != "capafy-reel-daily:${LIFE_MANAGER_RUN_ID:-}" ]; then
  printf 'capafy-reel-daily: exact runtime occurrence identity required\n' >&2
  exit 1
fi
export USER="${USER:-$(id -un)}"
export ARTICLE_CLAUDE_BIN="${ARTICLE_CLAUDE_BIN:-$HOME/.local/bin/claude}"

_lm_marketing_env="${LIFE_MANAGER_MARKETING_ENV_FILE:-$HOME/.local/state/life-manager/private/marketing.env}"
if [ -z "${LM_POSTIZ_API_KEY:-}" ] && [ -f "$_lm_marketing_env" ]; then
  # shellcheck source=/dev/null
  source "$LIFE_MANAGER_REPO/apps/life-manager/scripts/lib/load-env-file.sh"
  lm_load_env_file "$_lm_marketing_env"
fi
[ -n "${LM_POSTIZ_API_KEY:-}" ] || { echo "capafy-reel-daily: LM_POSTIZ_API_KEY missing" >&2; exit 2; }
export LM_POSTIZ_API_KEY

STATE_DIR="${CAPAFY_REEL_STATE_DIR:-$HOME/.local/state/life-manager/capafy-reel}"
RUN_DIR="$STATE_DIR/runs/$LIFE_MANAGER_RUN_ID"
mkdir -p "$RUN_DIR"
TARGET_DATE="$(TZ=Asia/Tokyo python3 -c 'import datetime as d; print(d.date.today() + d.timedelta(days=7))')"
python3 - "$RUN_DIR/occurrence.json" "$TARGET_DATE" <<'PY' || exit 1
import json, os, sys
with open(sys.argv[1], "w") as fh:
    json.dump({"owner_id": os.environ["LIFE_MANAGER_LOOP_ID"], "run_id": os.environ["LIFE_MANAGER_RUN_ID"],
               "occurrence_id": os.environ["LIFE_MANAGER_OCCURRENCE_ID"], "target_date": sys.argv[2]}, fh)
    fh.flush(); os.fsync(fh.fileno())
PY
export CAPAFY_REEL_RUN_DIR="$RUN_DIR"
exec python3 "$SCRIPT_DIR/scripts/capafy_reel_daily.py" "$TARGET_DATE"
