"use strict";
// HARD-3 billing lifecycle. Stripe webhook is the only writer of lm_users.paid.
// Telegram keeps its subscription-status mapping and past_due grace. Web Travel requires a card-backed trial
// or a paid invoice; payment failure, scheduled cancellation, and expiry stop Calendar work. Events are
// deduplicated in lm_stripe_events and ordered by event.created.

// PROVISION statuses: active + trialing are in good standing; past_due keeps access during the grace window
// (Stripe keeps retrying payment) while we send a dunning notice. Everything else = no access.
const PROVISION = new Set(["active", "trialing", "past_due"]);

// entitlementFor(status) → { paid, plan_status }. PURE. Unknown/empty/null → fail-safe paid=false.
function entitlementFor(status) {
  const s = status == null ? null : String(status).trim().toLowerCase();
  return { paid: !!s && PROVISION.has(s), plan_status: s || null };
}

// toEpoch: normalize a timestamp to UNIX seconds. Stripe sends ints (epoch seconds); Supabase stores
// timestamptz and PostgREST returns an ISO string — Number("2033-…")=NaN, so ISO values must be Date.parsed.
function toEpoch(v) {
  if (v == null) return 0;
  if (typeof v === "number") return v;
  const n = Number(v);
  if (!Number.isNaN(n) && String(v).trim() !== "") return n; // numeric string → epoch seconds
  const t = Date.parse(v);                                    // ISO timestamp → ms
  return Number.isNaN(t) ? 0 : Math.floor(t / 1000);
}

// parseStripeEvent(event) → normalized shape we act on, or null for event types we ignore (no-op 200).
//   checkout.session.completed → { kind:"checkout", uid, customerId, subscriptionId, paymentStatus, created }
//   customer.subscription.*     → { kind:"subscription", customerId, subscriptionId, status, currentPeriodEnd, created }
const SUBSCRIPTION_TYPES = new Set([
  "customer.subscription.created",
  "customer.subscription.updated",
  "customer.subscription.deleted",
]);
function parseStripeEvent(event) {
  const type = event && event.type;
  const o = (event && event.data && event.data.object) || {};
  const metadata = o.metadata && typeof o.metadata === "object" ? o.metadata : {};
  const created = (event && event.created) || 0; // event-level Unix seconds — the staleness ordering key
  if (type === "checkout.session.completed") {
    return {
      kind: "checkout",
      uid: o.client_reference_id || metadata.lm_uid || null,
      customerId: o.customer || null,
      subscriptionId: o.subscription || null,
      paymentStatus: o.payment_status || null, // 'paid' | 'unpaid' | 'no_payment_required'
      isWebTravel: metadata.lm_product === "life_manager_web_travel",
      created,
    };
  }
  if (SUBSCRIPTION_TYPES.has(type)) {
    const itemPeriodEnds = (((o.items || {}).data) || [])
      .map((item) => Number(item && item.current_period_end) || 0);
    return {
      kind: "subscription",
      customerId: o.customer || null,
      subscriptionId: o.id || null,
      status: o.status || null,
      currentPeriodEnd: Number(o.current_period_end) || Math.max(0, ...itemPeriodEnds),
      trialEnd: Number(o.trial_end) || 0,
      cancelAt: Number(o.cancel_at) || 0,
      cancelAtPeriodEnd: o.cancel_at_period_end === true,
      hasPaymentMethod: Boolean(o.default_payment_method || o.default_source),
      uid: metadata.lm_uid || null,
      isWebTravel: metadata.lm_product === "life_manager_web_travel",
      eventType: type,
      created,
    };
  }
  if (type === "invoice.paid" || type === "invoice.payment_failed") {
    const parentDetails = o.parent && o.parent.subscription_details || {};
    const rawSubscription = o.subscription || parentDetails.subscription || null;
    const subscriptionId = typeof rawSubscription === "string"
      ? rawSubscription : rawSubscription && rawSubscription.id || null;
    const parentMetadata = parentDetails.metadata && typeof parentDetails.metadata === "object"
      ? parentDetails.metadata : {};
    return {
      kind: "invoice",
      customerId: o.customer || null,
      subscriptionId,
      status: type === "invoice.paid" ? "paid" : "payment_failed",
      billingReason: o.billing_reason || null,
      uid: metadata.lm_uid || parentMetadata.lm_uid || null,
      isWebTravel: metadata.lm_product === "life_manager_web_travel"
        || parentMetadata.lm_product === "life_manager_web_travel",
      created,
    };
  }
  return null; // unknown type → caller acks 200 with no side effect
}

