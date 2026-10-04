#!/usr/bin/env bash
LIFE_MANAGER_REPO="${LIFE_MANAGER_REPO:-$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$LIFE_MANAGER_REPO" ] || { echo "LIFE_MANAGER_REPO could not be resolved" >&2; exit 2; }
export LIFE_MANAGER_REPO
# healthcheck-lib.sh — ONE shared supervisor used by every loop's healthcheck (FIND-011). Detects, in order:
# (a) DEAD session, (b) STUCK-asking-a-human interactive prompt (FIND-001), (c) STALE liveness heartbeat, (d)
# running-but-producing-NOTHING output staleness (FIND-009). Recovers by restart w/ backoff; on give-up it calls
# self-fix.sh DIRECTLY to spawn an Opus fixer (FIND-006).
# AUTHORITATIVE success signal = the REAL output artifact (published.jsonl / posts.jsonl freshness, cross-checked
# live by verify-loops.sh) — NOT any self-graded marker (FIND-015): a fixer that lies "SUCCESS" but leaves the
# output stale is re-escalated here anyway, because (d) reads the artifact, never the marker.
# Caller sets: HC_LOOP HC_SOCK HC_SESSION HC_HB HC_START HC_STALE_MIN HC_CLI HC_OUTPUT HC_OUTPUT_STALE_HRS HC_SELFFIX_HINT
#
# ★ REQ-LV-104 scope note ★ — this shared hc_run() (incl. its OUT_STALE_HRS artifact-age check in
# step (d)) is sourced ONLY by capafy-loop-healthcheck.sh / reddit-loop-healthcheck.sh /
# life-manager-loop-healthcheck.sh (verified via grep, 2026-07-08). The 7 Cadence Contract loops
# (clip/affiliate/video/gig/bounty/pm-earner/founder-loop) each run their OWN standalone
# *-healthcheck.sh (e.g. video-healthcheck.sh) that does NOT call this file — their "is today's
# contract met" judgment lives in cadence.py/cadence-evidence.py via verify-loops(-audit).sh
# instead. This is intentional, not an integration gap: REQ-LV-104 explicitly keeps the old
# fresh()/stale_hrs()-style artifact-age judgment for capafy/reddit/life-manager only.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
set -uo pipefail

# FIND-014/021: single source of truth for "is this pane an idle prompt awaiting a human?" — fires ONLY on
# unambiguous input-await markers AND ONLY when NOT actively generating ("esc to interrupt" = live generation).
# test-healthcheck-lib.sh sources THIS function (no duplication → no drift).
# FIND-034: restart-storm guard — see hc_run()'s STALE-check callers for why a fresh restart needs a grace
# window before the STALE check is allowed to fire again. test-healthcheck-lib.sh sources THIS function directly.
hc_recent_restart() {
  local log="$1" now="$2" grace="${HC_RESTART_GRACE_SEC:-1200}" last
  [ -f "$log" ] || return 1
  last="$(tail -1 "$log" 2>/dev/null)"
  [ -n "$last" ] || return 1
  [ $(( now - last )) -lt "$grace" ]
}

hc_is_stuck_pane() {
  local pane="$1"
  printf '%s' "$pane" | grep -qE 'Enter to select|↑/↓ to navigate|Type something\.|Do you want to proceed' \
    && ! printf '%s' "$pane" | grep -qE 'esc to interrupt'
}

# G2 item4 (2026-07-11 loop-arch redesign / LOOPS-TRUTH-AUDIT.md "healthcheck DEAD誤判定(connector:
# 正常終了をDEAD扱いでrestart storm→stuck)"): confirmed real incident 2026-07-11 -- connector's own
# standalone healthcheck.sh judged session-liveness (tmux has-session) alone, misjudged a legitimate
# once-daily-cron loop with a genuinely-completed recent pass as DEAD, and restart-stormed it (15分
# 4回restart観測), leaving a stuck orphan process (PID 73590, 10.5h). Any healthcheck for a loop
# whose cadence is "wakes, runs one pass, exits" (rather than "always-on tmux session") should check
# THIS before any DEAD/STALE judgment: a genuinely-completed-pass marker touched within the last
# max_age_min minutes means the loop is healthy right now, regardless of what a bare
# session-liveness check alone would conclude. Pure/testable (no side effects), shared here (not
# duplicated per-caller) so every standalone healthcheck.sh -- capafy/reddit/life-manager-loop via
# hc_run() today, and any future once-daily-cron loop's own healthcheck.sh (e.g. connector-style) --
# has ONE place to get this right instead of re-deriving it.
hc_last_pass_recent() {
  local hb_file="$1" max_age_min="$2" now mtime age_min
  [ -f "$hb_file" ] || return 1
  now=$(date +%s); mtime=$(stat -f %m "$hb_file" 2>/dev/null || echo 0)
  age_min=$(( (now - mtime) / 60 ))
  [ "$age_min" -lt "$max_age_min" ]
}

