#!/usr/bin/env bash
# daily_loop.sh — fire a provider-agnostic tool agent to drain ONE inventory listing to Capafy.
# Scheduled by launchd (com.anicca.capafy-daily). No human in the loop.
# Verification: lint (deterministic) + agent sanity re-read + split prepare/CP1/finish
# fail-closed gates, including official remote readback.
set -uo pipefail

AUTO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIFE_MANAGER_REPO="${LIFE_MANAGER_REPO:-$(git -C "$AUTO" rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$LIFE_MANAGER_REPO" ] || { echo "LIFE_MANAGER_REPO could not be resolved" >&2; exit 2; }
LIFE_MANAGER_STATE_HOME="${LIFE_MANAGER_STATE_HOME:-$HOME/.local/state/life-manager}"
CAPAFY_STATE_DIR="${CAPAFY_STATE_DIR:-$LIFE_MANAGER_STATE_HOME/state/capafy-autopublish}"
export LIFE_MANAGER_REPO LIFE_MANAGER_STATE_HOME CAPAFY_STATE_DIR
LOG="$CAPAFY_STATE_DIR/daily_loop.log"
RUN_AGENT="${CAPAFY_RUN_AGENT:-$LIFE_MANAGER_REPO/skills/earn/marketing-engine/run_agent.sh}"
# HEALTHY-PASS MARKER (self-fix-capafy-loop, 2026-07-08): touched whenever the loop reaches a
# HEALTHY terminal state — either it published something OR it correctly determined there is
# nothing to publish (inventory drained / cap full). The healthcheck watches THIS file's mtime,
# not published.jsonl. Why: this loop DRAINS a finite hand-built inventory; once every listing
# is online, published.jsonl can never grow, so the old "grew in 30h?" alarm false-escalated an
# Opus self-fix forever for a non-bug. This marker stays fresh while the loop is healthy-idle,
# and only goes stale if the loop stops running OR keeps hitting a real BLOCKED publish — which
# is exactly when a self-fix SHOULD fire.
MARK="$CAPAFY_STATE_DIR/.capafy-healthy-pass"
TS="$(date '+%Y-%m-%d %H:%M:%S')"
mkdir -p "$CAPAFY_STATE_DIR"

# EXCLUSIVE LOCK (self-fix-capafy-loop, 2026-07-12): two independent schedulers
# (launchd ai.anicca.capafy-loop-daily every hour via the full money-loop-core prompt,
# and OpenClaw cron "anicca-capafy-daily-publish" @ 09:00 JST calling this script directly)
# both end up invoking this drainer. Without a lock, overlapping runs raced on the SAME
# shared CloakBrowser tab (:9222), each seeing the other's mid-edit DOM state, burning
# through --max-turns without ever completing a save (observed 2026-07-12: 5 stacked
# invocations in ~90min, several dying with "Error: Reached max turns (40)"). mkdir is
# atomic on every POSIX fs and needs no extra binary (macOS ships no `flock` CLI) — a
# second concurrent invocation exits immediately instead of silently corrupting the first.
LOCK_DIR="$CAPAFY_STATE_DIR/.daily_loop.lockdir"
# The owner pid lives inside the lock. A holder killed with its parent pass (SIGKILL
# skips the EXIT trap) left the lock for 40 minutes on 2026-09-28, so every pass in
# between skipped the drainer; a dead owner is stolen at once.
take_lock() { echo "$$" >"$LOCK_DIR/pid"; trap 'rm -f "$LOCK_DIR/pid"; rmdir "$LOCK_DIR" 2>/dev/null' EXIT; }
if mkdir "$LOCK_DIR" 2>/dev/null; then
  take_lock
