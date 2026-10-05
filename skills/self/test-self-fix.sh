#!/usr/bin/env bash
# test-self-fix.sh — FIND-028/030/031: cover the mechanisms re-patched in rounds 4-6.
# (A) FIND-025 loop-name normalization  (B) FIND-029/030 hang fingerprint  (C) FIND-026/031 real lock acquire/steal.
set -uo pipefail; P=0; F=0; H="$(cd "$(dirname "${BASH_SOURCE[0]}")"&&pwd)"; SF="$H/self-fix.sh"
a(){ echo "$2"|grep -qF "$3"&&{ echo "  ok $1"; P=$((P+1)); }||{ echo "  FAIL $1 want:[$3] got:[$2]"; F=$((F+1)); }; }
eq(){ [ "$2" = "$3" ]&&{ echo "  ok $1"; P=$((P+1)); }||{ echo "  FAIL $1 ($2 vs $3)"; F=$((F+1)); }; }
ne(){ [ "$2" != "$3" ]&&{ echo "  ok $1"; P=$((P+1)); }||{ echo "  FAIL $1 (both $2)"; F=$((F+1)); }; }

echo "(A) loop-name normalization"
WIRING="$(AGENT_WIRING_PROBE_ONLY=1 /bin/bash "$SF" 2>&1)"
a "SelfFix wiring probe reports its dedicated code task class" "$WIRING" '"task_class":"self-fix-code-agent"'
S="$(SELF_FIX_DRYRUN=1 bash "$SF" capafy hint 2>&1)"; L="$(SELF_FIX_DRYRUN=1 bash "$SF" capafy-loop hint 2>&1)"
a "short 'capafy' → LOOP=capafy-loop" "$S" 'LOOP=capafy-loop'
a "short → RESULT .self-fix-capafy-loop.result" "$S" '.self-fix-capafy-loop.result'
eq "short==long identical" "$S" "$L"
a "life-manager → life-manager-loop" "$(SELF_FIX_DRYRUN=1 bash "$SF" life-manager h 2>&1)" 'LOOP=life-manager-loop'

echo "(B) FIND-029/030 hang fingerprint — frozen pane (only timer/tokens advance) = SAME hash; real progress = DIFF"
BODY='⏺ Running browser step
  ⎿  page.waitForSelector(".save-btn")'
F1="$(printf '%s\n✢ Deploying… (3m 12s · ↓ 19.4k tokens · esc to interrupt)' "$BODY" | bash "$SF" --fingerprint)"
F2="$(printf '%s\n✢ Deploying… (58m 40s · ↓ 77.8k tokens · esc to interrupt)' "$BODY" | bash "$SF" --fingerprint)"
eq "frozen body, only timer/tokens changed → SAME fingerprint (hang detectable)" "$F1" "$F2"
F3="$(printf '⏺ NEW: found the bug, editing publish_finish.sh now\n✢ Deploying… (59m · esc to interrupt)' | bash "$SF" --fingerprint)"
ne "real new text → DIFFERENT fingerprint (progress)" "$F1" "$F3"

echo "(D) FIND-032 past-ceiling continue-vs-kill decision (sf_should_continue)"
dec(){ bash "$SF" --should-continue "$1" "$2" "$3" >/dev/null 2>&1 && echo CONTINUE || echo KILL; }
a "generating + fingerprint advanced → CONTINUE" "$(dec 1 hashA hashB)" 'CONTINUE'
a "generating + fingerprint FROZEN → KILL (hung)" "$(dec 1 hashA hashA)" 'KILL'
a "not generating (idle/errored) → KILL" "$(dec 0 hashA hashB)" 'KILL'
a "first check (prev=none) generating → CONTINUE" "$(dec 1 hashA none)" 'CONTINUE'

echo "(E) FIND-036 blocker-changed (SUCCESS backoff must not mute a genuinely new blocker)"
bchg(){ bash "$SF" --blocker-changed "$1" "$2" >/dev/null 2>&1 && echo CHANGED || echo SAME; }
a "same blocker, same ids → SAME (stay backed off)" \
  "$(bchg "agent 8123079349 draft v1.0.4 same-Agent update stuck" "agent 8123079349 draft v1.0.4 same-Agent update stuck")" 'SAME'
