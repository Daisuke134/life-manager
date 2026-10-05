#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/self-improve-notify.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
SKILL="$TMP/skill"
mkdir -p "$SKILL/scripts" "$SKILL/state/learning" "$TMP/home/.openclaw/logs"
: >"$TMP/life-manager.env"

for helper in score-latest-run.sh topic-supply.sh; do
  printf '#!/usr/bin/env bash\nexit 0\n' >"$SKILL/scripts/$helper"
  chmod +x "$SKILL/scripts/$helper"
done

cat >"$SKILL/scripts/writer_learning_worker.py" <<'PY'
import json
import os
import sys
from pathlib import Path
command = sys.argv[1]
with Path(os.environ["LEARNING_CALLS"]).open("a", encoding="utf-8") as handle:
    handle.write(command + "\n")
if command == "close-canary":
    print(json.dumps({"status": "NO_APPLIED_CANARY"}))
elif command == "offline":
    print(json.dumps({
        "schema_version": 2,
        "status": "AWAITING_MATCHED_CANARY",
        "experiment_id": "learning-2026-07-28",
        "replay_receipts": 6,
    }))
else:
    raise SystemExit(f"unexpected command: {command}")
PY

cat >"$SKILL/scripts/self_improve_control.py" <<'PY'
import json
print(json.dumps({"checked_run": "daily-2026-07-27", "missing_count": 0}))
PY

cat >"$SKILL/scripts/writer_report_worker.py" <<'PY'
import json
import os
from pathlib import Path
Path(os.environ["NOTIFY_MARKER"]).write_text("learning-report\n", encoding="utf-8")
print(json.dumps({"status": "sent", "message_ids": ["fixture-42"]}))
PY

if ! NOTIFY_MARKER="$TMP/notified" \
  LEARNING_CALLS="$TMP/learning-calls" \
  HOME="$TMP/home" \
  LIFE_MANAGER_REPO="$(cd "$ROOT/../.." && pwd)" \
  LIFE_MANAGER_ENV_FILE="$TMP/life-manager.env" \
  WRITER_STATE_DIR="$SKILL/state" \
  ARTICLE_SKILL_DIR="$SKILL" \
  bash "$ROOT/scripts/self-improve.sh" >"$TMP/stdout" 2>"$TMP/stderr"; then
  cat "$TMP/stdout" >&2
  cat "$TMP/stderr" >&2
  exit 1
fi
if [[ "$(cat "$TMP/learning-calls")" != $'close-canary\noffline' ]]; then
  cat "$TMP/learning-calls" >&2
  echo "learning close/offline order is wrong" >&2
  exit 1
fi

if [[ ! -f "$TMP/notified" ]] || [[ "$(cat "$TMP/notified")" != "learning-report" ]]; then
  cat "$TMP/stdout" >&2
  cat "$TMP/stderr" >&2
  echo "learning report marker missing or mismatched" >&2
  exit 1
fi
if ! grep -q '"message_ids": \["fixture-42"\]' "$TMP/stdout"; then
  cat "$TMP/stdout" >&2
  echo "notification receipt missing from stdout" >&2
  exit 1
fi
echo "PASS: 22:30 wrapper reports replay-first learning receipt"

# Replace only this fixture's worker with the real implementation. A corrupt
# same-day offline receipt makes any accidental replay fail before config/model
# work, while the actual wrapper must still verify and report the READY wait.
cp "$ROOT/scripts/writer_learning_worker.py" "$SKILL/scripts/writer_learning_worker.py"
cp "$ROOT/scripts/writer_learning_experiment.py" "$SKILL/scripts/writer_learning_experiment.py"
CANDIDATE_HASH="$(python3 - "$SKILL/state" <<'PY'
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

state = Path(sys.argv[1])
learning = state / "learning"
experiment_id = "existing-canary"
candidate = b'{"headline_style":"reader-first"}\n'
candidate_hash = hashlib.sha256(candidate).hexdigest()
assignment = {
    "schema_version": 2,
    "status": "READY",
    "experiment_id": experiment_id,
    "candidate_strategy_sha256": candidate_hash,
}
assignment_path = learning / "canary-assignment.json"
assignment_path.write_text(json.dumps(assignment, sort_keys=True) + "\n", encoding="utf-8")
strategy = learning / "strategies" / f"{candidate_hash}.json"
strategy.parent.mkdir(parents=True)
strategy.write_bytes(candidate)
experiment = learning / "experiments" / experiment_id
experiment.mkdir(parents=True)
(experiment / "manifest.json").write_bytes(b"fixture manifest bytes\n")
receipt = learning / "offline-receipts" / (
    f"learning-{datetime.now().astimezone().date().isoformat()}.json"
)
receipt.parent.mkdir(parents=True)
receipt.write_text("fixture sentinel: offline must not read this\n", encoding="utf-8")
print(candidate_hash)
PY
)"
cp "$SKILL/state/learning/canary-assignment.json" "$TMP/ready-assignment"
cp "$SKILL/state/learning/strategies/$CANDIDATE_HASH.json" "$TMP/ready-candidate"
cp "$SKILL/state/learning/experiments/existing-canary/manifest.json" "$TMP/ready-manifest"
cp "$(printf '%s' "$SKILL/state/learning/offline-receipts"/*.json)" "$TMP/offline-sentinel"
rm -f "$TMP/notified"
if ! NOTIFY_MARKER="$TMP/notified" \
  HOME="$TMP/home" \
  LIFE_MANAGER_REPO="$(cd "$ROOT/../.." && pwd)" \
  LIFE_MANAGER_ENV_FILE="$TMP/life-manager.env" \
  WRITER_STATE_DIR="$SKILL/state" \
  ARTICLE_SKILL_DIR="$SKILL" \
  bash "$ROOT/scripts/self-improve.sh" >"$TMP/ready-stdout" 2>"$TMP/ready-stderr"; then
  cat "$TMP/ready-stdout" >&2
  cat "$TMP/ready-stderr" >&2
  echo "READY wrapper must not start offline replay" >&2
  exit 1
fi
if ! grep -q '"status": "AWAITING_MATCHED_CANARY"' "$TMP/ready-stdout"; then
  cat "$TMP/ready-stdout" >&2
  echo "READY close result missing from wrapper output" >&2
  exit 1
fi
if ! grep -q '"checked_run": "daily-2026-07-27"' "$TMP/ready-stdout"; then
  cat "$TMP/ready-stdout" >&2
  echo "READY wrapper did not reach verification" >&2
  exit 1
fi
if [[ ! -f "$TMP/notified" ]] || [[ "$(cat "$TMP/notified")" != "learning-report" ]]; then
  cat "$TMP/ready-stdout" >&2
  cat "$TMP/ready-stderr" >&2
  echo "READY wrapper did not reach reporting" >&2
  exit 1
fi
cmp -s "$TMP/ready-assignment" "$SKILL/state/learning/canary-assignment.json"
cmp -s "$TMP/ready-candidate" "$SKILL/state/learning/strategies/$CANDIDATE_HASH.json"
cmp -s "$TMP/ready-manifest" "$SKILL/state/learning/experiments/existing-canary/manifest.json"
cmp -s "$TMP/offline-sentinel" "$(printf '%s' "$SKILL/state/learning/offline-receipts"/*.json)"
if ! grep -q '"message_ids": \["fixture-42"\]' "$TMP/ready-stdout"; then
  cat "$TMP/ready-stdout" >&2
  echo "notification receipt missing from READY wrapper output" >&2
  exit 1
fi
echo "PASS: offline fallback remains; READY waits and reaches verify/report"
