#!/usr/bin/env bash
# Shared installer selection; sourcing this file does not probe or install tools.

lm_node_ready() {
  command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1 \
    && node -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit(major >= 24 || (major === 22 && minor >= 19) ? 0 : 1)' >/dev/null 2>&1
}

lm_ensure_node() {
  lm_node_ready && return 0
  lm_ensure_homebrew || return
  "$LM_BREW" install node >&2 || return
  export PATH="$(dirname "$LM_BREW"):$PATH"
  hash -r
  lm_node_ready || { echo '[life-manager] Node 22.19+ (22.x) or Node >=24, plus npm, are required' >&2; return 2; }
}

_lm_executable() {
  local resolved
  resolved="$(command -v "$1" 2>/dev/null)" || return 1
  [ -x "$resolved" ] || return 1
  case "$resolved" in
    /*) ;;
    *) resolved="$(cd "$(dirname "$resolved")" && pwd)/$(basename "$resolved")" ;;
  esac
  printf '%s\n' "$resolved"
}

_lm_find_homebrew() {
  local candidate resolved
  for candidate in "$(command -v brew 2>/dev/null || true)" \
    /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [ -n "$candidate" ] || continue
    resolved="$(_lm_executable "$candidate")" || continue
    if "$resolved" --version >/dev/null 2>&1; then
      LM_BREW="$resolved"
      return 0
    fi
  done
  return 1
}

lm_ensure_homebrew() {
  local installer
  LM_BREW=""
  _lm_find_homebrew && return 0
  installer="$(mktemp -t lm-homebrew.XXXXXX)" || return 1
  if ! curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh \
    -o "$installer"; then
    rm -f "$installer"
    return 1
  fi
  if ! /bin/bash "$installer" >&2; then
    rm -f "$installer"
    return 1
  fi
  rm -f "$installer"
  if ! _lm_find_homebrew; then
    echo '[life-manager] Homebrew installation did not provide a working brew' >&2
    return 2
  fi
}

_lm_select_python() {
  local resolved
  [ -n "$1" ] || return 1
  resolved="$(_lm_executable "$1")" || return 1
  if "$resolved" -c 'import sys; raise SystemExit(sys.version_info < (3, 13))' \
    >/dev/null 2>&1; then
    LM_PYTHON="$resolved"
    return 0
  fi
  return 1
}

lm_ensure_python() {
  local candidate prefix
  LM_PYTHON=""
  for candidate in "${LIFE_MANAGER_PYTHON:-}" "${PYTHON:-}" \
    python3.14 python3.13 python3; do
    _lm_select_python "$candidate" && return 0
  done
  lm_ensure_homebrew || return
  "$LM_BREW" install python@3.14 >&2 || return
  prefix="$("$LM_BREW" --prefix python@3.14)" || return
  for candidate in "$prefix/bin/python3.14" "$prefix/bin/python3"; do
    _lm_select_python "$candidate" && return 0
  done
  echo '[life-manager] Homebrew did not provide Python 3.13 or newer' >&2
  return 2
}
