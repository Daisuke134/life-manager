#!/usr/bin/env bash
# ebook-articles.sh -- account-free sell lane for The Anicca Reset (copy of line-sticker-articles.sh).
#
# 2026-10-16: the eBook Instagram lanes need a human (English Monk Instagram is not connected and
# Postiz refuses a new channel with 402), so free aniccaai.com articles with one checkout link are
# the lane that runs with no account. Its own owner, so a fenced Instagram/TikTok run never stops it.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../../.." && pwd -P)"

STATE_ROOT="${EBOOK_ARTICLES_STATE_ROOT:-$HOME/.local/state/life-manager/ebook-articles}"
mkdir -p "$STATE_ROOT"
LOG="${EBOOK_ARTICLES_LOG:-$STATE_ROOT/logs/ebook-articles.log}"
mkdir -p "$(dirname "$LOG")"
echo "=== ebook-articles run $(date '+%F %T %Z') ===" >>"$LOG"

ARTICLE_ROOT="$REPO_ROOT/skills/writer-agent"
source "$ARTICLE_ROOT/scripts/writer-runtime-env.sh"
export ARTICLE_SELF_OWNED_LANDING_ROOT="$HOME/.local/state/life-manager/writer/checkouts/self-owned-landing"

exec python3 "$SCRIPT_DIR/scripts/ebook_article_daily.py" --state-root "$STATE_ROOT" >>"$LOG" 2>&1
