#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd -P)"
ENV_FILE="${LIFE_MANAGER_ENV_FILE:-${HOME}/.local/state/life-manager/.env}"
# The release SHA belongs to the immutable launchd/release binding, never to
# the mutable operator-maintained env file. Keep its presence and value exact
# so this owner cannot be attributed to a stale release after env loading.
if [ "${LIFE_MANAGER_RELEASE_SHA+x}" = x ]; then
  RELEASE_SHA_BOUND=1
  RELEASE_SHA="${LIFE_MANAGER_RELEASE_SHA}"
else
  RELEASE_SHA_BOUND=0
fi
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/load-env-file.sh"
lm_load_env_file "$ENV_FILE"
if [ "$RELEASE_SHA_BOUND" -eq 1 ]; then
  export LIFE_MANAGER_RELEASE_SHA="$RELEASE_SHA"
else
  unset LIFE_MANAGER_RELEASE_SHA
fi
lm_require_data_root "${HOME}/.local/state/life-manager"
lm_require_env_keys LM_POSTIZ_API_KEY
source "$SCRIPT_DIR/lib/portable-runtime.sh"
lm_prepare_portable_runtime "$REPO_ROOT"
exec "$LM_PYTHON" "$LM_TIMEOUT_RUNNER" 300 "$LM_NODE" "$SCRIPT_DIR/instagram-metrics-due.js"
