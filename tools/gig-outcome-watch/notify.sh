#!/usr/bin/env bash
# Run the outcome watch and notify the owner when something is wrong.
#
# Intentionally outside skills/gig-work: the loop must not be able to edit the thing that
# judges it. Also intentionally dumb — no model call, no browser, so it cannot fail for the
# same reasons the loop fails.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${LIFE_MANAGER_RUNTIME_PYTHON:-${LIFE_MANAGER_PYTHON:-${PY:-python3}}}"
STATE="${LIFE_MANAGER_STATE_ROOT:-$HOME/.local/state/life-manager/gig-outcome-watch}"
SENDER="$HERE/../../skills/_shared/send-telegram.sh"
mkdir -p "$STATE"

ENV_FILE="${LIFE_MANAGER_ENV_FILE:-$HOME/.local/state/life-manager/.env}"
if [ -f "$ENV_FILE" ]; then
  set -a; . "$ENV_FILE"; set +a
fi
CHAT_ID="${GIG_WATCH_CHAT_ID:-${TELEGRAM_ALERT_CHAT_ID:-}}"

for helper in outcome_watch.py verify_domain_skills.sh; do
  [ -f "$HERE/$helper" ] || { echo "observation_failed: helper_missing=$helper" >&2; exit 75; }
done
json="$("$PY" "$HERE/outcome_watch.py" --window-hours "${WINDOW_HOURS:-24}" --json)"
rc=$?
[ "$rc" -le 1 ] || { echo "observation_failed: outcome_json exit=$rc" >&2; exit 75; }
text="$("$PY" "$HERE/outcome_watch.py" --window-hours "${WINDOW_HOURS:-24}")"
rc=$?
[ "$rc" -le 1 ] || { echo "observation_failed: outcome_text exit=$rc" >&2; exit 75; }

printf '%s\n' "$json" >> "$STATE/history.jsonl"

alerts="$(printf '%s' "$json" | "$PY" -c 'import json,sys; print(",".join(json.load(sys.stdin)["alerts"]))')" || {
  echo "observation_failed: invalid_outcome_json" >&2; exit 75;
}

# Did the live pass actually put the domain skills in front of the model?
#
# The first wiring attempt LOOKED correct and was not: step() carried the skills, but
# run_paid_work() and assess_paid_queue() compose their prompts inline and never enter
# step(), so the live PAID_WORK prompt contained zero of them. A unit test would have
# passed. Only reading the prompt the model was actually handed catches that — so it is
# checked here, hourly, against the newest real pass rather than trusted once at merge time.
#
# exit 1 = some prompts lack the skills (a real regression, alert).
# exit 2 = no evidence or no prompts yet (the pass has not run, not a regression, stay quiet).
ds_json="$(bash "$HERE/verify_domain_skills.sh")"
ds_rc=$?
[ "$ds_rc" -le 2 ] || { echo "observation_failed: domain_skills exit=$ds_rc" >&2; exit 75; }
printf '%s\n' "$ds_json" >> "$STATE/domain-skills.jsonl"
if [ "$ds_rc" -eq 1 ]; then
  alerts="${alerts:+$alerts,}domain_skills_missing"
  text="${text}

⚠️ ドメイン知識がモデルに渡っていません
$(printf '%s' "$ds_json" | "$PY" -c 'import json,sys; print("  pass {pass}: プロンプト {prompts}件中 {with_skills}件にしか載っていない".format(**json.load(sys.stdin)))')
  この状態のループは、8/5 に人手で洗い出した16項目を知らないまま走っています。"
fi

if [ -z "$alerts" ]; then
  echo "ok: no alerts"
  exit 0
fi

# One message per alert-set per day: a detector that repeats itself hourly gets muted by
# the human, and a muted detector is the same as no detector.
stamp="$(date +%F)-${alerts}"
if [ -f "$STATE/last-sent" ] && [ "$(cat "$STATE/last-sent")" = "$stamp" ]; then
  echo "suppressed duplicate: $stamp"
  exit 0
fi

# Delivery, and how we know it happened.
#
# The previous version piped curl to /dev/null and treated exit 0 as "sent". curl exits 0 on
# an HTTP 502 with a body, and on 2026-08-05 api.telegram.org returned 502 three times in a
# row to this machine — so the old code could mark an undelivered alert as sent and then
# suppress it for the rest of the day. A detector that cannot prove delivery is not a
# detector. Send through Life Manager's repository-owned client and only record
# last-sent when its provider receipt contains a message id.
attempt=1
while [ "$attempt" -le 3 ]; do
  errf="$(mktemp -t gigwatch)"
  resp="$(PYTHON="$PY" "$SENDER" "$text" "$CHAT_ID" 2>"$errf")"
  mid="$(printf '%s' "$resp" | sed -n 's/^TELEGRAM_SENT=true MSGID=//p' | tail -1)"
  if [ -n "$mid" ]; then
    rm -f "$errf"
    printf '%s' "$stamp" > "$STATE/last-sent"
    echo "sent: $alerts messageId=$mid attempt=$attempt"
    exit 0
  fi
  echo "send attempt=$attempt failed: out=$(printf '%s' "$resp" | tr '\n' ' ' | head -c 120) err=$(tr '\n' ' ' < "$errf" | head -c 120)" >&2
  rm -f "$errf"
  attempt=$((attempt + 1))
  [ "$attempt" -le 3 ] && sleep 5
done
# Not writing last-sent on failure is deliberate: an undelivered alert must be retried on the
# next hourly run, not suppressed for the day.
echo "UNDELIVERED after 3 attempts; alerts=$alerts" >&2
exit 1