# FIND-033 (life-manager-loop 3-day outage, 2026-07-10): a near-full data volume stops macOS growing its
# swapfile, which surfaces as intermittent fork() failures ("Resource temporarily unavailable") for EVERY
# new process on the box — including this script's own tmux/pkill calls (seen directly in launchd's error
# log) and every fresh `claude` spawn. A loop that is already DEAD needs a FRESH spawn every cycle, so it
# eats this failure on every single restart while already-idle sessions (needing no new fork) sail through
# — the loop can starve indefinitely even though its own code is fine. Reclaim only caches that are 100%
# regenerable package-manager/updater caches (never model weights like whisper/ollama/HF, never
# claudevm/colima — those need Dais approval per disk-hygiene policy) so a respawn actually has room to
# start. Cheap (~1s) when disk is fine; only doing real work under the low-disk condition.
hc_reclaim_disk_if_low() {
  local free_gb; free_gb="$(df -g /System/Volumes/Data 2>/dev/null | awk 'NR==2{print $4}')"
  [ -z "${free_gb:-}" ] && free_gb="$(df -g / 2>/dev/null | awk 'NR==2{print $4}')"
  [ -z "${free_gb:-}" ] && return 0
  [ "$free_gb" -ge 3 ] 2>/dev/null && return 0
  echo "$(date '+%F %T') disk low (${free_gb}GB free) → reclaiming safe regenerable caches before respawn" >> "${LOG:-/dev/null}"
  command -v npm >/dev/null 2>&1 && npm cache clean --force >/dev/null 2>&1
  rm -rf "$HOME/.cache/uv" 2>/dev/null
  rm -rf "$HOME/Library/Caches/com.anthropic.claudefordesktop.ShipIt"/* 2>/dev/null
  # camoufox is NOT cheap to regenerate: wiping it made verify-loops-audit re-download a 1.3GB
  # zip into its loop-tmp on every run (8 leftover zips = 8.3GB on 2026-10-04), so this reclaim
  # step itself drove the disk back to full. Keep the camoufox cache.
  rm -rf "$HOME/Library/Caches/node-gyp"/* 2>/dev/null
  rm -rf "$HOME/Library/Caches/pip"/* 2>/dev/null
  command -v brew >/dev/null 2>&1 && brew cleanup -s >/dev/null 2>&1
  return 0
}

# FIND-033: reap orphaned `cozempic guard --daemon` processes. Root cause discovered 2026-07-10: every Claude
# Code session (incl. every short-lived self-fix spawn) starts its OWN guard daemon via the global SessionStart
# hook, keyed by a per-session PID file (/tmp/cozempic_guard_<slug>.pid) — but the daemon does not reliably notice
# its parent session died, so these accumulate forever (observed: 291 live daemons, some >20h stale, vs ~9 real
# claude sessions). Left unchecked this exhausts kern.maxprocperuid, so ANY new fork() — incl. this loop's own
# `tmux new-session` — starts failing with "fork: Resource temporarily unavailable", which LOOKS like a capafy/
# reddit/life-manager-loop bug (session never comes up → DEAD) but is actually a whole-machine resource leak.
# Safe to kill: a guard is orphaned if its target session's transcript (~/.claude/projects/*/<slug-prefix>*.jsonl)
# has not been touched in HC_COZEMPIC_STALE_SEC — an idle session has nothing left to checkpoint anyway. Rate-
# limited to once per 4min system-wide (shared marker) since 3 loops source this file and would otherwise redo it.
hc_reap_stale_cozempic_guards() {
  local MARK="/tmp/.cozempic-reaper-last-run" now; now=$(date +%s)
  if [ -f "$MARK" ] && [ $(( now - $(stat -f %m "$MARK" 2>/dev/null||echo 0) )) -lt 240 ]; then return 0; fi
  touch "$MARK"
  local n; n=$(ls /tmp/cozempic_guard_*.pid 2>/dev/null | wc -l | tr -d ' ')
  [ "${n:-0}" -lt 50 ] && return 0   # small counts are normal (one per real active session) — nothing to reap
  python3 - "${HC_COZEMPIC_STALE_SEC:-1800}" <<'PYEOF' 2>/dev/null
import glob, os, re, sys, time, signal
stale_sec = float(sys.argv[1])
now = time.time()
slug_mtime = {}
for t in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
    base = os.path.basename(t)[:-6]
    slug = re.sub(r'[^a-z0-9_-]', '_', base.lower())[:12]
    try:
        m = os.path.getmtime(t)
    except OSError:
        continue
    if slug not in slug_mtime or m > slug_mtime[slug]:
        slug_mtime[slug] = m
killed = 0
for pf in glob.glob("/tmp/cozempic_guard_*.pid"):
    slug = os.path.basename(pf)[len("cozempic_guard_"):-4]
    try:
        pid = int(open(pf).read().strip().split()[0])
    except Exception:
        continue
    mt = slug_mtime.get(slug)
    if mt is not None and (now - mt) <= stale_sec:
        continue
    try:
        os.kill(pid, signal.SIGTERM)
        killed += 1
    except OSError:
        pass
    for f in (glob.glob(f"/tmp/cozempic_guard_{slug}*") + glob.glob(f"/tmp/cozempic_hook_{slug}*")
              + glob.glob(f"/tmp/cozempic_reload_{slug}*")):
        try:
            os.remove(f)
        except OSError:
            pass
print(f"reaped {killed} stale cozempic guard daemon(s)")
PYEOF
}

