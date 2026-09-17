#!/usr/bin/env bash
# life-manager-loop/loop.sh — ONE no-human wake of the LIFE MANAGER money loop (GLVS / HARD 0.40).
# Money = REAL Stripe $ MRR (to Dais's BANK). Split out of the (wrongly-combined) lm-capafy-loop.
# Anti-fake (VCSDD-proven): error→NA never masked-$0; $ MRR not sub-count (expand price, live-shape
# verified); NA→READ-FAILED; live-key guard; HEAL LM /health + Stripe; selfheal-request on HEAL.
# Seams: LM_TEST=1 + LM_FIXTURE=<dir>, LM_DIR, LM_REQ.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIR="${LM_DIR:-$HERE}"; STATE_MD="$DIR/state/STATE.md"; mkdir -p "$DIR/state"
set -a; . $HOME/.local/state/life-manager/.env 2>/dev/null; set +a
REQ="${LM_REQ:-$HOME/.local/state/life-manager/state/life-manager-loop-selfheal-request.json}"
fetch(){ local name="$1" url="$2"; shift 2
  if [ "${LM_TEST:-}" = "1" ] && [ -n "${LM_FIXTURE:-}" ]; then cat "$LM_FIXTURE/$name.json" 2>/dev/null || echo '{}'; return 0; fi
  curl -s --max-time 20 "$@" "$url" 2>/dev/null; }
HEAL=""; add_heal(){ HEAL="$HEAL$1; "; }

# Stripe read mode. Prefer the private runtime key; when it is absent, use the
# already-authenticated Stripe CLI profile instead of copying an OAuth credential
# into this loop's environment.
STRIPE_SOURCE=""
if [ "${LM_TEST:-}" = "1" ]; then
  case "${STRIPE_SECRET_KEY:-}" in sk_live_*|rk_live_*) STRIPE_SOURCE="fixture" ;; "") add_heal "STRIPE-KEY-MISSING";; *) add_heal "STRIPE-KEY-NOT-LIVE";; esac
elif [ -n "${STRIPE_SECRET_KEY:-}" ]; then
  case "$STRIPE_SECRET_KEY" in sk_live_*|rk_live_*) STRIPE_SOURCE="curl" ;; *) add_heal "STRIPE-KEY-NOT-LIVE";; esac
elif command -v stripe >/dev/null 2>&1; then
  STRIPE_SOURCE="cli"
else
  add_heal "STRIPE-KEY-MISSING"
fi
# LM /health
if [ "${LM_TEST:-}" != "1" ]; then
  LMH="$(curl -s --max-time 10 -o /dev/null -w '%{http_code}' https://life-call-production.up.railway.app/health 2>/dev/null||echo 000)"
  [ "$LMH" = "200" ] || add_heal "LM-HEALTH-$LMH → check Railway life-call"
fi
# real $ MRR and billing readbacks (INV: dollars, expand price, live-shape verified; $0 subs → $0)
if [ "$STRIPE_SOURCE" = "cli" ]; then
  if ! LM_SUBS="$(stripe subscriptions list --live --status active --limit 100 -e data.items.data.price 2>/dev/null)"; then
    add_heal "STRIPE-READ-FAILED"
    LM_SUBS='{}'
  fi
  if ! LM_REFUNDS="$(stripe refunds list --live --limit 100 2>/dev/null)"; then
    add_heal "STRIPE-REFUNDS-READ-FAILED"
    LM_REFUNDS='{}'
  fi
  if ! LM_PAYMENT_INTENTS="$(stripe payment_intents list --live --limit 100 2>/dev/null)"; then
    add_heal "STRIPE-PAYMENTS-READ-FAILED"
    LM_PAYMENT_INTENTS='{}'
  fi
else
  LM_SUBS="$(fetch lm_subs 'https://api.stripe.com/v1/subscriptions?status=active&limit=100&expand[]=data.items.data.price' -u "${STRIPE_SECRET_KEY:-x}:")"
  LM_REFUNDS="$(fetch lm_refunds 'https://api.stripe.com/v1/refunds?limit=100' -u "${STRIPE_SECRET_KEY:-x}:")"
  LM_PAYMENT_INTENTS="$(fetch lm_payment_intents 'https://api.stripe.com/v1/payment_intents?limit=100' -u "${STRIPE_SECRET_KEY:-x}:")"
fi
if [ "${LM_TEST:-}" = "1" ]; then
  LM_FUNNEL_USERS="$(fetch lm_funnel_users 'fixture')"; [ "$LM_FUNNEL_USERS" = "{}" ] && LM_FUNNEL_USERS='[]'
  LM_FUNNEL_PREFS="$(fetch lm_funnel_prefs 'fixture')"; [ "$LM_FUNNEL_PREFS" = "{}" ] && LM_FUNNEL_PREFS='[]'
  FUNNEL_SOURCE="fixture"
