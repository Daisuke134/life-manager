"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const {
  resolveMaritimeCloudConfig,
  createMaritimeCloudBillingStore,
  handleMaritimeCloudStripeWebhook,
} = require("./maritime-cloud-billing.js");

const TENANT_UID = "lm_123e4567-e89b-12d3-a456-426614174000";
const stripeKeyFixture = (mode, suffix, prefix = "sk") => `${prefix}_${mode}_${suffix}`;
const TEST_CLOUD_STRIPE_KEY = stripeKeyFixture("test", "cloudfixture");
const TEST_WEBHOOK_SECRET = ["whsec", "cloudfixture"].join("_");
const TEST_CONTACT_EMAIL = ["alice", "example.test"].join("@");
const TEST_STORE_KEY = ["service-role", "test", "fixture"].join("-");
const cloudEnv = Object.freeze({
  LM_CLOUD_STRIPE_MODE: "test",
  LM_CLOUD_STRIPE_SECRET_KEY: TEST_CLOUD_STRIPE_KEY,
  LM_CLOUD_STRIPE_WEBHOOK_SECRET: TEST_WEBHOOK_SECRET,
  LM_CLOUD_STRIPE_PRODUCT_ID: "prod_cloudfixture",
  LM_CLOUD_STRIPE_PRICE_ID: "price_cloudfixture",
  LM_STRIPE_PRODUCT_ID: "prod_calendarfixture",
  LM_STRIPE_PRICE_ID: "price_calendarfixture",
});

function stripeFor(event) {
  return {
    webhooks: {
      constructEvent(raw, signature, secret) {
        assert.equal(secret, TEST_WEBHOOK_SECRET);
        if (signature !== "signed-test-fixture") {
          throw new Error(`bad signature for ${TEST_CONTACT_EMAIL} with ${TEST_WEBHOOK_SECRET}`);
        }
        if (event === undefined) return JSON.parse(raw.toString("utf8"));
        return event;
      },
    },
  };
}

function subscriptionEvent({ id, created, status, subscriptionCreated = 90, subscriptionId = "sub_cloud1", tenantUid = TENANT_UID }) {
  const deleted = status === "canceled";
  return {
    id,
    type: deleted ? "customer.subscription.deleted" : "customer.subscription.updated",
    created,
    livemode: false,
    data: { object: {
      id: subscriptionId,
      object: "subscription",
      created: subscriptionCreated,
      status,
      metadata: { lm_tenant_uid: tenantUid, contact_email: TEST_CONTACT_EMAIL },
      items: { data: [{ price: { id: "price_cloudfixture", product: "prod_cloudfixture" }, quantity: 1 }] },
    } },
  };
}

function fakePostgrest() {
  const rows = new Map();
  const writes = [];
  const fetchImpl = async (requestUrl, options) => {
    const url = new URL(requestUrl);
    assert.equal(url.origin, "https://supabase.test");
    assert.equal(url.pathname, "/rest/v1/lm_maritime_cloud_subscriptions");
    assert.equal(options.headers.apikey, TEST_STORE_KEY);
    const method = options.method;
    if (method === "GET") {
      const uid = url.searchParams.get("uid").slice(3);
      const row = rows.get(uid);
      return fakeResponse(200, row ? [structuredClone(row)] : []);
    }
    if (method === "POST") {
      const row = JSON.parse(options.body);
      if (rows.has(row.uid)) return fakeResponse(409, { code: "23505" });
      rows.set(row.uid, row);
      writes.push({ method, row: structuredClone(row) });
      return fakeResponse(201, [structuredClone(row)]);
    }
    if (method === "PATCH") {
      const filters = Object.fromEntries([...url.searchParams].map(([key, value]) => [key, value.slice(3)]));
      const uid = filters.uid;
      const current = rows.get(uid);
      if (!current || Object.entries(filters).some(([key, value]) => String(current[key]) !== value)) {
        return fakeResponse(200, []);
      }
      const update = JSON.parse(options.body);
      Object.assign(current, update);
      rows.set(uid, current);
      writes.push({ method, row: structuredClone(current) });
      return fakeResponse(200, [structuredClone(current)]);
    }
    throw new Error(`unexpected fake method ${method}`);
  };
  return { rows, writes, fetchImpl };
}

function fakeResponse(status, body) {
  return { status, ok: status >= 200 && status < 300, json: async () => body };
}

function fakeStore(db) {
  return createMaritimeCloudBillingStore({
    supaUrl: "https://supabase.test",
    supaKey: TEST_STORE_KEY,
    fetchImpl: db.fetchImpl,
    now: () => "2026-10-27T00:00:00.000Z",
  });
}

