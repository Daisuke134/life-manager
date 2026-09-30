#!/usr/bin/env bash
# self_fix_code_path.sh — the ONE code path a self-fix fixer uses to actually change and ship a
# code fix (not a manual UI push-through). Issue #6063: the old self-fix fixer had no way to edit
# code — ~/loops/releases are immutable and ~/.local/state is not a git worktree — so it could only
# hand-push the current item, never fix the root cause. This gives it: its own worktree, a scope
# guard so it can only touch the loop-owning skill dirs, a test-baseline comparator so it can prove
# "no regression" without needing a clean pre-existing baseline run, then commit/PR/merge/release,
# and a result record. Subcommands are small and independently testable (no network, no git) so the
# guard rails can be proven without ever spawning a real fixer.
#
# Usage:
#   self_fix_code_path.sh scope-check <worktree_dir> <base_ref> <allowlist_regex> [max_diff_lines]
#   self_fix_code_path.sh backoff <loop> [state_dir] [now_epoch]
#   self_fix_code_path.sh new-failures <baseline_file> <current_file>
#   self_fix_code_path.sh record <loop> <outcome> <detail...> [state_dir]
#   self_fix_code_path.sh run <loop> "<blocker + fix hint>"   # full orchestration (real effects)
set -uo pipefail

SFCP_LIFE_MANAGER_REPO="${LIFE_MANAGER_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
SFCP_STATE_DIR_DEFAULT="${LIFE_MANAGER_STATE_HOME:-$HOME/.local/state/life-manager}/state"
SFCP_LOG_DIR_DEFAULT="${LIFE_MANAGER_STATE_HOME:-$HOME/.local/state/life-manager}/logs"

# The scope this code path is allowed to touch. Deliberately narrow to the Capafy publish
# pipeline (S1 / #6063); widen only per-loop when a second loop gets this same code path.
SFCP_DEFAULT_ALLOWLIST_REGEX='^skills/capafy-autopublish/|^skills/capafy/|^skills/self/capafy-loop/'
SFCP_MAX_DIFF_LINES_DEFAULT=800
SFCP_SUCCESS_BACKOFF_MIN=1200   # unchanged: a real fix landed, no need to re-fire soon
SFCP_FAIL_BACKOFF_MIN=60        # NEW: a failed code-path attempt is cheap to retry (worktree+tests,
                                 # no fixer-agent burn) -- 60min instead of the old flat 1200min so a
                                 # persistent code bug is not left blocking the pipeline for ~20h
                                 # (measured 2026-09-28 20:56 -> 2026-09-29 12:14, issue #6063).
SFCP_DAILY_CAP_DEFAULT=6        # per loop per day, counts only outcomes recorded by THIS script
                                 # (i.e. code-path attempts that actually reached a PR), so a
                                 # persistent bug cannot runaway-merge more than 6x/day.

# ---------------------------------------------------------------------------
# scope-check: every changed file (worktree vs base_ref) must match the allowlist regex, and the
# total changed-lines (insertions+deletions) must stay under max_diff_lines. Pure read of `git
# diff`; makes no changes. Prints violations to stderr.
# ---------------------------------------------------------------------------
sfcp_scope_check() {
  local worktree="$1" base_ref="$2" allow_regex="$3" max_lines="${4:-$SFCP_MAX_DIFF_LINES_DEFAULT}"
  local files violators=0 f
  files="$(git -C "$worktree" diff --name-only "$base_ref" 2>/dev/null)" || {
    echo "scope-check: git diff failed (bad worktree/base_ref)" >&2; return 2;
  }
  if [ -z "$files" ]; then
    echo "scope-check: no changes vs $base_ref" >&2
    return 1
  fi
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    if ! printf '%s\n' "$f" | grep -qE "$allow_regex"; then
      echo "scope-check: OUT-OF-SCOPE file: $f" >&2
      violators=$((violators + 1))
    fi
  done <<<"$files"
  if [ "$violators" -gt 0 ]; then
    echo "scope-check: FAIL ($violators file(s) outside allowlist)" >&2
    return 1
  fi
  local stat total_changed
  stat="$(git -C "$worktree" diff --shortstat "$base_ref" 2>/dev/null)"
  total_changed="$(printf '%s' "$stat" | grep -oE '[0-9]+ (insertion|deletion)s?\(\+?-?\)?' \
    | grep -oE '^[0-9]+' | awk '{s+=$1} END{print s+0}')"
  if [ "${total_changed:-0}" -gt "$max_lines" ]; then
    echo "scope-check: FAIL diff too large ($total_changed > $max_lines changed lines)" >&2
    return 1
  fi
  echo "scope-check: OK (${total_changed:-0} changed lines, all files in scope)"
  return 0
}