else
  # stale-lock guard: a dead owner, or a lock dir older than 40min, means a prior run
  # crashed without cleaning up (this script's own claude call is timeout-guarded at
  # 1200s=20min) — steal it rather than wedging the loop forever.
  AGE=$(( $(date +%s) - $(stat -f %m "$LOCK_DIR" 2>/dev/null || echo 0) ))
  OWNER="$(cat "$LOCK_DIR/pid" 2>/dev/null)"
  if [ "$AGE" -gt 2400 ] || { [ -n "$OWNER" ] && ! kill -0 "$OWNER" 2>/dev/null; } \
      || { [ -z "$OWNER" ] && [ "$AGE" -gt 60 ]; }; then
    rm -f "$LOCK_DIR/pid"; rmdir "$LOCK_DIR" 2>/dev/null; mkdir "$LOCK_DIR" 2>/dev/null
    take_lock
  else
    echo "=== $TS daily_loop SKIPPED — another instance holds $LOCK_DIR (age ${AGE}s) ===" >>"$LOG"
    exit 0
  fi
fi

# load env (keys) for the child
set -a; . "$LIFE_MANAGER_STATE_HOME/.env" 2>/dev/null; set +a

echo "=== $TS daily_loop start ===" >> "$LOG"

# Paid buyers can keep using already-listed Agents even when there is no new
# inventory. Check host funding before the healthy-idle exit so an exhausted
# key cannot remain invisible until the next publication attempt.
if ! KEY_HEALTH="$($AUTO/scripts/key_health_gate.sh 2>&1)"; then
  echo "$TS $KEY_HEALTH" >> "$LOG"
  echo "=== $TS daily_loop done rc=1 (HOST_KEY_UNHEALTHY — paid-user service at risk; marker NOT touched) ===" >> "$LOG"
  exit 1
fi
echo "$TS $KEY_HEALTH" >> "$LOG"

# ── RECONCILE THE LEDGER WITH SERVER TRUTH (self-fix-capafy-loop, 2026-07-07) ──
# state/published.jsonl mirrors the SERVER: every online agent recorded, REVIEW_REJECTED flagged,
# and orphan DRAFT stubs surfaced (2026-07-08) so a half-published card can't rot invisibly.
python3 "$AUTO/scripts/reconcile_ledger.py" --json >> "$LOG" 2>&1 || true

# ── DETERMINISTIC WORK CHECK (self-fix-capafy-loop, 2026-07-08) ──
# Ask the server: is there ANY real work? DRAINED/CAP_FULL = healthy idle → touch the marker and
# SKIP the expensive headless Claude run (protects the subscription quota — no point spending an
# LLM turn to re-discover "nothing to do"). Only PUBLISHABLE fires the publish flow.
INV="$(CAPAFY_COUNT_DRAFT_ATTEMPT=1 python3 "$AUTO/scripts/inventory_status.py" 2>>"$LOG")"
VERDICT="$(printf '%s\n' "$INV" | sed -n 's/^VERDICT=//p' | head -1)"
echo "$TS inventory verdict=$VERDICT :: $(printf '%s' "$INV" | tail -1)" >> "$LOG"

# Refresh the durable OFFLINE candidate backlog before any CAP_FULL/DRAINED exit.
# This consumes the inventory response already read above and performs no Capafy write.
printf '%s\n' "$INV" | tail -1 | python3 "$AUTO/scripts/candidate_backlog.py" refresh \
  --inventory-stdin >>"$LOG" 2>&1 || {
    echo "=== $TS candidate backlog refresh failed ===" >>"$LOG"
    exit 1
  }

case "$VERDICT" in
  DRAINED|CAP_FULL)
    touch "$MARK"
    echo "=== $TS daily_loop done rc=0 (HEALTHY-IDLE: $VERDICT — nothing to publish, marker touched, no LLM spend) ===" >> "$LOG"
    exit 0 ;;
  SERVER_UNREADABLE)
    # cannot confirm health → do NOT touch the marker; if this persists the marker goes stale and
    # the healthcheck escalates (auth/network genuinely broken = a real problem to self-fix).
    echo "=== $TS daily_loop done rc=1 (SERVER_UNREADABLE — marker NOT touched; escalates if it persists) ===" >> "$LOG"
    exit 1 ;;
esac

