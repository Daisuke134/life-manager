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

ACCOUNTS_CONFIG="${LINE_STICKER_DISTRIBUTE_ACCOUNTS_CONFIG:-$REPO_ROOT/config/line-sticker-distribute-accounts.json}"

# Day-3+ capped engagement and the one-time bio link (SSOT L17 gaps #2/#4) are each their own
# bounded, idempotent, date-gated step (see skills/loop-development/SKILL.md "Sustainable 24/7
# loops" -- one bounded transition per owned resource per wake). Best-effort: a failure here must
# never block the main post-due pass below.
python3 "$SCRIPT_DIR/scripts/engagement_daily.py" \
  --accounts-config "$ACCOUNTS_CONFIG" --state-root "$STATE_ROOT" "$@" >>"$LOG" 2>&1 || true
python3 "$SCRIPT_DIR/scripts/bio_link_setup.py" \
  --accounts-config "$ACCOUNTS_CONFIG" --state-root "$STATE_ROOT" "$@" >>"$LOG" 2>&1 || true
# Free Japanese articles on aniccaai.com (the site for everything Life Manager ships,
# Dais 2026-10-08), published through the Writer's landing checkout exactly like
# capafy-distribute-daily. article_daily.py owns its slot hours; best-effort, never blocks the reel pass.
if true; then
  (
    ARTICLE_ROOT="$REPO_ROOT/skills/writer-agent"
    # shellcheck source=../../writer-agent/scripts/writer-runtime-env.sh
    source "$ARTICLE_ROOT/scripts/writer-runtime-env.sh"
    export ARTICLE_SELF_OWNED_LANDING_ROOT="$HOME/.local/state/life-manager/writer/checkouts/self-owned-landing"
    python3 "$SCRIPT_DIR/scripts/article_daily.py" \
      --line-sticker-state-root "${LINE_STICKER_STATE_ROOT:-$HOME/.local/state/life-manager/line-sticker}" \
      --state-root "$STATE_ROOT"
  ) >>"$LOG" 2>&1 || true
fi

exec python3 "$SCRIPT_DIR/scripts/line_sticker_distribute.py" \
  --accounts-config "$ACCOUNTS_CONFIG" \
  --line-sticker-state-root "${LINE_STICKER_STATE_ROOT:-$HOME/.local/state/life-manager/line-sticker}" \
  --state-root "$STATE_ROOT" \
  "$@" >>"$LOG" 2>&1
