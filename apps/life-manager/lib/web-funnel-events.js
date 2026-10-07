"use strict";

const { randomUUID } = require("node:crypto");
const { sanitizeWebAttribution } = require("./web-attribution.js");

const WEB_UID_RE = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SAFE_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const WEB_FUNNEL_EVENTS = new Set([
  "landing_view", "google_connect_start", "google_authenticated", "calendar_active",
  "first_travel_block", "checkout_created", "trial_started", "paid_invoice",
  "cancellation_requested", "subscription_canceled", "refund_recorded",
]);
const BILLING_REASONS = new Set([
  "automatic_pending_invoice_item_invoice", "manual", "subscription", "subscription_create",
  "subscription_cycle", "subscription_threshold", "subscription_update", "upcoming", "quote_accept",
  "pending_update",
]);

function boundedId(value, name) {
  if (value == null || value === "") return null;
  const result = String(value);
  if (!SAFE_ID_RE.test(result)) throw new Error(`invalid ${name}`);
  return result;
}

function normalizeWebFunnelEvent(event = {}, nowMs = Date.now()) {
  if (!WEB_FUNNEL_EVENTS.has(event.eventName)) throw new Error("invalid Web funnel event");
  const eventId = boundedId(event.eventId || randomUUID(), "event id");
  const uid = event.uid == null ? null : String(event.uid);
  if (uid != null && !WEB_UID_RE.test(uid)) throw new Error("invalid Web funnel uid");
  const sourceObjectId = boundedId(event.sourceObjectId, "source object id");
  const sourceEventId = boundedId(event.sourceEventId, "source event id");
  const amountUsd = event.amountUsd == null ? null : Number(event.amountUsd);
  if (amountUsd != null && (!Number.isFinite(amountUsd) || amountUsd < 0)) throw new Error("invalid amount");
  const currency = event.currency == null ? null : String(event.currency).toLowerCase();
  if (currency != null && !/^[a-z]{3}$/.test(currency)) throw new Error("invalid currency");
  const billingReason = event.billingReason == null ? null : String(event.billingReason);
  if (billingReason != null && !BILLING_REASONS.has(billingReason)) throw new Error("invalid billing reason");
  const occurredAtMs = event.occurredAt == null ? Number(nowMs) : Date.parse(String(event.occurredAt));
  if (!Number.isFinite(occurredAtMs) || occurredAtMs < 0) throw new Error("invalid occurred time");

  return {
    event_id: eventId,
    event_name: event.eventName,
    uid,
    source_object_id: sourceObjectId,
    source_event_id: sourceEventId,
    attribution: sanitizeWebAttribution(event.attribution),
    amount_usd: amountUsd,
    currency,
    billing_reason: billingReason,
    occurred_at: new Date(occurredAtMs).toISOString(),
  };
}

