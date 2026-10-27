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
  "uid", "stripe_customer_id", "stripe_subscription_id", "stripe_product_id", "stripe_price_id", "stripe_status",
  "cancel_at_period_end", "entitled", "stripe_subscription_created", "last_event_created", "last_event_id", "updated_at",
].join(",");
const CLOUD_STATUSES = new Set([
  "active", "trialing", "past_due", "unpaid", "canceled", "incomplete", "incomplete_expired", "paused",
]);
const STORED_STATUSES = new Set([...CLOUD_STATUSES, "ambiguous"]);
const APPLY_ACTIONS = new Set(["applied", "duplicate", "unchanged", "stale", "ambiguous", "unmatched"]);
const ENTITLED_STATUSES = new Set(["active", "trialing", "past_due"]);

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
  if (!event || !["customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"].includes(event.type)) return null;
  const subscription = event.data && event.data.object;
  if (!subscription || subscription.object !== "subscription") throw cloudError("billing_cloud_event_invalid");
  const items = subscription.items && subscription.items.data;
  if (!Array.isArray(items) || items.length !== 1) return null;
  const price = items[0] && items[0].price;
  const priceId = price && typeof price.id === "string" ? price.id : "";
  const productId = stripeObjectId(price && price.product, "prod");
  if (priceId !== config.priceId || productId !== config.productId) return null;

  const tenantUid = subscription.metadata && subscription.metadata.lm_tenant_uid;
  const customerId = stripeObjectId(subscription.customer, "cus");
  const status = event.type === "customer.subscription.deleted" ? "canceled" : subscription.status;
  const eventCreated = event.created;
  const subscriptionCreated = subscription.created;
  if (!validEventId(event.id) || !positiveEpoch(eventCreated)
    || !validSubscriptionId(subscription.id) || !positiveEpoch(subscriptionCreated)
    || !validTenantUid(tenantUid) || !customerId || !CLOUD_STATUSES.has(status)
    || typeof subscription.cancel_at_period_end !== "boolean") {
    throw cloudError("billing_cloud_event_invalid");
  }
  return {
    event_id: event.id,
    event_created: eventCreated,
    tenant_uid: tenantUid,
    stripe_customer_id: customerId,
    stripe_subscription_id: subscription.id,
    stripe_subscription_created: subscriptionCreated,
    stripe_product_id: productId,
    stripe_price_id: priceId,
    stripe_status: status,
    cancel_at_period_end: subscription.cancel_at_period_end,
  };
}

function parseCloudInvoicePaymentFailed(event) {
  if (event?.type !== "invoice.payment_failed") return null;
  const invoice = event.data?.object;
  const subscriptionId = stripeObjectId(invoice?.subscription, "sub")
    || stripeObjectId(invoice?.parent?.subscription_details?.subscription, "sub");
  if (!invoice || invoice.object !== "invoice") throw cloudError("billing_cloud_event_invalid");
  if (!subscriptionId) return null;
  if (!validSubscriptionId(subscriptionId) || !validEventId(event.id) || !positiveEpoch(event.created)) {
    throw cloudError("billing_cloud_event_invalid");
  }
  return { event_id: event.id, event_created: event.created, stripe_subscription_id: subscriptionId };
}

function rowForEvent(event, now, status = event.stripe_status, subscriptionId = event.stripe_subscription_id, lastEventId = event.event_id, lastEventCreated = event.event_created) {
  return {
    uid: event.tenant_uid,
    stripe_customer_id: event.stripe_customer_id,
    stripe_subscription_id: subscriptionId,
    stripe_product_id: event.stripe_product_id,
    stripe_price_id: event.stripe_price_id,
    stripe_status: status,
    cancel_at_period_end: event.cancel_at_period_end,
    entitled: ENTITLED_STATUSES.has(status),
    stripe_subscription_created: event.stripe_subscription_created,
    last_event_created: lastEventCreated,
    last_event_id: lastEventId,
    updated_at: now(),
  };
}

