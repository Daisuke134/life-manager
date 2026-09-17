#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="${LM_TEST_TMP:-$(mktemp -d)}"
mkdir -p "$TMP"
if [ -z "${LM_TEST_TMP:-}" ]; then trap 'rm -rf "$TMP"' EXIT; fi

VIDEO="$TMP/video.mp4"
touch "$VIDEO"

cat >"$TMP/generate.sh" <<EOF
#!/usr/bin/env bash
printf '%s\n' '{"selected_id":"B03","output":"$VIDEO","duration_seconds":1}'
EOF

cat >"$TMP/distribute.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
[ "${1:-}" = "--creative-id" ]
[ "${3:-}" = "--platform" ]
[ "${4:-}" = "tiktok" ]
printf '%s\n' '{"creative_id":"B03","public_url":"https://www.tiktok.com/@anicca.comedy/video/123"}'
EOF

cat >"$TMP/self-improve.sh" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' '{"creative_id":"B03","status":"done","day_index":1,"next_creative_id":"B04","next_change_reason":"keep the hook"}'
EOF

cat >"$TMP/agent.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
while [ "$#" -gt 0 ]; do
  if [ "$1" = "--evidence-dir" ]; then
    EVIDENCE="$2"
    shift 2
  else
    shift
  fi
done
mkdir -p "$EVIDENCE"
printf '%s\n' '{"status":"success","selected_provider":"codex","selected_model":"gpt-5.6-luna"}' >"$EVIDENCE/summary.json"
EOF
chmod +x "$TMP"/*.sh

LM_DAILY_PLATFORM=tiktok \
LM_VIDEO_GENERATOR="$TMP/generate.sh" \
LM_VIDEO_DISTRIBUTOR="$TMP/distribute.sh" \
LM_MARKETING_SELF_IMPROVER="$TMP/self-improve.sh" \
RUN_AGENT_BIN="$TMP/agent.sh" \
LM_DATA_DIR="$TMP/data" \
LM_DAILY_LOG="$TMP/daily.log" \
LM_DAILY_RUN_LEDGER="$TMP/run-ledger.jsonl" \
LM_DAILY_USAGE_LEDGER="$TMP/usage.jsonl" \
LM_MARKETING_LEDGER="$TMP/marketing.jsonl" \
bash "$ROOT/skills/life-manager/life-manager-daily.sh"

grep -q 'daily distribution readback complete platform=tiktok creative=B03' "$TMP/daily.log"
grep -q '"status":"success"' "$TMP/run-ledger.jsonl"
echo "life-manager-daily TikTok-only contract: PASS"
