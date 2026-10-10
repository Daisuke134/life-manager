"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

let webBilling;
try { webBilling = require("./web-billing.js"); } catch { webBilling = null; }

const UID = "lm_11111111-1111-4111-8111-111111111111";
const ORIGIN = "https://life.example";
const NOW = Date.parse("2030-01-01T00:00:00.000Z");

function fixture(overrides = {}) {
  const row = {
    uid: UID,
    telegram_chat_id: null,
    calendar_provider: "composio_gcal",
    calendar_connected_account_id: "ca-selected-123",
    calendar_enable_pending: false,
    web_initial_scan_completed_at: "2030-01-01T00:00:00.000Z",
    web_first_travel_at: "2030-01-01T00:00:00.000Z",
    stripe_customer_id: null,
    stripe_subscription_id: null,
    trial_expires_at: null,
    plan_status: null,
    paid: false,
    ...overrides,
  };
  const calls = { prices: [], checkouts: [], portals: [], fetches: [], controlActions: [] };
  const stripeClient = {
    prices: {
      async retrieve(id) {
        calls.prices.push(id);
        return { id, active: true, currency: "usd", unit_amount: 2900,
          recurring: { interval: "month" }, livemode: false };
      },
    },
    checkout: { sessions: {
      async create(params, requestOptions) {
        calls.checkouts.push({ params, requestOptions });
        return { id: "cs_test_once", url: "https://checkout.stripe.com/c/pay/cs_test_once" };
      },
    } },
    billingPortal: { sessions: {
      async create(params) {
        calls.portals.push(params);
        return { url: "https://billing.stripe.com/p/session/test" };
      },
    } },
  };
  const fetchImpl = async (url, init = {}) => {
    calls.fetches.push({ url: String(url), init });
    if (String(url).includes("/rpc/control_lm_web_travel")) {
      calls.controlActions.push(JSON.parse(init.body));
      return { ok: true, json: async () => true };
    }
    if (!init.method) return { ok: true, status: 200, json: async () => [row] };
    if (init.method === "PATCH") return { ok: true, status: 204, json: async () => [] };
    return { ok: false, status: 404, json: async () => [] };
  };
  return {
    row, calls, stripeClient,
    opts: {
      env: { NODE_ENV: "test", STRIPE_SECRET_KEY: "sk_test_fixture", LM_STRIPE_PRICE_ID: "price_29existing" },
      supaUrl: "https://supabase.example",
      supaKey: "service-role-fixture",
      publicOrigin: ORIGIN,
      nowMs: NOW,
      stripeClient,
      fetchImpl,
      calendarAccountStatusImpl: async () => "ACTIVE",
      ...overrides.opts,
    },
  };
}

function createCheckout(...args) {
  return webBilling.createWebCheckoutSession(...args);
}

test("Web Checkout uses the existing $29 monthly price and never resumes automation before Stripe confirmation", async () => {
  assert.ok(webBilling, "web-billing behavior must be implemented");
  const funnelEvents = [];
  const f = fixture({ opts: { recordWebFunnelEventImpl: async (event) => { funnelEvents.push(event); return true; } } });
  const user = { uid: UID, subject: UID.slice(3), csrf: "server-verified" };
  const result = await createCheckout(UID, user, f.opts);
  const request = f.calls.checkouts[0];

  assert.equal(result.url, "https://checkout.stripe.com/c/pay/cs_test_once");
  assert.equal(result.trialEnd, Math.floor(NOW / 1000) + 7 * 86400);
  assert.equal(result.trialEligible, true);
  assert.deepEqual(f.calls.prices, ["price_29existing"]);
  assert.equal(request.params.mode, "subscription");
  assert.deepEqual(request.params.line_items, [{ price: "price_29existing", quantity: 1 }]);
  assert.equal(request.params.payment_method_collection, "always");
  assert.equal(request.params.subscription_data.trial_period_days, 7);
  assert.equal(request.params.client_reference_id, UID);
  assert.equal(request.params.metadata.lm_uid, UID);
  assert.equal(request.params.subscription_data.metadata.lm_uid, UID);
  assert.match(request.params.success_url, /^https:\/\/life\.example\/lm\?checkout=success/);
  assert.equal(request.params.cancel_url, "https://life.example/lm?checkout=cancelled");
  assert.match(request.requestOptions.idempotencyKey, /^lm-web-trial-/);
  assert.deepEqual(f.calls.controlActions, []);
  assert.deepEqual(funnelEvents, [{
    eventName: "checkout_created", uid: UID, sourceObjectId: "cs_test_once", attribution: {},
  }]);
});

