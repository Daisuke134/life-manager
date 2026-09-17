#!/usr/bin/env bash
# Compatibility entrypoint: the single production owner is launchd.
set -euo pipefail

LIFE_MANAGER_REPO="${LIFE_MANAGER_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)}"
[ -n "$LIFE_MANAGER_REPO" ] || { echo "LIFE_MANAGER_REPO could not be resolved" >&2; exit 2; }
CONTROL="${CAPAFY_LAUNCHCTL_SAFE:-$LIFE_MANAGER_REPO/bin/launchctl-safe}"
TARGET="${CAPAFY_LAUNCHCTL_DOMAIN:-gui/$(id -u)}/ai.anicca.capafy-loop-daily"

case "${1:-}" in
  --money)
    shift
    if [ "${1:-}" = "--json" ]; then
      shift
      [ "$#" -eq 0 ] || { echo "usage: $0 --money [--json]" >&2; exit 2; }
      exec "${LIFE_MANAGER_RUNTIME_PYTHON:-python3}" \
        "$LIFE_MANAGER_REPO/skills/earn/capafy-marketing/scripts/capafy_hourly_reconcile.py" --money --json
    fi
    [ "$#" -eq 0 ] || { echo "usage: $0 --money [--json]" >&2; exit 2; }
    exec "${LIFE_MANAGER_RUNTIME_PYTHON:-python3}" \
      "$LIFE_MANAGER_REPO/skills/earn/capafy-marketing/scripts/capafy_hourly_reconcile.py" --money
    ;;
  --status)
    "$CONTROL" print "$TARGET" >/dev/null
    echo "capafy-loop launchd owner loaded"
    ;;
  ""|--restart)
    "$CONTROL" preflight >/dev/null
    "$CONTROL" kickstart "$TARGET" >/dev/null
    echo "capafy-loop launchd owner kicked"
    ;;
  *)
    echo "usage: $0 [--money [--json]|--status|--restart]" >&2
    exit 2
    ;;
esac
