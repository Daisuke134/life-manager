#!/bin/bash
set -euo pipefail

export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
TARGET="${LIFE_MANAGER_CHECKOUT:-$HOME/life-manager}"

[ "$(uname -s)" = Darwin ] || {
  echo "[life-manager] この導入コマンドはmacOS用です" >&2
  exit 2
}

if ! command -v git >/dev/null 2>&1 || ! git --version >/dev/null 2>&1; then
  if ! command -v brew >/dev/null 2>&1; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" >&2
    for prefix in /opt/homebrew /usr/local; do
      [ ! -x "$prefix/bin/brew" ] || export PATH="$prefix/bin:$PATH"
    done
  fi
  brew install git >&2
fi

if [ -e "$TARGET" ]; then
  root="$(git -C "$TARGET" rev-parse --show-toplevel 2>/dev/null)" || {
    echo "[life-manager] 導入先がGit checkoutではありません: $TARGET" >&2; exit 2;
  }
  [ "$(cd "$root" && pwd -P)" = "$(cd "$TARGET" && pwd -P)" ] || {
    echo "[life-manager] 導入先が別checkoutの内側です" >&2; exit 2;
  }
  origin="$(git -C "$TARGET" remote get-url origin)"
  case "$origin" in
    https://github.com/Daisuke134/life-manager|https://github.com/Daisuke134/life-manager.git|git@github.com:Daisuke134/life-manager.git) ;;
    *) echo "[life-manager] 導入先のoriginがLife Managerではありません" >&2; exit 2 ;;
  esac
  [ "$(git -C "$TARGET" symbolic-ref --short HEAD 2>/dev/null)" = main ] || {
    echo "[life-manager] 作業中branchを保護します。cleanなmainの導入先を指定してください" >&2; exit 2;
  }
  [ -z "$(git -C "$TARGET" status --porcelain)" ] || {
    echo "[life-manager] 未commitの変更を保護します。先に保存してください" >&2; exit 2;
  }
  git -C "$TARGET" fetch origin main >&2
  git -C "$TARGET" merge-base --is-ancestor HEAD origin/main || {
    echo "[life-manager] 公開mainに含まれないlocal commitを保護します" >&2; exit 2;
  }
  git -C "$TARGET" merge --ff-only origin/main >&2
else
  git clone --depth 1 --branch main https://github.com/Daisuke134/life-manager.git "$TARGET" >&2
fi

export LIFE_MANAGER_CHECKOUT="$TARGET"
source "$TARGET/scripts/macos-runtime.sh"
lm_ensure_python
export LIFE_MANAGER_PYTHON="$LM_PYTHON"

if [ "$#" -gt 0 ]; then
  case "$1" in
    job-hunter)
      if [ -z "${JOB_SEARCH_PYTHON:-}" ]; then
        for candidate in "$HOME/.local/share/anicca/job-search/venv/bin/python" \
          "$HOME/.local/share/life-manager/venv/bin/python"; do
          if [ -x "$candidate" ] && _lm_select_python "$candidate"; then
            break
          fi
        done
      fi
      export JOB_SEARCH_PYTHON="${JOB_SEARCH_PYTHON:-$LM_PYTHON}"
      ;;
    list|plan)
      if ! command -v node >/dev/null 2>&1; then
        lm_ensure_homebrew
        "$LM_BREW" install node >&2
      fi
      ;;
  esac
  exec /bin/bash "$TARGET/install.sh" "$@"
fi

VENV="$HOME/.local/share/life-manager/venv"
if [ ! -x "$VENV/bin/python" ] \
  || ! "$VENV/bin/python" -c 'import sys; raise SystemExit(sys.version_info < (3, 13))'; then
  "$LM_PYTHON" -m venv --clear "$VENV"
fi
"$VENV/bin/python" -m pip install --disable-pip-version-check -r "$TARGET/requirements-runtime.txt" >&2

exec "$VENV/bin/python" "$TARGET/scripts/life-manager-onboarding-server.py" --open
