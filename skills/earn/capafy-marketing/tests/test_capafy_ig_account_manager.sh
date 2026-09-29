#!/usr/bin/env bash
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../../../.." && pwd)"
MANAGER="$ROOT/skills/earn/capafy-marketing/capafy-ig-account-manager.sh"
HANDOFF="$ROOT/skills/earn/capafy-marketing/capafy-marketing-handoff.sh"
LIFECYCLE="$ROOT/skills/earn/capafy-marketing/scripts/capafy_ig_lifecycle.py"
OUTCOME="$ROOT/skills/earn/capafy-marketing/scripts/capafy_outcome.py"
PASS=0 FAIL=0
ok(){ PASS=$((PASS+1)); printf '  ok %s\n' "$1"; }
bad(){ FAIL=$((FAIL+1)); printf '  not ok %s\n' "$1"; }
eq(){ [ "$2" = "$3" ] && ok "$1" || { bad "$1 (got=$2 want=$3)"; }; }
has(){ grep -Fq -- "$3" "$2" && ok "$1" || bad "$1 (missing $3)"; }

T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
mkdir -p "$T/bin"

cat >"$T/bin/browser" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$BROWSER_CALLS"
printf 'http://127.0.0.1:9444\n'
SH
cat >"$T/bin/runner" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$RUNNER_CALLS"
cat >/dev/null
python3 - "$CAPAFY_IG_ACCOUNTS_FILE" "$HOME" "${FAKE_PROVISION_MODE:-ok}" <<'PY'
import json, pathlib, sys
path, home, mode = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
rows=json.loads(path.read_text()) if path.exists() else []
if mode == "no_mutation":
    pass
elif mode == "malformed":
    rows.append({"handle":"capafy.skills25042","status":"warming","session_owner":"private_api"})
elif mode == "missing_identity":
    rows.append({"handle":"capafy.skills25042","profile":"capafy-mkt-25042","port":9444,"context_id":"capafy-test","status":"warming","session_owner":"browser","instance":"capafy","created":"2026-08-02","started_warming":"2026-08-02"})
else:
    rows.append({"handle":"capafy.skills25042","profile":"capafy-mkt-25042","port":9444,"context_id":"capafy-test","browser_identity":"instagram:capafy-provision","status":"warming","session_owner":"browser","instance":"capafy","created":"2026-08-02","started_warming":"2026-08-02"})
path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(rows))
if mode != "missing_credential":
    cred=home/".cloak"/"ig-capafy.skills25042.json"; cred.parent.mkdir(parents=True,exist_ok=True); cred.write_text('{"username":"capafy.skills25042","pw":"fixture"}')
PY
SH
cat >"$T/bin/verify" <<'SH'
#!/usr/bin/env bash
[ "${FAKE_VERIFY_MODE:-ok}" = "ok" ]
SH
cat >"$T/bin/sender" <<'SH'
#!/usr/bin/env bash
[ "${FAKE_SENDER_MODE:-ok}" = "ok" ] || exit 1
printf '%s\n' "$1" >>"$TELEGRAM_BODY"
printf 'TELEGRAM_SENT=true MSGID=6001\n'
SH
cat >"$T/bin/launchctl" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$KICKSTART_CALLS"
SH
cat >"$T/bin/guard" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$GUARD_CALLS"
SH
chmod +x "$T/bin/"*

probe="$(CAPAFY_IG_ACCOUNT_MANAGER_PROBE_ONLY=1 bash "$MANAGER" 2>&1)"; probe_rc=$?
eq "probe exits zero" "$probe_rc" 0
for token in task_class=marketing-agent interval=300 terminal_owner=capafy-marketing-handoff.sh; do
  case "$probe" in *"$token"*) ok "probe contains $token";; *) bad "probe missing $token";; esac
done

