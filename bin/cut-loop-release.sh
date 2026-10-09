#!/usr/bin/env bash
# cut-loop-release.sh — turn a commit into an immutable release that launchd can point at.
#
#   bash bin/cut-loop-release.sh [<ref>]        # default: HEAD
#
# Why this exists: 221 of the 241 launchd agents on this machine run their code straight out of a
# git working tree (measured 2026-08-17 via bin/launchd_inventory.py). A working tree follows
# whoever is working in it, so a branch switch deletes a scheduled job's code out from under it --
# which is exactly what happened to the x-repost loop that day.
#
# The shape is the one this house already uses for the gig lanes (~/gig/releases/<repo>/<sha>/) and
# the one Capistrano documents: releases accumulate under their own id, a single `current` symlink
# selects one, and rollback is moving that symlink back. 12-factor V puts it plainly -- "it is
# impossible to make changes to the code at runtime" -- which a chmod -R a-w export enforces
# literally rather than by convention.
#
# State is deliberately NOT inside a release: see LOOPS_STATE_ROOT below.
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${LIFE_MANAGER_SOURCE_REPO:-$SCRIPT_ROOT}" && pwd)"
LOOPS_ROOT="${LOOPS_ROOT:-$HOME/loops}"
RELEASES="$LOOPS_ROOT/releases"
DEPENDENCY_BUNDLES="$LOOPS_ROOT/dependency-bundles"
CURRENT="$LOOPS_ROOT/current"
# state root is intentionally not resolved here (see RELEASE.json note below)
KEEP="${LOOPS_KEEP_RELEASES:-1}"
REF="${1:-HEAD}"
RELEASE_PATHS="${LOOPS_RELEASE_PATHS:-}"
ACTIVATE_CURRENT="${LOOPS_ACTIVATE_CURRENT:-1}"
NPM_BIN="${NPM_BIN:-$(command -v npm 2>/dev/null || true)}"
NPM_NODE_BIN="${NPM_NODE_BIN:-}"
RUNTIME_PYTHON="${LOOPS_RUNTIME_PYTHON:-$(command -v python3 2>/dev/null || true)}"
CUT_LOCK="$LOOPS_ROOT/.release-cut.lock"
DEST=""
BUILD_COMPLETE=0
DEPENDENCY_BUILD=""
DEPENDENCY_RELATIVES=("" "runtime/compute-proxy" "runtime/agentmail" "apps/life-manager" \
  "skills/earn/taskmarket" "skills/earn/x402-sell" "services/x402-endpoint")

die() { echo "cut-loop-release: $*" >&2; exit 1; }

case "$ACTIVATE_CURRENT" in
  0|1) ;;
  *) die "LOOPS_ACTIVATE_CURRENT must be 0 or 1" ;;
esac

SHA="$(git -C "$REPO_ROOT" rev-parse "$REF" 2>/dev/null)" || die "cannot resolve ref '$REF'"
SHORT="${SHA:0:8}"

cleanup() {
  local status=$?
  trap - EXIT INT TERM HUP
  if [ -n "$DEST" ] && [ -d "$DEST" ] && [ "$BUILD_COMPLETE" -ne 1 ]; then
    find "$DEST" -type d -exec chmod u+w {} + 2>/dev/null || true
    find "$DEST" -depth -delete 2>/dev/null || true
  fi
  if [ -n "$DEPENDENCY_BUILD" ] && [ -d "$DEPENDENCY_BUILD" ]; then
    find "$DEPENDENCY_BUILD" -type d -exec chmod u+w {} + 2>/dev/null || true
    find "$DEPENDENCY_BUILD" -depth -delete 2>/dev/null || true
  fi
  find "$CUT_LOCK" -depth -delete 2>/dev/null || true
  exit "$status"
}

mkdir -p "$RELEASES" || die "cannot create release root"
if ! mkdir "$CUT_LOCK" 2>/dev/null; then
  LOCK_PID="$(cat "$CUT_LOCK/pid" 2>/dev/null || true)"
  if [[ "$LOCK_PID" =~ ^[0-9]+$ ]] && ! kill -0 "$LOCK_PID" 2>/dev/null; then
    find "$CUT_LOCK" -depth -delete 2>/dev/null || true
    mkdir "$CUT_LOCK" 2>/dev/null || die "another release build owns $CUT_LOCK"
  else
    die "another release build owns $CUT_LOCK"
  fi
fi
printf '%s\n' "$$" >"$CUT_LOCK/pid"
trap cleanup EXIT INT TERM HUP