async function recordWebFunnelEvent(event, opts = {}) {
  const env = opts.env && typeof opts.env === "object" ? opts.env : process.env;
  const supaUrl = String(opts.supaUrl || env.SUPABASE_URL || "").replace(/\/$/, "");
  const supaKey = String(opts.supaKey || env.SUPABASE_SERVICE_ROLE_KEY || "").trim();
  const fetchImpl = opts.fetchImpl || globalThis.fetch;
  if (!supaUrl || !supaKey || typeof fetchImpl !== "function") return false;
  let row;
  try { row = normalizeWebFunnelEvent(event, opts.nowMs == null ? Date.now() : opts.nowMs); }
  catch { return false; }
  try {
    const response = await fetchImpl(`${supaUrl}/rest/v1/lm_web_funnel_events`, {
      method: "POST",
      headers: {
        apikey: supaKey,
        Authorization: `Bearer ${supaKey}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify(row),
    });
    return Boolean(response && (response.ok || response.status === 409));
  } catch {
    return false;
  }
}

function webFunnelEventForRequest(requestUrl, method = "GET") {
  if (String(method || "GET").toUpperCase() !== "GET") return null;
  let url;
  try { url = new URL(String(requestUrl || "/"), "https://aniccaai.com"); }
  catch { return null; }
  const eventName = url.pathname === "/lm" ? "landing_view"
    : url.pathname === "/auth/google" ? "google_connect_start" : null;
  return eventName ? { eventName, attribution: sanitizeWebAttribution(url.searchParams) } : null;
}

function webFunnelEventFromStripe(event, parsed) {
  if (!event || !parsed || parsed.isWebTravel !== true || !WEB_UID_RE.test(String(parsed.uid || ""))) return null;
  const occurredAt = Number.isFinite(Number(event.created)) && Number(event.created) > 0
    ? new Date(Number(event.created) * 1000).toISOString() : undefined;
  const common = {
    uid: parsed.uid,
    sourceEventId: event.id || null,
    attribution: {},
    ...(occurredAt ? { occurredAt } : {}),
  };
  if (parsed.kind === "subscription") {
    if (parsed.eventType === "customer.subscription.updated" && parsed.cancelAtPeriodEnd === true) {
      return { ...common, eventName: "cancellation_requested", sourceObjectId: parsed.subscriptionId };
    }
    if (parsed.eventType === "customer.subscription.deleted" || parsed.status === "canceled") {
      return { ...common, eventName: "subscription_canceled", sourceObjectId: parsed.subscriptionId };
    }
    const cardBackedTrial = parsed.hasPaymentMethod === true || parsed.cardBackedTrial === true;
    if (parsed.status === "trialing" && cardBackedTrial) {
      return { ...common, eventName: "trial_started", sourceObjectId: parsed.subscriptionId };
    }
    return null;
  }
  if (parsed.kind === "invoice" && parsed.status === "paid" && Number(parsed.amountPaid) > 0) {
    const rawCurrency = event.data && event.data.object && event.data.object.currency;
    const currency = typeof rawCurrency === "string" ? rawCurrency.toLowerCase() : null;
    return {
      ...common,
      eventName: "paid_invoice",
      sourceObjectId: parsed.invoiceId,
      amountUsd: currency === "usd" ? Number((Number(parsed.amountPaid) / 100).toFixed(2)) : null,
      currency,
      billingReason: BILLING_REASONS.has(parsed.billingReason) ? parsed.billingReason : null,
    };
  }
  return null;
}

async function recordWebFunnelStripeEvent(event, parsed, billingResult, opts = {}) {
  if (event && ["refund.created", "refund.updated"].includes(event.type)) {
    return recordWebFunnelRefund(event, opts);
  }
  if (!parsed) return true;
  const funnelEvent = webFunnelEventFromStripe(event, {
    ...parsed,
    uid: billingResult && billingResult.uid || parsed.uid,
    cardBackedTrial: parsed.hasPaymentMethod === true
      || billingResult && billingResult.status === "trialing"
        && billingResult.action === "provision" && billingResult.paid === false,
  });
  if (!funnelEvent) return true;
  const write = opts.recordWebFunnelEventImpl || recordWebFunnelEvent;
  try {
    return (await write(funnelEvent, {
      supaUrl: opts.supaUrl,
      supaKey: opts.supaKey,
      fetchImpl: opts.fetchImpl,
    })) !== false;
  } catch { return false; }
}

function webFunnelEventFromRefund(event, uid) {
  const refund = event && event.data && event.data.object || {};
  if (!event || !["refund.created", "refund.updated"].includes(event.type)
    || refund.status !== "succeeded" || !WEB_UID_RE.test(String(uid || ""))) return null;
  const currency = typeof refund.currency === "string" ? refund.currency.toLowerCase() : null;
  const amount = Number(refund.amount);
  if (!refund.id || !Number.isFinite(amount) || amount <= 0) return null;
  const occurredAt = Number.isFinite(Number(event.created)) && Number(event.created) > 0
    ? new Date(Number(event.created) * 1000).toISOString() : undefined;
  return {
    eventName: "refund_recorded",
    uid,
    sourceObjectId: refund.id,
    sourceEventId: event.id || null,
    ...(currency === "usd" ? { amountUsd: Number((amount / 100).toFixed(2)) } : {}),
    currency,
    attribution: {},
    ...(occurredAt ? { occurredAt } : {}),
  };
}

async function recordWebFunnelRefund(event, opts = {}) {
  const refund = event && event.data && event.data.object || {};
  if (!event || !["refund.created", "refund.updated"].includes(event.type) || refund.status !== "succeeded") return true;
  let customerValue = refund.customer;
  let customerId = typeof customerValue === "string" ? customerValue : customerValue && customerValue.id;
  if (!customerId && refund.charge) {
    const chargeId = typeof refund.charge === "string" ? refund.charge : refund.charge.id;
    const stripe = opts.stripeClient || opts.stripe;
    if (!stripe || !chargeId) return false;
    try {
      const charge = await stripe.charges.retrieve(chargeId);
      customerValue = charge && charge.customer;
      customerId = typeof customerValue === "string" ? customerValue : customerValue && customerValue.id;
    } catch { return false; }
  }
  if (!customerId) return true;
  const env = opts.env && typeof opts.env === "object" ? opts.env : process.env;
  const supaUrl = String(opts.supaUrl || env.SUPABASE_URL || "").replace(/\/$/, "");
  const supaKey = String(opts.supaKey || env.SUPABASE_SERVICE_ROLE_KEY || "").trim();
  const fetchImpl = opts.fetchImpl || globalThis.fetch;
  if (!supaUrl || !supaKey || typeof fetchImpl !== "function") return false;
  let response;
  try {
    const url = new URL(`${supaUrl}/rest/v1/lm_users`);
    url.searchParams.set("stripe_customer_id", `eq.${customerId}`);
    url.searchParams.set("telegram_chat_id", "is.null");
    url.searchParams.set("web_first_travel_at", "not.is.null");
    url.searchParams.set("select", "uid");
    url.searchParams.set("limit", "2");
    response = await fetchImpl(url.toString(), {
      headers: { apikey: supaKey, Authorization: `Bearer ${supaKey}` },
    });
  } catch { return false; }
  if (!response || !response.ok) return false;
  const users = await response.json().catch(() => null);
  if (!Array.isArray(users) || users.length > 1) return false;
  if (!users.length) return true;
  const funnelEvent = webFunnelEventFromRefund(event, users[0].uid);
  if (!funnelEvent) return true;
  const write = opts.recordWebFunnelEventImpl || recordWebFunnelEvent;
  try {
    return (await write(funnelEvent, { supaUrl, supaKey, fetchImpl })) !== false;
  } catch { return false; }
}

async function recordWebFunnelRequest(requestUrl, opts = {}) {
  const { method = "GET", ...recordOptions } = opts;
  const event = webFunnelEventForRequest(requestUrl, method);
  return event ? recordWebFunnelEvent(event, recordOptions) : false;
}

module.exports = {
  WEB_FUNNEL_EVENTS, normalizeWebFunnelEvent, recordWebFunnelEvent,
  webFunnelEventForRequest, recordWebFunnelRequest, webFunnelEventFromStripe,
  webFunnelEventFromRefund, recordWebFunnelRefund, recordWebFunnelStripeEvent,
};
