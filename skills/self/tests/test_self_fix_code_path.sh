#!/usr/bin/env bash
# test_self_fix_code_path.sh — S1/#6063 regression test for skills/self/lib/self_fix_code_path.sh.
# Covers the three pure guard rails with no network/git/gh calls: scope guard, backoff decision,
# test-baseline comparison. Uses a throwaway git repo + throwaway state dir; never touches the real
# $HOME/.local/state/life-manager or the real origin.
set -uo pipefail
P=0; F=0
ok(){ echo "  ok $1"; P=$((P+1)); }
fail(){ echo "  FAIL $1"; F=$((F+1)); }

LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/lib/self_fix_code_path.sh"
# shellcheck source=../lib/self_fix_code_path.sh
source "$LIB"

echo "--- scope-check: allowlisted-only diff passes ---"
REPO="$(mktemp -d)"
git -C "$REPO" init -q
git -C "$REPO" -c user.email=t@t -c user.name=t commit -q --allow-empty -m base
BASE_SHA="$(git -C "$REPO" rev-parse HEAD)"
mkdir -p "$REPO/skills/capafy-autopublish/scripts" "$REPO/skills/other-loop"
echo one > "$REPO/skills/capafy-autopublish/scripts/x.py"
git -C "$REPO" add -A
if sfcp_scope_check "$REPO" "$BASE_SHA" "$SFCP_DEFAULT_ALLOWLIST_REGEX" 2>/tmp/sfcp_scope_out.$$; then
  ok "in-scope-only diff -> scope-check passes"
else
  fail "in-scope-only diff should pass: $(cat /tmp/sfcp_scope_out.$$)"
fi

echo "--- scope-check: any file outside allowlist fails the WHOLE diff ---"
echo two > "$REPO/skills/other-loop/y.py"
git -C "$REPO" add -A
if sfcp_scope_check "$REPO" "$BASE_SHA" "$SFCP_DEFAULT_ALLOWLIST_REGEX" 2>/tmp/sfcp_scope_out2.$$; then
  fail "out-of-scope file should have failed scope-check"
else
  grep -q "skills/other-loop/y.py" /tmp/sfcp_scope_out2.$$ && ok "out-of-scope diff -> scope-check fails and names the violator" \
    || fail "scope-check failed but did not name the violating file"
fi
rm -f /tmp/sfcp_scope_out.$$ /tmp/sfcp_scope_out2.$$

echo "--- scope-check: diff-size cap ---"
REPO2="$(mktemp -d)"
git -C "$REPO2" init -q
git -C "$REPO2" -c user.email=t@t -c user.name=t commit -q --allow-empty -m base
BASE2="$(git -C "$REPO2" rev-parse HEAD)"
mkdir -p "$REPO2/skills/capafy/x"
seq 1 50 > "$REPO2/skills/capafy/x/big.txt"
git -C "$REPO2" add -A
if sfcp_scope_check "$REPO2" "$BASE2" "$SFCP_DEFAULT_ALLOWLIST_REGEX" 10 2>/tmp/sfcp_cap.$$; then
  fail "50-line diff should exceed a 10-line cap"
else
  ok "diff exceeding cap is refused: $(cat /tmp/sfcp_cap.$$)"
fi
if sfcp_scope_check "$REPO2" "$BASE2" "$SFCP_DEFAULT_ALLOWLIST_REGEX" 1000 >/dev/null 2>&1; then
  ok "same diff passes under a generous cap"
else
  fail "same diff should pass under a 1000-line cap"
fi
rm -f /tmp/sfcp_cap.$$
rm -rf "$REPO" "$REPO2"

echo "--- new-failures: baseline comparison ---"
BASELINE="$(mktemp)"; CURRENT="$(mktemp)"
printf 'test_a\ntest_b\n' > "$BASELINE"
printf 'test_a\ntest_b\n' > "$CURRENT"
if sfcp_new_failures "$BASELINE" "$CURRENT" >/tmp/sfcp_nf1.$$; then
  ok "identical failure sets -> no new failures"
