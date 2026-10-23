#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command_name="${1:-install}"
[ "$#" -eq 0 ] || shift
venv="$HOME/.local/share/life-manager/venv"

case "$command_name" in
  plan|apply)
    python="${LIFE_MANAGER_PYTHON:-$venv/bin/python}"
    [ -x "$python" ] || python="$(command -v python3)"
    exec "$python" -m runtime.loop.local_install "$command_name" "$@"
    ;;
  prepare|install) ;;
  *) echo "usage: ./install.sh local [install|prepare|plan|apply --release PATH]" >&2; exit 2 ;;
esac

[ "$(uname -s)" = Darwin ] || { echo "[local] macOSが必要です" >&2; exit 2; }
case "$(uname -m)" in arm64|x86_64) ;; *) echo "[local] 対応CPUはApple SiliconとIntelです" >&2; exit 2 ;; esac
source "$ROOT/scripts/macos-runtime.sh"
lm_ensure_python
for dependency in node jq ffmpeg fontconfig; do
  executable="$dependency"
  [ "$dependency" != fontconfig ] || executable=fc-list
  if ! command -v "$executable" >/dev/null 2>&1; then
    lm_ensure_homebrew
    "$LM_BREW" install "$dependency" >&2
  fi
done

if ! _lm_select_python "$venv/bin/python"; then
  "$LM_PYTHON" -m venv --clear "$venv"
fi
"$venv/bin/python" -m pip install --disable-pip-version-check -r "$ROOT/requirements-runtime.txt" >&2
"$venv/bin/python" -c 'from cloakbrowser import ensure_binary; ensure_binary()' >&2
export PATH="$HOME/.local/bin:$PATH"
if ! command -v codex >/dev/null 2>&1; then
  installer="$(mktemp -t life-manager-codex.XXXXXX)"
  trap 'rm -f "$installer"' EXIT
  curl -fsSL https://chatgpt.com/codex/install.sh -o "$installer"
  /bin/bash "$installer" >&2
  rm -f "$installer"
  trap - EXIT
fi
export LIFE_MANAGER_PYTHON="$venv/bin/python"
exec "$venv/bin/python" -m runtime.loop.local_install "$command_name" "$@"