elif [ -n "${SUPABASE_URL:-}" ] && [ -n "${SUPABASE_SERVICE_ROLE_KEY:-}" ]; then
  LM_FUNNEL_USERS="$(curl -s --max-time 20 -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" "$SUPABASE_URL/rest/v1/lm_users?select=tg_onboard_stage,calendar_connected_account_id,phone,paid,plan_status" 2>/dev/null)"
  LM_FUNNEL_PREFS="$(curl -s --max-time 20 -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" "$SUPABASE_URL/rest/v1/lm_panel_preferences?select=call_enabled" 2>/dev/null)"
  FUNNEL_SOURCE="supabase"
else
  LM_FUNNEL_USERS='{}'; LM_FUNNEL_PREFS='{}'; FUNNEL_SOURCE="none"; add_heal "FUNNEL-READ-FAILED"
fi
LM_MRR="$(printf '%s' "$LM_SUBS" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    if 'error' in d or d.get('object')!='list': print('NA'); raise SystemExit
    total=0.0
    for s in d.get('data',[]):
        for it in (s.get('items',{}) or {}).get('data',[]):
            pr=it.get('price'); pr=pr if isinstance(pr,dict) else {}
            amt=(pr.get('unit_amount') or 0)/100.0
            if (pr.get('recurring') or {}).get('interval')=='year': amt/=12.0
            total+=amt*(it.get('quantity') or 1)
    print(round(total,2))
except SystemExit: pass
except Exception: print('NA')" 2>/dev/null||echo NA)"
LM_ACTIVE_SUBS="$(printf '%s' "$LM_SUBS" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print(len(d.get('data',[])) if d.get('object')=='list' else 'NA')
except Exception: print('NA')" 2>/dev/null||echo NA)"
LM_PERIOD_END_MIN="$(printf '%s' "$LM_SUBS" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    values=[s.get('current_period_end') for s in d.get('data',[]) if s.get('current_period_end')]
    print(min(values) if values else 'none')
except Exception: print('NA')" 2>/dev/null||echo NA)"
LM_PERIOD_END_MAX="$(printf '%s' "$LM_SUBS" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    values=[s.get('current_period_end') for s in d.get('data',[]) if s.get('current_period_end')]
    print(max(values) if values else 'none')
except Exception: print('NA')" 2>/dev/null||echo NA)"
LM_REFUNDS_COUNT="$(printf '%s' "$LM_REFUNDS" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    print(len(d.get('data',[])) if d.get('object')=='list' else 'NA')
except Exception: print('NA')" 2>/dev/null||echo NA)"
LM_FAILED_PAYMENTS="$(printf '%s' "$LM_PAYMENT_INTENTS" | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    rows=d.get('data',[])
    failed=[p for p in rows if p.get('status')=='canceled' or p.get('last_payment_error')]
    print(len(failed) if d.get('object')=='list' else 'NA')
except Exception: print('NA')" 2>/dev/null||echo NA)"
FUNNEL_USER_METRICS="$(printf '%s' "$LM_FUNNEL_USERS" | python3 -c '
import json, sys
try:
    users=json.load(sys.stdin)
    if not isinstance(users,list): raise ValueError
    stages={}
    for row in users:
        stage=str(row.get("tg_onboard_stage") or "null")
        stages[stage]=stages.get(stage,0)+1
    started=sum(
        bool(row.get("tg_onboard_stage"))
        or bool(row.get("calendar_connected_account_id"))
        or bool(row.get("phone"))
        or row.get("paid") is True
        or row.get("plan_status") == "active"
        for row in users
    )
    connected=sum(bool(row.get("calendar_connected_account_id")) for row in users)
    phone=sum(bool(row.get("phone")) for row in users)
    paid=sum(row.get("paid") is True for row in users)
    active=sum(row.get("plan_status") == "active" for row in users)
    stages_text=",".join(f"{key}={stages[key]}" for key in sorted(stages))
    print("ok",len(users),started,len(users)-started,connected,phone,paid,active,stages_text,sep="\t")
except Exception:
    print("error", "NA", "NA", "NA", "NA", "NA", sep="\t")
')"
IFS=$'\t' read -r FUNNEL_PARSE_STATUS FUNNEL_USERS FUNNEL_STARTED FUNNEL_UNSTARTED FUNNEL_CALENDAR FUNNEL_PHONE FUNNEL_PAID FUNNEL_ACTIVE_PLAN FUNNEL_STAGES <<<"$FUNNEL_USER_METRICS"
FUNNEL_PREF_METRICS="$(printf '%s' "$LM_FUNNEL_PREFS" | python3 -c '
import json,sys
try:
    prefs=json.load(sys.stdin)
    if not isinstance(prefs,list): raise ValueError
    print("ok",sum(row.get("call_enabled") is True for row in prefs),sep="\t")
except Exception:
    print("error\tNA")
')"
IFS=$'\t' read -r FUNNEL_PREF_STATUS FUNNEL_CALL_OPT_IN <<<"$FUNNEL_PREF_METRICS"
[ "$FUNNEL_PARSE_STATUS" = "ok" ] && [ "$FUNNEL_PREF_STATUS" = "ok" ] || add_heal "FUNNEL-READ-FAILED"