// isStale(incomingCreated, storedRow) → true when this event is OLDER (by event.created) than the last event
// we applied for this user. Keyed on event.created — the only monotonic ordering Stripe guarantees — so an
// immediate cancel (which may carry a current_period_end ≤ the active one) STILL applies. No stored row /
// no stored timestamp → first event → never stale.
function isStale(incomingCreated, storedRow) {
  if (!storedRow || !storedRow.stripe_event_at) return false;
  return toEpoch(incomingCreated) < toEpoch(storedRow.stripe_event_at);
}

// ── Supabase IO (service-role). All accept an injectable fetch for testing. ──────────────────────────
function hdr(key, extra) {
  return Object.assign({ apikey: key, Authorization: `Bearer ${key}` }, extra || {});
}

// claimEvent: INSERT into lm_stripe_events. 201 = claimed (process it) | 409 = duplicate (skip).
// No supa creds (local dev) → return true so the handler still runs once.
async function claimEvent(eventId, type, supaUrl, supaKey, fetchImpl) {
  const f = fetchImpl || fetch;
  if (!supaUrl || !supaKey) return true;
  const r = await f(`${supaUrl}/rest/v1/lm_stripe_events`, {
    method: "POST",
    headers: hdr(supaKey, { "Content-Type": "application/json", Prefer: "return=minimal" }),
    body: JSON.stringify({ event_id: eventId, type }),
  }).catch(() => null);
  return !!r && r.status === 201;
}

// unclaimEvent: DELETE the claim so a Stripe redelivery re-processes (used when the write failed). Returns
// true on success — the caller logs a RECONCILE marker if this fails (the transition would otherwise stick).
async function unclaimEvent(eventId, supaUrl, supaKey, fetchImpl) {
  const f = fetchImpl || fetch;
  if (!supaUrl || !supaKey) return true;
  const r = await f(`${supaUrl}/rest/v1/lm_stripe_events?event_id=eq.${encodeURIComponent(eventId)}`, {
    method: "DELETE",
    headers: hdr(supaKey, { Prefer: "return=minimal" }),
  }).catch(() => null);
  return !!r && (r.status === 204 || r.status === 200);
}

// userByCustomer(customerId) → the stored lm_users row (uid + billing cols incl. stripe_event_at) or null.
async function userByCustomer(customerId, supaUrl, supaKey, fetchImpl) {
  const f = fetchImpl || fetch;
  if (!supaUrl || !supaKey || !customerId) return null;
  const cols = "uid,telegram_chat_id,web_first_travel_at,calendar_connected_account_id,stripe_customer_id,stripe_subscription_id,current_period_end,stripe_event_at,plan_status,paid,trial_expires_at";
  const r = await f(
    `${supaUrl}/rest/v1/lm_users?stripe_customer_id=eq.${encodeURIComponent(customerId)}&select=${cols}`,
    { headers: hdr(supaKey) },
  ).catch(() => null);
  if (!r || !r.ok) return null;
  const d = await r.json().catch(() => []);
  return Array.isArray(d) && d[0] ? d[0] : null;
}

