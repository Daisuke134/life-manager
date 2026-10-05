#!/usr/bin/env bash
# Sealed releases do not contain .git; derive the root from this script.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P)" || SCRIPT_DIR=""
LIFE_MANAGER_REPO="${LIFE_MANAGER_REPO:-$(cd "$SCRIPT_DIR/../../.." 2>/dev/null && pwd -P)}"
if [ -z "$LIFE_MANAGER_REPO" ] || [ ! -f "$LIFE_MANAGER_REPO/skills/earn/line-sticker/factory.py" ]; then
  echo "LIFE_MANAGER_REPO could not be resolved" >&2
  exit 2
fi
export LIFE_MANAGER_REPO
# Hourly owner: advances the newest open LINE sticker set by exactly one stage (plan -> ... -> submitted).
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin:$PATH"
set -uo pipefail
PY="${LIFE_MANAGER_PYTHON:-$HOME/.local/share/life-manager/venv/bin/python}"
[ -x "$PY" ] || { echo "python with playwright is required" >&2; exit 2; }
ENV_FILE="${LINE_STICKER_ENV_FILE:-$HOME/.openclaw/.env}"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
fi
if [ -z "${FAL_KEY:-}" ] || [ -z "${OPENAI_API_KEY:-}" ]; then
  echo "FAL_KEY and OPENAI_API_KEY are required (checked $ENV_FILE)" >&2
  exit 2
fi
exec "$PY" "$LIFE_MANAGER_REPO/skills/earn/line-sticker/factory.py"
