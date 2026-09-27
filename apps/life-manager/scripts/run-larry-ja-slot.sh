#!/usr/bin/env bash
# Owner command for the JA Larry (native-carousel) lane. Replaces the old
# fixed-env-var invocation of anicca-larry-ja-canary.js: this resolves a
# fresh, rotation-selected, automated-gate-approved pack for the current
# slot (generate-larry-slide-pack.js) instead of always feeding the same
# env-pinned pack/media/caption/approval refs, then execs the canary
# unchanged -- every existing safety check in anicca-larry-ja-canary.js /
# marketing-native-carousel-publication-adapter.js still runs at publish
# time, this script only supplies which pack to try.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd -P)"
ENV_FILE="${LIFE_MANAGER_ENV_FILE:-${HOME}/.local/state/life-manager/.env}"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/load-env-file.sh"
lm_load_env_file "$ENV_FILE"
lm_require_env_keys LM_DATA_DIR LM_RUNTIME_TENANT_ID LM_POSTIZ_API_KEY LM_TELEGRAM_BOT_TOKEN LM_TELEGRAM_ALERT_CHAT_ID
source "$SCRIPT_DIR/lib/portable-runtime.sh"
lm_prepare_portable_runtime "$REPO_ROOT"

RESOLUTION="$("$LM_NODE" "$SCRIPT_DIR/generate-larry-slide-pack.js")"
eval "$RESOLUTION"

exec "$LM_NODE" "$SCRIPT_DIR/anicca-larry-ja-canary.js" run-ja-larry-production --slot "$LM_ANICCA_LARRY_JA_SLOT"
