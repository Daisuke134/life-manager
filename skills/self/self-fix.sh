#!/usr/bin/env bash
LIFE_MANAGER_REPO="${LIFE_MANAGER_REPO:-$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$LIFE_MANAGER_REPO" ] || { echo "LIFE_MANAGER_REPO could not be resolved" >&2; exit 2; }
export LIFE_MANAGER_REPO
SELF_FIX_RELEASE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

RUN_AGENT="$LIFE_MANAGER_REPO/skills/earn/marketing-engine/run_agent.sh"
if [ "${AGENT_WIRING_PROBE_ONLY:-0}" = "1" ]; then
  printf '{"task_class":"self-fix-code-agent","runner":"%s"}\n' "$RUN_AGENT"
  exit 0
fi

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin:$PATH"
# self-fix.sh — TRUE autonomous self-heal launcher (no human, no "file issue and wait"). When a loop hits a
# code/automation blocker it cannot fix in-pass, it (or a healthcheck) calls this to spawn a detached, full-power
# high-value agent that diagnoses → edits the correct mother-repo code → VERIFIES by a REAL side-effect → commits+pushes
# → writes a result marker. That is how the loops self-improve their own code without babysitting.
# Usage: self-fix.sh <loop-name> "<blocker + concrete fix hint>"
set -uo pipefail
# FIND-029: fingerprint the SUBSTANTIVE pane content only — strip the CLI's ever-changing status line (elapsed
# timer, token counter, spinner glyphs, "esc to interrupt") so a genuinely FROZEN (deadlocked) fixer produces the
# SAME fingerprint across checks (its reasoning/tool text is unchanged; only the timer ticks), while real progress
# (new text) changes it. Without this strip, the incrementing timer made every check look like "progress".
sf_pane_fingerprint(){ printf '%s' "$1" | tail -25 \
  | sed -E 's/[0-9]+//g; s/esc to interrupt//g' \
  | tr -d '✻✳✶✢⏺◐◓◑◒·↑↓…' \
  | grep -avE 'tokens' \
  | cksum | awk '{print $1"-"$2}'; }
if [ "${1:-}" = "--fingerprint" ]; then sf_pane_fingerprint "$(cat)"; exit 0; fi
# FIND-032: the past-ceiling continue-vs-kill decision as a PURE, testable predicate. Returns 0 (=let the fixer
# CONTINUE) ONLY when it is still generating AND its fingerprint advanced since the last check; otherwise 1 (=KILL:
# frozen/hung, or not generating = idle/errored). args: <generating 0|1> <cur_fp> <prev_fp>.
sf_should_continue(){ [ "$1" = "1" ] && [ "$2" != "$3" ]; }
if [ "${1:-}" = "--should-continue" ]; then sf_should_continue "${2:-}" "${3:-}" "${4:-}"; exit $?; fi
# FIND-036 (2026-09-29, issue: fixer SUCCESS at 12:29 muted a NEW update-draft bug that surfaced
# at 13:51 for the full 20h SUCCESS backoff): normalize a blocker string by stripping digit runs
# (agent ids, version ids, epoch/UTC timestamps) so two reports of the SAME standing condition
# compare equal while a genuinely DIFFERENT failure compares different. Pure, testable predicate.
sf_normalize_blocker(){ printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -s '[:space:]' ' ' | sed -E 's/[0-9]+/#/g'; }
sf_blocker_changed(){ [ "$(sf_normalize_blocker "$1")" != "$(sf_normalize_blocker "$2")" ]; }
if [ "${1:-}" = "--blocker-changed" ]; then sf_blocker_changed "${2:-}" "${3:-}"; exit $?; fi
# FIND-025: NORMALIZE the loop name to a single canonical form ("<x>-loop") so every call site — healthcheck
# (HC_LOOP=capafy-loop), STARTUP prompts (capafy), verify-loops (capafy) — maps to ONE session name + ONE result
# marker. Without this, "capafy" and "capafy-loop" spawn two mutually-unaware fixers and split the marker the
# anti-fake verifier reads. Idempotent: strip a trailing -loop then re-add it.
LOOP="${1:?loop name}"; LOOP="${LOOP%-loop}-loop"; BLOCKER="${2:?blocker+hint}"
SOCK="/tmp/anicca-selffix-$LOOP-tmux.sock"; SESSION="anicca-selffix-$LOOP"
STATE="$HOME/.local/state/life-manager/state"
LOG="$HOME/.local/state/life-manager/logs/self-fix-$LOOP.log"
RESULT="$STATE/.self-fix-$LOOP.result"       # the fixer writes SUCCESS/FAIL + evidence here (FIND-003)
STARTMARK="$STATE/.self-fix-$LOOP.started"    # epoch when the current fixer was spawned (FIND-005 stale-guard)
BLOCKER_FILE="$STATE/.self-fix-$LOOP.blocker" # FIND-036: blocker text of the run $RESULT concluded for
# FIND-028 test seam: print the normalized identity + derived paths and exit BEFORE any tmux/side-effect.
if [ "${SELF_FIX_DRYRUN:-}" = "1" ]; then printf 'LOOP=%s SESSION=%s SOCK=%s RESULT=%s\n' "$LOOP" "$SESSION" "$SOCK" "$RESULT"; exit 0; fi