new_case(){
  CASE="$T/$1"; mkdir -p "$CASE/home/.cloak" "$CASE/state"
  printf '[]\n' >"$CASE/accounts.json"; : >"$CASE/runner.calls"; : >"$CASE/telegram.body"; : >"$CASE/kick.calls"; : >"$CASE/guard.calls"; : >"$CASE/browser.calls"
  export HOME="$CASE/home" CAPAFY_IG_ACCOUNTS_FILE="$CASE/accounts.json"
  export CAPAFY_IG_LIFECYCLE_STATE="$CASE/state/lifecycle.json" CAPAFY_OUTCOME_STATE_DIR="$CASE/state"
  export CAPAFY_MARKETING_RESULT="$CASE/state/manager-result.json" CAPAFY_RUN_AGENT="$T/bin/runner"
  export CAPAFY_PROVISION_BROWSER="$T/bin/browser" CAPAFY_IG_SESSION_VERIFY="$T/bin/verify"
  export CAPAFY_TELEGRAM_SENDER="$T/bin/sender" CAPAFY_LAUNCHCTL="$T/bin/launchctl"
  export CAPAFY_BROWSER_GUARD="$T/bin/guard" GUARD_CALLS="$CASE/guard.calls"
  export RUNNER_CALLS="$CASE/runner.calls" TELEGRAM_BODY="$CASE/telegram.body" KICKSTART_CALLS="$CASE/kick.calls" BROWSER_CALLS="$CASE/browser.calls"
  export CAPAFY_ACCOUNT_MANAGER_LOCK_DIR="$CASE/manager.lock" CAPAFY_IG_LIFECYCLE="$LIFECYCLE" LIFE_MANAGER_GMAIL_ACCOUNT="owner@example.com"
  unset FAKE_PROVISION_MODE FAKE_VERIFY_MODE FAKE_SENDER_MODE CAPAFY_MARKETING_HANDOFF HANDOFF_CALLS
}

seed_recovery_incident(){
  local summary='active Instagram browser tab is missing' incident_json incident_id key
  incident_json="$(python3 "$OUTCOME" start-incident --owner marketer --summary "$summary" \
    --fingerprint "$(printf '%s' "$summary" | shasum -a 256 | awk '{print $1}')")"
  incident_id="$(python3 -c 'import json,sys;print(json.load(sys.stdin)["incident_id"])' <<<"$incident_json")"
  key="$(printf '%s' existing-recovery-receipt | shasum -a 256 | awk '{print $1}')"
  printf '%s' "$(python3 - "$incident_id" <<'PY'
import json,sys
print(json.dumps({"incident_id":sys.argv[1],"phase":"unresolved","repair_summary":"Existing browser recovery is waiting","next_retry_at":"2099-01-01T00:05:00Z"}))
PY
)" | python3 "$OUTCOME" transition-incident >/dev/null
  printf '%s' "$(python3 - "$incident_id" "$key" <<'PY'
import json,sys
print(json.dumps({"incident_id":sys.argv[1],"phase":"unresolved","terminal_message_key":sys.argv[2],"telegram_message_id":6001}))
PY
)" | python3 "$OUTCOME" transition-incident >/dev/null
  python3 - "$CAPAFY_IG_LIFECYCLE_STATE" "$incident_id" <<'PY'
import json,sys
path,incident_id=sys.argv[1:]
json.dump({"schema_version":1,"status":"replacement_requested","replacement_reason":"Instagram account verification failed for @capafy.recovery: malformed account row","replacement_requested":True,"incident_id":incident_id},open(path,"w"))
PY
  python3 - "$CAPAFY_IG_ACCOUNTS_FILE" "$incident_id" <<'PY'
import json,sys
path,incident_id=sys.argv[1:]
json.dump([{"handle":"capafy.recovery","status":"session_failed","session_owner":"browser","incident_id":incident_id,"retirement_reason":"Instagram account verification failed for @capafy.recovery: malformed account row","browser_identity":"instagram:capafy-provision","port":9444}],open(path,"w"))
PY
}

new_case success
bash "$MANAGER" >/dev/null 2>&1; rc=$?
eq "created account exits zero" "$rc" 0
eq "one provision invocation" "$(wc -l <"$RUNNER_CALLS" | tr -d ' ')" 1
eq "browser lease released after provisioning" "$(grep -Fc 'release instagram:capafy-provision' "$GUARD_CALLS")" 1
has "runner uses marketing lane" "$RUNNER_CALLS" "--task-class marketing-agent"
has "message has new handle" "$TELEGRAM_BODY" "@capafy.skills25042"
has "message says browser session" "$TELEGRAM_BODY" "browser session"
has "message says publish starts now" "$TELEGRAM_BODY" "starts now"
if grep -Eqi 'warmup|waiting' "$TELEGRAM_BODY"; then bad "account-created message still waits"; else ok "account-created message has no wait gate"; fi
eq "created account wakes daily publisher once" "$(grep -Fc 'ai.anicca.capafy-ig-marketing-daily' "$KICKSTART_CALLS")" 1
bash "$MANAGER" >/dev/null 2>&1; rc=$?
eq "second pass exits zero" "$rc" 0
eq "second pass does not reprovision" "$(wc -l <"$RUNNER_CALLS" | tr -d ' ')" 1
eq "second pass does not resend" "$(grep -Fc 'replacement account created and verified' "$TELEGRAM_BODY")" 1
eq "second pass does not re-kick publisher" "$(grep -Fc 'ai.anicca.capafy-ig-marketing-daily' "$KICKSTART_CALLS")" 1