test("Web Checkout pre-fills the authenticated Google email for a new Stripe customer", async () => {
  assert.ok(webBilling, "web-billing behavior must be implemented");
  const f = fixture();
  const email = "web-trial@example.test";
  await createCheckout(UID, { uid: UID, email }, f.opts);
  const params = f.calls.checkouts[0].params;

  assert.equal(params.customer_email, email);
  assert.equal(Object.hasOwn(params, "customer"), false);
});

test("Web Checkout lets Stripe collect email when the authenticated Google email is missing or invalid", async () => {
  assert.ok(webBilling, "web-billing behavior must be implemented");
  for (const email of [undefined, "  ", "not-an-email", "user@a..b", "user@-host.example", "user@host-.example"]) {
    const f = fixture();
    await createCheckout(UID, { uid: UID, email }, f.opts);
    const params = f.calls.checkouts[0].params;

    assert.equal(Object.hasOwn(params, "customer_email"), false);
    assert.equal(Object.hasOwn(params, "customer"), false);
  }
});

test("Web Checkout offers the seven-day card trial before the first scan or Travel block", async () => {
  assert.ok(webBilling, "web-billing behavior must be implemented");
  const f = fixture({ web_initial_scan_completed_at: null, web_first_travel_at: null });
  const result = await createCheckout(UID, { uid: UID }, f.opts);
  assert.equal(result.trialEligible, true);
  assert.equal(f.calls.checkouts.length, 1);
  assert.equal(f.calls.checkouts[0].params.subscription_data.trial_period_days, 7);
  assert.equal(f.calls.checkouts[0].params.payment_method_collection, "always");
});

test("Web Checkout rejects active and past-due users before Stripe", async () => {
  assert.ok(webBilling, "web-billing behavior must be implemented");
  for (const overrides of [
    { stripe_subscription_id: "sub_active", plan_status: "active", paid: true },
    { stripe_subscription_id: "sub_trial", plan_status: "trialing", paid: false,
      web_trial_payment_method_present: true, trial_expires_at: "2030-01-08T00:00:00.000Z" },
    { stripe_subscription_id: "sub_past_due", plan_status: "past_due", paid: false },
  ]) {
    const f = fixture(overrides);
    await assert.rejects(createCheckout(UID, { uid: UID }, f.opts), { status: 409 });
    assert.equal(f.calls.checkouts.length, 0);
  }
});

test("previous legacy trial starts a paid Checkout without granting a second trial", async () => {
  assert.ok(webBilling, "web-billing behavior must be implemented");
  const f = fixture({ trial_expires_at: "2029-12-31T00:00:00.000Z" });
  const result = await createCheckout(UID, { uid: UID }, f.opts);
  const request = f.calls.checkouts[0];
  assert.equal(result.trialEligible, false);
  assert.equal(result.trialEnd, null);
  assert.equal(request.params.line_items[0].price, "price_29existing");
  assert.equal(request.params.payment_method_collection, "always");
  assert.equal(Object.hasOwn(request.params.subscription_data, "trial_period_days"), false);
});

test("canceled Stripe customer can restart at $29 without another free trial", async () => {
  assert.ok(webBilling, "web-billing behavior must be implemented");
  const f = fixture({ stripe_customer_id: "cus_old", stripe_subscription_id: "sub_cancelled", plan_status: "canceled" });
  const result = await createCheckout(UID, { uid: UID, email: "web-trial@example.test" }, f.opts);
  const request = f.calls.checkouts[0];
  assert.equal(result.trialEligible, false);
  assert.equal(request.params.customer, "cus_old");
  assert.equal(Object.hasOwn(request.params, "customer_email"), false);
  assert.equal(Object.hasOwn(request.params.subscription_data, "trial_period_days"), false);
});

