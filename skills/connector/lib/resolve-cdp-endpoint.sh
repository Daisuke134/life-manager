#!/usr/bin/env bash
set -eu

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$HERE/../../.." && pwd -P)"
BROWSER_PORT_OWNER="${BROWSER_PORT_OWNER_BIN:-$REPO_ROOT/runtime/host/browser_port_owner.py}"
BROWSER_PORT_OWNER_PYTHON="${BROWSER_PORT_OWNER_PYTHON:-python3}"
NODE_BIN="${NODE_BIN:-$(command -v node || true)}"

[ -f "$BROWSER_PORT_OWNER" ] \
  && command -v "$BROWSER_PORT_OWNER_PYTHON" >/dev/null 2>&1 \
  && [ -n "$NODE_BIN" ] && [ -x "$NODE_BIN" ] || exit 2

BROWSER_ENDPOINT_JSON="$($BROWSER_PORT_OWNER_PYTHON -I "$BROWSER_PORT_OWNER" resolve \
  --port 9222 --owner life-manager-daily-driver)" || exit 1
"$NODE_BIN" -e '
const input = JSON.parse(process.argv[1]);
const { exactConnectorCdpEndpoint } = require(process.argv[2]);
process.stdout.write(exactConnectorCdpEndpoint(input.endpoint) + "\n");
' "$BROWSER_ENDPOINT_JSON" "$REPO_ROOT/apps/life-manager/lib/connector-browser-target-controller.js"
