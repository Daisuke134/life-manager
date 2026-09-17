#!/usr/bin/env bash
# Check that the repository's agent contract still points at one source and the
# current Superpowers entrypoint. This verifies contract drift, not model behavior.
set -euo pipefail

ROOT="${1:-.}"
ROOT="$(cd "$ROOT" && pwd -P)"
AGENTS="$ROOT/AGENTS.md"
CLAUDE="$ROOT/CLAUDE.md"

fail() {
  printf 'AGENT_CONTRACT_FAIL: %s\n' "$1" >&2
  exit 1
}

test -f "$AGENTS" || fail "AGENTS.md missing"
test -f "$CLAUDE" || fail "CLAUDE.md missing"
grep -Fq 'https://github.com/Daisuke134/life-manager.git' "$AGENTS" \
  || fail "canonical remote missing"
grep -Fq 'superpowers:using-superpowers' "$AGENTS" \
  || fail "using-superpowers requirement missing"
grep -Fqi 'Astra Advisor' "$AGENTS" || fail "Astra Advisor requirement missing"
grep -Fqi 'Ponytail' "$AGENTS" || fail "Ponytail requirement missing"
grep -Fqi 'remove that exact worktree without force' "$AGENTS" \
  || fail "worktree cleanup contract missing"
grep -Fxq '@AGENTS.md' "$CLAUDE" || fail "CLAUDE.md must import @AGENTS.md"

if grep -Eiq '(^|[/~])anicca-project|Felix' "$AGENTS" "$CLAUDE"; then
  fail "stale checkout or Felix reference"
fi

CONTROL_ROOM="$ROOT/control-room/CLAUDE.md"
test -f "$CONTROL_ROOM" \
  || fail "nested control-room CLAUDE.md missing"
grep -Fq '../AGENTS.md' "$CONTROL_ROOM" \
  || fail "nested control-room contract must inherit ../AGENTS.md"
if grep -Eiq 'anicca-project|Felix' "$CONTROL_ROOM"; then
  fail "nested control-room contract has stale reference"
fi

HYPERFRAMES_DIR="$ROOT/skills/video/hyperframes/capafy-o13-review"
test -f "$HYPERFRAMES_DIR/AGENTS.md" \
  || fail "nested HyperFrames AGENTS.md missing"
test -f "$HYPERFRAMES_DIR/CLAUDE.md" \
  || fail "nested HyperFrames CLAUDE.md missing"
test "$(cat "$HYPERFRAMES_DIR/CLAUDE.md")" = '@AGENTS.md' \
  || fail "nested HyperFrames CLAUDE.md must be exactly @AGENTS.md"

printf 'AGENT_CONTRACT_PASS root=%s\n' "$ROOT"
