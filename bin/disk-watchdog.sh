#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
# Keeps free space above threshold so nothing (esp. claude remote-control) dies on ENOSPC.
# Only deletes regenerable caches. Never touches transcripts, memory, state, repos.
MIN_GB=25
free_gb() { df -g /System/Volumes/Data | awk 'NR==2{print $4}'; }
log() { echo "$(date '+%F %T') $*" >> ~/Library/Logs/disk-watchdog.log; }

[ "$(free_gb)" -ge "$MIN_GB" ] && exit 0
log "free=$(free_gb)G below ${MIN_GB}G — pruning"

# Releases outgrow everything else here: one 1.2GB tree every 10-20 minutes.
# Their own GC refuses to touch a release that a loaded agent references or a
# process holds open, so asking it for tighter retention cannot strand a loop.
newest=$(ls -t ~/loops/releases 2>/dev/null | head -1)
if [ -n "$newest" ] && [ -f "$HOME/loops/releases/$newest/runtime/loop/central_cleanup.py" ]; then
  out=$(cd "$HOME/loops/releases/$newest" && LIFE_MANAGER_RELEASE_KEEP=2 \
          python3 runtime/loop/central_cleanup.py --release-gc-only 2>/dev/null)
  log "release gc: $(printf '%s' "$out" | head -c 200)"
fi
# The GC renames a tree to <release>.gc-trash.<pid> before unlinking it; a run
# that dies in between leaves the whole 1.2GB behind under that name.
rm -rf "$HOME"/loops/releases/*.gc-trash.* 2>/dev/null

rm -rf ~/.npm/_cacache ~/Library/Caches/pip ~/.cache/uv ~/Library/Caches/Homebrew 2>/dev/null
rm -rf ~/Library/Developer/Xcode/DerivedData/* 2>/dev/null
rm -rf ~/.cache/anicca-clones/* ~/.cache/anicca-worktrees/* /tmp/anicca-* 2>/dev/null
find /private/tmp/claude-501 -maxdepth 2 -type d -mtime +2 -exec rm -rf {} + 2>/dev/null
find ~/Library/Logs -name '*.log' -size +200M -exec truncate -s 0 {} \; 2>/dev/null

# Agent sessions create a worktree per task and rarely remove it; on 2026-10-06
# 71 of them held 6.2GB and 91 more were dead registrations. Remove only a
# worktree that is clean, whose PR is merged, and that no process uses as cwd.
REPO=/Users/anicca/Projects/life-manager-main
if [ -d "$REPO/.worktrees" ] && command -v gh >/dev/null; then
  merged=$(cd "$REPO" && gh pr list --state merged --limit 1500 --json headRefName -q '.[].headRefName' 2>/dev/null)
  inuse=$(lsof -d cwd -Fn 2>/dev/null | grep -o "$REPO/.worktrees/[^/]*" | sort -u)
  removed=0
  for w in "$REPO"/.worktrees/*/; do
    w=${w%/}
    b=$(git -C "$w" branch --show-current 2>/dev/null)
    [ -n "$b" ] && printf '%s\n' "$merged" | grep -qxF "$b" || continue
    [ -z "$(git -C "$w" status --porcelain 2>/dev/null)" ] || continue
    printf '%s\n' "$inuse" | grep -qxF "$w" && continue
    git -C "$REPO" worktree unlock "$w" 2>/dev/null
    git -C "$REPO" worktree remove "$w" 2>/dev/null && removed=$((removed+1))
  done
  git -C "$REPO" worktree prune 2>/dev/null
  log "merged worktrees removed: $removed"
fi

log "after prune free=$(free_gb)G"

# A full disk logged the Claude CLI out on 2026-10-06 and took Remote Control
# down; this script had written "STILL CRITICAL" to a log nobody reads for hours.
# Below 10GB after pruning, tell Dais — at most once per 6 hours.
ALERT_STAMP="$HOME/.local/state/life-manager/disk-watchdog.last-alert"
if [ "$(free_gb)" -lt 10 ]; then
  log "STILL CRITICAL — manual action needed"
  last=$(cat "$ALERT_STAMP" 2>/dev/null || echo 0)
  if [ $(( $(date +%s) - last )) -gt 21600 ]; then
    top=$(du -sk "$HOME"/* "$HOME"/.[!.]* 2>/dev/null | sort -rn | head -5 | awk '{printf "%s %.1fG, ", $2, $1/1048576}' | sed "s#$HOME/##g")
    bash "${DISK_ALERT_SH:-$REPO/skills/_shared/send-telegram.sh}" \
      "Mac mini のディスク空きが $(free_gb)GB です（自動掃除後）。満杯になると Claude がログアウトし Remote Control が切れます。大きい順: ${top}" \
      >/dev/null 2>&1 && date +%s >"$ALERT_STAMP"
  fi
fi
exit 0
