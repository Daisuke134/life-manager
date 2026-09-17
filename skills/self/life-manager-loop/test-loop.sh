#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; LOOP="$HERE/loop.sh"; PASS=0; FAIL=0
run(){ local T; T="$(mktemp -d)"; local F="$T/fx" S="$T/state" KEY="${2:-sk_live_test}"; mkdir -p "$F" "$S"; printf '%s' "$1">"$F/lm_subs.json"
  LM_TEST=1 LM_FIXTURE="$F" LM_DIR="$T" LM_REQ="$T/req.json" STRIPE_SECRET_KEY="$KEY" bash "$LOOP" >/dev/null 2>&1; cat "$S/STATE.md"; rm -rf "$T"; }
run_billing(){ local T; T="$(mktemp -d)"; local F="$T/fx" S="$T/state"; mkdir -p "$F" "$S"
  printf '%s' '{"object":"list","data":[{"current_period_end":200,"items":{"data":[{"quantity":1,"price":{"unit_amount":2900,"recurring":{"interval":"month"}}}]}}]}' > "$F/lm_subs.json"
  printf '%s' '{"object":"list","data":[{},{}]}' > "$F/lm_refunds.json"
  printf '%s' '{"object":"list","data":[{"status":"succeeded"},{"status":"canceled"},{"status":"requires_payment_method","last_payment_error":{"code":"card_declined"}}]}' > "$F/lm_payment_intents.json"
  printf '%s' '[{"tg_onboard_stage":"calendar","calendar_connected_account_id":"cal","phone":"test-phone","paid":true,"plan_status":"active"},{"tg_onboard_stage":"done","calendar_connected_account_id":null,"phone":null,"paid":false,"plan_status":null}]' > "$F/lm_funnel_users.json"
  printf '%s' '[{"call_enabled":true}]' > "$F/lm_funnel_prefs.json"
  LM_TEST=1 LM_FIXTURE="$F" LM_DIR="$T" LM_REQ="$T/req.json" STRIPE_SECRET_KEY="rk_live_test" bash "$LOOP" >/dev/null 2>&1; cat "$S/STATE.md"; rm -rf "$T"; }
a(){ echo "$2"|grep -qE "$3" && { echo "  ok $1"; PASS=$((PASS+1)); } || { echo "  FAIL $1 (/$3/)"; FAIL=$((FAIL+1)); }; }
a "stripe-err→NA"     "$(run '{"error":{"message":"bad"}}')"                                                                          '^lm_mrr_usd: NA'
a "err→READ-FAILED"   "$(run '{"error":{"message":"bad"}}')"                                                                          '^status: READ-FAILED'
a "real-\$20→20.0"    "$(run '{"object":"list","data":[{"items":{"data":[{"quantity":1,"price":{"unit_amount":2000,"recurring":{"interval":"month"}}}]}}]}')" '^lm_mrr_usd: 20.0'
a "\$20→EARNING"      "$(run '{"object":"list","data":[{"items":{"data":[{"quantity":1,"price":{"unit_amount":2000,"recurring":{"interval":"month"}}}]}}]}')" '^status: EARNING'
a "true-0→0.0"        "$(run '{"object":"list","data":[]}')"                                                                          '^lm_mrr_usd: 0.0'
a "0→NO revenue"      "$(run '{"object":"list","data":[]}')"                                                                          '^status: NO LM revenue'
a "rk_live accepted"  "$(run '{"object":"list","data":[]}' rk_live_test)"                                                            '^heal_first: all healthy'
a "billing active count" "$(run_billing)"                                                                                                  '^active_subscription_count: 1$'
a "billing period end"   "$(run_billing)"                                                                                                  '^subscription_period_end_min: 200$'
a "billing refunds"      "$(run_billing)"                                                                                                  '^refund_count: 2$'
a "billing failures"     "$(run_billing)"                                                                                                  '^failed_payment_count: 2$'
a "funnel users"         "$(run_billing)"                                                                                                  '^funnel_users: 2$'
a "funnel call opt-in"   "$(run_billing)"                                                                                                  '^funnel_call_opt_in: 1$'
echo "=== life-manager-loop: $PASS passed $FAIL failed ==="; [ "$FAIL" = 0 ] && echo GREEN || exit 1