# PRE-run online_count (server truth, from the same $INV that gated us into PUBLISHABLE). This is
# the only reliable "did a listing actually go live" signal — DRAINED/CAP_FULL can also happen when
# a REVIEW_REJECTED item is merely resubmitted into under_review (self-fix-capafy-loop, 2026-07-11:
# this exact confusion produced a false "PUBLISHED" label on a run where nothing went online).
PRE_ONLINE="$(printf '%s' "$INV" | tail -1 | python3 -c 'import json,sys; print(json.load(sys.stdin).get("online_count", -1))' 2>>"$LOG")"

# A resumed draft whose CP1 is already confirmed only needs CP2 -> CP3, which is
# deterministic. The agentic runbook re-enters CP1 and demands an edit URL that
# Capafy no longer issues once CP1 is saved (2026-09-28, Agent 9466718786: the
# refresh returned only /R<digits> and every resume stopped). publish_finish.sh
# refuses before any write unless is_confirmed_skills=true, so a draft that still
# needs CP1 falls through to the agentic flow below.
RESUME="$(printf '%s' "$INV" | tail -1 | python3 -c 'import json,os,sys
d=json.load(sys.stdin); i=d.get("item") or {}
if d.get("action") == "resume_draft" and i.get("agent_id") and i.get("skill") and i.get("listing"):
    print(i["agent_id"], os.path.basename(os.path.dirname(i["skill"])), i["listing"],
          os.path.dirname(i["skill"]), i.get("icon",""), sep="\t")' 2>>"$LOG")"
REUSE_PREPARE_ID=""
FRESH=""
if [ -n "$RESUME" ]; then
  IFS=$'\t' read -r R_ID R_SKILL R_LISTING R_SKILL_DIR R_ICON <<<"$RESUME"
  # A catalog-wide model switch (LISTING.md's Primary Model changed after this
  # draft's package/hosted-key were already confirmed) leaves the CONFIRMED
  # hosted model stale server-side -- deterministic finish would silently keep
  # re-saving the OLD model forever (2026-09-29, Agent 4973250899: LISTING said
  # DeepSeek, requiredCredentials still said Sonnet). Detect it BEFORE trusting
  # the "already confirmed, skip prepare/CP2" shortcut.
  MODEL_CHECK="$(python3 "$AUTO/scripts/check_hosted_model.py" --agent-id "$R_ID" --listing "$R_LISTING" 2>&1)"
  echo "$TS resume_draft $R_ID model-check: $MODEL_CHECK" >> "$LOG"
  # A draft whose package never finished uploading (Hook Lab 8123079349 v1.0.4,
  # 2026-09-29: all tabs red, workspace blank, no confirmed model) cannot be
  # finished from CP1 either -- re-prepare it on the same agent_id like a mismatch.
  if printf '%s' "$MODEL_CHECK" | grep -qE '^(MODEL_MISMATCH|MODEL_UNKNOWN no-confirmed-model-yet)'; then
    if [ -n "$R_SKILL_DIR" ] && [ -n "$R_ICON" ]; then
      # Same-agent model switch: re-prepare on the SAME agent_id with the
      # CURRENT LISTING model (CP1_AGENTIC.md "Switching an EXISTING agent's
      # hosted model resets Skill confirmation"). Reuses the existing
      # create_fresh prepare+agentic-CP1+publish_finish pipeline below instead
      # of a second implementation.
      FRESH="$(printf '%s\t%s\t%s' "$R_SKILL_DIR" "$R_LISTING" "$R_ICON")"
      REUSE_PREPARE_ID="$R_ID"
    else
      echo "$TS resume_draft $R_ID: model mismatch but item is missing skill_dir/icon; falling back to the agentic runbook" >> "$LOG"
    fi
  else
    R_MANIFEST="${CAPAFY_PUBLISHER_STATE_HOME:-$LIFE_MANAGER_STATE_HOME/runtime/capafy-publisher}/work/agents/$R_ID/publish-work-state.json"
    R_VERSION="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("agent_version_id",""))' "$R_MANIFEST" 2>>"$LOG")"
    if [ -n "$R_VERSION" ] && bash "$AUTO/scripts/publish_finish.sh" "$R_ID" "$R_SKILL" "$R_LISTING" "$R_VERSION" >>"$LOG" 2>&1; then
      touch "$MARK"; echo 0 > "$CAPAFY_STATE_DIR/.maxturns-streak"
      echo "=== $TS daily_loop done rc=0 (RESUMED — $R_ID finished CP2/CP3 deterministically; no LLM spend) ===" >> "$LOG"
      exit 0
    fi
    echo "$TS resume_draft $R_ID: deterministic finish did not complete; falling back to the agentic runbook" >> "$LOG"
  fi
