#!/usr/bin/env bash
# claude-projects-backup.sh — ~/.claude/projects (Claude Code session transcripts)
# の日次世代バックアップ。browser-state-backup.sh と同じ
# ~/.cloak/state-backups/<YYYY-MM-DD>/ に保存し、保護された過去世代は削除しない。
# 新しいmacOS世代はnative copyでデータブロックを共有し、原本と更新を分離する。
#
# なぜ要るか(2026-07-16 incident): Claude Code は起動の度に settings.json の
# cleanupPeriodDays より古い session transcript(*.jsonl) を自前で削除する
# (公式: docs.claude.com/en/docs/claude-code/settings, "at startup")。この削除は
# SessionStart hook より先に走るため、floor-guard.py の guard_cleanup_period()
# (値を99999へ復旧するだけ)では「値が壊れてから次回起動までの間」に消えた
# transcript を守れない(順序穴)。ここで日次スナップショットを取っておき、
# floor-guard.py の guard_restore_transcripts() が復元できる元を用意する。
#
# memory/ は不可侵 store(feedback: 消すな/動かすな)だが「読み取って backup に
# 含める」のは問題ない(backup は追加のみ、既存 memory を書き換えない)。
# 復元側(floor-guard.py)が memory/ に一切触れないことで担保する。
set -uo pipefail

SRC="$HOME/.claude/projects"
BACKUP_ROOT="$HOME/.cloak/state-backups"
mkdir -p "$BACKUP_ROOT"

_log() { echo "$(date '+%F %T') claude-projects-backup: $*" >&2; }

date_tag="$(date '+%F')"
dest="$BACKUP_ROOT/$date_tag/claude-projects"
new_generation=0
[ -d "$dest" ] || new_generation=1
mkdir -p "$dest"

if [ "$new_generation" -eq 1 ] && [ "$(uname -s)" = Darwin ]; then
  # Native copies have separate inodes; later writes/chmod cannot change old snapshots.
  /bin/cp -cRpP "$SRC/." "$dest/"
else
  rsync -a --update "$SRC/" "$dest/"
fi
rc=$?

count=$(find "$dest" -maxdepth 2 -name '*.jsonl' 2>/dev/null | wc -l | tr -d ' ')

# Protected generations are preserved; cleanup never deletes ~/.cloak or memory.

if [ "$rc" -eq 0 ]; then
  _log "ok: date=$date_tag jsonl_in_backup=$count dest=$dest"
else
  _log "WARN: rsync exit=$rc date=$date_tag jsonl_in_backup=$count"
fi
if [ "$rc" -eq 0 ]; then ok=true; else ok=false; fi
echo "{\"ok\": $ok, \"date\": \"$date_tag\", \"jsonl_count\": $count, \"dest\": \"$dest\"}"
exit "$rc"
