#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PUB="$ROOT/vendor/capafy-publisher"
STATE_HOME="$(mktemp -d)"
cleanup(){ rm -rf "$STATE_HOME"; }
trap cleanup EXIT
OPERATOR_HOME_TOKEN='$HOME'
OPENCLAW_PATH_SUFFIX='/.openclaw'

for script in "$ROOT/scripts/publish_prepare.sh" "$ROOT/scripts/publish_finish.sh"; do
  rg -q '^CAPAFY_PUBLISHER_STATE_HOME="\$\{CAPAFY_PUBLISHER_STATE_HOME:-\$LIFE_MANAGER_STATE_HOME/runtime/capafy-publisher\}"$' "$script"
  rg -q '^export CAPAFY_PUBLISHER_STATE_HOME$' "$script"
done
if rg -qF "${OPERATOR_HOME_TOKEN}${OPENCLAW_PATH_SUFFIX}" "$ROOT/scripts/publish_prepare.sh" "$ROOT/scripts/publish_finish.sh"; then
  echo "FAIL: publisher entrypoints read operator OpenClaw state" >&2
  exit 1
fi

for id in 1037238583 7631594519; do
  got="$(cd "$PUB" && LIFE_MANAGER_STATE_HOME="$STATE_HOME" CAPAFY_PUBLISH_WORK_DIR="$STATE_HOME/runtime/capafy-publisher/work/agents/$id" python3 - <<'PY'
from packaging.common.constants import DEVELOPER_WORK_DIR_PATH
print(DEVELOPER_WORK_DIR_PATH)
PY
)"
  [ "$got" = "$STATE_HOME/runtime/capafy-publisher/work/agents/$id" ] || { echo "FAIL $got"; exit 1; }
done

jq -e '.version == "0.9.11"' "$PUB/api-docs/index.json" >/dev/null || {
  echo "FAIL: vendored publisher is not exactly 0.9.11" >&2
  exit 1
}

(
  cd "$PUB"
  python3 - <<'PY'
from capafy_platform import api, http

calls = []

def fake_request(method, url, *args, **kwargs):
    calls.append((method, url, kwargs))
    return {"code": 0, "data": {}}, 200

http.request = fake_request
api.create_agent({}, access_token="test-token", base_url="https://capafy.test")
api.create_agent_version({}, access_token="test-token", base_url="https://capafy.test")
api.submit_package_credentials_raw(
    "agent-1", {}, access_token="test-token", base_url="https://capafy.test"
)
assert [entry[2].get("max_attempts") for entry in calls] == [1, 1, 1]
print("PASS")
PY
)

(
  cd "$PUB"
  python3 - <<'PY'
from packaging.publish.platform.runtime_mapping import LatestVersion

base = {
    "agentId": "agent-1",
    "agentVersionId": "version-1",
    "agentType": "run_online",
    "agentRuntime": "openclaw",
    "isConfirmedSkills": 1,
    "isConfirmedConfigKeys": 0,
    "status": 0,
    "auditStatus": 0,
    "workflowInfo": {},
    "agentPackageId": "pkg-1",
}
pending = LatestVersion.from_response(
    "agent-1", {**base, "packageUrl": "pending://draft"}
).public_payload()
uploaded = LatestVersion.from_response(
    "agent-1", {**base, "packageUrl": "https://storage.example/pkg.zip"}
).public_payload()
assert pending["platform_status"] == 0
assert pending["audit_status"] == 0
assert pending["is_confirmed_skills"] is True
assert pending["is_confirmed_config_keys"] is False
assert pending["agent_package_id"] == "pkg-1"
assert pending["package_uploaded"] is False
assert uploaded["package_uploaded"] is True
print("PASS")
PY
)

SELECTOR="$ROOT/scripts/select_publish_agent.py"
existing_id="$(printf '%s' '{"agents":[{"agent_id":"existing-1","name":"Existing","agent_type":"run_online","agent_status":"draft"}]}' | python3 "$SELECTOR" --title Existing)"
[ "$existing_id" = "existing-1" ] || { echo "FAIL: existing Agent fixture" >&2; exit 1; }
online_id="$(printf '%s' '{"agents":[{"agent_id":"9563867391","name":"Marketing Strategist — The One Move to Make","agent_status":"online"}]}' | python3 "$SELECTOR" --title 'Marketing Strategist — The One Move to Make')"
[ "$online_id" = "9563867391" ] || { echo "FAIL: same-Agent online version selection" >&2; exit 1; }
update_fixture='{"agents":[{"agent_id":"9563867391","name":"Marketing Strategist — The One Move to Make","agent_status":"online","latest_agent_version_id":"2070737929294868480"}]}'
update_id="$(printf '%s' "$update_fixture" | python3 "$SELECTOR" --title 'Marketing Strategist — The One Move to Make' --require-free-slot --expected-agent-id 9563867391 --expected-version-id 2070737929294868480)"
[ "$update_id" = "9563867391" ] || { echo "FAIL: same-Agent source version preflight" >&2; exit 1; }
if printf '%s' "$update_fixture" | python3 "$SELECTOR" --title 'Marketing Strategist — The One Move to Make' --require-free-slot --expected-agent-id 9563867391 --expected-version-id wrong-version >/dev/null 2>&1; then
  echo "FAIL: stale same-Agent source version was accepted" >&2
  exit 1