new_case missing-credential; export FAKE_PROVISION_MODE=missing_credential
bash "$MANAGER" >/dev/null 2>&1; rc=$?
[ "$rc" -ne 0 ] && ok "missing credential fails" || bad "missing credential accepted"
has "missing credential writes replacement terminal" "$CAPAFY_MARKETING_RESULT" '"result": "replacement_waiting"'
eq "missing credential retires candidate" "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[-1]["status"])' "$CAPAFY_IG_ACCOUNTS_FILE")" session_failed

new_case unverified; export FAKE_VERIFY_MODE=fail
bash "$MANAGER" >/dev/null 2>&1; rc=$?
[ "$rc" -ne 0 ] && ok "unverified session fails" || bad "unverified session accepted"
has "unverified session writes replacement terminal" "$CAPAFY_MARKETING_RESULT" '"result": "replacement_waiting"'
eq "unverified session retires candidate" "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[-1]["status"])' "$CAPAFY_IG_ACCOUNTS_FILE")" session_failed

new_case malformed; export FAKE_PROVISION_MODE=malformed
bash "$MANAGER" >/dev/null 2>&1; rc=$?
[ "$rc" -ne 0 ] && ok "malformed appended row fails" || bad "malformed row accepted"
has "malformed row writes replacement terminal" "$CAPAFY_MARKETING_RESULT" '"result": "replacement_waiting"'
eq "malformed row retires candidate" "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[-1]["status"])' "$CAPAFY_IG_ACCOUNTS_FILE")" session_failed

new_case missing-identity; export FAKE_PROVISION_MODE=missing_identity
bash "$MANAGER" >/dev/null 2>&1; rc=$?
[ "$rc" -ne 0 ] && ok "missing browser identity fails" || bad "missing browser identity accepted"
has "missing identity writes replacement terminal" "$CAPAFY_MARKETING_RESULT" '"result": "replacement_waiting"'
eq "missing identity retires candidate" "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[-1]["status"])' "$CAPAFY_IG_ACCOUNTS_FILE")" session_failed

new_case stale-lock; mkdir -p "$CAPAFY_ACCOUNT_MANAGER_LOCK_DIR"; printf '999999\n' >"$CAPAFY_ACCOUNT_MANAGER_LOCK_DIR/pid"
bash "$MANAGER" >/dev/null 2>&1; rc=$?
eq "dead lock is recovered" "$rc" 0

new_case sender-retry; export FAKE_SENDER_MODE=fail
bash "$MANAGER" >/dev/null 2>&1; first_rc=$?
[ "$first_rc" -ne 0 ] && ok "failed sender leaves retryable terminal" || bad "failed sender reported success"
export FAKE_SENDER_MODE=ok
bash "$MANAGER" >/dev/null 2>&1; second_rc=$?
eq "sender retry exits zero" "$second_rc" 0
eq "sender retry does not reprovision" "$(wc -l <"$RUNNER_CALLS" | tr -d ' ')" 1
eq "sender retry delivers once" "$(grep -Fc 'replacement account created and verified' "$TELEGRAM_BODY")" 1
eq "sender retry wakes publisher once" "$(grep -Fc 'ai.anicca.capafy-ig-marketing-daily' "$KICKSTART_CALLS")" 1

