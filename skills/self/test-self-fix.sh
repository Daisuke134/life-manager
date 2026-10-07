#!/usr/bin/env bash
# test-self-fix.sh — FIND-028/030/031: cover the mechanisms re-patched in rounds 4-6.
# (A) FIND-025 loop-name normalization  (B) FIND-029/030 hang fingerprint  (C) FIND-026/031 real lock acquire/steal.
set -uo pipefail; P=0; F=0; H="$(cd "$(dirname "${BASH_SOURCE[0]}")"&&pwd)"; SF="$H/self-fix.sh"
a(){ echo "$2"|grep -qF "$3"&&{ echo "  ok $1"; P=$((P+1)); }||{ echo "  FAIL $1 want:[$3] got:[$2]"; F=$((F+1)); }; }
eq(){ [ "$2" = "$3" ]&&{ echo "  ok $1"; P=$((P+1)); }||{ echo "  FAIL $1 ($2 vs $3)"; F=$((F+1)); }; }
ne(){ [ "$2" != "$3" ]&&{ echo "  ok $1"; P=$((P+1)); }||{ echo "  FAIL $1 (both $2)"; F=$((F+1)); }; }

echo "(A) loop-name normalization"
PURE_RUNTIME="$(mktemp -d)"
PURE_REPO="$PURE_RUNTIME/repo"; PURE_HOME="$PURE_RUNTIME/home"
mkdir -p "$PURE_REPO/skills/browser" "$PURE_HOME"
cat > "$PURE_REPO/skills/browser/ensure_browser.sh" <<'SH'
printf 'called\n' >> "$HOME/ensure-browser.calls"
SH
WIRING="$(env HOME="$PURE_HOME" LIFE_MANAGER_REPO="$PURE_REPO" AGENT_WIRING_PROBE_ONLY=1 /bin/bash "$SF" 2>&1)"
a "SelfFix wiring probe reports its dedicated code task class" "$WIRING" '"task_class":"self-fix-code-agent"'
S="$(env HOME="$PURE_HOME" LIFE_MANAGER_REPO="$PURE_REPO" SELF_FIX_DRYRUN=1 bash "$SF" capafy hint 2>&1)"
L="$(env HOME="$PURE_HOME" LIFE_MANAGER_REPO="$PURE_REPO" SELF_FIX_DRYRUN=1 bash "$SF" capafy-loop hint 2>&1)"
a "short 'capafy' → LOOP=capafy-loop" "$S" 'LOOP=capafy-loop'
a "short → RESULT .self-fix-capafy-loop.result" "$S" '.self-fix-capafy-loop.result'
eq "short==long identical" "$S" "$L"
a "life-manager → life-manager-loop" "$(env HOME="$PURE_HOME" LIFE_MANAGER_REPO="$PURE_REPO" SELF_FIX_DRYRUN=1 bash "$SF" life-manager h 2>&1)" 'LOOP=life-manager-loop'
eq "dryrun creates no state root" "$([ -e "$PURE_HOME/.local/state" ] && echo present || echo absent)" 'absent'
eq "wiring/dryrun do not ensure browser" "$([ -e "$PURE_HOME/ensure-browser.calls" ] && echo called || echo absent)" 'absent'

echo "(B) FIND-029/030 hang fingerprint — frozen pane (only timer/tokens advance) = SAME hash; real progress = DIFF"
BODY='⏺ Running browser step
  ⎿  page.waitForSelector(".save-btn")'
F1="$(printf '%s\n✢ Deploying… (3m 12s · ↓ 19.4k tokens · esc to interrupt)' "$BODY" | env HOME="$PURE_HOME" LIFE_MANAGER_REPO="$PURE_REPO" bash "$SF" --fingerprint)"
F2="$(printf '%s\n✢ Deploying… (58m 40s · ↓ 77.8k tokens · esc to interrupt)' "$BODY" | env HOME="$PURE_HOME" LIFE_MANAGER_REPO="$PURE_REPO" bash "$SF" --fingerprint)"
eq "frozen body, only timer/tokens changed → SAME fingerprint (hang detectable)" "$F1" "$F2"
F3="$(printf '⏺ NEW: found the bug, editing publish_finish.sh now\n✢ Deploying… (59m · esc to interrupt)' | env HOME="$PURE_HOME" LIFE_MANAGER_REPO="$PURE_REPO" bash "$SF" --fingerprint)"
ne "real new text → DIFFERENT fingerprint (progress)" "$F1" "$F3"