# An uncertain provider result is a fence, never a fresh-spawn signal. Preserve the marker and evidence until
# the owning provider path supplies exact official readback.
if [ -f "$RESULT" ] && grep -q '^HELD_EFFECT_UNKNOWN' "$RESULT" 2>/dev/null; then
  echo "self-fix[$LOOP] HELD_EFFECT_UNKNOWN — preserve marker and do not respawn"
  exit 75
fi

# Keep this pure: use the shared admission policy and measurement without invoking disk_headroom_ok(), which
# writes producer receipts. Verify the configured host state root exists first so the shared probe will not
# bootstrap a missing directory around an unavailable gate.
sf_disk_admission_probe() {
  PYTHONDONTWRITEBYTECODE=1 python3 - "$SELF_FIX_RELEASE_ROOT" <<'PY'
import json
import os
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
for name in ("LIFE_MANAGER_IGNORE_DISK_WRITERS_STOP", "LIFE_MANAGER_IGNORE_DISK_PRESSURE_BLOCK"):
    os.environ.pop(name, None)
sys.path.insert(0, str(repo_root))
reason = None
available = None
required = None
host_state_dir = None
try:
    from runtime.host import disk_admission
    host_state = disk_admission._host_state_dir()
    host_state_dir = str(host_state.absolute())
    if not host_state.is_dir() or host_state.is_symlink():
        raise OSError("host state directory unavailable")
    required_bytes = disk_admission.RECOVERY_FLOOR_BYTES
    policy_gate = disk_admission._producer_gate()
    available_bytes = disk_admission.disk_free_bytes(host_state)
except Exception:
    reason = "disk_policy_unavailable"
else:
    if isinstance(required_bytes, int) and not isinstance(required_bytes, bool) and required_bytes > 0:
        required = required_bytes
    if isinstance(available_bytes, int) and not isinstance(available_bytes, bool) and available_bytes >= 0:
        available = available_bytes
    if required is None:
        reason = "disk_policy_unavailable"
    elif policy_gate is not None:
        reason = policy_gate[0]
    elif available is None:
        reason = "disk_headroom_unavailable"
    elif available < required:
        reason = "disk_headroom_low"
result = {"status": "deferred" if reason else "admitted", "available_bytes": available,
          "required_bytes": required, "reason": reason, "host_state_dir": host_state_dir}
print(json.dumps(result, sort_keys=True, separators=(",", ":")))
raise SystemExit(75 if reason else 0)
PY
}

sf_require_disk_admission() {
  local gate_result
  if ! gate_result="$(sf_disk_admission_probe)"; then
    [ -n "$gate_result" ] || gate_result='{"status":"deferred","reason":"disk_policy_unavailable"}'
    echo "self-fix[$LOOP] deferred before heavy work: $gate_result"
    exit 75
  fi
  HOST_STATE_DIR_FOR_CHILD="$(printf '%s' "$gate_result" | python3 -c 'import json,sys; value=json.load(sys.stdin).get("host_state_dir"); print(value if isinstance(value,str) else "")')"
  if [ -z "$HOST_STATE_DIR_FOR_CHILD" ]; then
    echo "self-fix[$LOOP] deferred before heavy work: disk_policy_unavailable (host state path missing)"
    exit 75
  fi
}

sf_require_disk_admission
mkdir -p "$STATE" "$(dirname "$LOG")"
MAX_FIXER_MIN=180                             # FIND-023: a fixer older than 3h is presumed hung → kill+respawn. Set
                                              # ABOVE any legitimate fix duration (a real fix rarely needs >3h) so the
                                              # 6h audit re-invocation cannot kill an in-progress long fix; only a
                                              # genuinely stuck session (>3h) is replaced, still within the 6h window.