fi
if printf '%s' '{"agents":[{"agent_id":"online-1","name":"Online","agent_status":"online"},{"agent_id":"r1","name":"R1","agent_status":"under_review"},{"agent_id":"r2","name":"R2","agent_status":"under_review"},{"agent_id":"r3","name":"R3","agent_status":"under_review"},{"agent_id":"r4","name":"R4","agent_status":"under_review"},{"agent_id":"r5","name":"R5","agent_status":"under_review"}]}' | python3 "$SELECTOR" --title Online --require-free-slot >/dev/null 2>&1; then
  echo "FAIL: same-Agent new version bypassed CAP_FULL" >&2
  exit 1
fi
new_id="$(printf '%s' '{"agents":[{"agent_id":"other-1","name":"Other","agent_type":"run_online","agent_status":"banned"}]}' | python3 "$SELECTOR" --title New)"
[ -z "$new_id" ] || { echo "FAIL: new Agent fixture fell through" >&2; exit 1; }
if printf '%s' '{"agents":[{"agent_id":"a-1","name":"Duplicate","agent_status":"draft"},{"agent_id":"a-2","name":"Duplicate","agent_status":"draft"}]}' | python3 "$SELECTOR" --title Duplicate >/dev/null 2>&1; then
  echo "FAIL: duplicate exact title was accepted" >&2
  exit 1
fi
if printf '%s' '{"agents":[{"agentId":"legacy-1","name":"Legacy","agentStatus":"draft"}]}' | python3 "$SELECTOR" --title Legacy >/dev/null 2>&1; then
  echo "FAIL: legacy camelCase list shape was accepted" >&2
  exit 1
fi
if printf '%s' '{"agents":[{"agent_id":"rejected-1","name":"Rejected","agent_type":"run_online","agent_status":"review_rejected"}]}' | python3 "$SELECTOR" --title Other --reuse-agent-id rejected-1 >/dev/null 2>&1; then
  echo "FAIL: mismatched explicit reuse was accepted" >&2
  exit 1
fi
reuse_id="$(printf '%s' '{"agents":[{"agent_id":"rejected-1","name":"Rejected","agent_type":"run_online","agent_status":"review_rejected"}]}' | python3 "$SELECTOR" --title Rejected --reuse-agent-id rejected-1)"
[ "$reuse_id" = "rejected-1" ] || { echo "FAIL: explicit reuse fixture" >&2; exit 1; }
if printf '%s' '{"agents":[{"agent_id":"online-1","name":"Online","agent_status":"online"}]}' | python3 "$SELECTOR" --title Other --reuse-agent-id online-1 >/dev/null 2>&1; then
  echo "FAIL: explicit reuse accepted non-draft status" >&2
  exit 1
fi

URL_HELPER="$ROOT/scripts/save_review_url.py"
URL_PATH="$STATE_HOME/review-urls/agent-1/init.url"
URL='https://capafy.ai/developer/createAgent?draftKey=draft-key-1&page=edit'
url_result="$(printf '%s' "{\"agent_id\":\"agent-1\",\"review_url\":\"$URL\"}" | python3 "$URL_HELPER" --agent-id agent-1 --output "$URL_PATH")"
[ "$url_result" = "EDIT_URL_FILE=$URL_PATH" ] || { echo "FAIL: edit URL file result" >&2; exit 1; }
[ "$(<"$URL_PATH")" = "$URL" ] || { echo "FAIL: edit URL bytes changed" >&2; exit 1; }
[ "$(stat -f '%Lp' "$URL_PATH")" = "600" ] || { echo "FAIL: edit URL mode" >&2; exit 1; }
[ "$(stat -f '%Lp' "$(dirname "$URL_PATH")")" = "700" ] || { echo "FAIL: edit URL directory mode" >&2; exit 1; }
[ "$(stat -f '%Lp' "$(dirname "$(dirname "$URL_PATH")")")" = "700" ] || { echo "FAIL: edit URL root directory mode" >&2; exit 1; }
SHORT_URL='https://api.capafy.ai/E1234567890123456789'
SHORT_PATH="$STATE_HOME/review-urls/agent-1/short.url"
short_result="$(printf '%s' "{\"agent_id\":\"agent-1\",\"review_url\":\"$SHORT_URL\"}" | python3 "$URL_HELPER" --agent-id agent-1 --output "$SHORT_PATH")"
[ "$short_result" = "EDIT_URL_FILE=$SHORT_PATH" ] || { echo "FAIL: short review URL result" >&2; exit 1; }
[ "$(<"$SHORT_PATH")" = "$SHORT_URL" ] || { echo "FAIL: short review URL bytes changed" >&2; exit 1; }
[ "$(stat -f '%Lp' "$SHORT_PATH")" = "600" ] || { echo "FAIL: short review URL mode" >&2; exit 1; }
if [[ "$short_result" == *"$SHORT_URL"* ]]; then
  echo "FAIL: short review URL leaked to stdout" >&2
  exit 1