echo "(D) FIND-032 past-ceiling continue-vs-kill decision (sf_should_continue)"
dec(){ env HOME="$PURE_HOME" LIFE_MANAGER_REPO="$PURE_REPO" bash "$SF" --should-continue "$1" "$2" "$3" >/dev/null 2>&1 && echo CONTINUE || echo KILL; }
a "generating + fingerprint advanced → CONTINUE" "$(dec 1 hashA hashB)" 'CONTINUE'
a "generating + fingerprint FROZEN → KILL (hung)" "$(dec 1 hashA hashA)" 'KILL'
a "not generating (idle/errored) → KILL" "$(dec 0 hashA hashB)" 'KILL'
a "first check (prev=none) generating → CONTINUE" "$(dec 1 hashA none)" 'CONTINUE'

echo "(E) FIND-036 blocker-changed (SUCCESS backoff must not mute a genuinely new blocker)"
bchg(){ env HOME="$PURE_HOME" LIFE_MANAGER_REPO="$PURE_REPO" bash "$SF" --blocker-changed "$1" "$2" >/dev/null 2>&1 && echo CHANGED || echo SAME; }
a "same blocker, same ids → SAME (stay backed off)" \
  "$(bchg "agent 8123079349 draft v1.0.4 same-Agent update stuck" "agent 8123079349 draft v1.0.4 same-Agent update stuck")" 'SAME'
a "same blocker CLASS, different ids/timestamp → SAME (normalized)" \
  "$(bchg "agent 8123079349 draft v1.0.4 stuck at 2026-09-29T12:29:00Z" "agent 2844813315 draft v1.0.2 stuck at 2026-09-29T13:51:00Z")" 'SAME'
a "genuinely different failure text → CHANGED (bypass SUCCESS backoff)" \
  "$(bchg "publisher lock: same-Agent source version changed for 8123079349" "key-health gate FAIL: OpenRouter balance under \$20")" 'CHANGED'
eq "all pure probes create no state root" "$([ -e "$PURE_HOME/.local/state" ] && echo present || echo absent)" 'absent'
eq "all pure probes leave browser untouched" "$([ -e "$PURE_HOME/ensure-browser.calls" ] && echo called || echo absent)" 'absent'
rm -rf "$PURE_RUNTIME"

echo "(F) detached SelfFix runtime must own its cache environment"
D_RUNTIME="$(mktemp -d)"
TEST_REPO="$D_RUNTIME/repo"; TEST_HOME="$D_RUNTIME/home"
mkdir -p "$TEST_REPO/skills/browser" "$TEST_REPO/skills/self" \
  "$TEST_REPO/skills/earn/marketing-engine" "$TEST_REPO/runtime/host" "$TEST_HOME"
cat > "$TEST_REPO/skills/browser/ensure_browser.sh" <<'SH'
printf 'called\n' >> "$HOME/ensure-browser.calls"
{
  printf 'IGNORE_DISK_WRITERS_STOP=%s\n' "${LIFE_MANAGER_IGNORE_DISK_WRITERS_STOP:-unset}"
  printf 'IGNORE_DISK_PRESSURE_BLOCK=%s\n' "${LIFE_MANAGER_IGNORE_DISK_PRESSURE_BLOCK:-unset}"
  printf 'DISK_HEADROOM_KIB=%s\n' "${LIFE_MANAGER_DISK_HEADROOM_KIB:-unset}"
} > "$HOME/ensure-browser.env"
if [ "${SELF_FIX_TEST_DROP_AFTER_BROWSER:-0}" = "1" ]; then
  printf '%s\n' "${SELF_FIX_TEST_DROP_BYTES:-unknown}" > "$HOME/.self-fix-test-free-bytes"
fi
SH
cat > "$TEST_REPO/skills/self/healthcheck-lib.sh" <<'SH'
hc_reclaim_disk_if_low(){ return 0; }
SH
cat > "$TEST_REPO/runtime/host/disk_admission.py" <<'PY'
import os
import stat
from pathlib import Path

RECOVERY_FLOOR_BYTES = 2 * 1024**3
_POLICY_FLAGS = (
    ("disk-writers.stop", "disk_writers_stop"),
    ("disk-pressure.block", "disk_pressure_block"),
)

def _host_state_dir():
    configured = os.environ.get("LIFE_MANAGER_HOST_STATE_DIR")
    return Path(configured) if configured else Path.home() / ".local/state/life-manager/state"