function nextCloudState(current, event, now) {
  if (!current) return { action: "applied", row: rowForEvent(event, now) };
  if (!STORED_STATUSES.has(current.stripe_status) || current.entitled !== ENTITLED_STATUSES.has(current.stripe_status)
    || typeof current.cancel_at_period_end !== "boolean") {
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

  async function readBySubscription(subscriptionId) {
    const url = new URL(`${root}/rest/v1/${TABLE}`);
    url.searchParams.set("select", FIELDS);
    url.searchParams.set("stripe_subscription_id", `eq.${subscriptionId}`);
    const result = await request(url, "GET");
    if (!Array.isArray(result.body) || result.body.length > 1) throw cloudError("billing_cloud_store_unavailable");
    return result.body[0] || null;
  }

  async function patchCurrent(current, patch) {
    const url = new URL(`${root}/rest/v1/${TABLE}`);
    for (const [field, value] of Object.entries({
      uid: current.uid,
      stripe_subscription_id: current.stripe_subscription_id,
      stripe_subscription_created: current.stripe_subscription_created,
      stripe_status: current.stripe_status,
      cancel_at_period_end: current.cancel_at_period_end,
      entitled: current.entitled,
      last_event_created: current.last_event_created,
      last_event_id: current.last_event_id,
    })) url.searchParams.set(field, `eq.${value}`);
    const result = await request(url, "PATCH", patch);
    return !result.conflict && Array.isArray(result.body) && result.body.length === 1;
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

      if (await patchCurrent(current, transition.row)) return transition.action;
    }
    throw cloudError("billing_cloud_store_conflict");
  }

  async function applyPaymentFailed(event) {
    for (let attempt = 0; attempt < maxCasAttempts; attempt += 1) {
      const current = await readBySubscription(event.stripe_subscription_id);
      if (!current) return "unmatched";
      if (!STORED_STATUSES.has(current.stripe_status) || current.entitled !== ENTITLED_STATUSES.has(current.stripe_status)
        || typeof current.cancel_at_period_end !== "boolean") throw cloudError("billing_cloud_store_state_invalid");
      if (["unpaid", "canceled", "incomplete_expired", "ambiguous"].includes(current.stripe_status)) return "stale";
      if (!["active", "trialing", "past_due"].includes(current.stripe_status)) return "stale";
      const lastCreated = Number(current.last_event_created);
      if (!positiveEpoch(lastCreated)) throw cloudError("billing_cloud_store_state_invalid");
      if (event.event_created < lastCreated) return "stale";
      if (event.event_created === lastCreated) {
        if (event.event_id === current.last_event_id) return "duplicate";
        const patch = { ...current, stripe_status: "ambiguous", entitled: false,
          last_event_id: [event.event_id, current.last_event_id].sort()[0], updated_at: now() };
        if (await patchCurrent(current, patch)) return "ambiguous";
        continue;
      }
      const patch = { ...current, stripe_status: "past_due", entitled: true,
        last_event_created: event.event_created, last_event_id: event.event_id, updated_at: now() };
      if (await patchCurrent(current, patch)) return "applied";
    }
    throw cloudError("billing_cloud_store_conflict");
  }

  return { apply, applyPaymentFailed, readTenant: read, readBySubscription, async isEntitled(uid) {
    const row = await read(uid);
    return row?.uid === uid && row.entitled === true && ENTITLED_STATUSES.has(row.stripe_status);
  } };
}

function safeLog(logger, method, message) {
  try { if (logger && typeof logger[method] === "function") logger[method](message); }
  catch { /* logging must not affect the webhook result */ }
}

async function handleMaritimeCloudStripeWebhook({ rawBody, signature, env = process.env, stripe, store, requestStop, logger = console } = {}) {
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

  let normalized, invoiceFailure;
  try {
    normalized = parseCloudSubscriptionEvent(event, config);
    invoiceFailure = parseCloudInvoicePaymentFailed(event);
  }
  catch { return { statusCode: 400, body: { error: "invalid_event" } }; }
  if (!normalized && !invoiceFailure) return { statusCode: 200, body: { status: "ignored" } };
  if (!store || typeof store.apply !== "function"
    || (invoiceFailure && typeof store.applyPaymentFailed !== "function")) return { statusCode: 503, body: { error: "billing_not_configured" } };

  try {
    const status = invoiceFailure ? await store.applyPaymentFailed(invoiceFailure) : await store.apply(normalized);
    if (!APPLY_ACTIONS.has(status)) throw cloudError("billing_cloud_store_unavailable");
    if (typeof requestStop === "function") {
      const row = normalized
        ? await store.readTenant?.(normalized.tenant_uid)
        : await store.readBySubscription?.(invoiceFailure.stripe_subscription_id);
      if (row?.uid && row.entitled === false) await requestStop(row.uid, row.last_event_id);
    }
    return { statusCode: 200, body: { status } };
  } catch {
    safeLog(logger, "error", "[cloud-stripe] subscription update failed");
    return { statusCode: 500, body: { error: "billing_update_failed" } };
  }
}

function cloudIdempotencyKey(tenantUid, operation, supplied) {
  if (typeof supplied !== "string" || !/^[A-Za-z0-9_-]{16,128}$/.test(supplied)) return "";
  const digest = require("node:crypto").createHash("sha256").update(`${tenantUid}:${operation}:${supplied}`).digest("hex");
  return `lm-cloud-${operation}-${digest}`;
}