# FIND-005: skip only if a RECENT fixer is still running; if it is older than MAX_FIXER_MIN, it is hung → replace it.
if tmux -S "$SOCK" has-session -t "$SESSION" 2>/dev/null; then
  age_min=999; [ -f "$STARTMARK" ] && age_min=$(( ( $(date +%s) - $(cat "$STARTMARK" 2>/dev/null||echo 0) ) / 60 ))
  if [ "$age_min" -lt "$MAX_FIXER_MIN" ]; then
    echo "$(date '+%F %T') self-fix[$LOOP] running (${age_min}min<${MAX_FIXER_MIN}) — skip" >> "$LOG"; echo "self-fix[$LOOP] already running (${age_min}min)"; exit 0
  fi
  # FIND-023/027: past the ceiling, distinguish REAL PROGRESS from a HUNG tool. "esc to interrupt" alone is not enough
  # (a hung curl/waitForSelector shows the same spinner forever), so we compare the pane CONTENT between successive
  # past-ceiling checks: if the pane still shows generation AND its content ADVANCED since the last check → real
  # progress, continue; if it is frozen (unchanged) or not generating at all → genuinely hung/idle → kill+respawn.
  PANEHASH="$STATE/.self-fix-$LOOP.panehash"
  _pane="$(tmux -S "$SOCK" capture-pane -t "$SESSION" -p 2>/dev/null)"
  cur="$(sf_pane_fingerprint "$_pane")"   # FIND-029: volatile timer/token/spinner stripped → frozen pane = same hash
  prev="$(cat "$PANEHASH" 2>/dev/null||echo none)"; printf '%s' "$cur" > "$PANEHASH"
  generating=0; printf '%s' "$_pane" | tail -6 | grep -qE 'esc to interrupt' && generating=1
  if sf_should_continue "$generating" "$cur" "$prev"; then
    echo "$(date '+%F %T') self-fix[$LOOP] ${age_min}min, generating + pane ADVANCED → real progress, continue" >> "$LOG"; echo "self-fix[$LOOP] still progressing (${age_min}min)"; exit 0
  fi
  echo "$(date '+%F %T') self-fix[$LOOP] ${age_min}min, pane frozen/idle (prev=$prev cur=$cur) → hung → kill+respawn" >> "$LOG"; rm -f "$PANEHASH"
  tmux -S "$SOCK" kill-session -t "$SESSION" 2>/dev/null||true; sleep 1
fi