fi

# PUBLISHABLE → the shared agent runner tries the configured tool-agent providers in order and
# records durable per-attempt evidence. Keep ANTHROPIC_API_KEY unset so a Claude fallback uses the
# authenticated subscription instead of an exhausted pay-as-you-go key.
PROMPT="Follow this runbook exactly and do ONE iteration, terse output: $(cat "$AUTO/DAILY_LOOP.md")
AUTHORITATIVE INVENTORY ACTION: $(printf '%s' "$INV" | tail -1)
Execute exactly that action/item. Do not select or substitute another item from stale ledger or rejection history."
# create_fresh: run the deterministic prepare here, not inside the agent. The
# agent's own per-command timeout killed publish_prepare.sh mid-run on
# 2026-09-28 (Agent 4973250899 was created but its ID never came back), leaving
# an orphan draft. The agent now only drives CP1; publish_finish runs after it.
# FRESH may already be set above (a resume_draft model-switch re-prepare) --
# do not let a create_fresh (re-)read from $INV clobber that.
if [ -z "$FRESH" ]; then
  FRESH="$(printf '%s' "$INV" | tail -1 | python3 -c 'import json,os,sys
d=json.load(sys.stdin); i=d.get("item") or {}
if d.get("action") == "create_fresh" and i.get("skill") and i.get("listing") and i.get("icon"):
    print(os.path.dirname(i["skill"]), i["listing"], i["icon"], sep="\t")' 2>>"$LOG")"
fi
# An already-approved manual version has no local listing inputs, so it must not
# fall through as an underspecified generic publishing task.  Give the browser
# agent one bounded, observable transition: Test Run the exact selected version,
# require its completed response, then publish that same version and read back
# `online`.  (A successful action may leave another item PUBLISHABLE; the
# selected-ID post check below handles that queue state.)
TEST_AND_PUBLISH_ID="$(printf '%s' "$INV" | tail -1 | python3 -c 'import json,sys
d=json.load(sys.stdin); i=d.get("item") or {}
if d.get("action") == "test_and_publish" and i.get("agent_id"):
    print(i["agent_id"])' 2>>"$LOG")"
if [ -n "$TEST_AND_PUBLISH_ID" ]; then
  PROMPT="$PROMPT
