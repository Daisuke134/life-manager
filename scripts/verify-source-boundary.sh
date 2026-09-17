#!/usr/bin/env bash
# Verify that a command is running in the canonical Life Manager checkout.
# A normal checkout and its temporary .worktrees are valid; sibling clones are not.
set -euo pipefail

CANONICAL_ROOT="$(cd "$(dirname "$0")/.." 2>/dev/null && pwd -P)" || {
  printf 'source-boundary FAIL: script directory is unavailable\n' >&2
  exit 2
}
while [ "$CANONICAL_ROOT" != "/" ] && [ ! -d "$CANONICAL_ROOT/.git" ]; do
  CANONICAL_ROOT="$(dirname "$CANONICAL_ROOT")"
done
if [ ! -d "$CANONICAL_ROOT/.git" ]; then
  printf 'source-boundary FAIL: canonical Git root is unavailable\n' >&2
  exit 2
fi
EXPECTED_COMMON="$CANONICAL_ROOT/.git"
EXPECTED_REMOTE="https://github.com/Daisuke134/life-manager.git"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  printf 'source-boundary FAIL: current directory is not a Git repository\n' >&2
  exit 2
}
COMMON="$(cd "$(git rev-parse --git-common-dir 2>/dev/null)" 2>/dev/null && pwd -P)" || {
  printf 'source-boundary FAIL: Git common directory is unavailable (root=%s)\n' "$ROOT" >&2
  exit 2
}
REMOTE="$(git remote get-url origin 2>/dev/null)" || {
  printf 'source-boundary FAIL: origin is not configured (root=%s)\n' "$ROOT" >&2
  exit 2
}

case "$ROOT" in
  "$CANONICAL_ROOT"|"$CANONICAL_ROOT/.worktrees"/*) ;;
  *)
    printf 'source-boundary FAIL: wrong checkout root=%s expected=%s or its .worktrees\n' "$ROOT" "$CANONICAL_ROOT" >&2
    exit 2
    ;;
esac

if [ "$COMMON" != "$EXPECTED_COMMON" ]; then
  printf 'source-boundary FAIL: wrong Git common dir=%s expected=%s\n' "$COMMON" "$EXPECTED_COMMON" >&2
  exit 2
fi

case "$REMOTE" in
  "$EXPECTED_REMOTE"|"git@github.com:Daisuke134/life-manager.git") ;;
  *)
    printf 'source-boundary FAIL: wrong origin=%s expected=%s\n' "$REMOTE" "$EXPECTED_REMOTE" >&2
    exit 2
    ;;
esac

printf 'source-boundary PASS root=%s origin=%s\n' "$ROOT" "$REMOTE"
