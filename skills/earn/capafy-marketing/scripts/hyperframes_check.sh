#!/usr/bin/env bash
# Pre-post HyperFrames gate that always terminates.
#
# `hyperframes check` (0.8.8) intermittently never exits: it either prints
# "Check passed" and keeps its headless Chrome open, or stalls before sampling
# (observed 2026-09-27; two agent runs stopped it with exit 130 and no Reel was
# posted). `hyperframes lint` is deterministic and fast, so it is the blocking
# gate; `check` runs bounded and is advisory. The rendered-MP4 probes and frame
# inspection in the loop contract remain blocking.
set -u
DIR="${1:?usage: hyperframes_check.sh <project-dir>}"
LIMIT="${HYPERFRAMES_CHECK_TIMEOUT_SECONDS:-180}"
cd "$DIR" || exit 1

if ! npx --yes hyperframes@0.8.8 lint . </dev/null 2>&1 | grep -v "npm warn" | tee /dev/stderr | grep -qE "0 errors"; then
  echo "HYPERFRAMES_CHECK=FAIL reason=lint"
  exit 1
fi

# The render/check Chrome lives in ~/.cache/hyperframes and cache sweeps can
# delete it; a missing executable failed the 2026-09-29 Capafy Reel pass before
# posting. `browser ensure` is a no-op when present and re-downloads when not.
npx --yes hyperframes@0.8.8 browser ensure </dev/null >/dev/null 2>&1 || {
  echo "HYPERFRAMES_CHECK=FAIL reason=browser_unavailable"
  exit 1
}

LOG="$(mktemp "${TMPDIR:-/tmp}/hyperframes-check.XXXXXX")"
trap 'rm -f "$LOG"' EXIT
npx --yes hyperframes@0.8.8 check --no-browser-gpu . </dev/null >"$LOG" 2>&1 &
pid=$!
for _ in $(seq 1 "$LIMIT"); do
  grep -qE "Check passed|Check failed" "$LOG" && break
  kill -0 "$pid" 2>/dev/null || break
  sleep 1
done
kill_tree() {
  local child
  for child in $(pgrep -P "$1" 2>/dev/null); do kill_tree "$child"; done
  kill "$1" 2>/dev/null
}
kill_tree "$pid"
if grep -q "Check failed" "$LOG"; then
  grep -v "npm warn" "$LOG" | tail -20
  echo "HYPERFRAMES_CHECK=FAIL reason=check"
  exit 1
fi
advisory=$(grep -q "Check passed" "$LOG" && echo passed || echo timeout)
echo "HYPERFRAMES_CHECK=PASS lint=ok check=$advisory"
