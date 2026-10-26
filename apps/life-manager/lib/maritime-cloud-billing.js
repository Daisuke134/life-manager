"use strict";

const CLOUD_MODE_ENV = "LM_CLOUD_STRIPE_MODE";
const CLOUD_KEY_ENV = "LM_CLOUD_STRIPE_SECRET_KEY";
const CLOUD_WEBHOOK_SECRET_ENV = "LM_CLOUD_STRIPE_WEBHOOK_SECRET";
const CLOUD_PRODUCT_ENV = "LM_CLOUD_STRIPE_PRODUCT_ID";
const CLOUD_PRICE_ENV = "LM_CLOUD_STRIPE_PRICE_ID";
const CALENDAR_PRODUCT_ENV = "LM_STRIPE_PRODUCT_ID";
const CALENDAR_PRICE_ENV = "LM_STRIPE_PRICE_ID";
const TABLE = "lm_maritime_cloud_subscriptions";
const FIELDS = [
  "uid", "stripe_subscription_id", "stripe_product_id", "stripe_price_id", "stripe_status",
  "entitled", "stripe_subscription_created", "last_event_created", "last_event_id", "updated_at",
].join(",");
const CLOUD_STATUSES = new Set([
  "active", "trialing", "past_due", "unpaid", "canceled", "incomplete", "incomplete_expired", "paused",
]);
const STORED_STATUSES = new Set([...CLOUD_STATUSES, "ambiguous"]);
const APPLY_ACTIONS = new Set(["applied", "duplicate", "unchanged", "stale", "ambiguous"]);

function cloudError(code) {
  const error = new Error(code);
  error.code = code;
  error.status = code === "billing_cloud_config_unavailable" ? 503 : 500;
  return error;
}

function resolveMaritimeCloudConfig(env = process.env) {
  const mode = String(env[CLOUD_MODE_ENV] || "").trim();
  const secretKey = String(env[CLOUD_KEY_ENV] || "").trim();
  const webhookSecret = String(env[CLOUD_WEBHOOK_SECRET_ENV] || "").trim();
  const productId = String(env[CLOUD_PRODUCT_ENV] || "").trim();
  const priceId = String(env[CLOUD_PRICE_ENV] || "").trim();
  const calendarProductId = String(env[CALENDAR_PRODUCT_ENV] || "").trim();
  const calendarPriceId = String(env[CALENDAR_PRICE_ENV] || "").trim();
  if (mode !== "test"
    || !/^(?:sk|rk)_test_[A-Za-z0-9]+$/.test(secretKey)
    || !/^whsec_[A-Za-z0-9]+$/.test(webhookSecret)
    || !/^prod_[A-Za-z0-9]+$/.test(productId)
    || !/^price_[A-Za-z0-9]+$/.test(priceId)
    || !/^prod_[A-Za-z0-9]+$/.test(calendarProductId)
    || !/^price_[A-Za-z0-9]+$/.test(calendarPriceId)
    || productId === calendarProductId
    || priceId === calendarPriceId) {
    throw cloudError("billing_cloud_config_unavailable");
  }
  return { mode, secretKey, webhookSecret, productId, priceId };
}

function validEventId(value) { return typeof value === "string" && /^evt_[A-Za-z0-9]+$/.test(value); }
function validSubscriptionId(value) { return typeof value === "string" && /^sub_[A-Za-z0-9]+$/.test(value); }
function validTenantUid(value) {
  return typeof value === "string"
    && /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
}
function positiveEpoch(value) { return Number.isSafeInteger(value) && value > 0; }
function stripeObjectId(value, prefix) {
  const id = typeof value === "string" ? value : value && typeof value === "object" ? value.id : "";
  return typeof id === "string" && id.startsWith(`${prefix}_`) ? id : "";
}

