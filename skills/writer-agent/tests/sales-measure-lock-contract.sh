#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
WORKER="$REPO_ROOT/skills/writer-agent/scripts/writer-sales-measure-worker.sh"
LOCK_HELPER="$REPO_ROOT/runtime/host/owned_directory_lock.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

make_fixture() {
  local root="$1"
  mkdir -p "$root/scripts" "$root/state" "$root/runtime/host" "$root/skills/browser"
  ln -s "$LOCK_HELPER" "$root/runtime/host/owned_directory_lock.py"
  cat >"$root/skills/browser/browser-guard.sh" <<'EOF'
#!/usr/bin/env bash
if [ "$1" = acquire ]; then printf 'http://[::1]:9222\n'; fi
EOF
  cp "$WORKER" "$root/scripts/writer-sales-measure-worker.sh"
  cat >"$root/scripts/writer-runtime-env.sh" <<EOF
STATE_DIR="$root/state"
LIFE_MANAGER_REPO="$root"
WRITER_BROWSER_PYTHON="$root/fake-browser-python"
export STATE_DIR LIFE_MANAGER_REPO WRITER_BROWSER_PYTHON
EOF
  cat >"$root/fake-browser-python" <<EOF
#!/usr/bin/env bash
printf 'measured\n' >>"$root/measured"
EOF
  chmod +x "$root/fake-browser-python"
  cat >"$root/scripts/measure-sales.py" <<'PY'
# fixture consumed by fake-browser-python
PY
  cat >"$root/scripts/money_sync.py" <<EOF
from pathlib import Path
Path("$root/synced").write_text("synced\n")
EOF
}

stale="$TMP/stale"
make_fixture "$stale"
mkdir "$stale/state/.sales-measure.lock"
printf '999999999\n' >"$stale/state/.sales-measure.lock/pid"
touch -t 200001010000 "$stale/state/.sales-measure.lock"
/bin/bash "$stale/scripts/writer-sales-measure-worker.sh"
test -f "$stale/measured"
test -f "$stale/synced"

legacy_live="$TMP/legacy-live"
make_fixture "$legacy_live"
mkdir "$legacy_live/state/.sales-measure.lock"
printf '%s\n' "$$" >"$legacy_live/state/.sales-measure.lock/pid"
touch -t 200001010000 "$legacy_live/state/.sales-measure.lock"
set +e
/bin/bash "$legacy_live/scripts/writer-sales-measure-worker.sh"
rc=$?
set -e
test "$rc" -eq 75
test ! -e "$legacy_live/measured"
test ! -e "$legacy_live/synced"

busy="$TMP/busy"
make_fixture "$busy"
token="test-owner-token"
python3 "$LOCK_HELPER" acquire "$busy/state/.sales-measure.lock" "$$" "$token" >/dev/null
set +e
/bin/bash "$busy/scripts/writer-sales-measure-worker.sh"
rc=$?
set -e
test "$rc" -eq 75
test ! -e "$busy/measured"
test ! -e "$busy/synced"
python3 "$LOCK_HELPER" release "$busy/state/.sales-measure.lock" "$$" "$token" >/dev/null

printf 'sales-measure lock contract: PASS\n'
