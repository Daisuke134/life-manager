#!/usr/bin/env bash
# Verify that a command is running in the canonical Life Manager checkout.
# A normal checkout and its temporary .worktrees are valid; sibling clones are not.
set -euo pipefail

CANONICAL_ROOT="/Users/anicca/Projects/life-manager-main"
EXPECTED_REMOTE="https://github.com/Daisuke134/life-manager.git"

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  printf 'source-boundary FAIL: current directory is not a Git repository\n' >&2
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

case "$REMOTE" in
  "$EXPECTED_REMOTE"|"git@github.com:Daisuke134/life-manager.git") ;;
  *)
    printf 'source-boundary FAIL: wrong origin=%s expected=%s\n' "$REMOTE" "$EXPECTED_REMOTE" >&2
    exit 2
    ;;
esac

printf 'source-boundary PASS root=%s origin=%s\n' "$ROOT" "$REMOTE"