function parseCloudSubscriptionEvent(event, config) {
  if (!event || !["customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"].includes(event.type)) {
    return null;
  }
  const subscription = event.data && event.data.object;
  if (!subscription || subscription.object !== "subscription") throw cloudError("billing_cloud_event_invalid");
  const items = subscription.items && subscription.items.data;
  if (!Array.isArray(items) || items.length !== 1) return null;
  const price = items[0] && items[0].price;
  const priceId = price && typeof price.id === "string" ? price.id : "";
  const productId = stripeObjectId(price && price.product, "prod");
  if (priceId !== config.priceId || productId !== config.productId) return null;

  const tenantUid = subscription.metadata && subscription.metadata.lm_tenant_uid;
  const status = event.type === "customer.subscription.deleted" ? "canceled" : subscription.status;
  const eventCreated = event.created;
  const subscriptionCreated = subscription.created;
  if (!validEventId(event.id) || !positiveEpoch(eventCreated)
    || !validSubscriptionId(subscription.id) || !positiveEpoch(subscriptionCreated)
    || !validTenantUid(tenantUid) || !CLOUD_STATUSES.has(status)) {
    throw cloudError("billing_cloud_event_invalid");
  }
  return {
    event_id: event.id,
    event_created: eventCreated,
    tenant_uid: tenantUid,
    stripe_subscription_id: subscription.id,
    stripe_subscription_created: subscriptionCreated,
    stripe_product_id: productId,
    stripe_price_id: priceId,
    stripe_status: status,
  };
}

function rowForEvent(event, now, status = event.stripe_status, subscriptionId = event.stripe_subscription_id, lastEventId = event.event_id, lastEventCreated = event.event_created) {
  return {
    uid: event.tenant_uid,
    stripe_subscription_id: subscriptionId,
    stripe_product_id: event.stripe_product_id,
    stripe_price_id: event.stripe_price_id,
    stripe_status: status,
    entitled: status === "active",
    stripe_subscription_created: event.stripe_subscription_created,
    last_event_created: lastEventCreated,
    last_event_id: lastEventId,
    updated_at: now(),
  };
}

function nextCloudState(current, event, now) {
  if (!current) return { action: "applied", row: rowForEvent(event, now) };
  if (!STORED_STATUSES.has(current.stripe_status) || current.entitled !== (current.stripe_status === "active")) {
    throw cloudError("billing_cloud_store_state_invalid");
  }

  const currentSubscriptionCreated = Number(current.stripe_subscription_created);
  if (!positiveEpoch(currentSubscriptionCreated)) throw cloudError("billing_cloud_store_state_invalid");
  if (event.stripe_subscription_created < currentSubscriptionCreated) return { action: "stale" };
  if (event.stripe_subscription_created > currentSubscriptionCreated) return { action: "applied", row: rowForEvent(event, now) };

  if (current.stripe_status === "ambiguous") return { action: "ambiguous" };
  if (event.stripe_subscription_id !== current.stripe_subscription_id) {
    const row = rowForEvent(
      event,
      now,
      "ambiguous",
      [event.stripe_subscription_id, current.stripe_subscription_id].sort()[0],
      [event.event_id, current.last_event_id].sort()[0],
      Math.max(event.event_created, Number(current.last_event_created)),
    );
    return { action: "ambiguous", row };
  }

  const currentEventCreated = Number(current.last_event_created);
  if (!positiveEpoch(currentEventCreated)) throw cloudError("billing_cloud_store_state_invalid");
  if (event.event_created < currentEventCreated) return { action: "stale" };
  if (event.event_created === currentEventCreated) {
    if (event.event_id === current.last_event_id) return { action: "duplicate" };
    if (event.stripe_status !== current.stripe_status) {
      const row = rowForEvent(
        event,
        now,
        "ambiguous",
        current.stripe_subscription_id,
        [event.event_id, current.last_event_id].sort()[0],
        currentEventCreated,
      );
      return { action: "ambiguous", row };
    }
    return { action: "unchanged" };
  }

  return { action: "applied", row: rowForEvent(event, now) };
}