new_case exact-recovery
seed_recovery_incident
cat >"$CASE/handoff-counter" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$HANDOFF_CALLS"
exit 99
SH
chmod +x "$CASE/handoff-counter"
export CAPAFY_MARKETING_HANDOFF="$CASE/handoff-counter" HANDOFF_CALLS="$CASE/handoff.calls"
: >"$HANDOFF_CALLS"
before_record="$(find "$CAPAFY_OUTCOME_STATE_DIR/capafy-incidents" -name '*.json' -exec cat {} \;)"
before_events="$(cat "$CAPAFY_OUTCOME_STATE_DIR/capafy-revenue-events.jsonl" 2>/dev/null || true)"
bash "$MANAGER" >/dev/null 2>&1; exact_rc=$?
eq "exact recovery exits zero without handoff" "$exact_rc" 0
eq "exact recovery calls no handoff" "$(wc -l <"$HANDOFF_CALLS" | tr -d ' ')" 0
eq "exact recovery invokes browser once" "$(wc -l <"$BROWSER_CALLS" | tr -d ' ')" 1
eq "exact recovery does not invoke agent" "$(wc -l <"$RUNNER_CALLS" | tr -d ' ')" 0
eq "exact recovery wakes publisher once" "$(grep -Fc 'ai.anicca.capafy-ig-marketing-daily' "$KICKSTART_CALLS")" 1
eq "exact recovery sends no second Telegram" "$(wc -l <"$TELEGRAM_BODY" | tr -d ' ')" 0
eq "exact recovery keeps one active incident" "$(find "$CAPAFY_OUTCOME_STATE_DIR/capafy-incidents" -name '*.json' | wc -l | tr -d ' ')" 1
after_record="$(find "$CAPAFY_OUTCOME_STATE_DIR/capafy-incidents" -name '*.json' -exec cat {} \;)"
eq "exact recovery preserves delivery reservation" "$(python3 -c 'import json,sys;print(json.load(sys.stdin)["terminal_message_key"])' <<<"$after_record")" "$(python3 -c 'import json,sys;print(json.load(sys.stdin)["terminal_message_key"])' <<<"$before_record")"
eq "exact recovery preserves Telegram id" "$(python3 -c 'import json,sys;print(json.load(sys.stdin)["telegram_message_id"])' <<<"$after_record")" 6001
eq "exact recovery clears stale result" "$(test -e "$CAPAFY_MARKETING_RESULT"; echo $?)" 1
eq "exact recovery restores account row" "$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]))[0];print(d["status"],d["port"],d["browser_identity"])' "$CAPAFY_IG_ACCOUNTS_FILE")" 'ready_browser 9444 instagram:capafy-provision'
eq "exact recovery clears retirement markers" "$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]))[0];print(any(k in d for k in ("incident_id","retirement_reason","retired_at","poisoned_at")))' "$CAPAFY_IG_ACCOUNTS_FILE")" False
eq "exact recovery restores lifecycle" "$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d["status"],d["handle"],d["replacement_requested"])' "$CAPAFY_IG_LIFECYCLE_STATE")" 'publish_probe_ready capafy.recovery False'
after_lifecycle="$(python3 - "$CAPAFY_IG_LIFECYCLE_STATE" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); d.pop("updated_at",None); print(json.dumps(d,sort_keys=True))
PY
)"
first_lifecycle="$after_lifecycle"
eq "exact recovery preserves event ledger" "$(cat "$CAPAFY_OUTCOME_STATE_DIR/capafy-revenue-events.jsonl" 2>/dev/null || true)" "$before_events"
bash "$MANAGER" >/dev/null 2>&1; exact_replay_rc=$?
eq "exact recovery replay exits zero" "$exact_replay_rc" 0
eq "exact recovery replay calls no handoff" "$(wc -l <"$HANDOFF_CALLS" | tr -d ' ')" 0
eq "exact recovery replay keeps ready row" "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[0]["status"])' "$CAPAFY_IG_ACCOUNTS_FILE")" ready_browser
eq "exact recovery replay preserves lifecycle state" "$(python3 - "$CAPAFY_IG_LIFECYCLE_STATE" <<'PY'
import json,sys
d=json.load(open(sys.argv[1])); d.pop("updated_at",None); print(json.dumps(d,sort_keys=True))
PY
)" "$first_lifecycle"
eq "exact recovery replay preserves incident" "$(find "$CAPAFY_OUTCOME_STATE_DIR/capafy-incidents" -name '*.json' -exec cat {} \;)" "$before_record"
eq "exact recovery replay preserves event ledger" "$(cat "$CAPAFY_OUTCOME_STATE_DIR/capafy-revenue-events.jsonl" 2>/dev/null || true)" "$before_events"
eq "exact recovery replay sends no Telegram" "$(wc -l <"$TELEGRAM_BODY" | tr -d ' ')" 0
eq "exact recovery replay invokes no extra browser" "$(wc -l <"$BROWSER_CALLS" | tr -d ' ')" 1
eq "exact recovery replay invokes no agent" "$(wc -l <"$RUNNER_CALLS" | tr -d ' ')" 0
eq "exact recovery replay adds no publisher wake" "$(grep -Fc 'ai.anicca.capafy-ig-marketing-daily' "$KICKSTART_CALLS")" 1

new_case ambiguous-recovery
seed_recovery_incident
python3 - "$CAPAFY_IG_ACCOUNTS_FILE" <<'PY'
import json,sys
path=sys.argv[1]; rows=json.load(open(path)); rows.append(dict(rows[0],handle="capafy.recovery-two")); json.dump(rows,open(path,"w"))
PY
export FAKE_PROVISION_MODE=no_mutation
bash "$MANAGER" >/dev/null 2>&1; ambiguous_rc=$?
[ "$ambiguous_rc" -ne 0 ] && ok "ambiguous recovery fails through generic path" || bad "ambiguous recovery unexpectedly short-circuits"
[ "$(wc -l <"$BROWSER_CALLS" | tr -d ' ')" -gt 0 ] && ok "ambiguous recovery invokes browser" || bad "ambiguous recovery skipped browser"
[ "$(wc -l <"$RUNNER_CALLS" | tr -d ' ')" -gt 0 ] && ok "ambiguous recovery invokes agent" || bad "ambiguous recovery skipped agent"