else
  fail "identical failure sets should report clean: $(cat /tmp/sfcp_nf1.$$)"
fi
printf 'test_a\ntest_b\ntest_c\n' > "$CURRENT"
if sfcp_new_failures "$BASELINE" "$CURRENT" >/tmp/sfcp_nf2.$$; then
  fail "a genuinely new failing test should be detected"
else
  grep -q '^test_c$' /tmp/sfcp_nf2.$$ && ok "new failing test test_c is detected" \
    || fail "new-failures did not name test_c: $(cat /tmp/sfcp_nf2.$$)"
fi
rm -f "$BASELINE" "$CURRENT" /tmp/sfcp_nf1.$$ /tmp/sfcp_nf2.$$

echo "--- backoff: no prior result -> ALLOW ---"
STATE="$(mktemp -d)"
DEC="$(sfcp_backoff_decision capafy-loop "$STATE" 2000000000)"
[[ "$DEC" == ALLOW* ]] && ok "no prior result -> ALLOW ($DEC)" || fail "expected ALLOW, got: $DEC"

echo "--- backoff: FAIL outcome re-allows after 60min but not before ---"
sfcp_record capafy-loop FAIL "$STATE" "some code bug"
NOW="$(($(awk '{print $2}' "$STATE/.self-fix-code-path-capafy-loop.result") + 30*60))"
DEC="$(sfcp_backoff_decision capafy-loop "$STATE" "$NOW")"
[[ "$DEC" == SKIP* ]] && ok "FAIL + 30min -> still backing off ($DEC)" || fail "expected SKIP at 30min after FAIL, got: $DEC"
NOW="$(($(awk '{print $2}' "$STATE/.self-fix-code-path-capafy-loop.result") + 61*60))"
DEC="$(sfcp_backoff_decision capafy-loop "$STATE" "$NOW")"
[[ "$DEC" == ALLOW* ]] && ok "FAIL + 61min -> re-allowed ($DEC)" || fail "expected ALLOW at 61min after FAIL, got: $DEC"

echo "--- backoff: SUCCESS outcome keeps the long (1200min) backoff ---"
rm -f "$STATE/.self-fix-code-path-capafy-loop.result" "$STATE/.self-fix-code-path-capafy-loop.daily"
sfcp_record capafy-loop SUCCESS "$STATE" "shipped fix"
NOW="$(($(awk '{print $2}' "$STATE/.self-fix-code-path-capafy-loop.result") + 61*60))"
DEC="$(sfcp_backoff_decision capafy-loop "$STATE" "$NOW")"
[[ "$DEC" == SKIP* ]] && ok "SUCCESS + 61min -> still in the long backoff ($DEC)" || fail "expected SKIP at 61min after SUCCESS, got: $DEC"
NOW="$(($(awk '{print $2}' "$STATE/.self-fix-code-path-capafy-loop.result") + 1201*60))"
DEC="$(sfcp_backoff_decision capafy-loop "$STATE" "$NOW")"
[[ "$DEC" == ALLOW* ]] && ok "SUCCESS + 1201min -> re-allowed ($DEC)" || fail "expected ALLOW at 1201min after SUCCESS, got: $DEC"

echo "--- backoff: daily cap blocks further dispatches even when otherwise ALLOW ---"
rm -f "$STATE/.self-fix-code-path-capafy-loop.result" "$STATE/.self-fix-code-path-capafy-loop.daily"
NOW=2000000000
for i in 1 2 3 4 5 6; do sfcp_bump_daily_count capafy-loop "$STATE" "$NOW"; done
DEC="$(sfcp_backoff_decision capafy-loop "$STATE" "$NOW")"
[[ "$DEC" == SKIP*daily_cap* ]] && ok "6th dispatch same day -> daily cap SKIP ($DEC)" || fail "expected daily_cap SKIP, got: $DEC"
rm -rf "$STATE"

echo
echo "self_fix_code_path: $P ok, $F failed"
[ "$F" -eq 0 ]
