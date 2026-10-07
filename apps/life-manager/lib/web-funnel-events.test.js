"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
let funnelEvents = null;
try { funnelEvents = require("./web-funnel-events.js"); } catch {}

const UID = "lm_12345678-1234-1234-1234-123456789abc";

test("normalizes only allowlisted funnel fields and bounded UTM values", () => {
  assert.ok(funnelEvents, "Web funnel event module is implemented");
  const row = funnelEvents.normalizeWebFunnelEvent({
    eventName: "landing_view",
    eventId: "view-1",
    attribution: {
      utm_source: "instagram", utm_medium: "social", utm_campaign: "fall-travel",
      utm_id: "must-not-pass", utm_content: "c".repeat(241),
    },
    ip: "192.0.2.1", userAgent: "private-browser", email: "private@example.invalid",
  }, Date.parse("2030-01-01T00:00:00Z"));

  assert.deepEqual(row, {
    event_id: "view-1",
    event_name: "landing_view",
    uid: null,
    source_object_id: null,
    source_event_id: null,
    attribution: { utm_source: "instagram", utm_medium: "social", utm_campaign: "fall-travel" },
    amount_usd: null,
    currency: null,
    billing_reason: null,
    occurred_at: "2030-01-01T00:00:00.000Z",
  });
});

test("rejects invalid lifecycle events, user ids, amounts, and billing reasons", () => {
  assert.ok(funnelEvents, "Web funnel event module is implemented");
  assert.throws(() => funnelEvents.normalizeWebFunnelEvent({ eventName: "calendar_event_title" }));
  assert.throws(() => funnelEvents.normalizeWebFunnelEvent({ eventName: "paid_invoice", uid: "telegram-user" }));
  assert.throws(() => funnelEvents.normalizeWebFunnelEvent({ eventName: "paid_invoice", amountUsd: -1 }));
  assert.throws(() => funnelEvents.normalizeWebFunnelEvent({ eventName: "paid_invoice", billingReason: "customer@email" }));
});

test("writes the append-only event without retaining arbitrary request fields", async () => {
  assert.ok(funnelEvents, "Web funnel event module is implemented");
  let request;
  const ok = await funnelEvents.recordWebFunnelEvent({
    eventName: "paid_invoice", eventId: "evt_123", sourceObjectId: "in_123", sourceEventId: "evt_123",
    uid: UID, amountUsd: 29, currency: "USD", billingReason: "subscription_cycle",
    eventTitle: "private meeting", address: "private address",
  }, {
    supaUrl: "https://db.example", supaKey: "service-role-test-key", nowMs: 1000,
    fetchImpl: async (url, init) => {
      request = { url, init };
      return { ok: true, status: 201 };
    },
  });

  assert.equal(ok, true);
  assert.equal(request.url, "https://db.example/rest/v1/lm_web_funnel_events");
  assert.equal(request.init.method, "POST");
  const body = JSON.parse(request.init.body);
  assert.equal(body.uid, UID);
  assert.equal(body.amount_usd, 29);
  assert.equal(body.currency, "usd");
  assert.equal(body.billing_reason, "subscription_cycle");
  assert.equal(Object.hasOwn(body, "eventTitle"), false);
  assert.equal(Object.hasOwn(body, "address"), false);
  assert.equal(JSON.stringify(body).includes("private"), false);
});

test("a duplicate source event is successful and a ledger failure stays non-blocking", async () => {
  assert.ok(funnelEvents, "Web funnel event module is implemented");
  const duplicate = await funnelEvents.recordWebFunnelEvent({
    eventName: "paid_invoice", eventId: "evt_123", sourceEventId: "evt_123", uid: UID,
  }, {
    supaUrl: "https://db.example", supaKey: "fixture",
    fetchImpl: async () => ({ ok: false, status: 409 }),
  });
  const failure = await funnelEvents.recordWebFunnelEvent({ eventName: "landing_view" }, {
    supaUrl: "https://db.example", supaKey: "fixture",
    fetchImpl: async () => ({ ok: false, status: 503 }),
  });
  assert.equal(duplicate, true);
  assert.equal(failure, false);
});

test("server request funnel events retain only the exact landing and connect UTM fields", () => {
  assert.equal(typeof funnelEvents.webFunnelEventForRequest, "function");
  assert.deepEqual(funnelEvents.webFunnelEventForRequest(
    "/lm?utm_source=x&utm_medium=social&utm_campaign=travel&utm_id=discard",
  ), {
    eventName: "landing_view",
    attribution: { utm_source: "x", utm_medium: "social", utm_campaign: "travel" },
  });
  assert.deepEqual(funnelEvents.webFunnelEventForRequest(
    "/auth/google?utm_source=instagram&utm_campaign=founder-story",
  ), {
    eventName: "google_connect_start",
    attribution: { utm_source: "instagram", utm_campaign: "founder-story" },
  });
  assert.equal(funnelEvents.webFunnelEventForRequest("/auth/google/callback?code=private"), null);
  assert.equal(funnelEvents.webFunnelEventForRequest("/auth/google", "POST"), null);
  assert.equal(funnelEvents.webFunnelEventForRequest("/lm", "POST"), null);
  assert.equal(funnelEvents.webFunnelEventForRequest("/unknown?utm_source=x"), null);
});

