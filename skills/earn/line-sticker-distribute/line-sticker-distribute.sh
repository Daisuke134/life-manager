#!/usr/bin/env bash
# line-sticker-distribute.sh -- the LINE sticker factory's sell loop.
#
# Every money skill pairs a build loop with a distribute (sell) loop
# (AGENTS.md rule 8/9); skills/earn/line-sticker has the build loop
# (line-sticker-factory-hourly) but no sell loop. This is it: post short
# vertical videos of our LINE stickers to TikTok/Instagram via Postiz,
# pointing buyers at the sticker's LINE store page.
#
# Targets are config-driven (config/line-sticker-distribute-accounts.json).
# An empty accounts list is a no-op exit 0 -- it is NOT an error, and it must
# never fall back to any existing Anicca/Honne/eBook Postiz integration
# (Dais 2026-10-07: the sticker audience must never mix into another
# brand's account).
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd -P)"

STATE_ROOT="${LINE_STICKER_DISTRIBUTE_STATE_ROOT:-$HOME/.local/state/life-manager/line-sticker-distribute}"
mkdir -p "$STATE_ROOT"
LOG="${LINE_STICKER_DISTRIBUTE_LOG:-$STATE_ROOT/logs/line-sticker-distribute.log}"
mkdir -p "$(dirname "$LOG")"
echo "=== line-sticker-distribute run $(date '+%F %T %Z') ===" >>"$LOG"

# Postiz key: same private marketing.env every other Postiz loop reads.
if [ -z "${POSTIZ_API_KEY:-}" ]; then
  _lm_marketing_env="${LIFE_MANAGER_MARKETING_ENV_FILE:-$HOME/.local/state/life-manager/private/marketing.env}"
  if [ -f "$_lm_marketing_env" ]; then
    # shellcheck disable=SC1091
    source "$REPO_ROOT/apps/life-manager/scripts/lib/load-env-file.sh"
    lm_load_env_file "$_lm_marketing_env"
  fi
  [ -n "${LM_POSTIZ_API_KEY:-}" ] && export POSTIZ_API_KEY="$LM_POSTIZ_API_KEY"
fi

exec python3 "$SCRIPT_DIR/scripts/line_sticker_distribute.py" \
  --accounts-config "${LINE_STICKER_DISTRIBUTE_ACCOUNTS_CONFIG:-$REPO_ROOT/config/line-sticker-distribute-accounts.json}" \
  --line-sticker-state-root "${LINE_STICKER_STATE_ROOT:-$HOME/.local/state/life-manager/line-sticker}" \
  --state-root "$STATE_ROOT" \
  "$@" >>"$LOG" 2>&1