# FIND-020/026/031: acquire a per-loop lock. mkdir is atomic (one winner). A FRESH lock (<10min) = a live run → refuse
# (return 1). A STALE lock (>=10min, = a hard-killed prior run) is stolen with rm -rf (works even though the lock dir
# is NON-EMPTY due to the owner file — plain rmdir would fail and permanently disable self-heal). After (re)creating,
# claim by PID and re-verify to close the concurrent-steal race: exactly one survivor returns 0.
hc_acquire_lock() {
  local LOCK_DIR="$1" now="$2"
  if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    local lage=$(( ( now - $(stat -f %m "$LOCK_DIR" 2>/dev/null||echo "$now") ) / 60 ))
    if [ "$lage" -ge 10 ]; then rm -rf "$LOCK_DIR" 2>/dev/null||true; mkdir "$LOCK_DIR" 2>/dev/null || return 1
    else return 1; fi
  fi
  echo "$$" > "$LOCK_DIR/owner" 2>/dev/null; sleep 0.2
  [ "$(cat "$LOCK_DIR/owner" 2>/dev/null)" = "$$" ] || return 1
  return 0
}

hc_run() {
  local LOOP="$HC_LOOP" SOCK="$HC_SOCK" SESSION="$HC_SESSION" HB="$HC_HB" START="$HC_START"
  local STALE_MIN="$HC_STALE_MIN" CLI="$HC_CLI" OUTPUT="${HC_OUTPUT:-}" OUT_STALE_HRS="${HC_OUTPUT_STALE_HRS:-30}"
  local SELFFIX_HINT="${HC_SELFFIX_HINT:-loop produces no real output}"
  local STATE="$HOME/.local/state/life-manager/state"; mkdir -p "$STATE"
  local LOG="$HOME/.local/state/life-manager/logs/$LOOP-healthcheck.log"; mkdir -p "$(dirname "$LOG")"
  local RESTART_LOG="$STATE/.$LOOP-restart-log"
  local now; now=$(date +%s)

  # FIND-033: clear fork-table pressure from orphaned cozempic guard daemons BEFORE any tmux/fork attempt below —
  # see hc_reap_stale_cozempic_guards for why this is load-bearing, not cosmetic.
  local reap_out; reap_out="$(hc_reap_stale_cozempic_guards)"
  [ -n "$reap_out" ] && echo "$(date '+%F %T') $reap_out" >> "$LOG"

  # FIND-013: lock with a staleness escape hatch. A healthcheck killed abnormally must not disable self-heal forever
  # — if the lock is older than 10min it is stale (each run finishes in seconds), so steal it.
  local LOCK_DIR="/tmp/.$LOOP-healthcheck.lock"
  hc_acquire_lock "$LOCK_DIR" "$now" || return 0
  trap 'rm -rf "$LOCK_DIR" 2>/dev/null' RETURN

  # FIND-034 (capafy-loop restart storm, 2026-07-11): once the heartbeat crosses STALE_MIN, a restart-killed
  # session gets re-spawned but its STARTUP pass (CronList + read STATE.md + run daily_loop.sh + verify + report)
  # takes several minutes — LONGER than the 5min healthcheck cadence. Without a grace window, the VERY NEXT
  # healthcheck cycle sees the heartbeat still stale (it hasn't been touched yet — that only happens at the pass's
  # own final step) and kills+restarts AGAIN, forever pre-empting the one pass that would clear the staleness.
  # This burns all 5 restarts/60min and escalates to self-fix even though nothing is actually hung. Give a fresh
  # restart a grace window (default 20min, comfortably longer than one STARTUP pass) before the STALE check is
  # allowed to fire again — DEAD (a) and STUCK (b) checks above are untouched by this and still fire every cycle,
  # since those are real distress signals a busy-but-healthy pass cannot fake.

  _selffix() {  # FIND-006: give-up → actually spawn the Opus fixer, not a dead note
    echo "$(date '+%F %T') give-up → self-fix.sh $LOOP" >> "$LOG"
    bash "$LIFE_MANAGER_REPO/skills/self/self-fix.sh" "$LOOP" "$1" >> "$LOG" 2>&1 || echo "$(date '+%F %T') self-fix launch failed" >> "$LOG"
  }
  _restart() {  # backoff: >=5 restarts/60min → escalate to self-fix instead of thrashing
    local reason="$1" count=0 ts
    if [ -f "$RESTART_LOG" ]; then while IFS= read -r ts; do [ -n "$ts" ] && [ $(( now - ts )) -le 3600 ] && count=$(( count+1 )); done < "$RESTART_LOG"; fi
    if [ "$count" -ge 5 ]; then _selffix "the $LOOP loop keeps dying/stalling ($count restarts/60min; last reason: $reason). Diagnose why its cli.sh/STARTUP won't run a healthy pass and fix it."; return; fi
    echo "$now" >> "$RESTART_LOG"; pkill -f "claude --name $SESSION" 2>/dev/null||true; pkill -f "tmux -S $SOCK new-session" 2>/dev/null||true; sleep 1
    hc_reclaim_disk_if_low
    echo "$(date '+%F %T') $reason → restart" >> "$LOG"; bash "$CLI" --restart >> "$LOG" 2>&1||true
  }

  # (a) DEAD
  if ! tmux -S "$SOCK" has-session -t "$SESSION" 2>/dev/null; then _restart "$LOOP DEAD"; return; fi

  # (b) STUCK asking a human (FIND-001/014): fire ONLY on unambiguous input-await markers of Claude Code's interactive
  # picker/confirm/free-text, AND ONLY when the session is NOT actively generating. Active generation always shows
  # "esc to interrupt"; an idle-await prompt never does. This prevents false-restarting healthy long-running work.
  local pane; pane="$(tmux -S "$SOCK" capture-pane -t "$SESSION" -p 2>/dev/null | tail -25)"
  if hc_is_stuck_pane "$pane"; then
    echo "$(date '+%F %T') STUCK: idle interactive prompt (awaiting human input) → restart" >> "$LOG"; _restart "STUCK asking human"; return
  fi

  # (c) liveness heartbeat stale
  local hb_age m
  if [ ! -f "$HB" ]; then m="$(stat -f %m "$START" 2>/dev/null||echo "$now")"; hb_age=$(( (now-m)/60 ))
    if [ "$hb_age" -ge "$STALE_MIN" ]; then
      if hc_recent_restart "$RESTART_LOG" "$now"; then echo "$(date '+%F %T') STALE ${hb_age}min but restarted <grace ago → giving this pass room to finish" >> "$LOG"; return; fi
      _restart "no pass in ${hb_age}min"; return
    fi
  else hb_age=$(( (now-$(stat -f %m "$HB" 2>/dev/null||echo "$now"))/60 ))
    if [ "$hb_age" -ge "$STALE_MIN" ]; then
      if hc_recent_restart "$RESTART_LOG" "$now"; then echo "$(date '+%F %T') STALE ${hb_age}min but restarted <grace ago → giving this pass room to finish" >> "$LOG"; return; fi
      _restart "STALE ${hb_age}min"; return
    fi
  fi

  # (d) running but producing NOTHING real (FIND-009): the real output artifact is the ONLY success signal. If it has
  # not changed in OUT_STALE_HRS the loop is alive-but-useless (or a self-fix lied) → escalate a self-fix, once per window.
  if [ -n "$OUTPUT" ]; then
    local o_age=99999
    [ -f "$OUTPUT" ] && o_age=$(( (now-$(stat -f %m "$OUTPUT" 2>/dev/null||echo 0))/3600 ))
    if [ "$o_age" -ge "$OUT_STALE_HRS" ]; then
      local MK="$STATE/.$LOOP-output-stale-escalated"
      if [ ! -f "$MK" ] || [ "$(( (now-$(stat -f %m "$MK" 2>/dev/null||echo 0))/3600 ))" -ge "$OUT_STALE_HRS" ]; then
        touch "$MK"; _selffix "$SELFFIX_HINT (no real output for ${o_age}h; the loop is alive but STEP2/STEP3 produce nothing — find why and fix it so a real side-effect happens)."
        echo "$(date '+%F %T') ALIVE but output stale ${o_age}h → self-fix escalated" >> "$LOG"; return
      fi
    fi
    echo "$(date '+%F %T') ALIVE+fresh (hb ${hb_age}min, output ${o_age}h)" >> "$LOG"; return
  fi
  echo "$(date '+%F %T') ALIVE+fresh (hb ${hb_age}min)" >> "$LOG"
}