prune_releases_after() {
  local keep="$1"
  LIFE_MANAGER_RELEASE_KEEP="$keep" \
    python3 "$SCRIPT_ROOT/runtime/loop/central_cleanup.py" --release-gc-only >/dev/null || \
    die "safe release pruning failed"
}

prune_dependency_bundles() {
  local bundle release relative link referenced
  [ -d "$DEPENDENCY_BUNDLES" ] || return 0
  for bundle in "$DEPENDENCY_BUNDLES"/npm-*; do
    [ -d "$bundle" ] || continue
    referenced=0
    for release in "$RELEASES"/*; do
      [ -d "$release" ] || continue
      for relative in "${DEPENDENCY_RELATIVES[@]}"; do
        link="$release/${relative:+$relative/}node_modules"
        if [ -L "$link" ] && [ "$(readlink "$link")" = "$bundle/node_modules" ]; then
          referenced=1
          break 2
        fi
      done
    done
    if [ "$referenced" -eq 0 ]; then
      find "$bundle" -type d -exec chmod u+w {} + || return 1
      find "$bundle" -depth -delete || return 1
    fi
  done
}

# A release nobody else can fetch is not reproducible, and the acceptance bar this house already
# applies to the gig lanes is that the installed SHA is an ancestor of origin/main.
if ! git -C "$REPO_ROOT" cat-file -e "$SHA^{commit}" 2>/dev/null; then
  die "$SHORT is not a commit"
fi
git -C "$REPO_ROOT" fetch --quiet --no-auto-maintenance origin 2>/dev/null || echo "cut-loop-release: WARNING fetch failed, ancestry check uses stale refs" >&2
if git -C "$REPO_ROOT" merge-base --is-ancestor "$SHA" origin/main 2>/dev/null; then
  PROVENANCE="ancestor-of-origin-main"
elif git -C "$REPO_ROOT" branch -r --contains "$SHA" 2>/dev/null | grep -q .; then
  PROVENANCE="pushed-not-yet-on-main"
  echo "cut-loop-release: NOTE $SHORT is pushed but not on origin/main yet" >&2
else
  die "$SHORT exists only locally -- push it before cutting a release"
fi
if [ "$ACTIVATE_CURRENT" = "1" ] && [ "$PROVENANCE" != "ancestor-of-origin-main" ]; then
  die "current activation requires an origin/main ancestor; use LOOPS_ACTIVATE_CURRENT=0 for a candidate"
fi
if [ "$ACTIVATE_CURRENT" = "1" ] && [ -n "$RELEASE_PATHS" ]; then
  die "current activation requires a complete release; use LOOPS_ACTIVATE_CURRENT=0 for a sparse build"
fi

DEST="$RELEASES/$(date +%Y%m%dT%H%M%S)-$SHORT"
[ -e "$DEST" ] && die "$DEST already exists"
# Prune before export as well as after it. Waiting until after extraction requires enough free
# space for KEEP+1 complete trees and made an otherwise recoverable release install fail ENOSPC.
# Keep current plus rollback capacity; the new export becomes the next retained generation.
PRE_KEEP=$((KEEP > 1 ? KEEP - 1 : 1))
prune_releases_after "$PRE_KEEP"
prune_dependency_bundles || die "safe dependency bundle pruning failed"
# Only the release dir: each loop's state dir belongs to that loop's job, and creating a shared
# empty one here would advertise a location nothing actually writes to.
mkdir -p "$DEST" || die "cannot create $DEST"

# git archive exports the committed tree only: no .git, no untracked scratch, no local edits. A
# loop-specific owner may request a whitespace-separated path allowlist; the default remains the
# complete repository for callers that need it. This keeps a 300 KiB X runtime from requiring a
# 57 MiB export on a disk-constrained host.
ARCHIVE_PATHS=()
if [ -n "$RELEASE_PATHS" ]; then
  read -r -a ARCHIVE_PATHS <<<"$RELEASE_PATHS"
  # launchctl-safe is not standalone: every mutating command executes the shared Aqua/user
  # bootstrap preflight first. A sparse release that includes the wrapper but omits this module
  # cannot safely kick an owner, so close that dependency automatically instead of relying on
  # every caller to remember a second path.
  HAS_BIN=0
  HAS_SHARED=0
  HAS_CONNECTOR=0
  HAS_BROWSER_RUNTIME=0
  for path in "${ARCHIVE_PATHS[@]}"; do
    [ "$path" = "bin" ] && HAS_BIN=1
    [ "$path" = "skills/_shared" ] && HAS_SHARED=1
    { [ "$path" = "apps/life-manager" ] || [ "$path" = "skills/connector" ]; } && HAS_CONNECTOR=1
    [ "$path" = "runtime/browser" ] && HAS_BROWSER_RUNTIME=1
  done
  if [ "$HAS_BIN" -eq 1 ] && [ "$HAS_SHARED" -eq 0 ]; then
    ARCHIVE_PATHS+=("skills/_shared")
  fi
  # Connector's target-lease adapter imports the shared browser ownership
  # primitive at runtime. Keep sparse releases import-complete.
  if [ "$HAS_CONNECTOR" -eq 1 ] && [ "$HAS_BROWSER_RUNTIME" -eq 0 ]; then
    ARCHIVE_PATHS+=("runtime/browser")
  fi
fi
if [ "${#ARCHIVE_PATHS[@]}" -eq 0 ]; then
  git -C "$REPO_ROOT" archive --format=tar "$SHA" | tar -x -C "$DEST"
  ARCHIVE_RC=$?
else
  git -C "$REPO_ROOT" archive --format=tar "$SHA" -- "${ARCHIVE_PATHS[@]}" | tar -x -C "$DEST"
  ARCHIVE_RC=$?
fi
if [ "$ARCHIVE_RC" -ne 0 ]; then
  rm -rf "$DEST"
  die "export of $SHORT failed"
fi

matching_locked_dependencies() {
  local package_dir="$1" relative donor donor_package
  relative="${package_dir#"$DEST"}"
  for donor in "$RELEASES"/*; do
    [ "$donor" != "$DEST" ] || continue
    [ -f "$donor/RELEASE.json" ] || continue
    PYTHONPATH="$SCRIPT_ROOT" python3 -c \
      'import sys; from pathlib import Path; from runtime.loop.loop_cleanup import release_is_reclaimed; sys.exit(release_is_reclaimed(Path(sys.argv[1])))' \
      "$donor" || continue
    donor_package="$donor$relative"
    [ -d "$donor_package/node_modules" ] || continue
    [ -f "$donor_package/node_modules/.package-lock.json" ] || continue
    cmp -s "$package_dir/package.json" "$donor_package/package.json" || continue
    cmp -s "$package_dir/package-lock.json" "$donor_package/package-lock.json" || continue
    (cd "$donor_package/node_modules" && pwd -P)
    return
  done
  return 1
}

link_locked_dependencies() {
  local package_dir="$1" relative key bundle build donor_modules node_version npm_version
  relative="${package_dir#"$DEST"}"
  if [ -n "${NPM_NODE_VERSION:-}" ]; then
    node_version="$NPM_NODE_VERSION"
  elif [ -n "$NPM_NODE_BIN" ]; then
    node_version="$("$NPM_NODE_BIN" --version)" || return 1
  else
    node_version="$(node --version)" || return 1
  fi
  if [ -n "${NPM_VERSION:-}" ]; then
    npm_version="$NPM_VERSION"
  elif [ -n "$NPM_NODE_BIN" ]; then
    npm_version="$("$NPM_NODE_BIN" "$NPM_BIN" --version)" || return 1
  else
    npm_version="$("$NPM_BIN" --version)" || return 1
  fi
  key="$({
    printf 'command\0%s\0os\0%s\0arch\0%s\0node\0%s\0npm\0%s\0' \
      'npm-ci --omit=dev --ignore-scripts' "$(uname -s)" "$(uname -m)" \
      "$node_version" "$npm_version"
    printf 'package-json\0'; shasum -a 256 <"$package_dir/package.json"
    printf 'package-lock\0'; shasum -a 256 <"$package_dir/package-lock.json"
  } | shasum -a 256 | awk '{print $1}')" || return 1
  bundle="$DEPENDENCY_BUNDLES/npm-$key"
  if [ ! -f "$bundle/.complete" ] || [ ! -f "$bundle/node_modules/.package-lock.json" ]; then
    if [ -e "$bundle" ]; then
      find "$bundle" -type d -exec chmod u+w {} + 2>/dev/null || return 1
      find "$bundle" -depth -delete || return 1
    fi
    build="$DEPENDENCY_BUNDLES/.build-$key-$$"
    DEPENDENCY_BUILD="$build"
    mkdir -p "$build" || return 1
    cp "$package_dir/package.json" "$package_dir/package-lock.json" "$build/" || return 1
    if donor_modules="$(matching_locked_dependencies "$package_dir")"; then
      cp -alR "$donor_modules" "$build/node_modules" || return 1
    elif [ -n "$NPM_BIN" ]; then
      if [ -n "$NPM_NODE_BIN" ]; then
        (cd "$build" && "$NPM_NODE_BIN" "$NPM_BIN" ci --omit=dev --ignore-scripts) || return 1
      else
        (cd "$build" && "$NPM_BIN" ci --omit=dev --ignore-scripts) || return 1
      fi
    else
      return 1
    fi
    [ -f "$build/node_modules/.package-lock.json" ] || return 1
    printf '%s\n' "$key" >"$build/.complete" || return 1
    mv "$build" "$bundle" || return 1
    DEPENDENCY_BUILD="$bundle"
    chmod -R a-w "$bundle" || return 1
    DEPENDENCY_BUILD=""
  fi
  if [ -e "$package_dir/node_modules" ] || [ -L "$package_dir/node_modules" ]; then
    find "$package_dir/node_modules" -depth -delete || return 1
  fi
  ln -s "$bundle/node_modules" "$package_dir/node_modules" || return 1
}

mkdir -p "$DEPENDENCY_BUNDLES" || die "cannot create dependency bundle root"

for relative in "${DEPENDENCY_RELATIVES[@]}"; do
  package_dir="$DEST/${relative:+$relative}"
  relative="${package_dir#"$DEST"}"
  if ! { [ -f "$package_dir/package.json" ] && [ -f "$package_dir/package-lock.json" ]; }; then
    continue
  fi
  link_locked_dependencies "$package_dir" || \
    die "locked dependency bundle failed in $package_dir"
done

RUNTIME_PYTHON="$("$RUNTIME_PYTHON" -c 'import pathlib,sys; print(pathlib.Path(sys.executable).resolve())')" \
  || die "runtime python identity unavailable"
[ -x "$RUNTIME_PYTHON" ] || die "runtime python is unavailable"
RUNTIME_PYTHON_CACHE_TAG="$("$RUNTIME_PYTHON" -c 'import sys; print(sys.implementation.cache_tag)')" \
  || die "runtime python cache tag unavailable"
if [ -d "$DEST/runtime" ]; then
  "$RUNTIME_PYTHON" -m compileall -q -f --invalidation-mode checked-hash \
    -s "$DEST" "$DEST/runtime" || die "runtime bytecode build failed"
fi

cat >"$DEST/RELEASE.json" <<EOF
{
  "sha": "$SHA",
  "ref": "$REF",
  "provenance": "$PROVENANCE",
  "cut_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "repo": "$(git -C "$REPO_ROOT" remote get-url origin 2>/dev/null)",
  "state_root": "${LOOPS_STATE_ROOT:-set per loop by its launchd job, not by this release}",
  "runtime_python": "$RUNTIME_PYTHON",
  "runtime_python_cache_tag": "$RUNTIME_PYTHON_CACHE_TAG",
  "release_paths": "${ARCHIVE_PATHS[*]:-ALL}"
}
EOF
BUILD_COMPLETE=1

chmod -R a-w "$DEST" 2>/dev/null || true

if [ "$ACTIVATE_CURRENT" = "1" ]; then
  # A release builder can finish after a newer builder has already activated current.
  # Never let that late, older ancestor move the shared pointer backwards.
  CURRENT_SHA=""
  if [ -f "$CURRENT/RELEASE.json" ]; then
    CURRENT_SHA="$(python3 - "$CURRENT/RELEASE.json" <<'PY'
import json, sys
try:
    value = json.load(open(sys.argv[1], encoding="utf-8"))
    sha = value.get("sha", "")
    print(sha if isinstance(sha, str) else "")
except (OSError, ValueError, TypeError):
    print("")
PY
)"
  fi
  if [ -n "$CURRENT_SHA" ] && [ "$CURRENT_SHA" != "$SHA" ] \
    && git -C "$REPO_ROOT" merge-base --is-ancestor "$SHA" "$CURRENT_SHA" 2>/dev/null \
    && git -C "$REPO_ROOT" merge-base --is-ancestor "$CURRENT_SHA" origin/main 2>/dev/null; then
    BUILD_COMPLETE=0
    die "refusing to move current backwards from $CURRENT_SHA to $SHA"
  fi

  # Use the same host-wide owner lock as `lm-loop apply` while replacing `current` atomically.
  PYTHONPATH="$SCRIPT_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
    python3 -c 'import sys; from pathlib import Path; from runtime.host.resource_admission import durable_protocol_version; from runtime.loop.lm_loop import activate_current; activate_current(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), protocol_reader=durable_protocol_version)' \
    "$CURRENT" "$DEST" "$LOOPS_ROOT/.apply.lock" || die "could not activate current release"

  # Keep a few older releases so rollback is a symlink move rather than a rebuild.
  prune_releases_after "$KEEP"
  prune_dependency_bundles || die "safe dependency bundle pruning failed"
  echo "current -> $(readlink "$CURRENT")  ($PROVENANCE)"
else
  echo "release -> $DEST  ($PROVENANCE; current unchanged)"
fi
