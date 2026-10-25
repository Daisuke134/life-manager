#!/usr/bin/env bash
# Point one worktree's apps/landing/node_modules at a shared, lockfile-keyed install.
#
# Every AI Monk worktree used to carry its own 1.5 GB apps/landing/node_modules (five copies on
# 2026-10-25 pushed the Mac mini under its 10 GiB disk floor). All worktrees on the same
# package-lock.json need byte-identical installs, so one install per lockfile hash lives under
#   ~/.cache/anicca-products/landing-node_modules/<sha256(package-lock.json)>/node_modules
# and each worktree gets a symlink. Node resolves through the symlink exactly as it does for a real
# directory, and `next build` here runs with output:'export', so nothing in the tree depends on
# node_modules being a real directory.
#
# Usage:
#   scripts/landing-shared-node-modules.sh [<worktree-root>]     # default: the current checkout
#
# Idempotent. A worktree that already has a real node_modules seeds the store when the store is
# empty (a `mv`, no reinstall); otherwise the real copy is removed and replaced by the symlink.
# Refuses to touch a node_modules that any process has open.
set -euo pipefail

root="$(cd "${1:-$(git rev-parse --show-toplevel)}" && pwd -P)"
landing="$root/apps/landing"
lock="$landing/package-lock.json"
[ -f "$lock" ] || { echo "no package-lock.json under $landing" >&2; exit 2; }

store_root="${ANICCA_PRODUCTS_NODE_MODULES_STORE:-$HOME/.cache/anicca-products/landing-node_modules}"
hash="$(shasum -a 256 "$lock" | cut -c1-16)"
store="$store_root/$hash"
target="$landing/node_modules"

if [ -L "$target" ] && [ "$(readlink "$target")" = "$store/node_modules" ]; then
  echo "already shared: $target -> $store/node_modules"
  exit 0
fi

if [ -d "$target" ] && [ ! -L "$target" ] && [ -n "$(lsof +D "$target" 2>/dev/null | head -1)" ]; then
  echo "refusing: a process has files open under $target" >&2
  exit 3
fi

mkdir -p "$store"
if [ ! -d "$store/node_modules" ]; then
  if [ -d "$target" ] && [ ! -L "$target" ]; then
    echo "seeding store from $target"
    mv "$target" "$store/node_modules"
  else
    echo "installing store with npm ci (lock $hash)"
    cp "$landing/package.json" "$lock" "$store/"
    (cd "$store" && npm ci --no-audit --no-fund)
  fi
fi

if [ -e "$target" ] || [ -L "$target" ]; then
  rm -rf "$target"
fi
ln -s "$store/node_modules" "$target"
echo "shared: $target -> $store/node_modules"
