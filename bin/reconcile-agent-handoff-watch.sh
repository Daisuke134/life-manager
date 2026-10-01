#!/usr/bin/env bash
set -euo pipefail

release_root="${LIFE_MANAGER_RELEASE_ROOT:-$(cd "$(dirname "$0")/.." && pwd -P)}"
[ -x "$release_root/bin/reconcile-agent-runner-release.sh" ] || exit 69
export LIFE_MANAGER_RECONCILER_HANDOFF_ONLY=1
exec "$release_root/bin/reconcile-agent-runner-release.sh"
