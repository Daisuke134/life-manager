#!/usr/bin/env bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"  # launchd has a minimal PATH; python3 lives in homebrew
# earning-health-allslots.sh — GENERALIZES the sol-trade/pm-trade barren-earning CONTENT check
# (earning-health.py::is_fresh_but_barren) across every REQUIRED earn slot via ONE shared,
# registry-driven script (self-heal-allslots spec, REQ-AS-001..006). DRY: no per-slot copy-paste
# healthcheck.sh, no N launchd jobs — ONE job (ai.anicca.earning-health-allslots) iterates the
# registry and applies the SAME pure predicate `sol-trade-healthcheck.sh` already proved out.
#
# Adding barren-detection coverage for a new slot = add one registry entry (+ instrument that
# slot's own run.sh to emit {"action":"skip","reason":"..."} lines on a genuine mechanism
# rejection) — never write a new script. A registry entry with instrumented=false is a DOCUMENTED
# GAP (its gapNote explains why): this script logs it as NOT-INSTRUMENTED and NEVER calls
# self-fix.sh for it and NEVER prints OK/BARREN for it — never fabricate a verdict over data that
# does not exist (same "never fabricate, never brick" discipline earning-health.py's own docstring
# establishes).
#
# Instance-agnostic by design (REQ-AS-006): every path is resolved RELATIVE TO THIS SCRIPT'S OWN
# location (mirrors sol-trade-healthcheck.sh's SKILL_DIR-relative pattern), so whichever copy of
# the repo this runs from (a dev checkout, or an ANICCA_HOME-rsynced deployment such as Franklin's
# ~/.blockrun) checks ITS OWN adjacent registry/trace/state — never a different instance's
# hardcoded absolute path baked into shared OSS code. self-fix.sh's OWN bookkeeping paths
# ($HOME/.local/state/life-manager/{state,logs}) remain a documented graduation gap — see
# .vcsdd/features/self-heal-allslots/specs/behavioral-spec.md REQ-AS-006 / CHANGELOG.md.
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGISTRY="${EARNHC_REGISTRY:-$SELF_DIR/earning-health-registry.json}"
EARN_STATE_DIR="${EARNHC_EARN_STATE_DIR:-$SELF_DIR/../earn/state}"
STATE_DIR="${EARNHC_STATE_DIR:-$HOME/.local/state/life-manager/state}"; mkdir -p "$STATE_DIR" 2>/dev/null || true
# FIND-005 test seam (mirrors self-fix.sh's own SELF_FIX_DRYRUN seam): lets a test point the
# self-fix invocation at a stub script that records its raw args, so the sanitization boundary can
# be proven end-to-end without needing self-fix.sh itself to echo its BLOCKER (which it doesn't,
# even under SELF_FIX_DRYRUN=1). Defaults to the real self-fix.sh -- production behavior unchanged.
SELF_FIX_SCRIPT="${EARNHC_SELF_FIX_SCRIPT:-$SELF_DIR/self-fix.sh}"

if [ ! -f "$REGISTRY" ]; then
  echo "$(date '+%F %T') no registry at $REGISTRY -- nothing to check" >&2
  exit 0
fi

# Registry JSON -> one TSV row per slot. Pure field-extraction-with-defaults (no branching logic
# beyond that), so a dedicated unit test isn't split out separately — the wiring tests below
# exercise every field this emits end-to-end (REQ-AS-001, verification-architecture.md).
ROWS="$(python3 -c '
import json, sys
try:
    with open(sys.argv[1]) as f:
        reg = json.load(f)
except Exception as e:
    print(f"__REGISTRY_PARSE_ERROR__\t{e}")
    sys.exit(0)
for s in reg.get("slots", []) or []:
    row = [
        str(s.get("id", "")),
        "1" if s.get("instrumented") else "0",
        str(s.get("traceFile") or ""),
        str(s.get("minRun", 20)),
        str(s.get("selfFixTarget", "")),
        str(s.get("escalateEveryHrs", 24)),
        str(s.get("gapNote", "")).replace("\n", " ").replace("\t", " "),
    ]
    print("\x1f".join(row))
' "$REGISTRY")"

if printf '%s' "$ROWS" | grep -q '^__REGISTRY_PARSE_ERROR__'; then
  echo "$(date '+%F %T') registry at $REGISTRY is not valid JSON -- nothing to check" >&2
  exit 0
fi

# Registry v2's finite state report is the portfolio-facing health contract. Keep the historical
# trace-barren loop below as a second, narrower self-heal layer for trace-backed slots only.
REGISTRY_SCHEMA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("$schema",""))' "$REGISTRY" 2>/dev/null)"
if [ "$REGISTRY_SCHEMA" = "earning-health-registry v2" ]; then
  if RAIL_JSON="$(EARNHC_REGISTRY="$REGISTRY" \
      EARNHC_RUNTIME_ROOT="${EARNHC_RUNTIME_ROOT:-${ANICCA_HOME:-$SELF_DIR/../..}}" \
      node "$SELF_DIR/earning-rail-health.mjs" 2>/dev/null)"; then
    printf '%s' "$RAIL_JSON" | python3 -c '
import json, sys
report = json.load(sys.stdin)
for row in report.get("slots", []):
    print("SLOT {} {} reason={}".format(row.get("id"), str(row.get("state", "degraded")).upper(), row.get("reason", "probe_unavailable")))
for row in report.get("portfolios", []):
    print("PORTFOLIO {} {} reason={}".format(row.get("id"), str(row.get("state", "degraded")).upper(), row.get("reason", "probe_unavailable")))
' | while IFS= read -r health_line; do
      echo "$(date '+%F %T') $health_line" >&2
    done
  else
    echo "$(date '+%F %T') RAIL-HEALTH DEGRADED reason=report_failed" >&2
  fi