PREV="$(grep -E '^lm_mrr_usd:' "$STATE_MD" 2>/dev/null | awk '{print $2}' | tail -1)"; PREV="${PREV:-n/a}"
if [ -n "$HEAL" ]; then STATUS="HEAL-NEEDED — ${HEAL}(MRR \$$LM_MRR)"
elif [ "$LM_MRR" = "NA" ]; then STATUS="READ-FAILED — LM MRR cannot be read; DO NOT trust"
elif awk "BEGIN{exit !($LM_MRR>0)}" 2>/dev/null; then STATUS="EARNING \$$LM_MRR/mo — grow: fix the weakest funnel step + Reddit demand"
else STATUS="NO LM revenue yet (\$0/mo) — 3 test users only; bottleneck = DEMAND (real users); fix the weakest funnel step + drive signups"; fi
if [ -n "$HEAL" ]; then
  NEXT="HEAL-NEEDED→fix (a selfheal-request was written)"
else
  NEXT="ACT: read the Telegram funnel (start→calendar→phone→pay→retain), fix the ONE weakest step OR drive Reddit demand; VERIFY a real new paid Stripe sub"
fi
if [ -n "$HEAL" ]; then mkdir -p "$(dirname "$REQ")"; printf '{"loop":"life-manager","ts":"%s","heal":"%s"}\n' "$(date -u +%FT%TZ)" "${HEAL//\"/}" > "$REQ"; else rm -f "$REQ" 2>/dev/null||true; fi
TMP="$STATE_MD.tmp.$$"
{
  echo "# Life Manager money loop — STATE (GLVS, no-human, money → Dais bank)"
  echo "goal: real Stripe \$ MRR, growing. Real \$ only; never masked-error-as-0; \$ MRR not a sub count."
  echo "last_wake_utc: $(date -u +%FT%TZ)"
  echo "heal_first: ${HEAL:-all healthy (LM /health 200 ✓, Stripe ${STRIPE_SOURCE:-none} ✓)}"
  echo "stripe_source: ${STRIPE_SOURCE:-none}"
  echo "lm_mrr_usd: $LM_MRR"
  echo "active_subscription_count: $LM_ACTIVE_SUBS"
  echo "subscription_period_end_min: $LM_PERIOD_END_MIN"
  echo "subscription_period_end_max: $LM_PERIOD_END_MAX"
  echo "refund_count: $LM_REFUNDS_COUNT"
  echo "failed_payment_count: $LM_FAILED_PAYMENTS"
  echo "funnel_source: ${FUNNEL_SOURCE:-none}"
  echo "funnel_users: $FUNNEL_USERS"
  echo "funnel_started_users: $FUNNEL_STARTED"
  echo "funnel_unstarted_users: $FUNNEL_UNSTARTED"
  echo "funnel_calendar_connected: $FUNNEL_CALENDAR"
  echo "funnel_phone_saved: $FUNNEL_PHONE"
  echo "funnel_paid: $FUNNEL_PAID"
  echo "funnel_active_plan: $FUNNEL_ACTIVE_PLAN"
  echo "funnel_call_opt_in: $FUNNEL_CALL_OPT_IN"
  echo "funnel_stages: $FUNNEL_STAGES"
  echo "prev_lm_mrr_usd: $PREV"
  echo "status: $STATUS"
  echo "selfheal_request: ${HEAL:+written→$REQ}${HEAL:-none}"
  echo "next: $NEXT"
} > "$TMP" && mv "$TMP" "$STATE_MD"
echo "[life-manager-loop] MRR=\$$LM_MRR | heal=${HEAL:-none} | $STATUS"

# Liveness heartbeat (FIND-032): touch it HERE, in the deterministic MEASURE core (runs first on every
# pass — startup + daily cron — completes in ~2s, cannot derail). Previously the heartbeat was touched
# ONLY at the very end of the open-ended STARTUP/cron pass ("FINALLY touch"), AFTER STEP2 ACT — a
# rabbit-hole-prone agentic task (funnel/Telegram-bot debugging) that can run for hours and never return
# to the touch. That starved the heartbeat → healthcheck STALE → restart → pkill kills the in-progress
# claude → fresh claude re-enters the same STEP2 → still no touch within the 5-min window → STALE again
# → restart loop that kills the very session that would refresh the heartbeat → give-up → self-fix.
# The healthcheck contract is "liveness + stuck-detection only" (revenue truth = verify-loops.sh), so
# liveness must mean "the loop executed its measurable core this pass", NOT "an open-ended money task
# fully completed". Skip under test mode so the real prod heartbeat is never touched by test-loop.sh.
[ "${LM_TEST:-}" = "1" ] || { mkdir -p "$HOME/.local/state/life-manager/state" && touch "$HOME/.local/state/life-manager/state/.life-manager-loop-last-pass" 2>/dev/null; } || true