test("Cloud billing accepts only a dedicated TEST-mode product and price configuration", () => {
  const config = resolveMaritimeCloudConfig({
    ...cloudEnv,
    STRIPE_SECRET_KEY: stripeKeyFixture("live", "calendarfixture"),
    LM_STRIPE_PRICE_ID: "price_calendarfixture",
  });
  assert.equal(config.mode, "test");
  assert.equal(config.productId, "prod_cloudfixture");
  assert.equal(config.priceId, "price_cloudfixture");
  assert.equal(config.secretKey, TEST_CLOUD_STRIPE_KEY);

  const refused = [
    { ...cloudEnv, LM_CLOUD_STRIPE_MODE: "live" },
    { ...cloudEnv, LM_CLOUD_STRIPE_SECRET_KEY: stripeKeyFixture("live", "cloudfixture") },
    { ...cloudEnv, LM_CLOUD_STRIPE_SECRET_KEY: stripeKeyFixture("live", "cloudfixture", "rk") },
    { ...cloudEnv, LM_CLOUD_STRIPE_SECRET_KEY: "" },
    { ...cloudEnv, LM_CLOUD_STRIPE_WEBHOOK_SECRET: "" },
    { ...cloudEnv, LM_CLOUD_STRIPE_PRODUCT_ID: "bad-product" },
    { ...cloudEnv, LM_CLOUD_STRIPE_PRICE_ID: "bad-price" },
    { ...cloudEnv, LM_CLOUD_STRIPE_PRODUCT_ID: cloudEnv.LM_STRIPE_PRODUCT_ID },
    { ...cloudEnv, LM_CLOUD_STRIPE_PRICE_ID: cloudEnv.LM_STRIPE_PRICE_ID },
    { ...cloudEnv, LM_STRIPE_PRODUCT_ID: "" },
    { ...cloudEnv, LM_STRIPE_PRICE_ID: "" },
    { ...cloudEnv, LM_CLOUD_STRIPE_SECRET_KEY: "", STRIPE_SECRET_KEY: stripeKeyFixture("test", "fallbackfixture") },
    { STRIPE_SECRET_KEY: stripeKeyFixture("test", "calendarfixture"), LM_STRIPE_PRICE_ID: cloudEnv.LM_STRIPE_PRICE_ID },
  ];
  for (const env of refused) {
    assert.throws(() => resolveMaritimeCloudConfig(env), {
      code: "billing_cloud_config_unavailable",
      status: 503,
    });
  }
});

test("unverified and live-mode webhook events cannot change tenant entitlement or leak logs", async () => {
  const db = fakePostgrest();
  const store = fakeStore(db);
  const logs = [];
  const logger = { warn: (...args) => logs.push(args.join(" ")), error: (...args) => logs.push(args.join(" ")) };
  const rejected = await handleMaritimeCloudStripeWebhook({
    rawBody: Buffer.from("not-json alice@example.test"),
    signature: "attacker-signature",
    env: cloudEnv,
    stripe: stripeFor(undefined),
    store,
    logger,
  });
  assert.deepEqual(rejected, { statusCode: 400, body: { error: "invalid_signature" } });
  assert.equal(db.writes.length, 0);

  const liveEvent = { ...subscriptionEvent({ id: "evt_live", created: 100, status: "active" }), livemode: true };
  const live = await handleMaritimeCloudStripeWebhook({
    rawBody: Buffer.from(JSON.stringify(liveEvent)),
    signature: "signed-test-fixture",
    env: cloudEnv,
    stripe: stripeFor(liveEvent),
    store,
    logger,
  });
  assert.deepEqual(live, { statusCode: 400, body: { error: "test_mode_event_required" } });
  assert.equal(db.writes.length, 0);

  const persistenceFailure = await handleMaritimeCloudStripeWebhook({
    rawBody: Buffer.from("signed bytes"),
    signature: "signed-test-fixture",
    env: cloudEnv,
    stripe: stripeFor(subscriptionEvent({ id: "evt_storefail", created: 100, status: "active" })),
    store: { async apply() { throw new Error("service-role-test-fixture alice@example.test"); } },
    logger,
  });
  assert.deepEqual(persistenceFailure, { statusCode: 500, body: { error: "billing_update_failed" } });
  const logged = logs.join("\n");
  for (const sensitiveValue of ["attacker-signature", TEST_WEBHOOK_SECRET, TEST_CONTACT_EMAIL, TENANT_UID, TEST_STORE_KEY]) {
    assert.equal(logged.includes(sensitiveValue), false);
  }
});

