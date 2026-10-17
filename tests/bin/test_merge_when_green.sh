#!/usr/bin/env bash
# merge-when-green must never merge while a check is pending or failed.
set -u
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cat > "$TMP/gh" <<'GH'
#!/usr/bin/env bash
if [ "$1 $2" = "pr checks" ]; then cat "$STUB_STATES"; exit 0; fi
if [ "$1 $2" = "pr merge" ]; then echo merged >> "$STUB_LOG"; exit 0; fi
exit 1
GH
chmod +x "$TMP/gh"
export PATH="$TMP:$PATH" STUB_LOG="$TMP/log" MERGE_WHEN_GREEN_POLL=0 MERGE_WHEN_GREEN_TRIES=2
fail=0
run() { : > "$STUB_LOG"; printf '%s\n' "$1" > "$TMP/states"; STUB_STATES="$TMP/states" bash "$ROOT/bin/merge-when-green" 123 >/dev/null 2>&1; echo $?; }
[ "$(run 'SUCCESS SUCCESS')" = 0 ] && grep -q merged "$STUB_LOG" || { echo "FAIL green should merge"; fail=1; }
[ "$(run 'SUCCESS IN_PROGRESS')" != 0 ] && ! grep -q merged "$STUB_LOG" || { echo "FAIL pending must not merge"; fail=1; }
[ "$(run 'SUCCESS FAILURE')" != 0 ] && ! grep -q merged "$STUB_LOG" || { echo "FAIL failure must not merge"; fail=1; }
[ "$(run '')" != 0 ] && ! grep -q merged "$STUB_LOG" || { echo "FAIL no checks must not merge"; fail=1; }
[ $fail = 0 ] && echo PASS
exit $fail