# FIND-035 (A6, 2026-07-18): RESULT-MARKER BACKOFF. The has-session guard above only prevents a
# CONCURRENT second fixer — it does NOT stop the every-6h auditor from re-spawning a FRESH high-value
# agent each cycle when the underlying condition PERSISTS but is NOT a code bug: e.g. published.jsonl
# is legitimately stale >30h because inventory is drained (nothing to publish), or a prior fixer
# already concluded this is a genuine external blocker. Without backoff this burned one Sonnet every
# 6h forever for a non-bug (the "verify-loops-audit reflex-spawns self-fix" landmine, capafy 2026-07).
# If the PRIOR fixer for THIS loop already CONCLUDED (RESULT no longer 'RUNNING') within BACKOFF_MIN,
# skip — the condition was addressed (SUCCESS) or is a known standing blocker (FAIL); retry only after
# the backoff so a real regression is still eventually re-attempted. Test seam: SELF_FIX_BACKOFF_MIN
# (overrides both below when set, for back-compat with any caller pinning a single value).
# #6063 fix: a FAIL used to get the SAME 20h backoff as a SUCCESS, which left a persisting CODE BUG
# unaddressed for up to 20h (measured 2026-09-28 20:56 -> 2026-09-29 12:14) even though a fresh fixer
# armed with skills/self/lib/self_fix_code_path.sh (worktree+PR+merge) is cheap to re-try. A concluded
# SUCCESS still gets the long backoff (the fix landed, no need to re-fire soon); a concluded FAIL gets
# a short one so the next natural trigger can retry the code-path fix.
SUCCESS_BACKOFF_MIN="${SELF_FIX_BACKOFF_MIN:-${SELF_FIX_SUCCESS_BACKOFF_MIN:-1200}}"   # 20h
FAIL_BACKOFF_MIN="${SELF_FIX_BACKOFF_MIN:-${SELF_FIX_FAIL_BACKOFF_MIN:-60}}"           # 1h
if ! tmux -S "$SOCK" has-session -t "$SESSION" 2>/dev/null && [ -f "$RESULT" ] && ! grep -q '^RUNNING' "$RESULT" 2>/dev/null; then
  res_age_min=$(( ( $(date +%s) - $(stat -f %m "$RESULT" 2>/dev/null||echo 0) ) / 60 ))
  IS_FAIL=0
  BACKOFF_MIN="$SUCCESS_BACKOFF_MIN"
  head -c 7 "$RESULT" 2>/dev/null | grep -q '^FAIL' && { BACKOFF_MIN="$FAIL_BACKOFF_MIN"; IS_FAIL=1; }
  # FIND-036 (2026-09-29): a concluded SUCCESS's 20h backoff exists to stop re-firing for the
  # SAME resolved condition — it must not also mute a genuinely NEW, different blocker that
  # shows up inside that window (measured: fixer SUCCESS at 12:29, a new update-draft bug at
  # 13:51 sat unhandled until the backoff expired ~08:29 the next day). A FAIL's blocker is
  # still standing (its own short backoff already covers re-try), so only SUCCESS gets the
  # differs-from-what-succeeded check; the per-day dispatch cap in self_fix_code_path.sh is
  # unaffected by this and still bounds actual code-path re-attempts.
  if [ "$IS_FAIL" = 0 ] && [ -f "$BLOCKER_FILE" ] && sf_blocker_changed "$(cat "$BLOCKER_FILE")" "$BLOCKER"; then
    echo "$(date '+%F %T') self-fix[$LOOP] prior SUCCESS backoff active but blocker differs (normalized) from the one that succeeded → not backing off [$(head -c 70 "$RESULT" | tr -d '\n')]" >> "$LOG"
  elif [ "$res_age_min" -ge 0 ] && [ "$res_age_min" -lt "$BACKOFF_MIN" ]; then
    echo "$(date '+%F %T') self-fix[$LOOP] prior fixer concluded ${res_age_min}min ago (<${BACKOFF_MIN} backoff) → skip re-spawn [$(head -c 70 "$RESULT" | tr -d '\n')]" >> "$LOG"
    echo "self-fix[$LOOP] backoff — prior result ${res_age_min}min ago (<${BACKOFF_MIN}min)"; exit 0
  fi
fi

# The browser is shared with the other money loops: heal it, restore the logins, collect stray tabs.
(
  unset LIFE_MANAGER_IGNORE_DISK_WRITERS_STOP LIFE_MANAGER_IGNORE_DISK_PRESSURE_BLOCK LIFE_MANAGER_DISK_HEADROOM_KIB
  bash "$LIFE_MANAGER_REPO/skills/browser/ensure_browser.sh"
) || echo "WARN: browser not recovered"

# FIND-033 (life-manager-loop 3-day outage, 2026-07-10): a near-full disk stops swap from growing, which
# surfaces as fork() failures for every fresh spawn — including this fixer's own tmux/claude spawn below.
# Without this, self-fix keeps respawning fixers that die before they can even diagnose anything (observed:
# 40+ spawns over 24h, none completed). Reclaim only 100%-regenerable package-manager caches; see
# hc_reclaim_disk_if_low in healthcheck-lib.sh for the full rationale and the excluded (approval-needed) paths.
# shellcheck source=healthcheck-lib.sh
. "$LIFE_MANAGER_REPO/skills/self/healthcheck-lib.sh" 2>/dev/null && hc_reclaim_disk_if_low

# Browser/cache setup can consume disk after the first gate; remeasure before marker, temp, or agent writes.
sf_require_disk_admission