fi
for bad_short_url in \
  'http://api.capafy.ai/E1234567890123456789' \
  'https://api.capafy.ai:443/E1234567890123456789' \
  'https://user@api.capafy.ai/E1234567890123456789' \
  'https://api.capafy.ai/E1234567890123456789?x=1' \
  'https://api.capafy.ai/E1234567890123456789#fragment' \
  'https://api.capafy.ai/e1234567890123456789' \
  'https://api.capafy.ai/Eabcdefghijklmnopqr' \
  'https://api.capafy.ai/E123456789012345678' \
  'https://api.capafy.ai/E12345678901234567890' \
  'https://api.capafy.ai/E1234567890123456789/extra'; do
  if printf '%s' "{\"agent_id\":\"agent-1\",\"review_url\":\"$bad_short_url\"}" | python3 "$URL_HELPER" --agent-id agent-1 --output "$STATE_HOME/review-urls/agent-1/short-bad.url" >/dev/null 2>&1; then
    echo "FAIL: invalid short review URL accepted" >&2
    exit 1
  fi
done
LEGACY_URL='https://capafy.ai/developer/createAgent?source=temp-link&token=123456789&page=edit'
printf '%s' "{\"agent_id\":\"agent-1\",\"review_url\":\"$LEGACY_URL\"}" | python3 "$URL_HELPER" --agent-id agent-1 --output "$STATE_HOME/review-urls/agent-1/legacy.url" >/dev/null
[ "$(<"$STATE_HOME/review-urls/agent-1/legacy.url")" = "$LEGACY_URL" ] || { echo "FAIL: legacy edit URL bytes changed" >&2; exit 1; }
for bad_url in \
  'https://capafy.ai/developer/createAgent?draftKey=a&draftKey=b&page=edit' \
  'https://capafy.ai/developer/createAgent?draftKey=a&page=edit&extra=1' \
  'https://capafy.ai/developer/createAgent?draftKey=&page=edit' \
  'https://capafy.ai/developer/createAgent?draftKey=a&page=edit#fragment'; do
  if printf '%s' "{\"agent_id\":\"agent-1\",\"review_url\":\"$bad_url\"}" | python3 "$URL_HELPER" --agent-id agent-1 --output "$STATE_HOME/review-urls/agent-1/bad.url" >/dev/null 2>&1; then
    echo "FAIL: invalid edit URL accepted" >&2
    exit 1
  fi
done
if printf '%s' "{\"agent_id\":\"other\",\"review_url\":\"$URL\"}" | python3 "$URL_HELPER" --agent-id agent-1 --output "$STATE_HOME/review-urls/agent-1/mismatch.url" >/dev/null 2>&1; then
  echo "FAIL: mismatched refresh Agent ID accepted" >&2
  exit 1
fi

SELECTION_HELPER="$ROOT/scripts/build_publish_selection.py"
SKILL_ROOT="$STATE_HOME/skills/metadata-dir"
mkdir -p "$SKILL_ROOT"
printf '%s' '# explicit skill' > "$SKILL_ROOT/SKILL.md"
selection_payload="$(python3 - "$SKILL_ROOT" <<'PY'
import json, sys
root = sys.argv[1]
print(json.dumps({
    "status": "needs_selection",
    "action_type": "llm_selection",
    "skills": [{
        "path": ".openclaw/skills/metadata-dir",
        "name": "Metadata Name",
        "description": "metadata purpose",
        "source_path": root,
        "source_root": root,
    }],
}))
PY
)"
SELECTION_PATH="$STATE_HOME/selection.json"
selection_result="$(printf '%s' "$selection_payload" | python3 "$SELECTION_HELPER" --skill-dir "$SKILL_ROOT" --title Listing --output "$SELECTION_PATH")"
[ "$selection_result" = "SELECTION_FILE=$SELECTION_PATH" ] || { echo "FAIL: Phase A selection file result" >&2; exit 1; }
python3 - "$SELECTION_PATH" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1]))
assert payload["skills"] == [{"path": ".openclaw/skills/metadata-dir", "name": "Metadata Name", "purpose": "metadata purpose"}]
assert set(payload) == {"title", "description", "skills"}
PY
EXISTING_SELECTION_PATH="$STATE_HOME/selection-existing.json"
existing_selection_result="$(printf '%s' "$selection_payload" | python3 "$SELECTION_HELPER" --skill-dir "$SKILL_ROOT" --title Listing --agent-id agent-1 --output "$EXISTING_SELECTION_PATH")"
[ "$existing_selection_result" = "SELECTION_FILE=$EXISTING_SELECTION_PATH" ] || { echo "FAIL: existing Phase A selection result" >&2; exit 1; }
python3 - "$EXISTING_SELECTION_PATH" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1]))
assert payload["agent_id"] == "agent-1"
assert set(payload) == {"agent_id", "title", "description", "skills"}
PY
bad_selection_payload="$(printf '%s' "$selection_payload" | python3 -c 'import json,sys; p=json.load(sys.stdin); p["skills"][0]["source_path"]="/tmp/other-skill"; p["skills"][0]["source_root"]="/tmp/other-skill"; print(json.dumps(p))')"
if printf '%s' "$bad_selection_payload" | python3 "$SELECTION_HELPER" --skill-dir "$SKILL_ROOT" --title Listing --output "$STATE_HOME/selection-bad.json" >/dev/null 2>&1; then
  echo "FAIL: mismatched Phase A candidate was accepted" >&2
  exit 1
