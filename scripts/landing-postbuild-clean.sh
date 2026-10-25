#!/usr/bin/env bash
# Drop the webpack cache a landing build leaves behind.
#
# apps/landing builds with output:'export', so the deliverable is apps/landing/out/. The 1.4 GB
# apps/landing/.next/cache is only a speed-up for the next build in the same tree and, across the
# AI Monk worktrees, it was the second-largest disk consumer after node_modules (2026-10-25).
# Run after `npm run build`, or on any idle worktree. Refuses while a build or dev server is live.
#
# Usage:
#   scripts/landing-postbuild-clean.sh [<worktree-root>]     # default: the current checkout
set -euo pipefail

root="$(cd "${1:-$(git rev-parse --show-toplevel)}" && pwd -P)"
cache="$root/apps/landing/.next/cache"
[ -d "$cache" ] || { echo "nothing to clean: $cache"; exit 0; }

if pgrep -f "next (build|dev|start)" >/dev/null 2>&1 && [ -n "$(lsof +D "$root/apps/landing/.next" 2>/dev/null | head -1)" ]; then
  echo "refusing: a Next process has $root/apps/landing/.next open" >&2
  exit 3
fi

before="$(du -sm "$cache" | cut -f1)"
rm -rf "$cache"
echo "removed $cache (${before} MB)"