test("verified subscription events are tenant-bound and do not report Cloud MRR as earned", async () => {
  const db = fakePostgrest();
  const result = await handleMaritimeCloudStripeWebhook({
    rawBody: Buffer.from("signed bytes"),
    signature: "signed-test-fixture",
    env: cloudEnv,
    stripe: stripeFor(subscriptionEvent({ id: "evt_active", created: 100, status: "active" })),
    store: fakeStore(db),
    logger: { warn() {}, error() {} },
  });
  assert.deepEqual(result, { statusCode: 200, body: { status: "applied" } });
  assert.equal(db.rows.get(TENANT_UID).entitled, true);
  assert.equal(db.rows.get(TENANT_UID).stripe_status, "active");
  assert.equal(db.writes.length, 1);
  assert.deepEqual(Object.keys(db.writes[0].row).sort(), [
    "entitled", "last_event_created", "last_event_id", "stripe_price_id",
    "stripe_product_id", "stripe_status", "stripe_subscription_created",
    "stripe_subscription_id", "uid", "updated_at",
  ].sort());
  assert.equal(Object.hasOwn(result.body, "earned"), false);
  assert.equal(Object.hasOwn(result.body, "mrr"), false);
});

test("Calendar events are ignored and verified Cloud events remain isolated per tenant", async () => {
  const db = fakePostgrest();
  const store = fakeStore(db);
  const send = (event) => handleMaritimeCloudStripeWebhook({
    rawBody: Buffer.from("signed bytes"), signature: "signed-test-fixture", env: cloudEnv,
    stripe: stripeFor(event), store, logger: { warn() {}, error() {} },
  });
  const calendar = subscriptionEvent({ id: "evt_calendar", created: 100, status: "active" });
  calendar.data.object.items.data[0].price = {
    id: "price_calendarfixture",
    product: "prod_calendarfixture",
  };
  assert.deepEqual(await send(calendar), { statusCode: 200, body: { status: "ignored" } });

  const tenantB = "lm_987e6543-e21b-12d3-a456-426614174000";
  await send(subscriptionEvent({ id: "evt_tenantA", created: 100, status: "active" }));
  await send(subscriptionEvent({
    id: "evt_tenantB", created: 100, status: "canceled", tenantUid: tenantB, subscriptionId: "sub_cloud2",
  }));
  assert.equal(db.rows.size, 2);
  assert.equal(db.rows.get(TENANT_UID).entitled, true);
  assert.equal(db.rows.get(tenantB).entitled, false);
  assert.equal(db.writes.length, 2);
});

test("replayed and out-of-order events preserve the newest tenant entitlement", async () => {
  const db = fakePostgrest();
  const store = fakeStore(db);
  const send = (event) => handleMaritimeCloudStripeWebhook({
    rawBody: Buffer.from("signed bytes"), signature: "signed-test-fixture", env: cloudEnv,
    stripe: stripeFor(event), store, logger: { warn() {}, error() {} },
  });

  const active = subscriptionEvent({ id: "evt_active100", created: 100, status: "active" });
  const canceled = subscriptionEvent({ id: "evt_canceled200", created: 200, status: "canceled" });
  assert.deepEqual((await send(active)).body, { status: "applied" });
  assert.deepEqual((await send(active)).body, { status: "duplicate" });
  assert.deepEqual((await send(canceled)).body, { status: "applied" });
  assert.deepEqual((await send({ ...active, id: "evt_oldactive150", created: 150 })).body, { status: "stale" });
  assert.deepEqual((await send(canceled)).body, { status: "duplicate" });
  assert.equal(db.rows.get(TENANT_UID).entitled, false);
  assert.equal(db.rows.get(TENANT_UID).stripe_status, "canceled");
  assert.equal(db.writes.length, 2);
});

test("conflicting same-second events fail closed regardless of delivery order", async () => {
  async function finalStatus(events) {
    const db = fakePostgrest();
    const store = fakeStore(db);
    for (const event of events) {
      await handleMaritimeCloudStripeWebhook({
        rawBody: Buffer.from("signed bytes"), signature: "signed-test-fixture", env: cloudEnv,
        stripe: stripeFor(event), store, logger: { warn() {}, error() {} },
      });
    }
    return db.rows.get(TENANT_UID);
  }
  const active = subscriptionEvent({ id: "evt_sameactive", created: 100, status: "active" });
  const canceled = subscriptionEvent({ id: "evt_samecanceled", created: 100, status: "canceled" });
  const firstOrder = await finalStatus([active, canceled]);
  const reverseOrder = await finalStatus([canceled, active]);
  assert.equal(firstOrder.stripe_status, "ambiguous");
  assert.equal(reverseOrder.stripe_status, "ambiguous");
  assert.equal(firstOrder.entitled, false);
  assert.equal(reverseOrder.entitled, false);
});