fi
multi_selection_payload="$(printf '%s' "$selection_payload" | python3 -c 'import json,sys; p=json.load(sys.stdin); p["skills"].append(dict(p["skills"][0])); print(json.dumps(p))')"
if printf '%s' "$multi_selection_payload" | python3 "$SELECTION_HELPER" --skill-dir "$SKILL_ROOT" --title Listing --output "$STATE_HOME/selection-multi.json" >/dev/null 2>&1; then
  echo "FAIL: multiple Phase A candidates were accepted" >&2
  exit 1
fi

make_binding_fixture() {
  local state_root="$1" skill="unused-skill" home workspace config work
  home="$state_root/runtime/capafy-publisher-home/agents/agent-1"
  workspace="$home/.openclaw/workspace"
  config="$home/listing-config.json"
  work="$state_root/runtime/capafy-publisher/work/agents/agent-1"
  mkdir -p "$workspace/skills/$skill" "$(dirname "$config")" "$work"
  printf '%s\n' '# Fixture Skill' > "$workspace/skills/$skill/SKILL.md"
  printf '%s\n' icon > "$state_root/icon.png"
  python3 - "$config" "$home/.openclaw/openclaw.json" "$state_root/icon.png" "$work/publish-work-state.json" "$workspace" "$workspace/skills/$skill" <<'PY'
import json,sys
config, hosted, icon, manifest, workspace, skill_dir = sys.argv[1:]
model = "anthropic/claude-sonnet-4.6"
json.dump({"title":"Fixture","model":"Claude Sonnet 4.6","model_id":model,"max_tokens":128000,"icon":icon},open(config,"w"))
json.dump({"models":{"providers":{"openrouter":{"api":"openai-responses",
    "apiKey":"${CAPAFY_HOST_OPENROUTER_KEY}",
    "models":[{"id":model,"name":model,"maxTokens":128000}]}}},
    "agents":{"defaults":{"model":{"primary":"openrouter/"+model}}}},open(hosted,"w"))
json.dump({"agent_id":"agent-1","agent_version_id":"version-1",
    "extra":{"runtime_dir":workspace,"explicit_skill":{"source_path":skill_dir}}},
    open(manifest,"w"))
PY
  python3 "$ROOT/scripts/publish_input_contract.py" write \
    --agent-id agent-1 --skill-name "$skill" --config "$config" \
    --workspace "$workspace" --publisher-home "$home" --work-dir "$work"
}

FAKE_BIN="$STATE_HOME/fake-bin"
mkdir -p "$FAKE_BIN"
REAL_PYTHON="$(command -v python3)"
FAKE_CALLS="$STATE_HOME/status-gate-calls.log"
python3 - "$FAKE_BIN/python3" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_text(
    """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_CALLS"
if [ "$1" = "packager.py" ] && [ -n "${OPENCLAW_CONFIG_PATH:-}${OPENCLAW_STATE_DIR:-}" ]; then
  : > "$FAKE_OPENCLAW_LEAK"
  exit 97
fi
if [ "$1" = "packager.py" ] && [ "$2" = "publish-remote-status" ]; then
  if [ "$FAKE_MODE" = "submitted-mismatch" ]; then
    printf '%s\\n' '{"ok":true,"latest_version":{"agent_id":"agent-1","agent_version_id":"version-1","platform_status":1,"audit_status":1,"is_confirmed_skills":true,"is_confirmed_config_keys":true,"agent_package_id":"pkg-1","package_uploaded":true}}'
    exit 0
  fi
  printf '%s\\n' '{"ok":true,"latest_version":{"agent_id":"agent-1","agent_version_id":"version-1","platform_status":2,"audit_status":1,"is_confirmed_skills":true,"is_confirmed_config_keys":true,"agent_package_id":"pkg-1","package_uploaded":true}}'
  exit 0
fi
case "$1" in */verify_cp1_model.py) : > "$FAKE_CP1_MARKER"; exit 1 ;; esac
exec "$REAL_PYTHON" "$@"
""",
    encoding="utf-8",
)
PY
chmod +x "$FAKE_BIN/python3"
make_binding_fixture "$STATE_HOME/status-state"
set +e
FAKE_CALLS="$FAKE_CALLS" FAKE_OPENCLAW_LEAK="$STATE_HOME/openclaw-override-leaked" REAL_PYTHON="$REAL_PYTHON" PATH="$FAKE_BIN:$PATH" \
  OPENCLAW_CONFIG_PATH=/tmp/operator-openclaw.json OPENCLAW_STATE_DIR=/tmp/operator-openclaw \
  LIFE_MANAGER_STATE_HOME="$STATE_HOME/status-state" CAPAFY_PUBLISHER_STATE_HOME="$STATE_HOME/status-state/runtime/capafy-publisher" \
  bash "$ROOT/scripts/publish_finish.sh" agent-1 unused-skill "" version-1 >/dev/null 2>&1
status_gate_rc=$?
set -e
[ "$status_gate_rc" -ne 0 ] || { echo "FAIL: review_rejected status gate allowed finish" >&2; exit 1; }
[ ! -f "$STATE_HOME/openclaw-override-leaked" ] \
  || { echo "FAIL: inherited OpenClaw override reached publisher" >&2; exit 1; }
