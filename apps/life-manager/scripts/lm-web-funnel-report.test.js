"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { runWebFunnelReport, stripeFeeRows } = require("./lm-web-funnel-report.js");

const UID = "lm_11111111-1111-4111-8111-111111111111";

test("refund balance transaction resolves its customer through the charge and reads payout state", async () => {
  const calls = [];
  const stripe = {
    balanceTransactions: {
      async list(params) {
        if (params.payout) {
          calls.push(["balance_transactions_by_payout", params]);
          return { has_more: false, data: [{ id: "txn_refund" }] };
        }
        calls.push(["balance_transactions", params]);
        return { has_more: false, data: [{
          id: "txn_refund", type: "refund", source: { id: "re_web", customer: null, charge: "ch_web" },
          amount: -500, fee: 0, net: -500, currency: "usd", status: "available", created: 1_893_456_000,
        }] };
      },
    },
    charges: { async retrieve(id) { calls.push(["charge", id]); return { id, customer: "cus_web" }; } },
    payouts: { async list(params) {
      calls.push(["payouts", params]);
      return { has_more: false, data: [{
        id: "po_web", status: "paid", automatic: true, reconciliation_status: "completed",
      }] };
    } },
  };

  const result = await stripeFeeRows(stripe, new Map([["cus_web", UID]]), 1_893_000_000);

  assert.equal(result.complete, true);
  assert.equal(result.payoutsComplete, true);
  assert.deepEqual(result.rows, [{
    uid: UID,
    fee: 0,
    amount: -500,
    net: -500,
    currency: "usd",
    status: "available",
    type: "refund",
    payout_id: "po_web",
    payout_status: "paid",
    created: "2030-01-01T00:00:00.000Z",
  }]);
  assert.deepEqual(calls.map(([kind]) => kind), ["balance_transactions", "charge", "payouts", "balance_transactions_by_payout"]);
  const payoutTransactionsCall = calls.find(([kind]) => kind === "balance_transactions_by_payout");
  assert.equal(payoutTransactionsCall[1].payout, "po_web");
});

test("does not claim complete payout attribution for manual or unreconciled payouts", async (t) => {
  const cases = [
    { name: "manual payout", payout: { id: "po_manual", status: "paid", automatic: false, reconciliation_status: "not_applicable" } },
    { name: "automatic payout still reconciling", payout: { id: "po_reconciling", status: "paid", automatic: true, reconciliation_status: "in_progress" } },
  ];

  for (const { name, payout } of cases) {
    await t.test(name, async () => {
      const calls = [];
      const stripe = {
        balanceTransactions: { async list(params) {
          calls.push(["balance_transactions", params]);
          return { has_more: false, data: params.payout ? [] : [{
            id: "txn_charge", type: "charge", source: { id: "ch_web", customer: "cus_web" },
            amount: 500, fee: 20, net: 480, currency: "usd", status: "available", created: 1_893_456_000,
          }] };
        } },
        charges: { async retrieve(id) { return { id, customer: "cus_web" }; } },
        payouts: { async list() { return { has_more: false, data: [payout] }; } },
      };

      const result = await stripeFeeRows(stripe, new Map([["cus_web", UID]]), 1_893_000_000);

      assert.equal(result.complete, true);
      assert.equal(result.payoutsComplete, false);
      assert.equal(calls.filter(([kind]) => kind === "balance_transactions").length, 1);
    });
  }
});

test("report reads invoice history outside the current window to distinguish first sale from renewal", async () => {
  const nowMs = Date.parse("2030-02-01T00:00:00Z");
  const events = [
    { event_id: "evt_paid_old", event_name: "paid_invoice", uid: UID,
      source_object_id: "in_old", amount_usd: 29, currency: "usd",
      occurred_at: new Date(nowMs - 40 * 86400000).toISOString() },
    { event_id: "evt_paid_current", event_name: "paid_invoice", uid: UID,
      source_object_id: "in_current", amount_usd: 29, currency: "usd",
      occurred_at: new Date(nowMs - 1000).toISOString() },
  ];
  const requests = [];
  const fetchImpl = async (input) => {
    const url = new URL(String(input));
    requests.push(url);
    if (url.pathname.endsWith("/lm_users")) return { ok: true, json: async () => [{
      uid: UID, telegram_chat_id: null, web_first_touch: {}, web_first_travel_at: null,
      stripe_customer_id: null,
    }] };
    if (url.pathname.endsWith("/lm_web_funnel_events")) {
      const historyRead = url.searchParams.get("event_name") === "eq.paid_invoice";
      return { ok: true, json: async () => historyRead ? events : events.filter((event) => Date.parse(event.occurred_at) >= nowMs - 30 * 86400000) };
    }
    if (url.pathname.endsWith("/lm_api_cost")) return { ok: true, json: async () => [] };
    throw new Error("unexpected report read");
  };
  const stripeClient = {
    subscriptions: { async list() { return { data: [], has_more: false }; } },
    balanceTransactions: { async list() { throw new Error("no customer means no fee read"); } },
  };
  const result = await runWebFunnelReport({
    env: { SUPABASE_URL: "https://db.example", SUPABASE_SERVICE_ROLE_KEY: "service-key", STRIPE_SECRET_KEY: "sk_live_report" },
    fetchImpl, stripeClient, nowMs, periodDays: 30,
  });

  assert.ok(requests.some((url) => url.pathname.endsWith("/lm_web_funnel_events")
    && url.searchParams.get("event_name") === "eq.paid_invoice"
    && !url.searchParams.has("occurred_at")));
  assert.equal(result.funnel.paidInvoices, 1);
  assert.equal(result.funnel.firstPaidUsers, 0);
  assert.equal(result.funnel.renewalInvoices, 1);
});
