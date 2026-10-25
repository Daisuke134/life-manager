#!/usr/bin/env bash
# merge-when-green must never merge while a check is pending or failed.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/gh" <<'GH'
#!/usr/bin/env bash
if [ "$1 $2" = "pr view" ]; then printf '%s\t%s\n' "$STUB_HEAD" "$STUB_CHECK_STATE"; exit 0; fi
if [ "$1 $2" = "run list" ]; then printf '%s\n' "$STUB_WORKFLOW"; exit 0; fi
if [ "$1 $2" = "pr merge" ]; then echo "merged $*" >> "$STUB_LOG"; exit 0; fi
exit 1
GH
chmod +x "$TMP/gh"
export PATH="$TMP:$PATH" STUB_LOG="$TMP/log" MERGE_WHEN_GREEN_POLL=0 MERGE_WHEN_GREEN_TRIES=2
fail=0
run() {
  : > "$STUB_LOG"
  STUB_HEAD=abc123 STUB_CHECK_STATE="$1" STUB_WORKFLOW="$2" \
    bash "$ROOT/bin/merge-when-green" 123 >/dev/null 2>&1
  echo $?
}
[ "$(run green 'abc123 completed success')" = 0 ] && grep -q merged "$STUB_LOG" || { echo "FAIL green checks and mandatory workflow should merge"; fail=1; }
[ "$(run pending 'abc123 completed success')" != 0 ] && ! grep -q merged "$STUB_LOG" || { echo "FAIL pending check must not merge"; fail=1; }
[ "$(run fail 'abc123 completed success')" = 2 ] && ! grep -q merged "$STUB_LOG" || { echo "FAIL failed check must not merge"; fail=1; }
[ "$(run green 'abc123 completed failure')" = 2 ] && ! grep -q merged "$STUB_LOG" || { echo "FAIL failed mandatory workflow must not merge"; fail=1; }
[ "$(run unknown 'abc123 completed success')" = 2 ] && ! grep -q merged "$STUB_LOG" || { echo "FAIL unknown check state must fail closed"; fail=1; }
[ "$(run none 'abc123 completed success')" != 0 ] && ! grep -q merged "$STUB_LOG" || { echo "FAIL missing checks must not merge"; fail=1; }
[ "$(run green 'abc123 in_progress')" != 0 ] && ! grep -q merged "$STUB_LOG" || { echo "FAIL incomplete required workflow must not merge"; fail=1; }
[ "$(run green 'different-head completed success')" != 0 ] && ! grep -q merged "$STUB_LOG" || { echo "FAIL workflow on a different head must not merge"; fail=1; }
run green 'abc123 completed success' >/dev/null; grep -q -- "--match-head-commit abc123" "$STUB_LOG" || { echo "FAIL head not pinned"; fail=1; }
[ $fail = 0 ] && echo PASS
exit $fail