def _producer_gate():
    ignored = {
        "disk-writers.stop": os.environ.get("LIFE_MANAGER_IGNORE_DISK_WRITERS_STOP") in {"1", "true", "yes"},
        "disk-pressure.block": os.environ.get("LIFE_MANAGER_IGNORE_DISK_PRESSURE_BLOCK") in {"1", "true", "yes"},
    }
    host_state = _host_state_dir()
    for filename, reason in _POLICY_FLAGS:
        if ignored[filename]:
            continue
        try:
            info = (host_state / filename).lstat()
        except FileNotFoundError:
            continue
        except OSError:
            return "disk_policy_unavailable", host_state / filename
        if not stat.S_ISREG(info.st_mode):
            return "disk_policy_unavailable", host_state / filename
        return reason, host_state / filename
    return None

def disk_free_bytes(_path):
    try:
        value = (Path.home() / ".self-fix-test-free-bytes").read_text().strip()
    except OSError:
        return None
    if value == "unknown":
        return None
    try:
        return int(value)
    except ValueError:
        return None
PY
SF_FAKE="$TEST_REPO/skills/self/self-fix.sh"
cp "$SF" "$SF_FAKE"
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
  printf 'IGNORE_DISK_WRITERS_STOP=%s\n' "${LIFE_MANAGER_IGNORE_DISK_WRITERS_STOP:-unset}"
  printf 'IGNORE_DISK_PRESSURE_BLOCK=%s\n' "${LIFE_MANAGER_IGNORE_DISK_PRESSURE_BLOCK:-unset}"
  printf 'DISK_HEADROOM_KIB=%s\n' "${LIFE_MANAGER_DISK_HEADROOM_KIB:-unset}"
  printf 'HOST_STATE_DIR=%s\n' "${LIFE_MANAGER_HOST_STATE_DIR:-unset}"
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
prepare_self_fix_home(){
  local home="$1" free="$2"
  mkdir -p "$home/.local/state/life-manager/state"
  printf '%s\n' "$free" > "$home/.self-fix-test-free-bytes"
}
run_fake_self_fix(){
  local home="$1" loop="$2"; shift 2
  env HOME="$home" LIFE_MANAGER_REPO="$TEST_REPO" \
    LIFE_MANAGER_HOST_STATE_DIR="$home/.local/state/life-manager/state" SELF_FIX_DRYRUN= \
    AGENT_WIRING_PROBE_ONLY= "$@" /bin/bash "$SF_FAKE" "$loop" 'fixture-only blocker'
}
assert_no_self_fix_markers(){
  local home="$1" loop="$2" canonical="$2"
  canonical="${canonical%-loop}-loop"
  local state="$home/.local/state/life-manager/state"
  eq "$loop has no result marker" "$([ -e "$state/.self-fix-$canonical.result" ] && echo present || echo absent)" absent
  eq "$loop has no start marker" "$([ -e "$state/.self-fix-$canonical.started" ] && echo present || echo absent)" absent
  eq "$loop has no blocker marker" "$([ -e "$state/.self-fix-$canonical.blocker" ] && echo present || echo absent)" absent
  eq "$loop has no evidence temp root" "$([ -e "$state/agent-runner-evidence/self-fix-$canonical" ] && echo present || echo absent)" absent
  eq "$loop has no log" "$([ -e "$home/.local/state/life-manager/logs/self-fix-$canonical.log" ] && echo present || echo absent)" absent
  eq "$loop has no runner readback" "$([ -e "$home/observed-runtime.env" ] && echo present || echo absent)" absent
  tmux -S "/tmp/anicca-selffix-$canonical-tmux.sock" kill-server >/dev/null 2>&1 || true
}
assert_no_self_fix_attempt(){
  local home="$1" loop="$2"
  eq "$loop has no browser ensure" "$([ -f "$home/ensure-browser.calls" ] && echo called || echo absent)" absent
  assert_no_self_fix_markers "$home" "$loop"
}

echo "(G) finite SelfFix admission rejects low/unknown/host flags before effects"
GATE_FLOOR=$((11 * 1024 * 1024 * 1024))
LOW_HOME="$D_RUNTIME/low-home"; prepare_self_fix_home "$LOW_HOME" "$((GATE_FLOOR-1))"
LOW_OUT="$(run_fake_self_fix "$LOW_HOME" gate-low \
  LIFE_MANAGER_IGNORE_DISK_WRITERS_STOP=1 LIFE_MANAGER_IGNORE_DISK_PRESSURE_BLOCK=1 \
  LIFE_MANAGER_DISK_HEADROOM_KIB=1 2>&1)"; LOW_RC=$?
a "low headroom is typed as deferred" "$LOW_OUT" 'disk_headroom_low'
eq "low headroom exits deferred" "$LOW_RC" '75'
assert_no_self_fix_attempt "$LOW_HOME" gate-low

