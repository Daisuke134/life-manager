#!/usr/bin/env bash

lm_prepare_portable_runtime() {
  local repo_root="$1"
  # launchd does not inherit the interactive PATH. The shared plist injects the
  # absolute managed runtimes; use explicit caller overrides first, then those
  # immutable-release values, and only then PATH for local/manual invocation.
  LM_NODE="${NODE_BIN:-${LIFE_MANAGER_RUNTIME_NODE:-${LIFE_MANAGER_NODE:-$(command -v node 2>/dev/null || true)}}}"
  LM_PYTHON="${PYTHON_BIN:-${LIFE_MANAGER_RUNTIME_PYTHON:-${LIFE_MANAGER_PYTHON:-$(command -v python3 2>/dev/null || true)}}}"
  LM_TIMEOUT_RUNNER="$repo_root/runtime/run-with-timeout.py"
  if [[ -z "$LM_NODE" || ! -x "$LM_NODE" ]]; then
    echo '{"status":"setup_required","missing":"node"}' >&2
    return 2
  fi
  if [[ -z "$LM_PYTHON" || ! -x "$LM_PYTHON" ]]; then
    echo '{"status":"setup_required","missing":"python3"}' >&2
    return 2
  fi
  if [[ ! -f "$LM_TIMEOUT_RUNNER" ]]; then
    echo '{"status":"setup_required","missing":"runtime/run-with-timeout.py"}' >&2
    return 2
  fi
  export LM_NODE LM_PYTHON LM_TIMEOUT_RUNNER
}

lm_timeout() {
  "$LM_PYTHON" "$LM_TIMEOUT_RUNNER" "$@"
}
