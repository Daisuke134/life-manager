#!/usr/bin/env bash
# line-sticker-articles.sh -- free Japanese aniccaai.com articles for on-sale LINE sticker sets.
#
# Split out of line-sticker-distribute.sh (Dais 2026-10-11: distribute beyond Instagram/Threads,
# no human in the loop). Inside that loop the article step shared one wake and one effect fence
# with the Instagram/Threads posts, so a held Instagram post left the whole loop fenced and no
# article ran. Articles need no social account; this loop is their only publisher.
#
# aniccaai.com is the site for everything Life Manager ships (Dais 2026-10-08); the article goes
# through the Writer's landing checkout exactly like capafy-distribute-daily. article_daily.py
# owns its slot hours (9/12/15/18/21 JST) and its per-slot ledger (article-ledger.json).
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd -P)"

STATE_ROOT="${LINE_STICKER_ARTICLES_STATE_ROOT:-$HOME/.local/state/life-manager/line-sticker-articles}"
mkdir -p "$STATE_ROOT"
LOG="${LINE_STICKER_ARTICLES_LOG:-$STATE_ROOT/logs/line-sticker-articles.log}"
mkdir -p "$(dirname "$LOG")"
echo "=== line-sticker-articles run $(date '+%F %T %Z') ===" >>"$LOG"

ARTICLE_ROOT="$REPO_ROOT/skills/writer-agent"
# shellcheck source=../../writer-agent/scripts/writer-runtime-env.sh
source "$ARTICLE_ROOT/scripts/writer-runtime-env.sh"
export ARTICLE_SELF_OWNED_LANDING_ROOT="$HOME/.local/state/life-manager/writer/checkouts/self-owned-landing"

exec python3 "$SCRIPT_DIR/scripts/article_daily.py" \
  --line-sticker-state-root "${LINE_STICKER_STATE_ROOT:-$HOME/.local/state/life-manager/line-sticker}" \
  --state-root "$STATE_ROOT" >>"$LOG" 2>&1