UNKNOWN_HOME="$D_RUNTIME/unknown-home"; prepare_self_fix_home "$UNKNOWN_HOME" unknown
UNKNOWN_OUT="$(run_fake_self_fix "$UNKNOWN_HOME" gate-unknown 2>&1)"; UNKNOWN_RC=$?
a "unknown capacity fails closed" "$UNKNOWN_OUT" 'disk_headroom_unavailable'
eq "unknown capacity exits deferred" "$UNKNOWN_RC" '75'
assert_no_self_fix_attempt "$UNKNOWN_HOME" gate-unknown

for flag in disk-writers.stop disk-pressure.block; do
  FLAG_HOME="$D_RUNTIME/flag-${flag##*.}-$flag"; prepare_self_fix_home "$FLAG_HOME" "$((16*1024*1024*1024))"
  : > "$FLAG_HOME/.local/state/life-manager/state/$flag"
  if [ "$flag" = "disk-writers.stop" ]; then
    ignore_name=LIFE_MANAGER_IGNORE_DISK_WRITERS_STOP; reason=disk_writers_stop; loop=gate-stop
  else
    ignore_name=LIFE_MANAGER_IGNORE_DISK_PRESSURE_BLOCK; reason=disk_pressure_block; loop=gate-pressure
  fi
  FLAG_OUT="$(run_fake_self_fix "$FLAG_HOME" "$loop" "$ignore_name=1" \
    LIFE_MANAGER_DISK_HEADROOM_KIB=1 2>&1)"; FLAG_RC=$?
  a "$flag blocks despite caller ignore env" "$FLAG_OUT" "$reason"
  eq "$flag exits deferred" "$FLAG_RC" '75'
  assert_no_self_fix_attempt "$FLAG_HOME" "$loop"
done

DROP_HOME="$D_RUNTIME/drop-home"; prepare_self_fix_home "$DROP_HOME" "$((16*1024*1024*1024))"
DROP_OUT="$(run_fake_self_fix "$DROP_HOME" gate-drop-after-browser \
  SELF_FIX_TEST_DROP_AFTER_BROWSER=1 SELF_FIX_TEST_DROP_BYTES="$((GATE_FLOOR-1))" 2>&1)"; DROP_RC=$?
a "capacity is rechecked before markers and agent spawn" "$DROP_OUT" 'disk_headroom_low'
eq "post-browser low capacity exits deferred" "$DROP_RC" '75'
eq "preflight may ensure browser only after first pass" "$(cat "$DROP_HOME/ensure-browser.calls" 2>/dev/null | wc -l | tr -d ' ')" '1'
assert_no_self_fix_markers "$DROP_HOME" gate-drop-after-browser

HELD_HOME="$D_RUNTIME/held-home"; prepare_self_fix_home "$HELD_HOME" "$((16*1024*1024*1024))"
HELD_LOOP=gate-held; HELD_CANONICAL="$HELD_LOOP-loop"
HELD_RESULT="$HELD_HOME/.local/state/life-manager/state/.self-fix-$HELD_CANONICAL.result"
printf 'HELD_EFFECT_UNKNOWN occurrence=reddit:test\n' > "$HELD_RESULT"
mkdir -p "$HELD_HOME/.local/state/life-manager/state/agent-runner-evidence/self-fix-$HELD_CANONICAL/tmp"
printf 'keep\n' > "$HELD_HOME/.local/state/life-manager/state/agent-runner-evidence/self-fix-$HELD_CANONICAL/tmp/sentinel"
HELD_OUT="$(run_fake_self_fix "$HELD_HOME" "$HELD_LOOP" 2>&1)"; HELD_RC=$?
a "held unknown effect is not respawned" "$HELD_OUT" 'HELD_EFFECT_UNKNOWN'
eq "held effect remains deferred" "$HELD_RC" '75'
eq "held result marker is unchanged" "$(cat "$HELD_RESULT")" 'HELD_EFFECT_UNKNOWN occurrence=reddit:test'
eq "held evidence temp is preserved" "$(cat "$HELD_HOME/.local/state/life-manager/state/agent-runner-evidence/self-fix-$HELD_CANONICAL/tmp/sentinel")" keep
eq "held evidence temp has no new files" "$(find "$HELD_HOME/.local/state/life-manager/state/agent-runner-evidence/self-fix-$HELD_CANONICAL/tmp" -type f | wc -l | tr -d ' ')" '1'
eq "held marker does not ensure browser" "$([ -f "$HELD_HOME/ensure-browser.calls" ] && echo called || echo absent)" absent
eq "held marker does not write start marker" "$([ -e "$HELD_HOME/.local/state/life-manager/state/.self-fix-$HELD_CANONICAL.started" ] && echo present || echo absent)" absent
eq "held marker does not spawn runner" "$([ -e "$HELD_HOME/observed-runtime.env" ] && echo present || echo absent)" absent
tmux -S "/tmp/anicca-selffix-$HELD_CANONICAL-tmux.sock" kill-server >/dev/null 2>&1 || true