AUTHORITATIVE TEST-AND-PUBLISH: agent_id=$TEST_AND_PUBLISH_ID. Do not create a version or edit any listing. In the owned Capafy browser, select the approved version for exactly this ID, run Test Run with a factual sales prompt, and wait for a completed non-error response (for example, the UI's run-ended success signal). Only then click the manual publish control once. Require official publish-remote-status/publish-list readback for THIS agent_id to become online. If the test errors, do not publish; report the sanitized error. Stop immediately after the authoritative online readback."
fi
# Paid existing-Agent updates must use the same deterministic prepare/CP1/finish
# path as a fresh listing, while fencing the exact remote source version. Without
# this branch they fall through to the generic agent prompt, which has no bound
# Agent publisher home and fails before CP1 for an older download listing.
UPDATE_EXPECTED_ID=""
UPDATE_EXPECTED_FROM_VERSION=""
if [ -z "$FRESH" ]; then
  UPDATE="$(printf '%s' "$INV" | tail -1 | python3 -c 'import json,os,sys
d=json.load(sys.stdin); i=d.get("item") or {}; u=i.get("update_request") or {}
if (d.get("action") == "update_existing" and i.get("skill") and i.get("listing")
        and i.get("icon") and i.get("agent_id") and u.get("from_version_id")):
    print(os.path.dirname(i["skill"]), i["listing"], i["icon"], i["agent_id"],
          u["from_version_id"], sep="\t")' 2>>"$LOG")"
  if [ -n "$UPDATE" ]; then
    IFS=$'\t' read -r F_SKILL_DIR F_LISTING F_ICON UPDATE_EXPECTED_ID UPDATE_EXPECTED_FROM_VERSION <<<"$UPDATE"
    FRESH="$(printf '%s\t%s\t%s' "$F_SKILL_DIR" "$F_LISTING" "$F_ICON")"
  fi
fi
PREPARED=""
if [ -n "$FRESH" ]; then
  IFS=$'\t' read -r F_SKILL_DIR F_LISTING F_ICON <<<"$FRESH"
  PREP_OUT="$(CAPAFY_EXPECTED_AGENT_ID="$UPDATE_EXPECTED_ID" CAPAFY_EXPECTED_FROM_VERSION_ID="$UPDATE_EXPECTED_FROM_VERSION" bash "$AUTO/scripts/publish_prepare.sh" "$F_SKILL_DIR" "$F_LISTING" "$F_ICON" "$REUSE_PREPARE_ID" 2>&1)"
  PREP_RC=$?
  printf '%s\n' "$PREP_OUT" >> "$LOG"
  F_ID="$(printf '%s\n' "$PREP_OUT" | sed -n 's/^AGENT_ID=//p' | tail -1)"
  F_VERSION="$(printf '%s\n' "$PREP_OUT" | sed -n 's/^AGENT_VERSION_ID=//p' | tail -1)"
  if [ "$PREP_RC" -ne 0 ] || [ -z "$F_ID" ] || [ -z "$F_VERSION" ]; then
    echo "=== $TS daily_loop done rc=1 (PREPARE_FAILED rc=$PREP_RC — no agent spend) ===" >> "$LOG"
    exit 1
  fi
  PREPARED="1"
  if [ -n "$REUSE_PREPARE_ID" ]; then
    PROMPT="$PROMPT
SAME-AGENT RE-PREPARE created fresh version $F_VERSION for agent_id=$F_ID, so earlier CP1 tab state is not evidence for this version. Do NOT run publish_prepare.sh or publish_finish.sh. Its output:
$PREP_OUT
Complete all three CP1 tabs using CP1_AGENTIC.md and the exact EDIT_URL_FILE, CONFIG_PATH, and TARGET PRICING above: Basic Info / 基本情報, Agent ワークスペース, and Pricing / 価格設定. Re-enter or verify every required value on this fresh version; do not stop after clicking the pending Skill card or seeing a green tab. Set every plan to its printed target, run scripts/cp1_agent.py prices $F_LISTING, and require PRICES_MATCH before continuing. Use the screenshot loop for each action. Then click 下書きを保存 followed by 提出を確認. Stop only after the card-save success signal appears AND official publish-remote-status confirms latest_version.agent_version_id=$F_VERSION and latest_version.is_confirmed_skills=true. The wrapper runs publish_finish.sh (CP2 -> CP3) after you."
  else
  PROMPT="$PROMPT
PREPARE ALREADY DONE by the wrapper — do NOT run publish_prepare.sh or publish_finish.sh. Its output:
$PREP_OUT
Do only step 5b: complete all three CP1 tabs using CP1_AGENTIC.md and the exact EDIT_URL_FILE, CONFIG_PATH, and TARGET PRICING above: Basic Info / 基本情報 (fill every empty or red field from CONFIG_PATH), Agent ワークスペース, and Pricing / 価格設定. Clicking the pending Skill card alone does not set is_confirmed_skills on the server; it turns true only after the card is saved. Set every plan to its printed target, run scripts/cp1_agent.py prices with the listing above, and require PRICES_MATCH. Then click 下書きを保存 followed by 提出を確認. Stop only after the card-save success signal appears AND official publish-remote-status confirms latest_version.is_confirmed_skills=true. The wrapper runs publish_finish.sh (CP2 -> CP3) after you."
  fi
fi
EVIDENCE_DIR="$LIFE_MANAGER_STATE_HOME/state/agent-runner-evidence/capafy-drainer/$(date +%s)-$$"
# 1200s was too short for the CP1 price tab driven by screenshots (2026-10-08 18:55: 76 UI steps, rc=124,
# and the timeout leaves an effect_unknown fence that costs the next slot). 1800s keeps the whole pass
# (prepare + agent + CP2/CP3) inside the 3600s loop limit. Stopgap until prices are set by a verified CLI verb.
printf '%s\n' "$PROMPT" | timeout "${CAPAFY_CP1_AGENT_TIMEOUT_SECONDS:-1800}" env -u ANTHROPIC_API_KEY "$RUN_AGENT" \
  --task-class application-lane-agent \
  --evidence-dir "$EVIDENCE_DIR" \
  --task-label capafy-drainer \
  --loop capafy \
  --workdir "$LIFE_MANAGER_REPO" >> "$LOG" 2>&1
RC=$?
# rc 75 with no provider attempt recorded = agent_runner deferred before any provider call
# (e.g. "provider deferred: disk_headroom_low"). rc 75 alone is not proof: budget_blocked can
# follow a real attempt, which leaves attempt-*/attempts.jsonl behind. Refund only the no-attempt
# case, or deferred passes exhaust MAX_DRAFT_ATTEMPTS and drop the draft for good
# (2026-10-11 Hook Lab/TikTok/YouTube price restores).
if [ "$RC" -eq 75 ] && [ -z "$(find "$EVIDENCE_DIR" -maxdepth 1 -name 'attempt*' 2>/dev/null)" ]; then
  ATTEMPT_ID="$(printf '%s' "$INV" | tail -1 | python3 -c 'import json,sys
d=json.load(sys.stdin)
if d.get("action") in ("resume_draft", "retry_existing"): print((d.get("item") or {}).get("agent_id") or "")' 2>>"$LOG")"
  [ -n "$ATTEMPT_ID" ] && python3 "$AUTO/scripts/inventory_status.py" --refund-draft-attempt "$ATTEMPT_ID" 2>>"$LOG" \
    && echo "$TS agent deferred (rc=75): refunded draft attempt for $ATTEMPT_ID" >> "$LOG"
fi
if [ -n "$PREPARED" ]; then
  F_SKILL="$(basename "$F_SKILL_DIR")"
  if bash "$AUTO/scripts/publish_finish.sh" "$F_ID" "$F_SKILL" "$F_LISTING" "$F_VERSION" >> "$LOG" 2>&1; then
    RC=0; echo "$TS prepared $F_ID: publish_finish completed (CP2 -> CP3)" >> "$LOG"
    # Same healthy terminal as RESUMED above: one submission per pass is the goal, and the
    # queue still holds more updates, so post-verdict stays PUBLISHABLE and the branch below
    # would log BLOCKED and wake self-fix for a successful pass (live 2026-09-29 23:40, 1037238583).
    touch "$MARK"; echo 0 > "$CAPAFY_STATE_DIR/.maxturns-streak"
    echo "=== $TS daily_loop done rc=0 (SUBMITTED — $F_ID finished CP2/CP3 after prepare) ===" >> "$LOG"
    exit 0
  else
    echo "$TS prepared $F_ID: publish_finish did not complete; draft resumes on a later pass" >> "$LOG"
  fi
fi

# Post-run truth: did a listing actually go live (online_count increased), not just "did the
# rejected/publishable buckets empty out"? A REVIEW_REJECTED item resubmitted into under_review also
# clears those buckets (verdict=DRAINED) without ever going online — that is NOT a publish, it's a
# pending-review state, and must never be logged as PUBLISHED (self-fix-capafy-loop, 2026-07-11).
POST_JSON="$(python3 "$AUTO/scripts/inventory_status.py" 2>>"$LOG")"
POST="$(printf '%s\n' "$POST_JSON" | sed -n 's/^VERDICT=//p' | head -1)"
POST_ONLINE="$(printf '%s' "$POST_JSON" | tail -1 | python3 -c 'import json,sys; print(json.load(sys.stdin).get("online_count", -1))' 2>>"$LOG")"

# A successful test_and_publish normally exposes the next ready approved
# version, so the aggregate post-verdict remains PUBLISHABLE.  That is a queue
# condition, not a failure of the selected action.  Check the exact selected
# Agent against the authoritative post-readback before declaring the pass
# blocked; otherwise every successful manual publication starves the health
# marker and re-escalates this self-fix.
if [ -n "$TEST_AND_PUBLISH_ID" ]; then
  TEST_AND_PUBLISH_ONLINE="$(printf '%s' "$POST_JSON" | tail -1 | python3 -c 'import json,sys
d=json.load(sys.stdin); target=sys.argv[1]
for agent in d.get("agents", []):
    if str(agent.get("agent_id") or "") == target:
        print("1" if agent.get("remote_status") == "online" or agent.get("lifecycle") == "listed" else "0")
        break
else:
    print("0")' "$TEST_AND_PUBLISH_ID" 2>>"$LOG")"
  if [ "$TEST_AND_PUBLISH_ONLINE" = "1" ]; then
    touch "$MARK"; echo 0 > "$CAPAFY_STATE_DIR/.maxturns-streak"
    echo "=== $TS daily_loop done rc=0 (TEST_AND_PUBLISHED — $TEST_AND_PUBLISH_ID is online; post-verdict=$POST, marker touched) ===" >> "$LOG"
    exit 0
  fi
fi

# A3 (2026-07-18): a per-pass max-turns exhaustion is a BUDGET limit, not a broken pipeline. Track a
# streak so a single/short exhaustion continues next pass (marker kept fresh) but a PERSISTENT one
# still escalates. Reset on any healthy or differently-failed pass.
MAXTURNS_STREAK="$CAPAFY_STATE_DIR/.maxturns-streak"
if [ "$POST" = "DRAINED" ] || [ "$POST" = "CAP_FULL" ]; then
  touch "$MARK"; echo 0 > "$MAXTURNS_STREAK"
  if [ -n "$PRE_ONLINE" ] && [ -n "$POST_ONLINE" ] && [ "$POST_ONLINE" -gt "$PRE_ONLINE" ] 2>/dev/null; then
    echo "=== $TS daily_loop done rc=$RC (PUBLISHED — online_count $PRE_ONLINE -> $POST_ONLINE, post-verdict=$POST, marker touched) ===" >> "$LOG"
  else
    echo "=== $TS daily_loop done rc=$RC (HEALTHY-IDLE: no new listing went online (online_count unchanged at $POST_ONLINE), post-verdict=$POST, marker touched) ===" >> "$LOG"
  fi
elif tail -60 "$LOG" | grep -q "Reached max turns"; then
  # max-turns exhaustion: the agentic CP1 screenshot loop can legitimately need >60 turns. A single
  # exhausted pass must NOT starve the healthy-pass marker (that fired a self-fix for a non-bug —
  # the 2026-07-17 incident). Bounded continuation: touch the marker + continue for up to 3 passes;
  # only a persistent streak (>=3) is left to escalate. A rejected cfg=1 retry should take the
  # deterministic publish_finish.sh path and never enter the agentic loop at all (DAILY_LOOP.md 2a).
  N=$(( $(cat "$MAXTURNS_STREAK" 2>/dev/null || echo 0) + 1 )); echo "$N" > "$MAXTURNS_STREAK"
  if [ "$N" -lt 3 ]; then
    touch "$MARK"
    echo "=== $TS daily_loop done rc=$RC (MAXTURNS-CONTINUE ${N}/3 — headless agent hit the 60-turn budget mid-publish; marker touched (alive), continues next pass, self-fix NOT escalated) ===" >> "$LOG"
  else
    echo "=== $TS daily_loop done rc=$RC (MAXTURNS-STUCK ${N} passes — persistent budget exhaustion, marker NOT touched → self-fix will escalate) ===" >> "$LOG"
  fi
else
  echo 0 > "$MAXTURNS_STREAK"
  echo "=== $TS daily_loop done rc=$RC (BLOCKED — post-verdict=$POST, marker NOT touched → self-fix will escalate) ===" >> "$LOG"
fi
exit $RC
