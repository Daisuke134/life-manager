"use strict";

const WEB_UID_RE = /^lm_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const ATTRIBUTION_FIELDS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"];
const ZERO_FUNNEL = () => ({
  landingViews: 0,
  googleConnectStarts: 0,
  googleAuthenticatedUsers: 0,
  calendarActiveUsers: 0,
  firstTravelUsers: 0,
  checkoutSessions: 0,
  trialStartedUsers: 0,
  paidInvoices: 0,
  firstPaidUsers: 0,
  renewalInvoices: 0,
  cancellationRequests: 0,
  canceledUsers: 0,
  refundsUsd: 0,
});

function finite(value) {
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function eventTime(event) {
  const value = Date.parse(String(event && (event.occurred_at || event.created_at) || ""));
  return Number.isFinite(value) ? value : null;
}

function inPeriod(value, startMs, nowMs) {
  const time = typeof value === "number" ? value : Date.parse(String(value || ""));
  return Number.isFinite(time) && time >= startMs && time <= nowMs;
}

function normalizedAttribution(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  return Object.fromEntries(ATTRIBUTION_FIELDS
    .filter((key) => typeof source[key] === "string" && source[key].trim())
    .map((key) => [key, source[key].trim()]));
}

function attributionKey(value) {
  const attribution = normalizedAttribution(value);
  return JSON.stringify(ATTRIBUTION_FIELDS.map((key) => attribution[key] || ""));
}

function eventAttribution(event, usersByUid) {
  const explicit = normalizedAttribution(event.attribution);
  if (Object.keys(explicit).length) return explicit;
  return normalizedAttribution(usersByUid.get(String(event.uid || ""))?.web_first_touch);
}

function firstPaidInvoiceByUid(events, usersByUid) {
  const rows = (Array.isArray(events) ? events : [])
    .filter((event) => event && event.event_name === "paid_invoice"
      && String(event.currency || "").toLowerCase() === "usd"
      && finite(event.amount_usd) > 0
      && usersByUid.has(String(event.uid || ""))
      && event.source_object_id);
  rows.sort((a, b) => (eventTime(a) || 0) - (eventTime(b) || 0));
  const first = new Map();
  for (const row of rows) {
    const uid = String(row.uid);
    if (!first.has(uid)) first.set(uid, String(row.source_object_id));
  }
  return first;
}

function addEventCount(bucket, event, usersByUid, uidSets) {
  const uid = String(event.uid || "");
  switch (event.event_name) {
    case "landing_view": bucket.landingViews++; break;
    case "google_connect_start": bucket.googleConnectStarts++; break;
    case "google_authenticated": if (uid) uidSets.auth.add(uid); break;
    case "calendar_active": if (uid) uidSets.calendar.add(uid); break;
    case "first_travel_block": if (uid) uidSets.travel.add(uid); break;
    case "checkout_created": uidSets.checkouts.add(String(event.source_object_id || event.event_id || uid)); break;
    case "trial_started": if (uid) uidSets.trials.add(uid); break;
    case "paid_invoice": {
      const invoiceId = String(event.source_object_id || event.event_id || "");
      if (!invoiceId || String(event.currency || "").toLowerCase() !== "usd") break;
      uidSets.paidInvoices.set(invoiceId, { uid, time: eventTime(event), amount: finite(event.amount_usd) || 0, sourceObjectId: invoiceId });
      break;
    }
    case "cancellation_requested": if (uid) uidSets.cancelRequests.add(uid); break;
    case "subscription_canceled": if (uid) uidSets.canceled.add(uid); break;
    case "refund_recorded":
      if (String(event.currency || "").toLowerCase() === "usd") {
        bucket.refundsUsd += Math.max(0, finite(event.amount_usd) || 0);
      }
      break;
    default: break;
  }
}

function monthlyAmount(subscription) {
  let total = 0;
  let priced = false;
  for (const item of (((subscription.items || {}).data) || [])) {
    const price = item && item.price || {};
    if (String(price.currency || "").toLowerCase() !== "usd" || !price.recurring) continue;
    const cents = finite(price.unit_amount ?? price.unit_amount_decimal);
    const quantity = finite(item.quantity) ?? 1;
    const intervalCount = Math.max(1, finite(price.recurring.interval_count) ?? 1);
    if (cents == null || quantity <= 0) continue;
    const interval = price.recurring.interval;
    const multiplier = interval === "month" ? 1 / intervalCount
      : interval === "year" ? 1 / (12 * intervalCount)
        : interval === "week" ? 52 / (12 * intervalCount)
          : interval === "day" ? 365 / (12 * intervalCount) : 0;
    if (!multiplier) continue;
    total += cents * quantity * multiplier / 100;
    priced = true;
  }
  return priced ? total : null;
}

function buildWebFunnelReport(input = {}) {
  const nowMs = Number.isFinite(Number(input.nowMs)) ? Number(input.nowMs) : Date.now();
  const periodDays = Math.max(1, Math.min(365, Math.floor(finite(input.periodDays) || 30)));
  const startMs = nowMs - periodDays * 86400000;
  const users = (Array.isArray(input.users) ? input.users : [])
    .filter((user) => user && WEB_UID_RE.test(String(user.uid || "")) && user.telegram_chat_id == null);
  const usersByUid = new Map(users.map((user) => [String(user.uid), user]));
  const firstPaidInvoiceIds = firstPaidInvoiceByUid(input.paidInvoiceHistory || input.events, usersByUid);
  const events = (Array.isArray(input.events) ? input.events : [])
    .filter((event) => event && inPeriod(eventTime(event), startMs, nowMs))
    .filter((event) => event.uid == null || usersByUid.has(String(event.uid)));
  const totals = ZERO_FUNNEL();
  const totalSets = {
    auth: new Set(), calendar: new Set(), travel: new Set(), checkouts: new Set(), trials: new Set(),
    paidInvoices: new Map(), cancelRequests: new Set(), canceled: new Set(),
  };
  const buckets = new Map();
  for (const event of events) {
    const attribution = eventAttribution(event, usersByUid);
    const key = attributionKey(attribution);
    let entry = buckets.get(key);
    if (!entry) {
      entry = { attribution: Object.fromEntries(ATTRIBUTION_FIELDS.map((field) => [field, attribution[field] || null])), ...ZERO_FUNNEL(),
        _sets: { auth: new Set(), calendar: new Set(), travel: new Set(), checkouts: new Set(), trials: new Set(),
          paidInvoices: new Map(), cancelRequests: new Set(), canceled: new Set() } };
      buckets.set(key, entry);
    }
    addEventCount(totals, event, usersByUid, totalSets);
    addEventCount(entry, event, usersByUid, entry._sets);
  }

  function finalize(bucket, sets) {
    bucket.googleAuthenticatedUsers = sets.auth.size;
    bucket.calendarActiveUsers = sets.calendar.size;
    bucket.firstTravelUsers = sets.travel.size;
    bucket.checkoutSessions = sets.checkouts.size;
    bucket.trialStartedUsers = sets.trials.size;
    bucket.paidInvoices = sets.paidInvoices.size;
    const firstPaid = new Set();
    for (const invoice of sets.paidInvoices.values()) {
      if (!invoice.uid) continue;
      if (firstPaidInvoiceIds.get(invoice.uid) === String(invoice.sourceObjectId)) firstPaid.add(invoice.uid);
      else bucket.renewalInvoices++;
    }
    bucket.firstPaidUsers = firstPaid.size;
    bucket.cancellationRequests = sets.cancelRequests.size;
    bucket.canceledUsers = sets.canceled.size;
    bucket.refundsUsd = Number(bucket.refundsUsd.toFixed(2));
    return bucket;
  }
  finalize(totals, totalSets);
  const attribution = Array.from(buckets.values()).map((entry) => {
    const sets = entry._sets;
    delete entry._sets;
    return finalize(entry, sets);
  }).sort((a, b) => JSON.stringify(a.attribution).localeCompare(JSON.stringify(b.attribution)));

  const activePaidUids = new Set();
  let grossMrrUsd = 0;
  let activeTrials = 0;
  for (const subscription of Array.isArray(input.subscriptions) ? input.subscriptions : []) {
    const metadata = subscription && subscription.metadata || {};
    const uid = String(metadata.lm_uid || "");
    const user = usersByUid.get(uid);
    if (!user || metadata.lm_product !== "life_manager_web_travel") continue;
    if (subscription.status === "trialing") {
      if (user.plan_status === "trialing" && user.paid !== true
        && user.web_trial_payment_method_present === true
        && Date.parse(String(user.trial_expires_at || "")) > nowMs
        && user.stripe_subscription_id === subscription.id) activeTrials++;
      continue;
    }
    if (subscription.status !== "active") continue;
    if (user.paid !== true || user.plan_status !== "active" || user.stripe_subscription_id !== subscription.id) continue;
    const amount = monthlyAmount(subscription);
    if (amount == null) continue;
    grossMrrUsd += amount;
    activePaidUids.add(uid);
  }

  function retention(days) {
    const cutoff = nowMs - days * 86400000;
    const matured = users.filter((user) => inPeriod(
      user.web_first_travel_at && Date.parse(user.web_first_travel_at), 0, cutoff,
    ));
    return {
      maturedUsers: matured.length,
      activePaidUsers: matured.filter((user) => activePaidUids.has(String(user.uid))).length,
    };
  }

  let providerEstimatedKnownUsd = 0;
  let providerEstimateUnknownRows = 0;
  let providerActualUsd = 0;
  let providerActualComplete = true;
  let providerCostRows = 0;
  for (const row of Array.isArray(input.providerCosts) ? input.providerCosts : []) {
    if (!usersByUid.has(String(row.uid || "")) || !inPeriod(row.ts, startMs, nowMs)) continue;
    if (row.kind && row.kind !== "provider_usage") continue;
    providerCostRows++;
    const estimate = finite(row.est_usd);
    if (estimate != null && estimate >= 0) providerEstimatedKnownUsd += estimate;
    else providerEstimateUnknownRows++;
    const actual = finite(row.meta && row.meta.actual_usd);
    if (actual == null) providerActualComplete = false;
    else if (actual >= 0) providerActualUsd += actual;
  }
  let stripeFeesUsd = 0;
  const stripeFeesComplete = input.stripeFeesComplete !== false;
  let balanceAvailableNetCents = 0;
  let balancePendingNetCents = 0;
  let paidPayoutNetCents = 0;
  let stripePayoutsComplete = input.stripePayoutsComplete !== false;
  let paidInvoiceUsd = 0;
  for (const event of events) {
    const amount = finite(event.amount_usd);
    if (event.event_name === "paid_invoice" && String(event.currency || "").toLowerCase() === "usd" && amount != null && amount > 0) {
      paidInvoiceUsd += amount;
    }
  }
  for (const row of Array.isArray(input.balanceTransactions) ? input.balanceTransactions : []) {
    if (!usersByUid.has(String(row.uid || "")) || String(row.currency || "").toLowerCase() !== "usd"
      || !inPeriod(row.created, startMs, nowMs)) continue;
    const fee = finite(row.fee);
    if (fee != null) stripeFeesUsd += fee / 100;
    const net = finite(row.net);
    if (net != null && row.status === "available") balanceAvailableNetCents += net;
    if (net != null && row.status === "pending") balancePendingNetCents += net;
    if (row.payout_id && !row.payout_status) stripePayoutsComplete = false;
    if (net != null && row.payout_status === "paid") paidPayoutNetCents += net;
  }

  return {
    period: { days: periodDays, start: new Date(startMs).toISOString(), end: new Date(nowMs).toISOString() },
    funnel: totals,
    attribution,
    subscription: {
      activeTrials,
      activePaidUsers: activePaidUids.size,
      grossMrrUsd: Number(grossMrrUsd.toFixed(2)),
    },
    retention: { d7: retention(7), d30: retention(30) },
    costs: {
      providerEstimatedUsd: providerCostRows > 0 && providerEstimateUnknownRows === 0
        ? Number(providerEstimatedKnownUsd.toFixed(6)) : null,
      providerEstimatedKnownUsd: Number(providerEstimatedKnownUsd.toFixed(6)),
      providerEstimateUnknownRows,
      providerEstimateComplete: providerCostRows > 0 && providerEstimateUnknownRows === 0,
      providerActualUsd: providerCostRows > 0 && providerActualComplete ? Number(providerActualUsd.toFixed(6)) : null,
      stripeFeesUsd: stripeFeesComplete ? Number(stripeFeesUsd.toFixed(2)) : null,
      hostingUsd: null,
      marketingUsd: null,
      netContributionUsd: null,
    },
    stripeCash: {
      paidInvoiceUsd: Number(paidInvoiceUsd.toFixed(2)),
      balanceAvailableNetUsd: Number((balanceAvailableNetCents / 100).toFixed(2)),
      balancePendingNetUsd: Number((balancePendingNetCents / 100).toFixed(2)),
      paidPayoutNetUsd: stripePayoutsComplete ? Number((paidPayoutNetCents / 100).toFixed(2)) : null,
    },
    metricDefinitions: {
      landingViews: "request count, not unique people",
      googleAuthenticatedUsers: "distinct Web uid in the period",
      firstPaidUsers: "distinct Web uid whose first-ever positive USD invoice occurred in the period",
      renewalInvoices: "positive USD invoices after the first-ever invoice, classified using retained invoice history",
      retention: "matured first-Travel cohort with a currently active paid Stripe subscription",
      balanceAvailableNetUsd: "Stripe balance transactions with status=available; this is not a bank payout receipt",
      balancePendingNetUsd: "Stripe balance transactions with status=pending",
      stripeFeesUsd: "fees on Web-linked charge/refund BalanceTransactions; other account-level or FX fees are not allocated",
      paidPayoutNetUsd: "net value of Web-linked balance transactions whose Stripe payout status is paid; bank receipt is not independently verified",
      providerActualUsd: "null when any provider usage row lacks an actual bill amount",
      netContributionUsd: "null until hosting, marketing, provider actuals, and settled Stripe fees are attributable",
    },
  };
}

module.exports = { buildWebFunnelReport };