LOOP_INPUT="owned-runtime-test-$(basename "$D_RUNTIME")"
LOOP_CANONICAL="${LOOP_INPUT}-loop"
SOCK="/tmp/anicca-selffix-$LOOP_CANONICAL-tmux.sock"
prepare_self_fix_home "$TEST_HOME" "$((16*1024*1024*1024))"
SERVER_HOST_STATE="$TEST_HOME/server-state"
CALLER_HOST_STATE="$TEST_HOME/caller-state"
mkdir -p "$SERVER_HOST_STATE" "$CALLER_HOST_STATE"
mkdir -p "$D_RUNTIME/server-tmp" "$D_RUNTIME/server-npm" "$D_RUNTIME/server-node" \
  "$D_RUNTIME/audit-tmp" "$D_RUNTIME/audit-npm" "$D_RUNTIME/audit-node"
env -i HOME="$TEST_HOME" PATH="$PATH" TERM=xterm TMPDIR="$D_RUNTIME/server-tmp" \
  NPM_CONFIG_CACHE="$D_RUNTIME/server-npm" NODE_COMPILE_CACHE="$D_RUNTIME/server-node" \
  tmux -S "$SOCK" new-session -d -s owned-runtime-keepalive 'sleep 60'
tmux -S "$SOCK" set-environment -g LIFE_MANAGER_IGNORE_DISK_WRITERS_STOP 1
tmux -S "$SOCK" set-environment -g LIFE_MANAGER_IGNORE_DISK_PRESSURE_BLOCK 1
tmux -S "$SOCK" set-environment -g LIFE_MANAGER_DISK_HEADROOM_KIB 1
tmux -S "$SOCK" set-environment -g LIFE_MANAGER_HOST_STATE_DIR "$SERVER_HOST_STATE"
(
  unset SELF_FIX_DRYRUN AGENT_WIRING_PROBE_ONLY
  export HOME="$TEST_HOME" LIFE_MANAGER_REPO="$TEST_REPO"
  export TMPDIR="$D_RUNTIME/audit-tmp" NPM_CONFIG_CACHE="$D_RUNTIME/audit-npm"
  export NODE_COMPILE_CACHE="$D_RUNTIME/audit-node"
  export LIFE_MANAGER_IGNORE_DISK_WRITERS_STOP=1 LIFE_MANAGER_IGNORE_DISK_PRESSURE_BLOCK=1
  export LIFE_MANAGER_DISK_HEADROOM_KIB=1 LIFE_MANAGER_HOST_STATE_DIR="$CALLER_HOST_STATE"
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
  eq "detached runner does not inherit stop-flag ignore" "$(printf '%s\n' "$OBSERVED_RUNTIME" | sed -n 's/^IGNORE_DISK_WRITERS_STOP=//p')" unset
  eq "detached runner does not inherit pressure-flag ignore" "$(printf '%s\n' "$OBSERVED_RUNTIME" | sed -n 's/^IGNORE_DISK_PRESSURE_BLOCK=//p')" unset
  eq "detached runner does not inherit lowered threshold" "$(printf '%s\n' "$OBSERVED_RUNTIME" | sed -n 's/^DISK_HEADROOM_KIB=//p')" unset
  eq "detached runner uses caller host namespace over tmux server namespace" "$(printf '%s\n' "$OBSERVED_RUNTIME" | sed -n 's/^HOST_STATE_DIR=//p')" "$CALLER_HOST_STATE"
  a "browser ensure does not inherit stop-flag ignore" "$(cat "$TEST_HOME/ensure-browser.env")" 'IGNORE_DISK_WRITERS_STOP=unset'
  a "browser ensure does not inherit pressure-flag ignore" "$(cat "$TEST_HOME/ensure-browser.env")" 'IGNORE_DISK_PRESSURE_BLOCK=unset'
  a "browser ensure does not inherit lowered threshold" "$(cat "$TEST_HOME/ensure-browser.env")" 'DISK_HEADROOM_KIB=unset'
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