test("Stripe webhook mappings capture Web trial, paid invoice, and cancellation with server ids", () => {
  assert.equal(typeof funnelEvents.webFunnelEventFromStripe, "function");
  const { parseStripeEvent } = require("./billing.js");
  const base = {
    created: 1_893_456_000,
    data: { object: { metadata: { lm_uid: UID, lm_product: "life_manager_web_travel" } } },
  };
  const trial = { ...base, id: "evt_trial", type: "customer.subscription.created",
    data: { object: { ...base.data.object, id: "sub_web", status: "trialing", default_payment_method: "pm_saved" } } };
  assert.deepEqual(funnelEvents.webFunnelEventFromStripe(trial, parseStripeEvent(trial)), {
    eventName: "trial_started", uid: UID, sourceObjectId: "sub_web", sourceEventId: "evt_trial",
    attribution: {}, occurredAt: "2030-01-01T00:00:00.000Z",
  });
  const noCardTrial = { ...trial, id: "evt_trial_no_card", data: { object: {
    ...trial.data.object, default_payment_method: null,
  } } };
  assert.equal(funnelEvents.webFunnelEventFromStripe(noCardTrial, parseStripeEvent(noCardTrial)), null);

  const paid = { ...base, id: "evt_invoice", type: "invoice.paid", data: { object: {
    ...base.data.object, id: "in_web", amount_paid: 2900, currency: "usd",
    billing_reason: "subscription_cycle", subscription: "sub_web",
  } } };
  assert.deepEqual(funnelEvents.webFunnelEventFromStripe(paid, parseStripeEvent(paid)), {
    eventName: "paid_invoice", uid: UID, sourceObjectId: "in_web", sourceEventId: "evt_invoice",
    amountUsd: 29, currency: "usd", billingReason: "subscription_cycle", attribution: {},
    occurredAt: "2030-01-01T00:00:00.000Z",
  });

  const canceled = { ...base, id: "evt_cancel", type: "customer.subscription.deleted",
    data: { object: { ...base.data.object, id: "sub_web", status: "canceled" } } };
  assert.equal(funnelEvents.webFunnelEventFromStripe(canceled, parseStripeEvent(canceled)).eventName, "subscription_canceled");
  assert.equal(funnelEvents.webFunnelEventFromStripe({ ...paid, id: "evt_zero", data: { object: {
    ...paid.data.object, amount_paid: 0,
  } } }, parseStripeEvent({ ...paid, id: "evt_zero", data: { object: {
    ...paid.data.object, amount_paid: 0,
  } } })), null);
});

test("trial-period cancellation maps to cancellation and the Stripe writer persists lifecycle events", async () => {
  assert.equal(typeof funnelEvents.recordWebFunnelStripeEvent, "function");
  const { parseStripeEvent } = require("./billing.js");
  const event = {
    id: "evt_trial_cancel", type: "customer.subscription.updated", created: 1_893_456_000,
    data: { object: {
      id: "sub_trial", status: "trialing", cancel_at_period_end: true,
      metadata: { lm_uid: UID, lm_product: "life_manager_web_travel" },
    } },
  };
  const rows = [];
  const recorded = await funnelEvents.recordWebFunnelStripeEvent(event, parseStripeEvent(event), { uid: UID }, {
    recordWebFunnelEventImpl: async (row) => { rows.push(row); return true; },
  });
  assert.equal(recorded, true);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].eventName, "cancellation_requested");
  assert.equal(rows[0].sourceObjectId, "sub_trial");
  assert.equal(rows[0].sourceEventId, "evt_trial_cancel");
});

test("refund webhook mapping records only a succeeded refund for an exact Web uid", () => {
  assert.equal(typeof funnelEvents.webFunnelEventFromRefund, "function");
  const event = {
    id: "evt_refund", type: "refund.updated", created: 1_893_456_000,
    data: { object: { id: "re_web", status: "succeeded", amount: 500, currency: "usd" } },
  };
  assert.deepEqual(funnelEvents.webFunnelEventFromRefund(event, UID), {
    eventName: "refund_recorded", uid: UID, sourceObjectId: "re_web", sourceEventId: "evt_refund",
    amountUsd: 5, currency: "usd",
    attribution: {}, occurredAt: "2030-01-01T00:00:00.000Z",
  });
  assert.equal(funnelEvents.webFunnelEventFromRefund({ ...event, data: { object: {
    ...event.data.object, status: "pending",
  } } }, UID), null);
  assert.equal(funnelEvents.webFunnelEventFromRefund(event, "telegram-user"), null);
});

test("refund webhook recording joins only the saved Web Stripe customer and retries store failures", async () => {
  assert.equal(typeof funnelEvents.recordWebFunnelRefund, "function");
  const event = {
    id: "evt_refund", type: "refund.created", created: 1_893_456_000,
    data: { object: { id: "re_web", status: "succeeded", amount: 500, currency: "usd", customer: "cus_web" } },
  };
  const calls = [];
  const ok = await funnelEvents.recordWebFunnelRefund(event, {
    supaUrl: "https://db.example", supaKey: "service-role-test-key",
    fetchImpl: async (url) => {
      calls.push(String(url));
      return { ok: true, json: async () => [{ uid: UID }] };
    },
    recordWebFunnelEventImpl: async (row) => { calls.push(row); return true; },
  });
  assert.equal(ok, true);
  assert.match(calls[0], /stripe_customer_id=eq\.cus_web/);
  assert.match(calls[0], /telegram_chat_id=is\.null/);
  assert.match(calls[0], /web_first_travel_at=not\.is\.null/);
  assert.equal(calls[1].uid, UID);
  assert.equal(calls[1].amountUsd, 5);
  assert.equal(calls[1].sourceObjectId, "re_web");

  const failed = await funnelEvents.recordWebFunnelRefund(event, {
    supaUrl: "https://db.example", supaKey: "service-role-test-key",
    fetchImpl: async () => ({ ok: true, json: async () => [{ uid: UID }] }),
    recordWebFunnelEventImpl: async () => false,
  });
  assert.equal(failed, false, "a failed refund receipt can be retried by Stripe");
});
