#!/usr/bin/env bash
# test_verify_loops_audit_capafy_label_mismatch.sh — G2 item3 regression test (2026-07-11
# loop-arch redesign / LOOPS-TRUTH-AUDIT.md: "capafy: 'PUBLISHED/DRAINED'等ラベルの誤表示を実
# side-effect(新listing/新post)で照合してない"). Confirmed real incident 2026-07-11:
# daily_loop.log's own "done" line read '...rc=1 (PUBLISHED — post-verdict=DRAINED, marker
# touched)' immediately after 'Error: Reached max turns' and a reconcile pass with appended=0 --
# PUBLISHED there is a static post-verdict label, not proof a listing went live. Proves: (a) a
# PUBLISHED-labeled done-line with zero new live published.jsonl rows today escalates self-fix,
# (b) a PUBLISHED-labeled done-line THAT DOES have a real new live row today does NOT escalate,
# (c) a done-line that never claims PUBLISHED at all does NOT escalate via this check. Mirrors
# this codebase's own fake-SELF-dir stubbing convention.
set -uo pipefail
P=0; F=0
ok(){ echo "  ok $1"; P=$((P+1)); }
fail(){ echo "  FAIL $1"; F=$((F+1)); }

REAL_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/verify-loops-audit.sh"
TODAY_JST="$(TZ=Asia/Tokyo date +%F)"

setup(){
  FAKE_SELF="$(mktemp -d)"
  FAKE_HOME="$(mktemp -d)"
  mkdir -p "$FAKE_HOME/.openclaw/state" "$FAKE_HOME/.openclaw/logs" \
           "$FAKE_HOME/.openclaw/skills/capafy-autopublish/state" \
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
  # fresh published.jsonl (mtime=now) so the pre-existing stale_hrs>=30 escalation never fires
  # here -- this test isolates ONLY the new label-vs-reality check.
  : > "$FAKE_HOME/.openclaw/skills/capafy-autopublish/state/published.jsonl"
}
capafy_call_count(){ local f="$FAKE_HOME/.openclaw/state/self-fix-calls.log"; [ -f "$f" ] || { echo 0; return; }; local n; n="$(grep -c '^capafy$' "$f" 2>/dev/null)"; echo "${n:-0}"; }
run(){ HOME="$FAKE_HOME" LIFE_MANAGER_REPO="$FAKE_HOME/.openclaw" VERIFY_LOOPS_SELF_DIR="$FAKE_SELF" VERIFY_LOOPS_AUDIT_CURL_BIN=/bin/false bash "$REAL_SCRIPT" >/dev/null 2>&1; }

# --- scenario 1 (THE FIX): daily_loop.log's newest done-line claims PUBLISHED but published.jsonl
# gained NO new live (status=4/online) row today -- the real 2026-07-11 incident -> escalation
# MUST fire ---
setup
cat > "$FAKE_HOME/.openclaw/skills/capafy-autopublish/state/daily_loop.log" <<'EOF'
=== 2026-07-11 12:36:55 daily_loop start ===
Error: Reached max turns (40)=== 2026-07-11 12:36:55 daily_loop done rc=1 (PUBLISHED — post-verdict=DRAINED, marker touched) ===
EOF
: > "$FAKE_HOME/.openclaw/skills/capafy-autopublish/state/published.jsonl"
run
[ "$(capafy_call_count)" = 1 ] && ok "PUBLISHED-labeled done-line + zero new live rows today -> 1 capafy self-fix call (the fix)" \
  || fail "label lie: expected 1 call, got $(capafy_call_count) (label-vs-reality check not wired)"
rm -rf "$FAKE_SELF" "$FAKE_HOME"

# --- scenario 2 (no false positive): PUBLISHED-labeled done-line AND a real new live row landed
# today (status contains status=4) -> NO escalation ---
setup
cat > "$FAKE_HOME/.openclaw/skills/capafy-autopublish/state/daily_loop.log" <<'EOF'
=== 2026-07-11 12:36:55 daily_loop start ===
=== 2026-07-11 12:36:55 daily_loop done rc=0 (PUBLISHED — post-verdict=PUBLISHABLE, marker touched) ===
EOF
printf '{"agent_id": "1", "title": "Real New Listing", "status": "online (status=4 listed)", "date": "%s"}\n' "$TODAY_JST" \
  > "$FAKE_HOME/.openclaw/skills/capafy-autopublish/state/published.jsonl"
run
[ "$(capafy_call_count)" = 0 ] && ok "PUBLISHED label + real new status=4 row today -> 0 capafy self-fix calls (label is true)" \
  || fail "label is true: expected 0 calls, got $(capafy_call_count)"
rm -rf "$FAKE_SELF" "$FAKE_HOME"

# --- scenario 3 (guard preserved): done-line never claims PUBLISHED at all (e.g. legitimately
# "no action taken this pass") -> this check never fires regardless of the ledger ---
setup
cat > "$FAKE_HOME/.openclaw/skills/capafy-autopublish/state/daily_loop.log" <<'EOF'
=== 2026-07-11 12:36:55 daily_loop start ===
=== 2026-07-11 12:36:55 daily_loop done rc=0 (NOOP — nothing publishable this pass) ===
EOF
: > "$FAKE_HOME/.openclaw/skills/capafy-autopublish/state/published.jsonl"
run
[ "$(capafy_call_count)" = 0 ] && ok "no PUBLISHED claim in done-line -> 0 capafy self-fix calls (nothing to check)" \
  || fail "no PUBLISHED claim: expected 0 calls, got $(capafy_call_count)"
rm -rf "$FAKE_SELF" "$FAKE_HOME"

echo "=== test_verify_loops_audit_capafy_label_mismatch: $P passed $F failed ==="
[ "$F" = 0 ] && exit 0 || exit 1