# FIND-003/004: the fixer MUST verify a real side-effect, commit in the CORRECT repo (the one the edited file lives
# in — discovered via git rev-parse, NOT guessed), and write a result marker the caller/healthcheck can check.
printf '%s' "$BLOCKER" > "$BLOCKER_FILE"   # FIND-036: record what THIS spawn is fixing, for the next backoff check
printf 'RUNNING %s\n' "$(date -u +%FT%TZ)" > "$RESULT"
TASK="AUTONOMOUS SELF-FIX for the ${LOOP} loop. You are a high-value autonomous dev with browser (CloakBrowser daily-driver CDP :9222), Bash, Edit. NEVER ask a human and NEVER present a menu — a blocker is not stop. BLOCKER + HINT: ${BLOCKER}.
DO, in order:
(0) CHECK FOR PRIOR DIAGNOSIS FIRST (2026-07-13 fix — a prior self-fix spawn burned 400-1400min re-discovering an already-known external blocker from scratch): before any expensive live reproduction, search for an existing diagnosis of THIS exact blocker — tail the loop's own lessons/audit files under its state dir (e.g. ~/gig/lessons.jsonl, ~/gig/audit.jsonl) for recent matching entries, and run 'gh issue list -R Daisuke134/anicca --label gig-lesson --search \"<keyword from the blocker>\"' to find prior write-ups. If a recent (last ~24h) prior diagnosis already concluded this is a genuine external/physical blocker (e.g. a real-world device state, a third-party account lock needing a human's physical action, an outage) — do ONE cheap, fast confirmation that the same condition still holds (a single live check, not a repeat of the full multi-hour investigation), then write FAIL citing the existing issue/lesson instead of re-running the whole diagnosis. Only do a full fresh investigation when no matching prior diagnosis exists or the prior one looks stale/resolved.
(1) Reproduce the failure yourself and find the ROOT cause (read the actual code + run it + watch where it breaks).
(1b) IF the root cause is a CODE BUG in \$LIFE_MANAGER_REPO under skills/capafy-autopublish/**, skills/capafy/**, or skills/self/capafy-loop/** (the Capafy publish pipeline — the immutable ~/loops/releases tree and non-worktree ~/.local/state CANNOT be edited in place, issue #6063), use the dedicated code-path helper instead of hand-editing in place: 'bash \$LIFE_MANAGER_REPO/skills/self/lib/self_fix_code_path.sh run capafy-loop \"<blocker>\"' to get a fresh worktree (its own \`/private/tmp/selffix-capafy-loop-<ts>\` checkout on branch \`self-fix/capafy-loop/<ts>\` from current origin/main — it prints WORKTREE=... BRANCH=...). Make your fix ONLY inside that worktree and ONLY inside the three allowlisted paths above. Then, still inside that worktree: run \`/opt/homebrew/bin/python3 -m pytest skills/capafy-autopublish/test skills/self/tests skills/self/__tests__ -q\` and confirm you introduce NO NEW failing test id versus the same suite on origin/main (a handful of pre-existing failures on main is expected — only a NEW one blocks you); run \`bash \$LIFE_MANAGER_REPO/skills/self/lib/self_fix_code_path.sh scope-check <worktree> origin/main '^skills/capafy-autopublish/|^skills/capafy/|^skills/self/capafy-loop/'\` and require it to print OK before committing. Only once both pass: commit, \`git push -u origin <branch>\`, \`gh pr create --repo Daisuke134/life-manager\`, then \`gh pr merge <PR> --repo Daisuke134/life-manager --squash --admin\`. After merge, cut a release with \`bash \$LIFE_MANAGER_REPO/bin/cut-loop-release.sh\` (it self-serializes against any concurrent cut via its own PID-owned lock — never pgrep/kill another release process). Record PR number, merge sha and release sha in your RESULT line (step 5) and remove the worktree (\`git -C \$LIFE_MANAGER_REPO worktree remove <worktree>\`) when done. NEVER force-push, NEVER touch a file outside the allowlist, NEVER touch another loop's worktree/branch.
(2) Fix the code. If the root cause is a brittle DOM-coordinate/selector script that broke on a UI change, do NOT just re-tune coordinates: rebuild the failing step as two-layer agentic (a thin script opens the page, then YOU look at real screenshots and decide each click/type, looping until the real success signal appears).
(3) VERIFY with a REAL side-effect — an actually-published skill URL you then curl and see live / a real posted comment URL / the tool actually succeeding once end-to-end. A patch that only compiles is NOT done. No dry runs, no fake success, no 'should work'.
(4) COMMIT IN THE CORRECT REPO: for EACH file you changed, cd into its directory, run 'git rev-parse --show-toplevel' and 'git remote -v' to confirm which repo it is, then commit+push THERE. Ground truth: the Capafy publish pipeline lives under $HOME/.local/state/life-manager (remote = anicca-dais, PRIVATE) — commit those there, NOT to anicca-products. The loop harness lives under $LIFE_MANAGER_REPO (remote = anicca, public). Never commit $HOME/.local/state/life-manager runtime state or secrets.
(5) Write the outcome to ${RESULT} as a single line: 'SUCCESS <utc> <one-line real evidence, e.g. published URL>' or 'FAIL <utc> <why + what is still blocked>'. If the fix resolved a selfheal-request json, rm it.
If after honest effort the fix is genuinely impossible (e.g. an external service is down), write FAIL with a precise diagnosis to ${RESULT} and invoke self/issue-dev — still never ask a human. Report what you fixed + the real evidence at the end."
TASK="${TASK} 重要な結果（数字・IDを含む成果、realized P&L、致命的エラー）が出たら PushNotification ツールで Dais へ verbatim 送信してから終了する。narration・定常報告には使わない。"
EVIDENCE_ROOT="$STATE/agent-runner-evidence/self-fix-$LOOP"
mkdir -p "$EVIDENCE_ROOT"
EVIDENCE_DIR="$(mktemp -d "$EVIDENCE_ROOT/$(date +%s)-$$.XXXXXX")" || exit 2
mkdir -p "$EVIDENCE_DIR/tmp" "$EVIDENCE_DIR/npm-cache" "$EVIDENCE_DIR/node-compile-cache" || exit 2
chmod 700 "$EVIDENCE_DIR" "$EVIDENCE_DIR/tmp" "$EVIDENCE_DIR/npm-cache" "$EVIDENCE_DIR/node-compile-cache" || exit 2
export TMPDIR="$EVIDENCE_DIR/tmp"
export NPM_CONFIG_CACHE="$EVIDENCE_DIR/npm-cache"
export NODE_COMPILE_CACHE="$EVIDENCE_DIR/node-compile-cache"
PROMPT_FILE="$(mktemp "$TMPDIR/self-fix-$LOOP.prompt.XXXXXX")" || exit 2
printf '%s\n' "$TASK" > "$PROMPT_FILE"

# Keep the historical detached tmux lifecycle, but delegate provider/model selection to the
# shared task-class runner. Shell-escape every interpolated value before tmux evaluates the command.
printf -v RUN_AGENT_Q '%q' "$RUN_AGENT"
printf -v EVIDENCE_DIR_Q '%q' "$EVIDENCE_DIR"
printf -v TMPDIR_Q '%q' "$TMPDIR"
printf -v NPM_CONFIG_CACHE_Q '%q' "$NPM_CONFIG_CACHE"
printf -v NODE_COMPILE_CACHE_Q '%q' "$NODE_COMPILE_CACHE"
printf -v TASK_LABEL_Q '%q' "self-fix-$LOOP"
printf -v LOOP_Q '%q' "$LOOP"
printf -v ESCALATION_REASON_Q '%q' "SelfFix code repair"
printf -v PROMPT_FILE_Q '%q' "$PROMPT_FILE"
printf -v LOG_Q '%q' "$LOG"
printf -v HOST_STATE_DIR_Q '%q' "$HOST_STATE_DIR_FOR_CHILD"
tmux -S "$SOCK" new-session -d -s "$SESSION" \
  "unset LIFE_MANAGER_IGNORE_DISK_WRITERS_STOP LIFE_MANAGER_IGNORE_DISK_PRESSURE_BLOCK LIFE_MANAGER_DISK_HEADROOM_KIB; exec /usr/bin/env LIFE_MANAGER_HOST_STATE_DIR=$HOST_STATE_DIR_Q TMPDIR=$TMPDIR_Q NPM_CONFIG_CACHE=$NPM_CONFIG_CACHE_Q NODE_COMPILE_CACHE=$NODE_COMPILE_CACHE_Q /bin/bash $RUN_AGENT_Q --task-class self-fix-code-agent --escalation-reason $ESCALATION_REASON_Q --evidence-dir $EVIDENCE_DIR_Q --task-label $TASK_LABEL_Q --loop $LOOP_Q < $PROMPT_FILE_Q >> $LOG_Q 2>&1"
date +%s > "$STARTMARK"
echo "$(date '+%F %T') self-fix[$LOOP] SPAWNED (self-fix-code-agent): ${BLOCKER:0:90}" >> "$LOG"
echo "self-fix[$LOOP] spawned (self-fix-code-agent, detached). result→$RESULT log→$LOG evidence→$EVIDENCE_DIR"