async function handleMaritimeCloudBillingRequest(req, res, options = {}) {
  const pathname = new URL(req.url || "/", "http://localhost").pathname;
  if (!["/api/stripe/cloud/checkout", "/api/stripe/cloud/portal"].includes(pathname)) return false;
  const send = (status, body) => {
    res.writeHead(status, { "content-type": "application/json; charset=utf-8", "cache-control": "no-store",
      "referrer-policy": "no-referrer", "x-content-type-options": "nosniff" });
    res.end(JSON.stringify(body));
  };
  if (req.method !== "POST") { send(405, { error: "method_not_allowed" }); return true; }
  let config;
  try { config = resolveMaritimeCloudConfig(options.env || process.env); }
  catch { send(503, { error: "billing_not_configured" }); return true; }
  const publicOrigin = String(options.publicOrigin || "").replace(/\/$/, "");
  if (!/^https:\/\//.test(publicOrigin) || req.headers?.origin !== publicOrigin) { send(403, { error: "origin_rejected" }); return true; }
  let user;
  try { user = await (options.resolveUserImpl || require("./maritime-manager-auth.js").resolveMaritimeManagerUser)(req, res, options); }
  catch { user = null; }
  if (!user?.uid || !validTenantUid(user.uid) || !user.email || !user.csrf) { send(401, { error: "authentication_required" }); return true; }
  const suppliedCsrf = Buffer.from(String(req.headers?.["x-lm-web-csrf"] || ""));
  const expectedCsrf = Buffer.from(user.csrf);
  if (suppliedCsrf.length !== expectedCsrf.length || !require("node:crypto").timingSafeEqual(suppliedCsrf, expectedCsrf)) {
    send(403, { error: "csrf_rejected" }); return true;
  }
  let body = "";
  try {
    for await (const chunk of req) {
      body += chunk.toString("utf8");
      if (Buffer.byteLength(body) > 4096) throw new Error();
    }
    const parsed = body ? JSON.parse(body) : {};
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed) || Object.keys(parsed).length !== 0) throw new Error();
  } catch { send(400, { error: "invalid_request" }); return true; }
  const idempotencyKey = cloudIdempotencyKey(user.uid, pathname.endsWith("/portal") ? "portal" : "checkout",
    req.headers?.["idempotency-key"]);
  if (!idempotencyKey) { send(400, { error: "idempotency_key_required" }); return true; }
  const origin = publicOrigin;
  try {
    const stripe = options.stripeClient || (options.createStripeClient || ((key) => require("stripe")(key,
      { apiVersion: "2026-09-30.endive" })))(config.secretKey);
    if (pathname.endsWith("/checkout")) {
      const session = await stripe.checkout.sessions.create({ mode: "subscription",
        line_items: [{ price: config.priceId, quantity: 1 }], client_reference_id: user.uid,
        customer_email: user.email, subscription_data: { metadata: { lm_tenant_uid: user.uid } },
        success_url: `${origin}/maritime?cloud_checkout=success`, cancel_url: `${origin}/maritime?cloud_checkout=canceled` },
      { idempotencyKey });
      if (typeof session?.url !== "string" || !session.url.startsWith("https://checkout.stripe.com/")) throw new Error();
      send(200, { url: session.url }); return true;
    }
    const row = await options.billingStore?.readTenant?.(user.uid);
    if (!row || row.uid !== user.uid || !/^cus_[A-Za-z0-9]+$/.test(row.stripe_customer_id || "")) {
      send(409, { error: "cloud_customer_unavailable" }); return true;
    }
    const session = await stripe.billingPortal.sessions.create({ customer: row.stripe_customer_id,
      return_url: `${origin}/maritime` }, { idempotencyKey });
    if (typeof session?.url !== "string" || !session.url.startsWith("https://billing.stripe.com/")) throw new Error();
    send(200, { url: session.url }); return true;
  } catch {
    safeLog(options.logger, "error", "[cloud-stripe] billing session creation failed");
    send(502, { error: "checkout_unavailable" }); return true;
  }
}

async function requestMaritimeCloudStop({ tenantUid, eventId, managerStore, enqueueJob } = {}) {
  if (!validTenantUid(tenantUid) || !validEventId(eventId)) throw cloudError("billing_cloud_stop_request_invalid");
  if (typeof managerStore?.read !== "function" || typeof enqueueJob !== "function") throw cloudError("billing_cloud_stop_unconfigured");
  const row = await managerStore.read(tenantUid);
  if (!row || row.uid !== tenantUid || row.status !== "active" || row.paused_at || !row.agent_id) return { requested: false };
  const buildStopJob = require("./maritime-manager-runtime.js").buildMaritimeManagerProvisionJob;
  for (let stopAttempt = 0; stopAttempt <= 32; stopAttempt += 1) {
    const job = buildStopJob({ tenantId: tenantUid, releaseSha: row.release_sha, phase: "billing-stop", eventId, stopAttempt });
    const result = await enqueueJob(job);
    if (!result || typeof result.created !== "boolean" || result.job?.job_id !== job.job_id
      || result.job?.tenant_id !== tenantUid || !["queued", "running", "reconciling", "completed", "dead_letter"].includes(result.job.status)) {
      throw cloudError("billing_cloud_stop_unconfirmed");
    }
    if (result.job.status !== "dead_letter") return result;
  }
  throw cloudError("billing_cloud_stop_unconfirmed");
}

module.exports = {
  resolveMaritimeCloudConfig,
  createMaritimeCloudBillingStore,
  handleMaritimeCloudStripeWebhook,
  handleMaritimeCloudBillingRequest,
  requestMaritimeCloudStop,
};
