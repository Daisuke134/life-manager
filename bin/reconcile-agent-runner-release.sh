#!/usr/bin/env bash
# Keep managed runners on one complete pushed-main release without interrupting active loops.
set -euo pipefail

SOURCE_REPO="${LIFE_MANAGER_SOURCE_REPO:-$HOME/Projects/life-manager-main}"
LOOPS_ROOT="${LOOPS_ROOT:-$HOME/loops}"
CURRENT="$LOOPS_ROOT/current"
SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

fetch_timeout_seconds="${LIFE_MANAGER_RELEASE_FETCH_TIMEOUT_SECONDS:-600}"
case "$fetch_timeout_seconds" in
  ''|*[!0-9]*)
    printf 'agent-runner reconcile refused: invalid fetch timeout\n' >&2
    exit 64
    ;;
esac
if [ "$fetch_timeout_seconds" -lt 1 ]; then
  printf 'agent-runner reconcile refused: invalid fetch timeout\n' >&2
  exit 64
fi
runtime_python="${LIFE_MANAGER_RUNTIME_PYTHON:-$(command -v python3 || true)}"
timeout_runner="$SCRIPT_ROOT/runtime/run-with-timeout.py"
if [ -z "$runtime_python" ] || [ ! -f "$timeout_runner" ]; then
  printf 'agent-runner reconcile refused: portable timeout unavailable\n' >&2
  exit 69
fi

reconcile_release() {
  local release_root="$1"
  local status=0
  if ! LIFE_MANAGER_RELEASE_ROOT="$release_root" "$release_root/bin/lm-loop" \
    reconcile shared-agent-runner --loaded-idle-only; then
    status=1
  fi
  if ! LIFE_MANAGER_RELEASE_ROOT="$release_root" "$release_root/bin/lm-loop" \
    reconcile deterministic --loaded-idle-only; then
    status=1
  fi
  local admission_root="${LIFE_MANAGER_RESOURCE_ADMISSION_ROOT:-$HOME/.local/state/life-manager/host-admission/resources}"
  if [ ! -f "$admission_root/protocol.json" ] && \
    ! LIFE_MANAGER_RELEASE_ROOT="$release_root" "$release_root/bin/lm-loop" admission-v2-enable; then
    status=1
  fi
  return "$status"
}

"$runtime_python" "$timeout_runner" --grace-seconds 15 "$fetch_timeout_seconds" \
  git -C "$SOURCE_REPO" fetch --quiet --no-tags --no-auto-maintenance \
    --negotiation-tip=refs/remotes/origin/main origin main
main_sha="$(git -C "$SOURCE_REPO" rev-parse origin/main)"
initial_release_root="$(cd "$CURRENT" 2>/dev/null && pwd -P || true)"
current_sha=""
current_paths=""
if [ -n "$initial_release_root" ]; then
  current_sha="$(jq -r '.sha // ""' "$initial_release_root/RELEASE.json" 2>/dev/null || true)"
  current_paths="$(jq -r '.release_paths // ""' "$initial_release_root/RELEASE.json" 2>/dev/null || true)"
fi
current_complete=0
[ "$current_paths" = "ALL" ] && current_complete=1
release_sha_target="$main_sha"

# The public specs and the Gig progress ledger are not runtime inputs. Re-exporting the complete
# tree for a progress-only main commit consumes about a GiB while changing no runnable byte.
# Keep reconciling stale target labels to the existing complete release; cut a new release as soon
# as any other path differs. A missing/non-ancestor current SHA fails closed into a cut.
if [ "$current_complete" -eq 1 ] && [ -n "$current_sha" ] \
  && git -C "$SOURCE_REPO" merge-base --is-ancestor "$current_sha" "$main_sha" 2>/dev/null \
  && git -C "$SOURCE_REPO" diff --quiet "$current_sha" "$main_sha" -- . \
    ':(exclude)docs/**' ':(exclude)skills/earn/gig/TODO.md'; then
  release_sha_target="$current_sha"
fi

if [ "$release_sha_target" != "$current_sha" ] || [ "$current_complete" -ne 1 ]; then
  cutter="$CURRENT/bin/cut-loop-release.sh"
  [ -x "$cutter" ] || cutter="$SOURCE_REPO/bin/cut-loop-release.sh"
  LIFE_MANAGER_SOURCE_REPO="$SOURCE_REPO" LOOPS_ROOT="$LOOPS_ROOT" LOOPS_RELEASE_PATHS= \
    bash "$cutter" "$main_sha"
fi

RELEASE_ROOT="$(cd "$CURRENT" && pwd -P)"
release_sha="$(jq -r '.sha // ""' "$RELEASE_ROOT/RELEASE.json")"
release_paths="$(jq -r '.release_paths // ""' "$RELEASE_ROOT/RELEASE.json")"
if [ "$release_sha" != "$release_sha_target" ] || [ "$release_paths" != "ALL" ]; then
  printf 'agent-runner reconcile refused: release is not the full pushed-main build\n' >&2
  exit 1
fi

reconcile_release "$RELEASE_ROOT"
