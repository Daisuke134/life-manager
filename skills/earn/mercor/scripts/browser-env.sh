#!/usr/bin/env zsh
set -euo pipefail

# Mercor must resolve its profile-owned browser at wake time.  A fixed :9222
# endpoint can silently be Dais's interactive browser even when the Mercor
# auth/session state is valid, so the provider lane fails closed on identity
# resolution instead of borrowing an unrelated profile.
: "${ROOT:?ROOT is required}"
LEASE_PYTHON="${LEASE_PYTHON:-/usr/bin/python3}"
RESOLVER_PYTHON="${LIFE_MANAGER_BROWSER_RESOLVER_PYTHON:-/usr/bin/python3}"
BROWSER_IDENTITY="${LIFE_MANAGER_BROWSER_IDENTITY:-mercor:dais}"
BROWSER_TARGET_OWNER="${LIFE_MANAGER_BROWSER_TARGET_OWNER:-mercor-revenue-browser}"
BROWSER_REGISTRY="${AI_BROWSER_REGISTRY:-$HOME/.config/ai/registry/browsers.toml}"
BROWSER_RESOLVER="${LIFE_MANAGER_BROWSER_RESOLVER:-$ROOT/skills/browser/resolve_cdp_endpoint.py}"

RESOLVED_JSON=$(
  "$RESOLVER_PYTHON" "$BROWSER_RESOLVER" \
    --registry "$BROWSER_REGISTRY" --identity "$BROWSER_IDENTITY"
)
CDP=$(
  "$RESOLVER_PYTHON" - "$RESOLVED_JSON" <<'PY'
import json
import sys

value = json.loads(sys.argv[1])
if (
    value.get("reachable") is not True
    or value.get("http_status") != 200
    or value.get("websocket_url_valid") is not True
    or not isinstance(value.get("endpoint"), str)
):
    raise SystemExit("mercor_browser_identity_unavailable")
print(value["endpoint"], end="")
PY
)

export CDP
export MERCOR_CDP_BASE_URL="$CDP"
export CLOAK_CDP_BASE_URL="$CDP"
export LIFE_MANAGER_BROWSER_IDENTITY="$BROWSER_IDENTITY"
export LIFE_MANAGER_BROWSER_TARGET_OWNER="$BROWSER_TARGET_OWNER"
