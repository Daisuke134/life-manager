#!/usr/bin/env bash
# test_verify_loops_audit_capafy_cap_full.sh — self-fix 2026-07-19 regression test. Reproduced live:
# published.jsonl stale >=30h fired the capafy self-fix on every 6h audit pass even when
# inventory_status.py's own server-truth verdict was CAP_FULL (Capafy's 5-slot review cap
# saturated, all 5 genuinely under_review -- an external condition, not a code bug) or DRAINED
# (finite inventory fully published -- healthy idle). This is the exact false-alarm class
# inventory_status.py's docstring (2026-07-08) was written to solve for the daily loop itself, but
# it was never consulted by THIS separate audit script. Proves: (a) stale + CAP_FULL -> no
# escalation, (b) stale + DRAINED -> no escalation, (c) stale + PUBLISHABLE (a genuine stuck
# pipeline) -> escalation still fires, (d) inventory_status.py missing/unreadable -> fails OPEN to
# the old behavior (escalation fires) so a real break can never be silently swallowed.
set -uo pipefail
P=0; F=0
ok(){ echo "  ok $1"; P=$((P+1)); }
fail(){ echo "  FAIL $1"; F=$((F+1)); }

REAL_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/verify-loops-audit.sh"

setup(){
  FAKE_SELF="$(mktemp -d)"
  FAKE_HOME="$(mktemp -d)"
  mkdir -p "$FAKE_HOME/.openclaw/state" "$FAKE_HOME/.openclaw/logs" \
           "$FAKE_HOME/.openclaw/skills/capafy-autopublish/state" \
           "$FAKE_HOME/.openclaw/skills/capafy-autopublish/scripts" \
           "$FAKE_SELF/reddit-loop/state" "$FAKE_SELF/life-manager-loop/state"
  cat > "$FAKE_SELF/verify-loops.sh" <<'EOF'
#!/usr/bin/env bash
echo "stub verify-loops output"
EOF
  cat > "$FAKE_SELF/cadence-deadline-check.sh" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  cat > "$FAKE_SELF/cadence-evidence.py" <<'PYEOF'
import json, sys
loop = sys.argv[2]
print(json.dumps({"loop": loop, "met": True, "streak": 1, "scorecard": "ok"}))
PYEOF
  SELF_FIX_CALLS="$FAKE_HOME/.openclaw/state/self-fix-calls.log"
  cat > "$FAKE_SELF/self-fix.sh" <<EOF
#!/usr/bin/env bash
echo "\$1" >> "$SELF_FIX_CALLS"
EOF
  chmod +x "$FAKE_SELF/self-fix.sh" "$FAKE_SELF/verify-loops.sh" "$FAKE_SELF/cadence-deadline-check.sh"
  : > "$FAKE_SELF/reddit-loop/state/posts.jsonl"
  # stale published.jsonl (mtime far in the past) so the >=30h condition is true in every scenario
  # here -- this test isolates ONLY the live-verdict gate.
  touch -t 202001010000 "$FAKE_HOME/.openclaw/skills/capafy-autopublish/state/published.jsonl"
}
capafy_call_count(){ local f="$FAKE_HOME/.openclaw/state/self-fix-calls.log"; [ -f "$f" ] || { echo 0; return; }; local n; n="$(grep -c '^capafy$' "$f" 2>/dev/null)"; echo "${n:-0}"; }
run(){ HOME="$FAKE_HOME" LIFE_MANAGER_REPO="$FAKE_HOME/.openclaw" VERIFY_LOOPS_SELF_DIR="$FAKE_SELF" VERIFY_LOOPS_AUDIT_CURL_BIN=/bin/false bash "$REAL_SCRIPT" >/dev/null 2>&1; }
stub_inventory(){ cat > "$FAKE_HOME/.openclaw/skills/capafy-autopublish/scripts/inventory_status.py" <<PYEOF
print("VERDICT=$1")
PYEOF
}

# --- scenario 1 (THE FIX): stale + CAP_FULL (external: Capafy's own 5-slot review cap saturated) ---
setup
stub_inventory CAP_FULL
run
[ "$(capafy_call_count)" = 0 ] && ok "stale + CAP_FULL -> 0 capafy self-fix calls (external, not a code bug)" \
  || fail "CAP_FULL false alarm: expected 0 calls, got $(capafy_call_count)"
rm -rf "$FAKE_SELF" "$FAKE_HOME"

# --- scenario 2: stale + DRAINED (finite inventory fully published) -> no escalation ---
setup
stub_inventory DRAINED
run
[ "$(capafy_call_count)" = 0 ] && ok "stale + DRAINED -> 0 capafy self-fix calls (healthy idle)" \
  || fail "DRAINED false alarm: expected 0 calls, got $(capafy_call_count)"
rm -rf "$FAKE_SELF" "$FAKE_HOME"

# --- scenario 3 (no regression): stale + PUBLISHABLE (a real stuck pipeline) -> escalation fires ---
setup
stub_inventory PUBLISHABLE
run
[ "$(capafy_call_count)" = 1 ] && ok "stale + PUBLISHABLE -> 1 capafy self-fix call (genuine bug still caught)" \
  || fail "real bug swallowed: expected 1 call, got $(capafy_call_count)"
rm -rf "$FAKE_SELF" "$FAKE_HOME"

# --- scenario 4 (fail open): inventory_status.py missing -> falls back to the old stale-only check ---
setup
rm -f "$FAKE_HOME/.openclaw/skills/capafy-autopublish/scripts/inventory_status.py"
run
[ "$(capafy_call_count)" = 1 ] && ok "inventory_status.py missing -> 1 capafy self-fix call (fails open, old behavior)" \
  || fail "fail-open broken: expected 1 call, got $(capafy_call_count)"
rm -rf "$FAKE_SELF" "$FAKE_HOME"

echo "=== test_verify_loops_audit_capafy_cap_full: $P passed $F failed ==="
[ "$F" = 0 ] && exit 0 || exit 1