if rg -q 'drive_checkpoint|publish-submit|publish-refresh-url|key_health_gate' "$FAKE_CALLS"; then
  echo "FAIL: status gate reached provider/browser effect" >&2
  exit 1
fi
make_binding_fixture "$STATE_HOME/submitted-state"
FAKE_CP1_MARKER="$STATE_HOME/submitted-cp1-checked"
set +e
FAKE_MODE=submitted-mismatch FAKE_CP1_MARKER="$FAKE_CP1_MARKER" FAKE_CALLS="$FAKE_CALLS" REAL_PYTHON="$REAL_PYTHON" PATH="$FAKE_BIN:$PATH" \
  LIFE_MANAGER_STATE_HOME="$STATE_HOME/submitted-state" CAPAFY_PUBLISHER_STATE_HOME="$STATE_HOME/submitted-state/runtime/capafy-publisher" \
  bash "$ROOT/scripts/publish_finish.sh" agent-1 unused-skill "" version-1 >/dev/null 2>&1
submitted_rc=$?
set -e
[ "$submitted_rc" -ne 0 ] && [ -f "$FAKE_CP1_MARKER" ] \
  || { echo "FAIL: submitted version bypassed official CP1 model gate" >&2; exit 1; }
[ ! -f "$STATE_HOME/submitted-state/state/capafy-autopublish/published.jsonl" ] \
  || { echo "FAIL: CP1 model mismatch wrote the submission ledger" >&2; exit 1; }

UNKNOWN_BIN="$STATE_HOME/unknown-bin"
mkdir -p "$UNKNOWN_BIN"
UNKNOWN_CALLS="$STATE_HOME/unknown-calls.log"
UNKNOWN_REMOTE_COUNT="$STATE_HOME/unknown-remote-count"
FAKE_REFRESH_MARKER="$STATE_HOME/fake-refresh-mismatch.marker"
python3 - "$UNKNOWN_BIN/python3" "$UNKNOWN_BIN/curl" <<'PY'
from pathlib import Path
import sys
python_path, curl_path = sys.argv[1:]
Path(python_path).write_text(
    """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_CALLS"
if [ "$1" = "packager.py" ] && [ "$2" = "publish-remote-status" ]; then
  count=0
  if [ -f "$FAKE_REMOTE_COUNT" ]; then count=$(cat "$FAKE_REMOTE_COUNT"); fi
  count=$((count + 1)); printf '%s' "$count" > "$FAKE_REMOTE_COUNT"
  status=0; config=true
  if [ "$FAKE_MODE" = "unknown-config" ]; then config=2; fi
  if [ "$FAKE_MODE" = "refresh-mismatch" ]; then config=0; fi
  if [ "$FAKE_MODE" = "unknown-post" ] && [ "$count" -ge 5 ]; then status=9; fi
  printf '%s\\n' "{\\\"ok\\\":true,\\\"latest_version\\\":{\\\"agent_id\\\":\\\"agent-1\\\",\\\"agent_version_id\\\":\\\"version-1\\\",\\\"platform_status\\\":$status,\\\"audit_status\\\":0,\\\"is_confirmed_skills\\\":true,\\\"is_confirmed_config_keys\\\":$config,\\\"agent_package_id\\\":\\\"pkg-1\\\",\\\"package_uploaded\\\":true}}"
  exit 0
fi
if [ "$1" = "packager.py" ] && [ "$2" = "publish-refresh-url" ]; then
  if [ "$FAKE_MODE" = "refresh-mismatch" ]; then
    printf '%s' ok > "$FAKE_REFRESH_MARKER"
    printf '%s\\n' '{"ok":true,"agent_id":"other-agent","review_url":"https://capafy.ai/developer/createAgent?draftKey=other&page=review"}'
    exit 0
  fi
fi
case "$1" in */verify_cp1_model.py) printf '%s\\n' CP1_MODEL=VERIFIED; exit 0 ;; esac
exec "$REAL_PYTHON" "$@"
""",
    encoding="utf-8",
)
Path(curl_path).write_text(
    """#!/bin/sh
case "$*" in
  *https://openrouter.ai/api/v1/key*) printf '%s\\n' '{"data":{"limit_remaining":null}}' ;;
  *https://openrouter.ai/api/v1/credits*) printf '%s\\n' '{"data":{"total_credits":30,"total_usage":1}}' ;;
  *https://openrouter.ai/api/v1/chat/completions*) printf '%s\\n' '{"choices":[{"message":{"content":"ok"}}]}' ;;
  *) exit 1 ;;
esac
""",
    encoding="utf-8",
)
PY
chmod +x "$UNKNOWN_BIN/python3" "$UNKNOWN_BIN/curl"
for mode in unknown-config unknown-post refresh-mismatch stale-version; do
  : > "$UNKNOWN_REMOTE_COUNT"
  make_binding_fixture "$STATE_HOME/$mode-state"
  expected_version=version-1
  [ "$mode" != stale-version ] || expected_version=version-0
  set +e
  FAKE_CALLS="$UNKNOWN_CALLS" REAL_PYTHON="$REAL_PYTHON" FAKE_REMOTE_COUNT="$UNKNOWN_REMOTE_COUNT" FAKE_REFRESH_MARKER="$FAKE_REFRESH_MARKER" FAKE_MODE="$mode" PATH="$UNKNOWN_BIN:$PATH" \
    LIFE_MANAGER_STATE_HOME="$STATE_HOME/$mode-state" CAPAFY_PUBLISHER_STATE_HOME="$STATE_HOME/$mode-state/runtime/capafy-publisher" CAPAFY_HOST_OPENROUTER_KEY=test-key \
    bash "$ROOT/scripts/publish_finish.sh" agent-1 unused-skill "" "$expected_version" >/dev/null 2>&1
  unknown_rc=$?
  set -e
  [ "$unknown_rc" -ne 0 ] || { echo "FAIL: $mode readback was not fail-closed" >&2; exit 1; }
