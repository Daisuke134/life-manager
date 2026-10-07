"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
let reportModule = null;
try { reportModule = require("./web-funnel-report.js"); } catch {}

const UID_A = "lm_11111111-1111-4111-8111-111111111111";
const UID_B = "lm_22222222-2222-4222-8222-222222222222";
const NOW = Date.parse("2030-02-01T00:00:00Z");

test("reports the Web funnel, active MRR, provider estimates, fees, refunds, and mature retention separately", () => {
  assert.ok(reportModule, "Web funnel report module is implemented");
  const events = [
    { event_name: "landing_view", attribution: { utm_source: "instagram", utm_medium: "social", utm_campaign: "founder" }, occurred_at: new Date(NOW - 10_000).toISOString() },
    { event_name: "landing_view", attribution: { utm_source: "instagram", utm_medium: "social", utm_campaign: "founder" }, occurred_at: new Date(NOW - 9_000).toISOString() },
    { event_name: "google_connect_start", attribution: { utm_source: "instagram", utm_medium: "social", utm_campaign: "founder" }, occurred_at: new Date(NOW - 8_000).toISOString() },
    { event_name: "google_authenticated", uid: UID_A, occurred_at: new Date(NOW - 7_000).toISOString() },
    { event_name: "calendar_active", uid: UID_A, occurred_at: new Date(NOW - 6_000).toISOString() },
    { event_name: "first_travel_block", uid: UID_A, occurred_at: new Date(NOW - 5_000).toISOString() },
    { event_name: "first_travel_block", uid: UID_B, occurred_at: new Date(NOW - 4_000).toISOString() },
    { event_name: "checkout_created", uid: UID_A, source_object_id: "cs_1", occurred_at: new Date(NOW - 3_000).toISOString() },
    { event_name: "trial_started", uid: UID_A, source_object_id: "sub_a", occurred_at: new Date(NOW - 2_000).toISOString() },
    { event_name: "paid_invoice", uid: UID_A, source_object_id: "in_1", amount_usd: 29, currency: "usd", occurred_at: new Date(NOW - 1_000).toISOString() },
    { event_name: "paid_invoice", uid: UID_A, source_object_id: "in_2", amount_usd: 29, currency: "usd", occurred_at: new Date(NOW - 500).toISOString() },
    { event_name: "refund_recorded", uid: UID_A, source_object_id: "re_1", amount_usd: 4, currency: "usd", occurred_at: new Date(NOW - 250).toISOString() },
  ];
  const users = [
    { uid: UID_A, telegram_chat_id: null, web_first_touch: { utm_source: "instagram", utm_medium: "social", utm_campaign: "founder" }, web_first_travel_at: new Date(NOW - 40 * 86400000).toISOString() },
    { uid: UID_B, telegram_chat_id: null, web_first_touch: { utm_source: "x", utm_medium: "social" }, web_first_travel_at: new Date(NOW - 3 * 86400000).toISOString() },
    { uid: "telegram-user", telegram_chat_id: "123", paid: true, web_first_travel_at: new Date(NOW - 50 * 86400000).toISOString() },
  ];
  const providerCosts = [
    { uid: UID_A, ts: new Date(NOW - 1000).toISOString(), est_usd: 0.1, meta: { actual_usd: null } },
    { uid: UID_B, ts: new Date(NOW - 500).toISOString(), est_usd: 0.05, meta: { actual_usd: null } },
    { uid: "telegram-user", ts: new Date(NOW - 500).toISOString(), est_usd: 99, meta: { actual_usd: 99 } },
  ];
  const subscriptions = [
    { id: "sub_a", status: "active", metadata: { lm_uid: UID_A, lm_product: "life_manager_web_travel" }, items: { data: [
      { quantity: 1, price: { unit_amount: 2900, currency: "usd", recurring: { interval: "month", interval_count: 1 } } },
    ] } },
    { id: "sub_b", status: "trialing", metadata: { lm_uid: UID_B, lm_product: "life_manager_web_travel" }, items: { data: [
      { quantity: 1, price: { unit_amount: 2900, currency: "usd", recurring: { interval: "month", interval_count: 1 } } },
    ] } },
  ];
  const balanceTransactions = [
    { uid: UID_A, fee: 117, net: 2883, currency: "usd", status: "available", created: new Date(NOW - 1000).toISOString() },
    { uid: UID_B, fee: 2, net: 2898, currency: "usd", status: "pending", created: new Date(NOW - 500).toISOString() },
  ];

  const result = reportModule.buildWebFunnelReport({
    events, users, providerCosts, subscriptions, balanceTransactions, nowMs: NOW, periodDays: 30,
  });

  assert.deepEqual(result.funnel, {
    landingViews: 2,
    googleConnectStarts: 1,
    googleAuthenticatedUsers: 1,
    calendarActiveUsers: 1,
    firstTravelUsers: 2,
    checkoutSessions: 1,
    trialStartedUsers: 1,
    paidInvoices: 2,
    firstPaidUsers: 1,
    renewalInvoices: 1,
    cancellationRequests: 0,
    canceledUsers: 0,
    refundsUsd: 4,
  });
  assert.equal(result.subscription.activeTrials, 1);
  assert.equal(result.subscription.activePaidUsers, 1);
  assert.equal(result.subscription.grossMrrUsd, 29);
  assert.equal(result.retention.d7.maturedUsers, 1);
  assert.equal(result.retention.d7.activePaidUsers, 1);
  assert.equal(result.retention.d30.maturedUsers, 1);
  assert.equal(result.retention.d30.activePaidUsers, 1);
  assert.equal(result.costs.providerEstimatedUsd, 0.15);
  assert.equal(result.costs.providerActualUsd, null);
  assert.equal(result.costs.stripeFeesUsd, 1.19);
  assert.equal(result.costs.hostingUsd, null);
  assert.equal(result.costs.marketingUsd, null);
  assert.equal(result.costs.netContributionUsd, null);
  const instagram = result.attribution.find((row) => row.attribution.utm_source === "instagram");
  assert.equal(instagram.landingViews, 2);
  assert.equal(instagram.googleConnectStarts, 1);
  assert.equal(instagram.firstTravelUsers, 1);
});

test("never counts trials as MRR and leaves actual provider cost unknown when any request lacks a bill", () => {
  assert.ok(reportModule, "Web funnel report module is implemented");
  const result = reportModule.buildWebFunnelReport({
    events: [],
    users: [{ uid: UID_B, telegram_chat_id: null, web_first_touch: {}, web_first_travel_at: null }],
    providerCosts: [{ uid: UID_B, ts: new Date(NOW).toISOString(), est_usd: 0.04, meta: { actual_usd: null } }],
    subscriptions: [{ id: "sub_trial", status: "trialing", metadata: { lm_uid: UID_B, lm_product: "life_manager_web_travel" }, items: { data: [] } }],
    balanceTransactions: [], nowMs: NOW, periodDays: 30,
  });
  assert.equal(result.subscription.grossMrrUsd, 0);
  assert.equal(result.subscription.activeTrials, 1);
  assert.equal(result.costs.providerEstimatedUsd, 0.04);
  assert.equal(result.costs.providerActualUsd, null);
  assert.equal(result.costs.netContributionUsd, null);
});
