#!/usr/bin/env bash
set -euo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
[[ "$#" -gt 0 ]] || set -- install
managed_python="$HOME/.local/share/life-manager/venv/bin/python"
case "$1" in
  plan)
    python="${LIFE_MANAGER_PYTHON:-$managed_python}"
    [[ -x "$python" ]] || python="$(command -v python3)"
    ;;
  install)
    bash "$ROOT/scripts/install-local.sh" prepare >/dev/null
    python="$managed_python"
    ;;
  *) echo "usage: ./install.sh crowdworks [install|plan] [--candidate-profile PATH] [--provider-profile PATH]" >&2; exit 2 ;;
esac
exec "$python" "$ROOT/skills/earn/crowdworks/scripts/install_local.py" "$@"
