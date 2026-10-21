#!/bin/bash
LIFE_MANAGER_REPO="${LIFE_MANAGER_REPO:-$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$LIFE_MANAGER_REPO" ] || { echo "LIFE_MANAGER_REPO could not be resolved" >&2; exit 2; }
export LIFE_MANAGER_REPO
# promote_gate.sh — close-loop Gap 3: REQ-RH4 step 3, the per-candidate promotion adversary.
#
# Thin shell entrypoint (mirrors run_evolve.sh's own absolute-path/minimal-PATH conventions — no
# reliance on `command -v` for the durable venv) around lib/promote_gate_run.py, which does the
# real work: deterministic pre-checks (scope_guard/stage1/stage2/trip-wire, via
# lib/promote_gate.py — unit-tested, no LLM cost), and — ONLY for a candidate that clears all of
# those — a real, fresh, headless Codex adversary call (exactly the
# $LIFE_MANAGER_REPO/skills/self/self-fix.sh pattern: --model opus --dangerously-skip-permissions, here as a
# synchronous `--print` call rather than a detached tmux session, since promote_gate.sh needs the
# verdict back before deciding whether to promote — no human anywhere in this path).
#
# Usage: promote_gate.sh <candidate_program_path> <run_dir> [--dry-run]
#   <candidate_program_path>  the openevolve-proposed strategy file to assess (e.g.
#                             $RUN_DIR/best/best_program.py)
#   <run_dir>                 where assessment.json / promote_gate.log / verdict.json are written
#   --dry-run                 (or PROMOTE_GATE_DRY_RUN=1) run the full real assessment + real
#                             adversary call, but never actually commit a promotion — for
#                             smoke-testing the mechanism against a hand-crafted candidate without
#                             mutating the committed baseline strategy file.
set -u
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SKILL_DIR" || { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) FATAL cannot cd to $SKILL_DIR" >&2; exit 1; }
PY_BIN="${PY_BIN:-$HOME/.anicca-venvs/self-improve/bin/python3}"

if [ ! -x "$PY_BIN" ]; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) FATAL python not found or not executable at $PY_BIN" >&2
  exit 1
fi

exec "$PY_BIN" "$SKILL_DIR/lib/promote_gate_run.py" "$@"
