#!/usr/bin/env bash
# capafy-improvement-ledger.sh -- hourly funnel diagnosis + improvement ledger (deterministic, no LLM, no effects).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)" || SCRIPT_DIR=""
LIFE_MANAGER_REPO="${LIFE_MANAGER_REPO:-$(cd "$SCRIPT_DIR/../../.." 2>/dev/null && pwd -P)}"
if [ -z "$LIFE_MANAGER_REPO" ] || [ ! -f "$LIFE_MANAGER_REPO/skills/earn/capafy-marketing/scripts/capafy_improvement_ledger.py" ]; then
  echo "LIFE_MANAGER_REPO could not be resolved" >&2
  exit 2
fi
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin:$PATH"
set -uo pipefail
PY="${CAPAFY_PYTHON:-${LIFE_MANAGER_PYTHON:-$(command -v python3 2>/dev/null)}}"
[ -n "$PY" ] || { echo "python3 is required" >&2; exit 2; }
exec "$PY" "$LIFE_MANAGER_REPO/skills/earn/capafy-marketing/scripts/capafy_improvement_ledger.py" "$@"