a "same blocker CLASS, different ids/timestamp → SAME (normalized)" \
  "$(bchg "agent 8123079349 draft v1.0.4 stuck at 2026-09-29T12:29:00Z" "agent 2844813315 draft v1.0.2 stuck at 2026-09-29T13:51:00Z")" 'SAME'
a "genuinely different failure text → CHANGED (bypass SUCCESS backoff)" \
  "$(bchg "publisher lock: same-Agent source version changed for 8123079349" "key-health gate FAIL: OpenRouter balance under \$20")" 'CHANGED'

echo "(F) detached SelfFix runtime must own its cache environment"
D_RUNTIME="$(mktemp -d)"
TEST_REPO="$D_RUNTIME/repo"; TEST_HOME="$D_RUNTIME/home"
mkdir -p "$TEST_REPO/skills/browser" "$TEST_REPO/skills/self" "$TEST_REPO/skills/earn/marketing-engine" "$TEST_HOME"
cat > "$TEST_REPO/skills/browser/ensure_browser.sh" <<'SH'
exit 0
SH
cat > "$TEST_REPO/skills/self/healthcheck-lib.sh" <<'SH'
hc_reclaim_disk_if_low(){ return 0; }
SH
cat > "$TEST_REPO/skills/earn/marketing-engine/run_agent.sh" <<'SH'
#!/bin/bash
set -euo pipefail
evidence=""
task_class=""
escalation_reason=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --evidence-dir) evidence="$2"; shift 2 ;;
    --task-class) task_class="$2"; shift 2 ;;
    --escalation-reason) escalation_reason="$2"; shift 2 ;;
    *) shift ;;
  esac
done
exists=0; [ -d "$evidence" ] && exists=1
{
  printf 'EVIDENCE_EXISTS_AT_START=%s\n' "$exists"
  printf 'EVIDENCE_DIR=%s\n' "$evidence"
  printf 'TASK_CLASS=%s\n' "$task_class"
  printf 'ESCALATION_REASON=%s\n' "$escalation_reason"
  printf 'TMPDIR=%s\n' "${TMPDIR:-}"
  printf 'NPM_CONFIG_CACHE=%s\n' "${NPM_CONFIG_CACHE:-}"
  printf 'NODE_COMPILE_CACHE=%s\n' "${NODE_COMPILE_CACHE:-}"
  for name in tmp npm-cache node-compile-cache; do
    path="$evidence/$name"
    if [ -d "$path" ]; then
      printf '%s_MODE=%s\n' "$name" "$(stat -f '%Lp' "$path")"
    else
      printf '%s_MODE=missing\n' "$name"
    fi
  done
} > "$HOME/observed-runtime.env"
SH
chmod +x "$TEST_REPO/skills/earn/marketing-engine/run_agent.sh"
LOOP_INPUT="owned-runtime-test-$(basename "$D_RUNTIME")"
LOOP_CANONICAL="${LOOP_INPUT}-loop"
SOCK="/tmp/anicca-selffix-$LOOP_CANONICAL-tmux.sock"
mkdir -p "$D_RUNTIME/server-tmp" "$D_RUNTIME/server-npm" "$D_RUNTIME/server-node" \
  "$D_RUNTIME/audit-tmp" "$D_RUNTIME/audit-npm" "$D_RUNTIME/audit-node"
env -i HOME="$TEST_HOME" PATH="$PATH" TERM=xterm TMPDIR="$D_RUNTIME/server-tmp" \
  NPM_CONFIG_CACHE="$D_RUNTIME/server-npm" NODE_COMPILE_CACHE="$D_RUNTIME/server-node" \
  tmux -S "$SOCK" new-session -d -s owned-runtime-keepalive 'sleep 60'
(
  unset SELF_FIX_DRYRUN AGENT_WIRING_PROBE_ONLY
  export HOME="$TEST_HOME" LIFE_MANAGER_REPO="$TEST_REPO"
  export TMPDIR="$D_RUNTIME/audit-tmp" NPM_CONFIG_CACHE="$D_RUNTIME/audit-npm"
  export NODE_COMPILE_CACHE="$D_RUNTIME/audit-node"
  /bin/bash "$SF" "$LOOP_INPUT" 'fixture-only blocker'
)
WAIT_RUNTIME=0
while [ "$WAIT_RUNTIME" -lt 100 ] && [ ! -f "$TEST_HOME/observed-runtime.env" ]; do
  sleep 0.05
  WAIT_RUNTIME=$((WAIT_RUNTIME+1))