// userByUid(uid) → the stored lm_users row (billing cols incl. stripe_event_at) or null. Used by the
// checkout branch (keyed by uid via client_reference_id) for the same staleness guard the subscription
// branch uses (FIND-007).
async function userByUid(uid, supaUrl, supaKey, fetchImpl) {
  const f = fetchImpl || fetch;
  if (!supaUrl || !supaKey || !uid) return null;
  const cols = "uid,telegram_chat_id,web_first_travel_at,calendar_connected_account_id,stripe_customer_id,stripe_subscription_id,current_period_end,stripe_event_at,plan_status,paid,trial_expires_at";
  const r = await f(
    `${supaUrl}/rest/v1/lm_users?uid=eq.${encodeURIComponent(uid)}&select=${cols}`,
    { headers: hdr(supaKey) },
  ).catch(() => null);
  if (!r || !r.ok) return null;
  const d = await r.json().catch(() => []);
  return Array.isArray(d) && d[0] ? d[0] : null;
}

// patchUser: write the billing patch onto lm_users by a PostgREST filter.
async function patchUser(filter, patch, supaUrl, supaKey, fetchImpl) {
  const f = fetchImpl || fetch;
  if (!supaUrl || !supaKey) return true;
  const r = await f(`${supaUrl}/rest/v1/lm_users?${filter}`, {
    method: "PATCH",
    headers: hdr(supaKey, { "Content-Type": "application/json", Prefer: "return=minimal" }),
    body: JSON.stringify(patch),
  }).catch(() => null);
  return !!r && (r.status === 204 || r.status === 200);
}

const isoOrNull = (epochSecs) => (epochSecs ? new Date(epochSecs * 1000).toISOString() : null);

function isWebTravelUser(row) {
  return Boolean(row && row.telegram_chat_id === null && row.web_first_travel_at);
}

function webTrialEligible(row) {
  if (!isWebTravelUser(row)) return false;
  const priorStatus = String(row.plan_status || "").trim().toLowerCase();
  return !row.stripe_subscription_id && !row.trial_expires_at && row.paid !== true
    && !priorStatus;
}

function webPaidCheckoutEligible(row) {
  if (!isWebTravelUser(row) || row.paid === true) return false;
  const status = String(row.plan_status || "").trim().toLowerCase();
  if (!["", "canceled", "unpaid", "incomplete_expired"].includes(status)) return false;
  if (row.stripe_subscription_id && !status) return false;
  return true;
}

function webTravelEntitled(row, nowMs = Date.now()) {
  if (!isWebTravelUser(row) || row.paid !== true) return false;
  const status = String(row.plan_status || "").trim().toLowerCase();
  if (status === "active") return true;
  return status === "trialing" && toEpoch(row.trial_expires_at) > Math.floor(Number(nowMs) / 1000);
}

async function resumeWebAutomation(uid, row, supaUrl, supaKey, fetchImpl) {
  const accountId = String(row && row.calendar_connected_account_id || "");
  if (!accountId || !supaUrl || !supaKey) return false;
  const f = fetchImpl || fetch;
  const response = await f(`${String(supaUrl).replace(/\/$/, "")}/rest/v1/rpc/control_lm_web_travel`, {
    method: "POST",
    headers: hdr(supaKey, { "Content-Type": "application/json" }),
    body: JSON.stringify({ p_uid: uid, p_calendar_account_id: accountId, p_action: "resume" }),
  }).catch(() => null);
  if (!response || !response.ok) return false;
  const value = await response.json().catch(() => null);
  return value === true || Array.isArray(value) && value[0] === true;
}

async function rowForEvent(p, supaUrl, supaKey, fetchImpl) {
  if (p.uid) {
    const row = await userByUid(p.uid, supaUrl, supaKey, fetchImpl);
    if (row || p.isWebTravel) return row;
  }
  return userByCustomer(p.customerId, supaUrl, supaKey, fetchImpl);
}

