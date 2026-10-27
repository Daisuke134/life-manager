"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { Readable } = require("node:stream");
const { handleMaritimeCloudBillingRequest } = require("./maritime-cloud-billing.js");

const UID_A = "lm_123e4567-e89b-12d3-a456-426614174000";
const UID_B = "lm_987e6543-e21b-12d3-a456-426614174000";
const EMAIL = ["alice", "example.test"].join("@");
const CLOUD_KEY = ["sk", "test", "checkoutfixture"].join("_");
const WEBHOOK_SECRET = ["whsec", "checkoutfixture"].join("_");
const cloudEnv = Object.freeze({
  NODE_ENV: "test",
  LM_CLOUD_STRIPE_MODE: "test",
  LM_CLOUD_STRIPE_SECRET_KEY: CLOUD_KEY,
  LM_CLOUD_STRIPE_WEBHOOK_SECRET: WEBHOOK_SECRET,
  LM_CLOUD_STRIPE_PRODUCT_ID: "prod_cloudfixture",
  LM_CLOUD_STRIPE_PRICE_ID: "price_cloudfixture",
  LM_STRIPE_PRODUCT_ID: "prod_calendarfixture",
  LM_STRIPE_PRICE_ID: "price_calendarfixture",
});

function response() {
  return { headers: {}, statusCode: null, body: "", writeHead(status, headers = {}) {
    this.statusCode = status; Object.assign(this.headers, headers);
  }, end(body = "") { this.body = String(body); } };
}

function request(path, { uid = UID_A, idempotencyKey = "123e4567-e89b-12d3-a456-426614174001", body = {}, headers = {} } = {}) {
  const req = Readable.from([JSON.stringify(body)]);
  req.url = path;
  req.method = "POST";
  req.headers = { origin: "https://cloud.example.test", "content-type": "application/json",
    "x-lm-web-csrf": "csrf-fixture", "idempotency-key": idempotencyKey, ...headers };
  req.fixtureUid = uid;
  return req;
}

function fakeStripe() {
  const calls = { checkout: [], portal: [] };
  return { calls, checkout: { sessions: { async create(params, options) {
    calls.checkout.push({ params, options });
    return { id: "cs_test_fixture", url: "https://checkout.stripe.com/c/pay/cs_test_fixture" };
  } } }, billingPortal: { sessions: { async create(params, options) {
    calls.portal.push({ params, options });
    return { url: "https://billing.stripe.com/p/session/test_fixture" };
  } } } };
}

async function send(req, { env = cloudEnv, stripe = fakeStripe(), rows = new Map(), logger = { warn() {}, error() {} } } = {}) {
  const res = response();
  const result = await handleMaritimeCloudBillingRequest(req, res, {
    env,
    publicOrigin: "https://cloud.example.test",
    stripeClient: stripe,
    resolveUserImpl: async request => ({ uid: request.fixtureUid, email: EMAIL, csrf: "csrf-fixture" }),
    billingStore: { async readTenant(uid) { return rows.get(uid) || null; } },
    logger,
  });
  return { result, res, stripe };
}

test("Cloud checkout is tenant-bound, uses only Cloud price/config, and retries idempotently", async () => {
  const stripe = fakeStripe();
  const first = await send(request("/api/stripe/cloud/checkout"), { stripe });
  const replay = await send(request("/api/stripe/cloud/checkout"), { stripe });
  const otherTenant = await send(request("/api/stripe/cloud/checkout", { uid: UID_B }), { stripe });

  assert.equal(first.res.statusCode, 200);
  assert.deepEqual(JSON.parse(first.res.body), { url: "https://checkout.stripe.com/c/pay/cs_test_fixture" });
  const { params, options } = stripe.calls.checkout[0];
  assert.equal(params.mode, "subscription");
  assert.deepEqual(params.line_items, [{ price: "price_cloudfixture", quantity: 1 }]);
  assert.equal(params.client_reference_id, UID_A);
  assert.equal(params.subscription_data.metadata.lm_tenant_uid, UID_A);
  assert.equal(params.customer_email, EMAIL);
  assert.equal(Object.hasOwn(params.subscription_data, "trial_period_days"), false);
  assert.equal(JSON.stringify(params).includes("calendar"), false);
  assert.equal(options.idempotencyKey, stripe.calls.checkout[1].options.idempotencyKey);
  assert.notEqual(options.idempotencyKey, stripe.calls.checkout[2].options.idempotencyKey);
  assert.equal(replay.res.statusCode, 200);
  assert.equal(otherTenant.res.statusCode, 200);
});