test("repeated Web trial requests reuse the same Stripe idempotency key", async () => {
  assert.ok(webBilling, "web-billing behavior must be implemented");
  const f = fixture();
  await createCheckout(UID, { uid: UID }, f.opts);
  f.opts.nowMs += 30 * 60 * 1000;
  await createCheckout(UID, { uid: UID }, f.opts);
  assert.equal(f.calls.checkouts.length, 2);
  assert.equal(f.calls.checkouts[0].requestOptions.idempotencyKey, f.calls.checkouts[1].requestOptions.idempotencyKey);
});

test("Customer Portal is scoped to the verified Web customer's Stripe id", async () => {
  assert.ok(webBilling, "web-billing behavior must be implemented");
  const f = fixture({ stripe_customer_id: "cus_web_123", stripe_subscription_id: "sub_web_123" });
  const result = await webBilling.createCustomerPortalSession(UID, { uid: UID }, f.opts);
  assert.equal(result.url, "https://billing.stripe.com/p/session/test");
  assert.deepEqual(f.calls.portals, [{ customer: "cus_web_123", return_url: "https://life.example/lm" }]);
});

test("billing handler derives uid from verified session and checks CSRF and same origin", async () => {
  assert.ok(webBilling, "web-billing behavior must be implemented");
  const f = fixture();
  const response = { status: 0, headers: {}, body: "",
    writeHead(status, headers) { this.status = status; this.headers = headers; },
    end(body) { this.body = String(body); } };
  const user = { uid: UID, csrf: "verified-csrf" };
  const req = { method: "POST", url: "/api/lm-web/checkout", testBody: {}, headers: {
    origin: ORIGIN, "content-type": "application/json", "x-lm-web-csrf": user.csrf,
  } };
  const status = await webBilling.handleWebBillingRequest(req, response, {
    ...f.opts,
    resolveWebUserImpl: async () => user,
    readJsonImpl: async (request) => request.testBody,
  });
  assert.equal(status, undefined);
  assert.equal(response.status, 200);
  assert.equal(JSON.parse(response.body).url, "https://checkout.stripe.com/c/pay/cs_test_once");
  assert.equal(f.calls.checkouts[0].params.client_reference_id, UID);

  const denied = { status: 0, body: "", writeHead(status) { this.status = status; }, end(body) { this.body = String(body); } };
  await webBilling.handleWebBillingRequest({ ...req, headers: { ...req.headers, origin: "https://attacker.example" } }, denied, {
    ...f.opts,
    resolveWebUserImpl: async () => user,
    readJsonImpl: async (request) => request.testBody,
  });
  assert.equal(denied.status, 403);
  assert.equal(f.calls.checkouts.length, 1);

  const deniedCsrf = { status: 0, body: "", writeHead(status) { this.status = status; }, end(body) { this.body = String(body); } };
  await webBilling.handleWebBillingRequest({ ...req, headers: { ...req.headers, "x-lm-web-csrf": "attacker-token" } }, deniedCsrf, {
    ...f.opts,
    resolveWebUserImpl: async () => user,
    readJsonImpl: async (request) => request.testBody,
  });
  assert.equal(deniedCsrf.status, 403);
  assert.equal(f.calls.checkouts.length, 1);

  const deniedUid = { status: 0, body: "", writeHead(status) { this.status = status; }, end(body) { this.body = String(body); } };
  await webBilling.handleWebBillingRequest({ ...req, testBody: { uid: "lm_22222222-2222-4222-8222-222222222222" } }, deniedUid, {
    ...f.opts,
    resolveWebUserImpl: async () => user,
    readJsonImpl: async (request) => request.testBody,
  });
  assert.equal(deniedUid.status, 400);
  assert.equal(f.calls.checkouts.length, 1);
});
