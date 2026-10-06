#!/usr/bin/env bash
set -euo pipefail

ROOT="${LIFE_MANAGER_RELEASE_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
source "$ROOT/apps/life-manager/scripts/lib/portable-runtime.sh"
lm_prepare_portable_runtime "$ROOT"
exec "$LM_NODE" "$ROOT/apps/life-manager/scripts/ebook-distribute-daily.js" "$@"