test("checkout refuses live Cloud config, Calendar reuse, missing idempotency, bad origin, and CSRF", async () => {
  const stripe = fakeStripe();
  const refusedEnvs = [
    { ...cloudEnv, LM_CLOUD_STRIPE_SECRET_KEY: ["sk", "live", "fixture"].join("_") },
    { ...cloudEnv, LM_CLOUD_STRIPE_MODE: "live" },
    { ...cloudEnv, LM_CLOUD_STRIPE_PRICE_ID: cloudEnv.LM_STRIPE_PRICE_ID },
    { ...cloudEnv, LM_CLOUD_STRIPE_PRODUCT_ID: cloudEnv.LM_STRIPE_PRODUCT_ID },
  ];
  for (const env of refusedEnvs) {
    const result = await send(request("/api/stripe/cloud/checkout"), { env, stripe });
    assert.equal(result.res.statusCode, 503);
  }
  for (const [req, status] of [
    [request("/api/stripe/cloud/checkout", { idempotencyKey: "" }), 400],
    [request("/api/stripe/cloud/checkout", { headers: { origin: "https://attacker.example.test" } }), 403],
    [request("/api/stripe/cloud/checkout", { headers: { "x-lm-web-csrf": "wrong" } }), 403],
    [request("/api/stripe/cloud/checkout", { body: { uid: UID_B, priceId: "price_calendarfixture" } }), 400],
  ]) assert.equal((await send(req, { stripe })).res.statusCode, status);
  assert.equal(stripe.calls.checkout.length, 0);
});

test("portal uses the authenticated tenant's Cloud customer and never request-supplied Calendar IDs", async () => {
  const stripe = fakeStripe();
  const rows = new Map([[UID_A, { uid: UID_A, stripe_customer_id: "cus_clouda" }]]);
  const { res } = await send(request("/api/stripe/cloud/portal", { body: { customer: "cus_calendar" } }), { stripe, rows });
  assert.equal(res.statusCode, 400);
  assert.equal(stripe.calls.portal.length, 0);

  const successful = await send(request("/api/stripe/cloud/portal"), { stripe, rows });
  assert.equal(successful.res.statusCode, 200);
  assert.deepEqual(stripe.calls.portal[0].params, {
    customer: "cus_clouda", return_url: "https://cloud.example.test/maritime",
  });
  assert.match(stripe.calls.portal[0].options.idempotencyKey, /^lm-cloud-portal-/);
  assert.equal(JSON.stringify(stripe.calls.portal[0].params).includes("calendar"), false);
});

test("billing API failures return and log no Stripe secrets or customer email", async () => {
  const secretError = new Error(`${CLOUD_KEY} ${WEBHOOK_SECRET} ${EMAIL}`);
  const logs = [];
  const logger = { warn: value => logs.push(String(value)), error: value => logs.push(String(value)) };
  const stripe = fakeStripe();
  stripe.checkout.sessions.create = async () => { throw secretError; };
  const { res } = await send(request("/api/stripe/cloud/checkout"), { stripe, logger });
  assert.equal(res.statusCode, 502);
  assert.deepEqual(JSON.parse(res.body), { error: "checkout_unavailable" });
  for (const secret of [CLOUD_KEY, WEBHOOK_SECRET, EMAIL, secretError.message]) {
    assert.equal(logs.join("\n").includes(secret), false);
    assert.equal(res.body.includes(secret), false);
  }
});