done
[ -f "$FAKE_REFRESH_MARKER" ] || { echo "FAIL: refresh-mismatch fixture did not execute fake refresh branch" >&2; exit 1; }
if rg -q 'publish-submit|drive_checkpoint2|drive_checkpoint3' "$UNKNOWN_CALLS"; then
  echo "FAIL: unknown finish readback reached an external effect" >&2
  exit 1
fi

PREPARE_BIN="$STATE_HOME/prepare-envelope-bin"
mkdir -p "$PREPARE_BIN"
PREPARE_COUNT="$STATE_HOME/prepare-count"
CONTINUE_COUNT="$STATE_HOME/continue-count"
CP2_MARKER="$STATE_HOME/cp2-marker"
CP3_MARKER="$STATE_HOME/cp3-marker"
python3 - "$PREPARE_BIN/python3" "$PREPARE_BIN/curl" <<'PY'
from pathlib import Path
import sys
python_path, curl_path = sys.argv[1:]
Path(python_path).write_text(
    """#!/bin/sh
inc() {
  n=0
  if [ -f \"$1\" ]; then n=$(cat \"$1\"); fi
  n=$((n + 1)); printf '%s' \"$n\" > \"$1\"
}
if [ \"$1\" = \"packager.py\" ] && [ \"$2\" = \"publish-remote-status\" ]; then
  printf '%s\\n' '{\"ok\":true,\"latest_version\":{\"agent_id\":\"agent-1\",\"agent_version_id\":\"version-1\",\"platform_status\":0,\"audit_status\":0,\"is_confirmed_skills\":true,\"is_confirmed_config_keys\":false,\"agent_package_id\":\"\",\"package_uploaded\":false}}'
  exit 0
fi
if [ \"$1\" = \"packager.py\" ] && [ \"$2\" = \"publish-submit\" ]; then
  case \"$*\" in
    *'--action prepare'*)
      inc \"$PREPARE_COUNT\"
      case \"$FAKE_MODE\" in
        prepare-envelope) payload='{"ok":true,"agent_id":"agent-1","status":"security_review_required","security_ready":true,"next_action":"continue_upload"}' ;;
        wrong-status) payload='{"ok":true,"agent_id":"agent-1","status":"security_ready","security_ready":true,"next_action":"continue_upload"}' ;;
        security-false) payload='{"ok":true,"agent_id":"agent-1","status":"security_review_required","security_ready":false,"next_action":"continue_upload"}' ;;
        next-action-missing) payload='{"ok":true,"agent_id":"agent-1","status":"security_review_required","security_ready":true}' ;;
        wrong-agent) payload='{"ok":true,"agent_id":"other-agent","status":"security_review_required","security_ready":true,"next_action":"continue_upload"}' ;;
      esac
      printf '%s\\n' \"$payload\"
      exit 0
      ;;
    *'--action continue_upload'*)
      inc \"$CONTINUE_COUNT\"
      printf '%s\\n' '{"ok":false,"agent_id":"agent-1","blocking_category":"deliberate_test_failure"}'
      exit 7
      ;;
  esac
fi
case \"$*\" in
  *drive_checkpoint2.py*) : > \"$CP2_MARKER\"; exit 0 ;;
  *drive_checkpoint3.py*) : > \"$CP3_MARKER\"; exit 0 ;;
esac
case \"$1\" in */verify_cp1_model.py) printf '%s\\n' CP1_MODEL=VERIFIED; exit 0 ;; esac
exec \"$REAL_PYTHON\" \"$@\"
""",
    encoding="utf-8",
)
Path(curl_path).write_text(
    """#!/bin/sh
case \"$*\" in
  *https://openrouter.ai/api/v1/key*) printf '%s\\n' '{"data":{"limit_remaining":null}}' ;;
  *https://openrouter.ai/api/v1/credits*) printf '%s\\n' '{"data":{"total_credits":30,"total_usage":1}}' ;;
  *https://openrouter.ai/api/v1/chat/completions*) printf '%s\\n' '{"choices":[{"message":{"content":"ok"}}]}' ;;
  *) exit 1 ;;
esac
""",
    encoding="utf-8",
)
PY
chmod +x "$PREPARE_BIN/python3" "$PREPARE_BIN/curl"
for mode in prepare-envelope wrong-status security-false next-action-missing wrong-agent; do
  rm -f "$PREPARE_COUNT" "$CONTINUE_COUNT" "$CP2_MARKER" "$CP3_MARKER"
  make_binding_fixture "$STATE_HOME/$mode-state"
  set +e
  PREPARE_COUNT="$PREPARE_COUNT" CONTINUE_COUNT="$CONTINUE_COUNT" CP2_MARKER="$CP2_MARKER" CP3_MARKER="$CP3_MARKER" \
    REAL_PYTHON="$REAL_PYTHON" FAKE_MODE="$mode" PATH="$PREPARE_BIN:$PATH" \
    LIFE_MANAGER_STATE_HOME="$STATE_HOME/$mode-state" CAPAFY_PUBLISHER_STATE_HOME="$STATE_HOME/$mode-state/runtime/capafy-publisher" CAPAFY_HOST_OPENROUTER_KEY=test-key \
    bash "$ROOT/scripts/publish_finish.sh" agent-1 unused-skill "" version-1 >/dev/null 2>&1
  prepare_rc=$?
  set -e
  [ "$prepare_rc" -ne 0 ] || { echo "FAIL: prepare envelope mode $mode unexpectedly succeeded" >&2; exit 1; }
  [ "$(cat "$PREPARE_COUNT" 2>/dev/null || printf '0')" = "1" ] || { echo "FAIL: $mode prepare count" >&2; exit 1; }
  expected_continue=0
  [ "$mode" = "prepare-envelope" ] && expected_continue=1
  [ "$(cat "$CONTINUE_COUNT" 2>/dev/null || printf '0')" = "$expected_continue" ] || { echo "FAIL: $mode continue count" >&2; exit 1; }
  [ ! -e "$CP2_MARKER" ] || { echo "FAIL: $mode reached CP2" >&2; exit 1; }
  [ ! -e "$CP3_MARKER" ] || { echo "FAIL: $mode reached CP3" >&2; exit 1; }
