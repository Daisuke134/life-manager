#!/usr/bin/env bash
# The factory must refuse any frozen Agent id, at prepare and at finish.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"; S="$HERE/../scripts"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
printf '{"agent_ids":["8123079349"]}' >"$tmp/FROZEN.json"
export CAPAFY_FROZEN_FILE="$tmp/FROZEN.json"
CAPAFY_EXPECTED_AGENT_ID=8123079349 bash "$S/publish_prepare.sh" "$tmp" "$tmp/L.md" "$tmp/i.png" >/dev/null 2>"$tmp/e1"; rc1=$?
bash "$S/publish_finish.sh" 8123079349 hook-lab "" "" >/dev/null 2>"$tmp/e2"; rc2=$?
mkdir -p "$tmp/sk"; printf '{"agent_id":"8123079349"}' >"$tmp/sk/UPDATE.json"
bash "$S/publish_prepare.sh" "$tmp/sk" "$tmp/L.md" "$tmp/i.png" >/dev/null 2>"$tmp/e3"; rc3=$?
bash "$S/publish_finish.sh" 1111111111 x "" "" >/dev/null 2>"$tmp/e4"; rc4=$?
[ "$rc1" = 3 ] && grep -q FROZEN_AGENT_REFUSED "$tmp/e1" || { echo "FAIL prepare expected-id rc=$rc1"; exit 1; }
[ "$rc2" = 3 ] && grep -q FROZEN_AGENT_REFUSED "$tmp/e2" || { echo "FAIL finish rc=$rc2"; exit 1; }
[ "$rc3" = 3 ] && grep -q FROZEN_AGENT_REFUSED "$tmp/e3" || { echo "FAIL prepare UPDATE.json rc=$rc3"; exit 1; }
! grep -q FROZEN_AGENT_REFUSED "$tmp/e4" || { echo "FAIL non-frozen refused"; exit 1; }
echo PASS
