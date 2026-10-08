#!/usr/bin/env bash
set -euo pipefail

release_root="${LIFE_MANAGER_RELEASE_ROOT:-$(cd "$(dirname "$0")/.." && pwd -P)}"
runner="$release_root/bin/reconcile-agent-runner-release.sh"
launchctl_safe="$release_root/bin/launchctl-safe"
[ -x "$runner" ] && [ -x "$launchctl_safe" ] || exit 69
domain="gui/$(id -u)"
helper_label="ai.anicca.life-manager-release-reconciler-self-handoff"
old_label="ai.anicca.life-manager-release-reconciler"

helper_detail=""
helper_rc=0
helper_detail="$("$launchctl_safe" print "$domain/$helper_label" 2>&1)" || helper_rc=$?
if [ "$helper_rc" -eq 0 ]; then
  helper_state="$(printf '%s\n' "$helper_detail" | sed -nE 's/^[[:space:]]*state = ([[:alnum:]_-]+)[[:space:]]*$/\1/p' | head -n 1)"
  helper_pid="$(printf '%s\n' "$helper_detail" | sed -nE 's/^[[:space:]]*pid = ([0-9]+)[[:space:]]*$/\1/p' | head -n 1)"
  case "$helper_state" in
    running)
      case "$helper_pid" in ''|0|1|*[!0-9]*) exit 69 ;; esac
      kill -0 "$helper_pid" 2>/dev/null || exit 69
      exit 0
      ;;
    waiting|idle)
      if [ -n "$helper_pid" ]; then
        case "$helper_pid" in ''|0|1|*[!0-9]*) exit 69 ;; esac
        kill -0 "$helper_pid" 2>/dev/null && exit 0
      fi
      "$launchctl_safe" bootout "$domain/$helper_label" >/dev/null 2>&1 || exit 69
      ;;
    *)
      exit 69
      ;;
  esac
elif ! printf '%s' "$helper_detail" | grep -Eqi 'could not find service|service not found|absent'; then
  exit 69
fi

old_detail=""
old_rc=0
old_detail="$("$launchctl_safe" print "$domain/$old_label" 2>&1)" || old_rc=$?
if [ "$old_rc" -ne 0 ]; then
  printf '%s' "$old_detail" | grep -Eqi 'could not find service|service not found|absent' || exit 69
  export LIFE_MANAGER_RECONCILER_FORCE_HANDOFF=1
else
  old_state="$(printf '%s\n' "$old_detail" | sed -nE 's/^[[:space:]]*state = ([[:alnum:]_-]+)[[:space:]]*$/\1/p' | head -n 1)"
  case "$old_state" in running|waiting|idle) ;; *) exit 69 ;; esac
fi

export LIFE_MANAGER_RECONCILER_HANDOFF_ONLY=1
exec "$runner"