fi

while IFS=$'\x1f' read -r ID INSTR TRACEFILE MINRUN TARGET ESC_HRS GAPNOTE; do
  [ -z "$ID" ] && continue

  # REQ-AS-004: a non-instrumented slot is a DOCUMENTED gap, never a fabricated OK/BARREN verdict.
  if [ "$INSTR" != "1" ]; then
    echo "$(date '+%F %T') NOT-INSTRUMENTED $ID -- ${GAPNOTE:-no gapNote recorded}" >&2
    continue
  fi

  # Non-trace v2 probes are already represented by the finite state report above; the legacy
  # barren predicate has no work to do for them.
  [ -z "$TRACEFILE" ] && continue
  TRACE="$EARN_STATE_DIR/$TRACEFILE"
  if [ ! -f "$TRACE" ]; then
    echo "$(date '+%F %T') $ID: no trace file at $TRACE -- nothing to check (not deployed/run here yet)" >&2
    continue
  fi

  # bound the read (trace files grow forever); MINRUN*3 always has headroom for a mix of
  # live-pass/skip lines in between, without reading a multi-hundred-KB file every 5min.
  TAIL_JSON="$(tail -n "$(( MINRUN * 3 ))" "$TRACE" 2>/dev/null)"

  # REQ-AS-002: reuse the SAME pure predicate sol-trade-healthcheck.sh already uses, unmodified.
  # FIND-001: is-barren itself now also recognizes a sustained run of action=="error" (not just
  # "skip") as unhealthy -- see earning-health.py::is_fresh_but_barren / _mechanism_failure_cause.
  if printf '%s\n' "$TAIL_JSON" | python3 "$SELF_DIR/earning-health.py" is-barren "$MINRUN"; then
    # FIND-001: the window's shared cause lives in `reason` for a skip entry, `error` for an error
    # entry (pm-trade's run.sh never writes a `reason` field on its error lines) -- read whichever
    # is present on the LAST line.
    RAW_REASON="$(printf '%s\n' "$TAIL_JSON" | tail -1 | python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read())
    print(d.get("reason") or d.get("error") or "unknown")
except Exception:
    print("unknown")
' 2>/dev/null)"
    # FIND-005: RAW_REASON is trace-derived free text that ultimately feeds self-fix.sh''s
    # --dangerously-skip-permissions autonomous claude spawn prompt with ZERO human confirmation
    # gate -- never let it reach that prompt un-neutralized. Sanitize through the SAME pure
    # allowlist function earning-health.py::sanitize_for_prompt exposes (single source of truth,
    # unit-tested at the pure-core level in test_earning_health.py) -- likewise sanitize the
    # (registry-derived, but defense-in-depth) slot id. The self-fix invocation below embeds ONLY
    # these two sanitized fields into a FIXED structured message, never the raw trace text itself.
    REASON="$(printf '%s' "$RAW_REASON" | python3 "$SELF_DIR/earning-health.py" sanitize-reason 200)"
    [ -z "$REASON" ] && REASON="unspecified"
    SAFE_ID="$(printf '%s' "$ID" | python3 "$SELF_DIR/earning-health.py" sanitize-reason 80)"
    [ -z "$SAFE_ID" ] && SAFE_ID="unspecified-slot"
    # reason=="kill-switch" is that slot's own operator-authored freeze (a literal KILL file the
    # slot's run.sh checks at its own top), not a bug -- see sol-trade-healthcheck.sh's identical
    # guard and SOL-1 (2026-07-17: sol-trade frozen after 850 passes / 0 swaps / $0 realized).
    # Escalating an intentional freeze every ESC_HRS wastes a full self-fix agent spawn forever.
    if [ "$RAW_REASON" = "kill-switch" ]; then
      echo "$(date '+%F %T') $ID FROZEN (intentional KILL file present, reason=kill-switch) -- not a bug, no escalation" >&2
      continue
    fi
    now=$(date +%s)
    # REQ-AS-003: a per-SLOT marker filename (never one shared marker) so N slots never collide.
    SLOTKEY="$(printf '%s' "$ID" | tr -c 'A-Za-z0-9' '_')"
    MK="$STATE_DIR/.earning-health-allslots-${SLOTKEY}-escalated"
    age_hrs=99999
    [ -f "$MK" ] && age_hrs=$(( (now - $(stat -f %m "$MK" 2>/dev/null || echo 0)) / 3600 ))
    if [ "$age_hrs" -ge "$ESC_HRS" ]; then
      touch "$MK"
      echo "$(date '+%F %T') $ID BARREN: last $MINRUN trace lines are all skip/error, cause '$REASON' -> self-fix escalated" >&2
      bash "$SELF_FIX_SCRIPT" "$TARGET" "$SAFE_ID trace is fresh (a new line every wake) but the last $MINRUN wakes are ALL a mechanism-failure action (skip or error) with the identical cause '$REASON' -- the loop is alive but a deterministic guard or a code/env error (identity-mismatch / kill-switch / earn-guard / missing AGENT_HOME / a crashing sub-process) is rejecting or breaking every wake before the agent ever gets to trade. Diagnose why (identity resolution, ANICCA_HOME/ANICCA_REPO path, env) and fix it so the agent actually gets to run its pass." >&2 \
        || echo "$(date '+%F %T') $ID: self-fix launch failed" >&2
    else
      echo "$(date '+%F %T') $ID BARREN but already escalated ${age_hrs}h ago (<${ESC_HRS}h) -- skip (no repeat spam)" >&2
    fi
  else
    echo "$(date '+%F %T') $ID OK (last $MINRUN trace entries are not all-same-cause skip/error)" >&2
  fi
done <<< "$ROWS"