new_case ambiguous-invalid-recovery
seed_recovery_incident
python3 - "$CAPAFY_IG_ACCOUNTS_FILE" <<'PY'
import json,sys
path=sys.argv[1]; rows=json.load(open(path)); rows.append(dict(rows[0],handle="legacy-user")); json.dump(rows,open(path,"w"))
PY
export FAKE_PROVISION_MODE=no_mutation
bash "$MANAGER" >/dev/null 2>&1; ambiguous_invalid_rc=$?
[ "$ambiguous_invalid_rc" -ne 0 ] && ok "valid plus invalid recovery fails closed" || bad "valid plus invalid recovery unexpectedly short-circuits"
[ "$(wc -l <"$BROWSER_CALLS" | tr -d ' ')" -gt 0 ] && ok "valid plus invalid recovery invokes browser" || bad "valid plus invalid recovery skipped browser"
[ "$(wc -l <"$RUNNER_CALLS" | tr -d ' ')" -gt 0 ] && ok "valid plus invalid recovery invokes agent" || bad "valid plus invalid recovery skipped agent"

new_case invalid-recovery
seed_recovery_incident
python3 - "$CAPAFY_IG_ACCOUNTS_FILE" <<'PY'
import json,sys
path=sys.argv[1]; rows=json.load(open(path)); rows[0]["handle"]="legacy-user"; json.dump(rows,open(path,"w"))
PY
export FAKE_PROVISION_MODE=no_mutation
bash "$MANAGER" >/dev/null 2>&1; invalid_rc=$?
[ "$invalid_rc" -ne 0 ] && ok "single invalid recovery fails closed" || bad "single invalid recovery unexpectedly short-circuits"
[ "$(wc -l <"$BROWSER_CALLS" | tr -d ' ')" -gt 0 ] && ok "single invalid recovery invokes browser" || bad "single invalid recovery skipped browser"
[ "$(wc -l <"$RUNNER_CALLS" | tr -d ' ')" -gt 0 ] && ok "single invalid recovery invokes agent" || bad "single invalid recovery skipped agent"

new_case challenge
python3 - "$CAPAFY_IG_ACCOUNTS_FILE" <<'PY'
import json,sys
json.dump([{"handle":"capafy.failed","status":"warming","session_owner":"browser","created":"2026-08-01"}],open(sys.argv[1],"w"))
PY
printf '%s\n' '{"result":"challenge","handle":"capafy.failed","reason":"checkpoint challenge","next_retry_at":"immediately"}' >"$CAPAFY_MARKETING_RESULT"
CAPAFY_IG_LIFECYCLE="$LIFECYCLE" bash "$HANDOFF" 1 fixture >/dev/null 2>&1; challenge_rc=$?
eq "challenge is unresolved terminal" "$challenge_rc" 1
eq "challenge retires failed row" "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))[0]["status"])' "$CAPAFY_IG_ACCOUNTS_FILE")" session_failed
eq "challenge wakes manager once" "$(wc -l <"$KICKSTART_CALLS" | tr -d ' ')" 1
has "challenge wakes exact label" "$KICKSTART_CALLS" "ai.anicca.capafy-ig-account-manager"
if grep -Eqi 'Client\(\)\.login|login_by_sessionid|password.*login' "$KICKSTART_CALLS" "$RUNNER_CALLS"; then bad "challenge attempted private login"; else ok "challenge never attempts private login"; fi
bash "$MANAGER" >/dev/null 2>&1; replacement_rc=$?
eq "challenge chain provisions replacement" "$replacement_rc" 0
eq "replacement row is appended after retired history" "$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(len(d))' "$CAPAFY_IG_ACCOUNTS_FILE")" 2
eq "replacement becomes publish_probe_ready" "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["status"])' "$CAPAFY_IG_LIFECYCLE_STATE")" publish_probe_ready
eq "replacement lifecycle closure is delivered once" "$(grep -Fc 'replacement account created and verified' "$TELEGRAM_BODY")" 1
eq "replacement completion wakes daily publisher" "$(grep -Fc 'ai.anicca.capafy-ig-marketing-daily' "$KICKSTART_CALLS")" 1

printf '=== test_capafy_ig_account_manager: %s passed %s failed ===\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