done
if [ -f "$TEST_HOME/observed-runtime.env" ]; then
  OBSERVED_RUNTIME="$(cat "$TEST_HOME/observed-runtime.env")"
  EVIDENCE_DIR="$(printf '%s\n' "$OBSERVED_RUNTIME" | sed -n 's/^EVIDENCE_DIR=//p')"
  a "evidence namespace exists before detached runner" "$OBSERVED_RUNTIME" 'EVIDENCE_EXISTS_AT_START=1'
  eq "detached TMPDIR is evidence-owned" "$(printf '%s\n' "$OBSERVED_RUNTIME" | sed -n 's/^TMPDIR=//p')" "$EVIDENCE_DIR/tmp"
  eq "detached npm cache is evidence-owned" "$(printf '%s\n' "$OBSERVED_RUNTIME" | sed -n 's/^NPM_CONFIG_CACHE=//p')" "$EVIDENCE_DIR/npm-cache"
  eq "detached node compile cache is evidence-owned" "$(printf '%s\n' "$OBSERVED_RUNTIME" | sed -n 's/^NODE_COMPILE_CACHE=//p')" "$EVIDENCE_DIR/node-compile-cache"
  ne "audit TMPDIR is not inherited" "$(printf '%s\n' "$OBSERVED_RUNTIME" | sed -n 's/^TMPDIR=//p')" "$D_RUNTIME/audit-tmp"
  ne "existing tmux server TMPDIR is not inherited" "$(printf '%s\n' "$OBSERVED_RUNTIME" | sed -n 's/^TMPDIR=//p')" "$D_RUNTIME/server-tmp"
  a "evidence tmp uses mode 700" "$OBSERVED_RUNTIME" 'tmp_MODE=700'
  a "npm cache uses mode 700" "$OBSERVED_RUNTIME" 'npm-cache_MODE=700'
  a "node compile cache uses mode 700" "$OBSERVED_RUNTIME" 'node-compile-cache_MODE=700'
  eq "evidence root uses mode 700" "$(stat -f '%Lp' "$EVIDENCE_DIR")" '700'
  PROMPT_FILE="$(find "$EVIDENCE_DIR/tmp" -maxdepth 1 -type f -name "self-fix-$LOOP_CANONICAL.prompt.*" -print -quit 2>/dev/null)"
  a "self-fix prompt mktemp is inside owned TMPDIR" "$PROMPT_FILE" "$EVIDENCE_DIR/tmp/"
  eq "detached SelfFix class is dedicated to code repair" "$(printf '%s\n' "$OBSERVED_RUNTIME" | sed -n 's/^TASK_CLASS=//p')" 'self-fix-code-agent'
  eq "detached SelfFix carries its bounded escalation reason" "$(printf '%s\n' "$OBSERVED_RUNTIME" | sed -n 's/^ESCALATION_REASON=//p')" 'SelfFix code repair'
else
  echo "  FAIL detached fake runner did not write its fixture readback"
  F=$((F+1))
fi
tmux -S "$SOCK" kill-server >/dev/null 2>&1 || true
rm -rf "$D_RUNTIME"

echo "(C) FIND-026/031 real lock acquire/steal via hc_acquire_lock"
source "$H/healthcheck-lib.sh"; now=$(date +%s)
D="$(mktemp -d)"; LK="$D/.lk"
hc_acquire_lock "$LK" "$now" && { echo "  ok acquire when no lock"; P=$((P+1)); } || { echo "  FAIL acquire when free"; F=$((F+1)); }
# now a FRESH lock exists (just made) → a second acquire must REFUSE
hc_acquire_lock "$LK" "$now" && { echo "  FAIL acquired a fresh held lock"; F=$((F+1)); } || { echo "  ok refuse fresh held lock"; P=$((P+1)); }
# simulate a hard-killed run: NON-EMPTY stale lock (owner file, old mtime) → must be STOLEN (FIND-026)
rm -rf "$LK"; mkdir "$LK"; echo 88 > "$LK/owner"; touch -t 202607010000 "$LK"
hc_acquire_lock "$LK" "$now" && { echo "  ok steal NON-EMPTY stale lock (rm -rf recovery)"; P=$((P+1)); } || { echo "  FAIL could not steal non-empty stale lock"; F=$((F+1)); }
rm -rf "$D"

echo "=== self-fix: $P passed $F failed ==="; [ "$F" = 0 ]&&echo GREEN||exit 1
