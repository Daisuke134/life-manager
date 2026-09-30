#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd -P)"
ENV_FILE="${LIFE_MANAGER_ENV_FILE:-${HOME}/.local/state/life-manager/.env}"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/load-env-file.sh"
lm_load_env_file "$ENV_FILE"
lm_require_env_keys LM_POSTIZ_API_KEY
source "$SCRIPT_DIR/lib/portable-runtime.sh"
lm_prepare_portable_runtime "$REPO_ROOT"
# Lease the TikTok browser like every other browser loop (browser-guard), outside the 300 s
# work timeout so a busy lease cannot eat the collection budget; the lease hands us the endpoint.
export LM_TIKTOK_METRICS_NODE="$LM_NODE" LM_TIKTOK_METRICS_PY="$LM_PYTHON" LM_TIKTOK_METRICS_TIMEOUT="$LM_TIMEOUT_RUNNER" LM_TIKTOK_METRICS_SCRIPT="$SCRIPT_DIR/tiktok-metrics-due.js"
exec bash "$REPO_ROOT/skills/browser/with-browser.sh" tiktok-anicca-jp -- bash -c 'export LM_CDP_ENDPOINT="$CLOAK_CDP_BASE_URL"; exec "$LM_TIKTOK_METRICS_PY" "$LM_TIKTOK_METRICS_TIMEOUT" 300 "$LM_TIKTOK_METRICS_NODE" "$LM_TIKTOK_METRICS_SCRIPT"'