done

before_shim_calls="$(wc -l < "$FAKE_CALLS")"
set +e
PATH="$FAKE_BIN:$PATH" bash "$ROOT/scripts/publish_one.sh" unused unused unused >/dev/null 2>&1
shim_rc=$?
set -e
[ "$shim_rc" -ne 0 ] || { echo "FAIL: legacy publish_one shim returned success" >&2; exit 1; }
[ "$(wc -l < "$FAKE_CALLS")" = "$before_shim_calls" ] || {
  echo "FAIL: legacy publish_one shim invoked a provider/runtime" >&2
  exit 1
}
if find "$ROOT/scripts" -type f -perm -111 -print0 | xargs -0 rg -n 'publish-configure|publish-ship|refresh configure|refresh ship'; then
  echo "FAIL: retired publisher command remains in an executable script" >&2
  exit 1
fi

rg -q 'CAPAFY_PUBLISH_WORK_DIR="\$CAPAFY_PUBLISHER_STATE_HOME/work/agents/\$ID"' "$ROOT/scripts/publish_prepare.sh"
rg -q 'BOOTSTRAP_ROOT="\$CAPAFY_PUBLISHER_STATE_HOME/work/bootstrap"' "$ROOT/scripts/publish_prepare.sh"
rg -q 'mkdir -p "\$BOOTSTRAP_ROOT"' "$ROOT/scripts/publish_prepare.sh"
rg -q 'BOOTSTRAP_WORK_DIR="\$\(mktemp -d "\$BOOTSTRAP_ROOT/capafy\.XXXXXX"\)"' "$ROOT/scripts/publish_prepare.sh"
rg -q 'mv "\$BOOTSTRAP_WORK_DIR" "\$AGENT_WORK_DIR"' "$ROOT/scripts/publish_prepare.sh"
rg -q 'export CAPAFY_PUBLISH_WORK_DIR="\$AGENT_WORK_DIR"' "$ROOT/scripts/publish_prepare.sh"
rg -q 'echo "CONFIG_PATH=\$CFG_ONE"' "$ROOT/scripts/publish_prepare.sh"
rg -q 'echo "EDIT_URL_FILE=\$EDIT_URL_FILE"' "$ROOT/scripts/publish_prepare.sh"
if rg -q 'echo "EDIT_URL=|EDIT="' "$ROOT/scripts/publish_prepare.sh"; then
  echo "FAIL: publish_prepare exposes or reconstructs edit URL" >&2
  exit 1
fi
rg -q 'DISCOVERY_OUT=.*publish-init --env openclaw --runtime-dir .*--skill-dir .*--agent-id "\$ID"' "$ROOT/scripts/publish_prepare.sh"
rg -q 'DISCOVERY_OUT=.*publish-init --env openclaw --runtime-dir .*--skill-dir .* 2>&1' "$ROOT/scripts/publish_prepare.sh"
rg -q 'PREPARE_OUT=.*publish-submit --agent-id "\$ID" --action prepare 2>&1' "$ROOT/scripts/publish_finish.sh"
rg -q 'PREPARE_SECURITY_READY' "$ROOT/scripts/publish_finish.sh"
if rg -q -- '--deep-scan|findings-file|inspect_deep_scan\.py' "$ROOT/scripts/publish_finish.sh"; then
  echo "FAIL: finish invokes deep-scan/custom findings flow" >&2
  exit 1
fi
if rg -q 'publish-configure|publish-ship' "$ROOT/scripts/publish_finish.sh"; then
  echo "FAIL: retired publisher CLI remains in finish wrapper" >&2
  exit 1