// applyBilling(event, deps) — orchestrates ONE event into a lm_users write. Returns a result object for
// logging/tests. deps = { supaUrl, supaKey, fetchImpl, notify }. Throws on a write failure so the webhook
// handler can 500 + unclaim → Stripe redelivers.
async function applyBilling(event, deps) {
  const { supaUrl, supaKey, fetchImpl, notify } = deps || {};
  const p = parseStripeEvent(event);
  if (!p) return { action: "ignored", type: event && event.type };

  if (p.kind === "checkout") {
    if (!p.uid) return { action: "orphan-checkout" };
    // FIND-007: guard the checkout branch by event.created too (same as subscription) — a late/out-of-order
    // checkout must NOT clobber a fresher applied state (downgrade an active payer, or regress stripe_event_at).
    const row = await userByUid(p.uid, supaUrl, supaKey, fetchImpl);
    if (isStale(p.created, row)) return { action: "stale-checkout", uid: p.uid };
    if (p.isWebTravel) {
      if (!isWebTravelUser(row)) return { action: "orphan-web-checkout", uid: p.uid };
      if (row.stripe_customer_id && p.customerId && row.stripe_customer_id !== p.customerId) {
        return { action: "customer-mismatch", uid: p.uid };
      }
      const patch = {};
      if (p.customerId) patch.stripe_customer_id = p.customerId;
      if (p.subscriptionId) patch.stripe_subscription_id = p.subscriptionId;
      const status = String(row.plan_status || "").toLowerCase();
      if (!(row.paid === true && ["trialing", "active"].includes(status))) {
        patch.paid = false;
        patch.plan_status = "incomplete";
      }
      if (Object.keys(patch).length && !(await patchUser(`uid=eq.${encodeURIComponent(p.uid)}`, patch, supaUrl, supaKey, fetchImpl))) {
        throw new Error("web checkout link patch failed");
      }
      return { action: "link-web-checkout", uid: p.uid, paid: row.paid === true };
    }
    // FIND-003: only provision when the session is actually paid. An 'unpaid' checkout links the customer
    // but must NOT grant access — the subsequent subscription.* event sets the real status.
    const paid = p.paymentStatus === "paid" || p.paymentStatus === "no_payment_required";
    const patch = {
      stripe_customer_id: p.customerId,
      stripe_subscription_id: p.subscriptionId,
      paid,
      plan_status: paid ? "active" : "incomplete",
      stripe_event_at: isoOrNull(p.created),
    };
    if (!(await patchUser(`uid=eq.${encodeURIComponent(p.uid)}`, patch, supaUrl, supaKey, fetchImpl))) {
      throw new Error("checkout patch failed");
    }
    return { action: paid ? "provision" : "link-unpaid", uid: p.uid, paid };
  }

  const row = await rowForEvent(p, supaUrl, supaKey, fetchImpl);
  if (!row || !row.uid) return { action: `orphan-${p.kind}`, customerId: p.customerId };
  const web = isWebTravelUser(row);
  if (p.isWebTravel && !web) return { action: "web-tenant-mismatch", uid: p.uid || null };
  if (row.stripe_customer_id && p.customerId && row.stripe_customer_id !== p.customerId) {
    return { action: "customer-mismatch", uid: row.uid };
  }
  if (p.kind === "invoice") {
    const currentSubscriptionId = String(row.stripe_subscription_id || "");
    const inactivePriorSubscription = ["canceled", "unpaid", "incomplete_expired"]
      .includes(String(row.plan_status || "").toLowerCase());
    const canLinkWebSubscription = web && (p.uid === row.uid || row.stripe_customer_id === p.customerId)
      && (!currentSubscriptionId || inactivePriorSubscription);
    if (!p.subscriptionId || (p.subscriptionId !== currentSubscriptionId && !canLinkWebSubscription)) {
      return { action: "stale-invoice-subscription", uid: row.uid };
    }
    if (isStale(p.created, row)) return { action: "stale-invoice", uid: row.uid };
    const paid = p.status === "paid";
    const patch = {
      paid: web ? paid : paid || row.paid === true,
      plan_status: paid ? "active" : web ? "past_due" : row.plan_status || "past_due",
      stripe_event_at: isoOrNull(p.created),
      ...(web ? {
        stripe_customer_id: p.customerId || row.stripe_customer_id,
        stripe_subscription_id: p.subscriptionId,
        trial_expires_at: null,
      } : {}),
    };
    if (!(await patchUser(`uid=eq.${encodeURIComponent(row.uid)}`, patch, supaUrl, supaKey, fetchImpl))) {
      throw new Error("invoice patch failed");
    }
    return { action: paid ? "invoice-paid" : "invoice-failed", uid: row.uid, paid: patch.paid };
  }

  if (!web && p.isWebTravel) return { action: "web-tenant-mismatch", uid: row.uid };
  if (web && !row.web_first_travel_at) return { action: "web-first-travel-required", uid: row.uid };
  if (web && row.stripe_subscription_id && p.subscriptionId !== row.stripe_subscription_id) {
    const priorStatus = String(row.plan_status || "").toLowerCase();
    const priorInactive = ["canceled", "unpaid", "incomplete_expired"].includes(priorStatus);
    const sameWebTenant = p.uid === row.uid
      || Boolean(p.customerId && row.stripe_customer_id && p.customerId === row.stripe_customer_id);
    if (!priorInactive || !sameWebTenant) return { action: "stale-subscription-id", uid: row.uid };
  }
  if (isStale(p.created, row)) return { action: "stale", customerId: p.customerId };

  if (web) {
    const trialing = p.status === "trialing";
    const trialEnd = trialing && p.trialEnd > 0 ? isoOrNull(p.trialEnd) : null;
    const cancellationRequested = p.cancelAtPeriodEnd === true || p.cancelAt > 0;
    const paid = trialing
      ? Boolean(p.hasPaymentMethod && trialEnd && !cancellationRequested)
      : p.status === "active" && row.paid === true
        && String(row.plan_status || "").toLowerCase() === "active" && !cancellationRequested;
    const patch = {
      stripe_customer_id: p.customerId || row.stripe_customer_id,
      stripe_subscription_id: p.subscriptionId,
      paid,
      plan_status: p.status || null,
      current_period_end: isoOrNull(p.currentPeriodEnd),
      trial_expires_at: trialEnd,
      stripe_event_at: isoOrNull(p.created),
    };
    if (!(await patchUser(`uid=eq.${encodeURIComponent(row.uid)}`, patch, supaUrl, supaKey, fetchImpl))) {
      throw new Error("web subscription patch failed");
    }
    if (p.eventType === "customer.subscription.created" && paid
      && !(await resumeWebAutomation(row.uid, row, supaUrl, supaKey, fetchImpl))) {
      throw new Error("web automation activation failed");
    }
    return { action: paid ? "provision" : "deprovision", uid: row.uid, paid, status: p.status };
  }

  // Legacy subscription behavior remains shared with Telegram, including past_due grace.
  if (isStale(p.created, row)) return { action: "stale", customerId: p.customerId };

  const ent = entitlementFor(p.status);
  const patch = {
    paid: ent.paid,
    plan_status: ent.plan_status,
    stripe_subscription_id: p.subscriptionId,
    current_period_end: isoOrNull(p.currentPeriodEnd),
    stripe_event_at: isoOrNull(p.created),
  };
  if (!(await patchUser(`uid=eq.${encodeURIComponent(row.uid)}`, patch, supaUrl, supaKey, fetchImpl))) {
    throw new Error("subscription patch failed");
  }

  // Dunning: past_due keeps access but warns once. notify is injected (best-effort; never blocks the webhook).
  if (p.status === "past_due" && typeof notify === "function") {
    try { await notify(row.uid); } catch { /* dunning is best-effort */ }
  }
  return { action: ent.paid ? "provision" : "deprovision", uid: row.uid, paid: ent.paid, status: p.status };
}

module.exports = {
  entitlementFor,
  isWebTravelUser,
  webTrialEligible,
  webPaidCheckoutEligible,
  webTravelEntitled,
  resumeWebAutomation,
  parseStripeEvent,
  isStale,
  toEpoch,
  claimEvent,
  unclaimEvent,
  userByCustomer,
  userByUid,
  patchUser,
  applyBilling,
};