# ---------------------------------------------------------------------------
# new-failures: baseline_file/current_file are one pytest nodeid per line (failed tests only).
# Prints any nodeid present in current but not baseline (a REGRESSION). Empty output + rc0 = clean.
# ---------------------------------------------------------------------------
sfcp_new_failures() {
  local baseline_file="$1" current_file="$2"
  [ -f "$baseline_file" ] || { echo "new-failures: missing baseline file $baseline_file" >&2; return 2; }
  [ -f "$current_file" ] || { echo "new-failures: missing current file $current_file" >&2; return 2; }
  local new
  new="$(grep -vFxf "$baseline_file" "$current_file" 2>/dev/null | grep -v '^[[:space:]]*$' || true)"
  if [ -n "$new" ]; then
    printf '%s\n' "$new"
    return 1
  fi
  return 0
}

# ---------------------------------------------------------------------------
# backoff: decide ALLOW vs SKIP for a fresh code-path attempt for <loop>. Reads:
#   $state_dir/.self-fix-code-path-<loop>.result   -> "SUCCESS <epoch> ..." or "FAIL <epoch> ..."
#   $state_dir/.self-fix-code-path-<loop>.daily    -> "<YYYY-MM-DD> <count>"
# Never mutates state (pure decision); the caller applies the daily-count bump on actual dispatch.
# ---------------------------------------------------------------------------
sfcp_backoff_decision() {
  local loop="$1" state_dir="${2:-$SFCP_STATE_DIR_DEFAULT}" now_epoch="${3:-$(date +%s)}"
  local result_file="$state_dir/.self-fix-code-path-$loop.result"
  local daily_file="$state_dir/.self-fix-code-path-$loop.daily"
  local today count
  today="$(date -u -r "$now_epoch" +%F 2>/dev/null || date -u +%F)"
  count=0
  if [ -f "$daily_file" ]; then
    read -r d c < "$daily_file" 2>/dev/null || true
    [ "${d:-}" = "$today" ] && count="${c:-0}"
  fi
  local cap="${SFCP_DAILY_CAP:-$SFCP_DAILY_CAP_DEFAULT}"
  if [ "${count:-0}" -ge "$cap" ]; then
    echo "SKIP daily_cap_reached count=$count cap=$cap"
    return 1
  fi
  if [ ! -f "$result_file" ]; then
    echo "ALLOW no_prior_result"
    return 0
  fi
  local outcome concluded_epoch
  outcome="$(awk '{print $1; exit}' "$result_file")"
  concluded_epoch="$(awk '{print $2; exit}' "$result_file")"
  case "$outcome" in
    RUNNING)
      echo "SKIP prior_attempt_running"
      return 1
      ;;
    SUCCESS) backoff_min="${SFCP_SUCCESS_BACKOFF_MIN}" ;;
    FAIL) backoff_min="${SFCP_FAIL_BACKOFF_MIN}" ;;
    *) backoff_min="${SFCP_FAIL_BACKOFF_MIN}" ;;   # unknown/corrupt marker: treat like FAIL (safe, short)
  esac
  case "${concluded_epoch:-}" in
    ''|*[!0-9]*) echo "ALLOW unparseable_prior_result"; return 0 ;;
  esac
  local elapsed_min=$(( (now_epoch - concluded_epoch) / 60 ))
  if [ "$elapsed_min" -lt "$backoff_min" ]; then
    echo "SKIP backoff outcome=$outcome elapsed=${elapsed_min}min<${backoff_min}min"
    return 1
  fi
  echo "ALLOW backoff_elapsed outcome=$outcome elapsed=${elapsed_min}min>=${backoff_min}min"
  return 0
}

# Bump today's dispatch counter (call only once a code-path attempt is actually dispatched).
sfcp_bump_daily_count() {
  local loop="$1" state_dir="${2:-$SFCP_STATE_DIR_DEFAULT}" now_epoch="${3:-$(date +%s)}"
  local daily_file="$state_dir/.self-fix-code-path-$loop.daily"
  local today count=0
  today="$(date -u -r "$now_epoch" +%F 2>/dev/null || date -u +%F)"
  if [ -f "$daily_file" ]; then
    read -r d c < "$daily_file" 2>/dev/null || true
    [ "${d:-}" = "$today" ] && count="${c:-0}"
  fi
  mkdir -p "$state_dir"
  printf '%s %s\n' "$today" "$((count + 1))" > "$daily_file"
}

# record: write the terminal outcome marker the backoff decision (and the caller/healthcheck) reads.
sfcp_record() {
  local loop="$1" outcome="$2" state_dir="${3:-$SFCP_STATE_DIR_DEFAULT}"; shift 3 || shift $#
  mkdir -p "$state_dir"
  printf '%s %s %s\n' "$outcome" "$(date +%s)" "$*" > "$state_dir/.self-fix-code-path-$loop.result"
}