function createMaritimeCloudBillingStore(options = {}) {
  const root = String(options.supaUrl || options.env && options.env.SUPABASE_URL || "").replace(/\/$/, "");
  const key = options.supaKey || options.env && options.env.SUPABASE_SERVICE_ROLE_KEY;
  const fetchImpl = options.fetchImpl || globalThis.fetch;
  const now = options.now || (() => new Date().toISOString());
  const maxCasAttempts = 6;

  async function request(url, method, body) {
    if (!root || !key || typeof fetchImpl !== "function") throw cloudError("billing_cloud_store_unconfigured");
    let response;
    try {
      response = await fetchImpl(url, {
        method,
        headers: {
          apikey: key,
          Authorization: `Bearer ${key}`,
          "Content-Type": "application/json",
          Prefer: "return=representation",
        },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
    } catch {
      throw cloudError("billing_cloud_store_unavailable");
    }
    if (!response.ok && response.status !== 409) throw cloudError("billing_cloud_store_unavailable");
    if (response.status === 409) return { conflict: true, body: null };
    let parsed;
    try { parsed = await response.json(); }
    catch { throw cloudError("billing_cloud_store_unavailable"); }
    return { conflict: false, body: parsed };
  }

  async function read(uid) {
    const url = new URL(`${root}/rest/v1/${TABLE}`);
    url.searchParams.set("select", FIELDS);
    url.searchParams.set("uid", `eq.${uid}`);
    const result = await request(url, "GET");
    if (!Array.isArray(result.body) || result.body.length > 1) throw cloudError("billing_cloud_store_unavailable");
    return result.body[0] || null;
  }

  async function apply(event) {
    for (let attempt = 0; attempt < maxCasAttempts; attempt += 1) {
      const current = await read(event.tenant_uid);
      const transition = nextCloudState(current, event, now);
      if (!transition.row) return transition.action;

      if (!current) {
        const url = `${root}/rest/v1/${TABLE}`;
        const result = await request(url, "POST", transition.row);
        if (result.conflict) continue;
        if (!Array.isArray(result.body) || result.body.length !== 1) throw cloudError("billing_cloud_store_unavailable");
        return transition.action;
      }

      const url = new URL(`${root}/rest/v1/${TABLE}`);
      for (const [field, value] of Object.entries({
        uid: current.uid,
        stripe_subscription_id: current.stripe_subscription_id,
        stripe_subscription_created: current.stripe_subscription_created,
        stripe_status: current.stripe_status,
        entitled: current.entitled,
        last_event_created: current.last_event_created,
        last_event_id: current.last_event_id,
      })) {
        url.searchParams.set(field, `eq.${value}`);
      }
      const result = await request(url, "PATCH", transition.row);
      if (!result.conflict && Array.isArray(result.body) && result.body.length === 1) return transition.action;
    }
    throw cloudError("billing_cloud_store_conflict");
  }

  return { apply };
}

function safeLog(logger, method, message) {
  try { if (logger && typeof logger[method] === "function") logger[method](message); }
  catch { /* logging must not affect the webhook result */ }
}

async function handleMaritimeCloudStripeWebhook({ rawBody, signature, env = process.env, stripe, store, logger = console } = {}) {
  let config;
  try { config = resolveMaritimeCloudConfig(env); }
  catch { return { statusCode: 503, body: { error: "billing_not_configured" } }; }
  if (!Buffer.isBuffer(rawBody) || !stripe || !stripe.webhooks || typeof stripe.webhooks.constructEvent !== "function") {
    return { statusCode: 503, body: { error: "billing_not_configured" } };
  }

  let event;
  try { event = stripe.webhooks.constructEvent(rawBody, signature, config.webhookSecret); }
  catch {
    safeLog(logger, "warn", "[cloud-stripe] signature rejected");
    return { statusCode: 400, body: { error: "invalid_signature" } };
  }
  if (!event || event.livemode !== false) {
    safeLog(logger, "warn", "[cloud-stripe] test-mode event required");
    return { statusCode: 400, body: { error: "test_mode_event_required" } };
  }

  let normalized;
  try { normalized = parseCloudSubscriptionEvent(event, config); }
  catch { return { statusCode: 400, body: { error: "invalid_event" } }; }
  if (!normalized) return { statusCode: 200, body: { status: "ignored" } };
  if (!store || typeof store.apply !== "function") return { statusCode: 503, body: { error: "billing_not_configured" } };

  try {
    const status = await store.apply(normalized);
    if (!APPLY_ACTIONS.has(status)) throw cloudError("billing_cloud_store_unavailable");
    return { statusCode: 200, body: { status } };
  } catch {
    safeLog(logger, "error", "[cloud-stripe] subscription update failed");
    return { statusCode: 500, body: { error: "billing_update_failed" } };
  }
}

module.exports = {
  resolveMaritimeCloudConfig,
  createMaritimeCloudBillingStore,
  handleMaritimeCloudStripeWebhook,
};