fi
continue_upload_calls="$(rg -o 'python3 packager\.py publish-submit --agent-id "\$ID" --action continue_upload' "$ROOT/scripts/publish_finish.sh" | wc -l | tr -d ' ')"
[ "$continue_upload_calls" = "1" ] || {
  echo "FAIL: continue_upload command count=$continue_upload_calls (want 1)" >&2
  exit 1
}
rg -q 'refresh publish' "$ROOT/scripts/publish_finish.sh"
if rg -q 'refresh (configure|ship)|--step (configure|ship)' "$ROOT/scripts/publish_finish.sh"; then
  echo "FAIL: retired refresh step remains in finish wrapper" >&2
  exit 1
fi
python3 - "$ROOT/scripts/publish_prepare.sh" <<'PY'
from pathlib import Path
import sys
text = Path(sys.argv[1]).read_text()
existing_discovery = text.index('DISCOVERY_OUT="$(python3 packager.py publish-init')
existing_selection = text.index('SELECTION_RESULT=', existing_discovery)
existing_submit = text.index('REBIND_OUT="$(python3 packager.py publish-init')
new_branch = text.index('BOOTSTRAP_ROOT=')
new_discovery = text.index('DISCOVERY_OUT="$(python3 packager.py publish-init', new_branch)
new_selection = text.index('SELECTION_RESULT=', new_discovery)
new_submit = text.index('INIT_OUT="$(python3 packager.py publish-init', new_discovery)
assert existing_discovery < existing_selection < existing_submit, 'existing-agent Phase A must precede selection submission'
assert new_discovery < new_selection < new_submit, 'new-agent Phase A must precede selection submission'
existing_selection_line = text[existing_selection:text.index('\n', existing_selection)]
new_selection_line = text[new_selection:text.index('\n', new_selection)]
assert '--agent-id "$ID"' in existing_selection_line, 'existing selection must carry the selected Agent ID'
assert '--agent-id "$ID"' not in new_selection_line, 'new selection must omit Agent ID'
assert text.index('SEL_FILE=', existing_discovery) > existing_discovery, 'selection file must be built after Phase A'
PY
rg -q 'CAPAFY_PUBLISH_WORK_DIR="\$CAPAFY_PUBLISHER_STATE_HOME/work/agents/\$ID"' "$ROOT/scripts/publish_finish.sh"
rg -q 'CFG_ONE="\$CAPAFY_PUBLISH_HOME/listing-config\.json"' "$ROOT/scripts/publish_prepare.sh"
rg -q 'CFG_ONE="\$CAPAFY_PUBLISH_HOME/listing-config\.json"' "$ROOT/scripts/publish_finish.sh"
rg -q 'build_config\.py.*"\$CFG_ONE"' "$ROOT/scripts/publish_prepare.sh"
rg -q 'python3 - "\$CFG_ONE"' "$ROOT/scripts/publish_prepare.sh"
rg -q 'CAPAFY_PUBLISH_WORK_DIR/staging' "$ROOT/scripts/publish_finish.sh"
rg -q -U 'if \[ -e "\$CAPAFY_PUBLISH_WORK_DIR/staging" \]; then\n\s+chmod -R u\+w "\$CAPAFY_PUBLISH_WORK_DIR/staging" 2>/dev/null \|\| true\n\s+rm -rf "\$CAPAFY_PUBLISH_WORK_DIR/staging" 2>/dev/null \\\n\s+\|\| die .*\n\s+fi' "$ROOT/scripts/publish_finish.sh"
rg -q 'chmod -R u\+w "\$WS/skills/\$SKILL_NAME"' "$ROOT/scripts/publish_prepare.sh"
if rg -qF '.temp/cfg_one.json' "$ROOT/CP1_AGENTIC.md"; then
  echo "FAIL: CP1 instructions use a release-local config path" >&2
  exit 1
fi
if rg -qF '$PUB/.temp' "$ROOT/scripts/publish_prepare.sh" "$ROOT/scripts/publish_finish.sh" \
  || rg -q 'open\(.*\.temp' "$ROOT/scripts/publish_prepare.sh" "$ROOT/scripts/publish_finish.sh"; then
  echo "FAIL: publisher entrypoints write mutable files inside the release" >&2
  exit 1
fi
if rg -q 'CAPAFY_PUBLISH_WORK_DIR="\$\{CAPAFY_PUBLISH_WORK_DIR:-' \
  "$ROOT/scripts/publish_prepare.sh" "$ROOT/scripts/publish_finish.sh"; then
  echo "FAIL: publisher resume may inherit another agent's work-state" >&2
  exit 1
fi
python3 - "$ROOT/scripts/publish_finish.sh" <<'PY'
from pathlib import Path
import sys
text = Path(sys.argv[1]).read_text()
config_case = text.index('case "$CONFIG_STATE" in')
config_unknown = text.index('die "is_confirmed_config_keys readback is missing or unknown')
upload = text.index('publish-submit --agent-id "$ID" --action continue_upload')
assert config_case < config_unknown < upload, "unknown config must fail before upload"
post_case = text.index('case "$POST_CP2_STATUS" in')
post_unknown = text.index('die "unsupported or unreadable post-CP2 platform_status')
post_zero = text.index('0)\n  step "[6] CP3 submit', post_case)
cp3 = text.index('drive_checkpoint3.py')
assert post_case < post_zero < cp3 < post_unknown, "unknown post-CP2 status must fail before CP3"
PY
echo PASS