# ---------------------------------------------------------------------------
# release: cut a release via bin/cut-loop-release.sh, waiting for any in-flight cut using ITS OWN
# PID-ownership lock ($LOOPS_ROOT/.release-cut.lock/pid + kill -0) rather than a pgrep argv pattern
# (a pgrep pattern for "cut-loop-release.sh" can match this very wrapper's own invocation line and
# self-deadlock). Reuses the existing lock instead of adding a second one.
# ---------------------------------------------------------------------------
sfcp_wait_for_release_lock() {
  local loops_root="${1:-${LOOPS_ROOT:-$HOME/loops}}" max_wait_s="${2:-600}"
  local lock="$loops_root/.release-cut.lock"
  local waited=0
  while [ -d "$lock" ]; do
    local owner_pid
    owner_pid="$(cat "$lock/pid" 2>/dev/null || true)"
    if [[ "$owner_pid" =~ ^[0-9]+$ ]] && kill -0 "$owner_pid" 2>/dev/null; then
      [ "$waited" -ge "$max_wait_s" ] && { echo "release-lock: still held by pid $owner_pid after ${max_wait_s}s" >&2; return 1; }
      sleep 5; waited=$((waited + 5)); continue
    fi
    # stale lock (no live owner pid) -- cut-loop-release.sh itself reclaims this; nothing to do here.
    break
  done
  return 0
}

# ---------------------------------------------------------------------------
# run: the full real orchestration a spawned fixer calls for a Capafy CODE bug. Every step after
# scope-check/tests is a real git/gh/release effect -- do not call this outside a real fixer run.
# ---------------------------------------------------------------------------
sfcp_run() {
  local loop="$1" blocker="$2"
  local repo="$SFCP_LIFE_MANAGER_REPO"
  local state_dir="$SFCP_STATE_DIR_DEFAULT" log_dir="$SFCP_LOG_DIR_DEFAULT"
  mkdir -p "$state_dir" "$log_dir"
  local log="$log_dir/self-fix-code-path-$loop.log"
  local decision
  decision="$(sfcp_backoff_decision "$loop" "$state_dir")"
  if [[ "$decision" != ALLOW* ]]; then
    echo "$(date -u +%FT%TZ) $loop: $decision" | tee -a "$log"
    return 0
  fi
  echo "$(date -u +%FT%TZ) $loop: $decision -> dispatching code-path fixer" | tee -a "$log"
  sfcp_bump_daily_count "$loop" "$state_dir"
  sfcp_record "$loop" RUNNING "$state_dir" "$blocker"

  local ts br wt
  ts="$(date +%s)"
  br="self-fix/$loop/$ts"
  wt="/private/tmp/selffix-$loop-$ts"

  git -C "$repo" fetch origin main >>"$log" 2>&1 || { sfcp_record "$loop" FAIL "$state_dir" "git fetch failed"; return 1; }
  if ! git -C "$repo" worktree add -b "$br" "$wt" origin/main >>"$log" 2>&1; then
    sfcp_record "$loop" FAIL "$state_dir" "worktree add failed"
    return 1
  fi
  echo "WORKTREE=$wt BRANCH=$br" | tee -a "$log"
  # NOTE: the actual code edit is the fixer agent's job (Edit tool), not this script's. The fixer
  # is expected to: edit inside $wt, then re-invoke this script's scope-check/new-failures/ship
  # subcommands from here before commit. This function stops after preparing the worktree; ship+
  # release+record+cleanup are separate subcommands so a fixer can call them once its edit is done.
  echo "$(date -u +%FT%TZ) $loop: worktree ready at $wt (branch $br) -- fixer edits, then run ship/release/cleanup" >>"$log"
}

# ship: commit+push+PR create+merge --admin. Expects the worktree already has the fixer's edits
# committed-or-not (stages everything). Refuses on scope/test failures internally via caller.
sfcp_ship() {
  local wt="$1" br="$2" title="$3" body="$4"
  git -C "$wt" add -A
  git -C "$wt" diff --cached --quiet && { echo "ship: nothing staged, refusing empty commit" >&2; return 1; }
  git -C "$wt" commit -m "$title" -m "$body" || return 1
  git -C "$wt" push -u origin "$br" || return 1
  local pr_url
  pr_url="$(gh pr create --repo Daisuke134/life-manager --head "$br" --base main \
    --title "$title" --body "$body" 2>&1)" || { echo "$pr_url" >&2; return 1; }
  echo "$pr_url"
  local pr_num
  pr_num="$(printf '%s\n' "$pr_url" | grep -oE '[0-9]+$' | tail -1)"
  [ -n "$pr_num" ] || return 1
  gh pr merge "$pr_num" --repo Daisuke134/life-manager --squash --admin || return 1
  echo "PR_NUMBER=$pr_num"
}

sfcp_main() {
  local cmd="${1:-}"; shift || true
  case "$cmd" in
    scope-check) sfcp_scope_check "$@" ;;
    new-failures) sfcp_new_failures "$@" ;;
    backoff) sfcp_backoff_decision "$@" ;;
    bump-daily) sfcp_bump_daily_count "$@" ;;
    record) sfcp_record "$@" ;;
    wait-release-lock) sfcp_wait_for_release_lock "$@" ;;
    run) sfcp_run "$@" ;;
    ship) sfcp_ship "$@" ;;
    *)
      echo "usage: self_fix_code_path.sh {scope-check|new-failures|backoff|bump-daily|record|wait-release-lock|run|ship} ..." >&2
      return 64
      ;;
  esac
}

# Allow sourcing for tests (BASH_SOURCE != 0) without executing main.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  sfcp_main "$@"
  exit $?
fi
