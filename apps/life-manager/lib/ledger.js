"use strict";

function headers(key, extra) {
  return Object.assign({ apikey: key, Authorization: `Bearer ${key}` }, extra || {});
}

// Best-effort cost persistence. Ledger failures must never break a call or scheduler tick.
async function recordCost({ uid, kind, quantity, unit, estUsd, meta } = {}, opts = {}) {
  const supaUrl = opts.supaUrl || process.env.SUPABASE_URL;
  const supaKey = opts.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY;
  const fetchImpl = opts.fetchImpl || globalThis.fetch;
  const log = opts.log || console.error;
  try {
    if (!supaUrl || !supaKey || !kind || typeof fetchImpl !== "function") {
      throw new Error("Supabase credentials or ledger kind missing");
    }
    const response = await fetchImpl(`${supaUrl}/rest/v1/lm_api_cost`, {
      method: "POST",
      headers: headers(supaKey, { "Content-Type": "application/json", Prefer: "return=minimal" }),
      body: JSON.stringify({
        uid: uid == null ? null : String(uid),
        kind: String(kind),
        quantity: Number(quantity) || 0,
        unit: unit == null ? null : String(unit),
        est_usd: opts.extendedFields && Object.hasOwn(opts.extendedFields, "est_usd")
          ? opts.extendedFields.est_usd : Number(estUsd) || 0,
        meta: meta == null ? {} : meta,
        ...(opts.extendedFields || {}),
      }),
    });
    if (!response.ok) throw new Error(`Supabase insert failed (${response.status})`);
    return true;
  } catch (error) {
    log("[ledger] recordCost failed", error && error.message ? error.message : error);
    return false;
  }
}

const BILLING_STATUSES = new Set(["estimated", "settled", "unknown", "not_applicable"]);
const SECRET_META_KEY = /(api[_-]?key|authorization|credential|password|secret|token)/i;

function providerDimension(value, name) {
  const text = String(value == null ? "" : value).trim();
  if (!text || text.length > 256 || /[\r\n]/.test(text)) throw new Error(`${name} is required`);
  return text;
}

function nullableAmount(value, name) {
  if (value == null || value === "") return null;
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) throw new Error(`${name} invalid`);
  return number;
}

function providerMeta(value) {
  const meta = value == null ? {} : value;
  if (!meta || typeof meta !== "object" || Array.isArray(meta)) throw new Error("meta must be an object");
  if (Object.keys(meta).some((key) => SECRET_META_KEY.test(key))) throw new Error("secret-shaped metadata key");
  return { ...meta };
}

async function recordProviderCost({
  uid, provider, product, sku, operation, quantity, unit,
  estimatedUsd = null, actualUsd = null, billingStatus = "unknown", pricingVersion = null,
  sourceReceiptRef, meta = {},
} = {}, opts = {}) {
  if (!BILLING_STATUSES.has(billingStatus)) throw new Error("billingStatus invalid");
  const amount = nullableAmount(actualUsd, "actualUsd");
  if (billingStatus === "settled" && amount === null) throw new Error("actualUsd required for settled billing");
  if (billingStatus !== "settled" && amount !== null) throw new Error("actualUsd only allowed for settled billing");
  const units = nullableAmount(quantity, "quantity");
  if (units === null) throw new Error("quantity required");
  const estimated = nullableAmount(estimatedUsd, "estimatedUsd");
  const fields = {
    provider: providerDimension(provider, "provider"), product: providerDimension(product, "product"),
    sku: providerDimension(sku, "sku"), operation: providerDimension(operation, "operation"),
    pricing_version: pricingVersion == null ? null : providerDimension(pricingVersion, "pricingVersion"),
    source_receipt_ref: providerDimension(sourceReceiptRef, "sourceReceiptRef"),
    actual_usd: amount, billing_status: billingStatus,
    est_usd: estimated,
  };
  return recordCost({ uid, kind: "provider_cost", quantity: units, unit, estUsd: estimated, meta: providerMeta(meta) }, {
    ...opts, extendedFields: fields,
  });
}

// DB-backed daily aggregation: every process/tick asks Supabase whether today's per-user row exists.
// No process-memory counter is authoritative, so restarts cannot create a fresh daily bucket.
async function recordDailyComposioPoll(uid, opts = {}) {
  const supaUrl = opts.supaUrl || process.env.SUPABASE_URL;
  const supaKey = opts.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY;
  const fetchImpl = opts.fetchImpl || globalThis.fetch;
  const log = opts.log || console.error;
  try {
    if (!supaUrl || !supaKey || !uid || typeof fetchImpl !== "function") {
      throw new Error("Supabase credentials or uid missing");
    }
    const now = new Date(opts.nowMs == null ? Date.now() : opts.nowMs);
    const dayStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
    const nextDay = new Date(dayStart.getTime() + 86400000);
    const query = [
      `uid=eq.${encodeURIComponent(uid)}`,
      "kind=eq.composio_poll",
      `ts=gte.${encodeURIComponent(dayStart.toISOString())}`,
      `ts=lt.${encodeURIComponent(nextDay.toISOString())}`,
      "select=id",
      "limit=1",
    ].join("&");
    const response = await fetchImpl(`${supaUrl}/rest/v1/lm_api_cost?${query}`, {
      headers: headers(supaKey),
    });
    if (!response.ok) throw new Error(`Supabase daily lookup failed (${response.status})`);
    const rows = await response.json().catch(() => []);
    if (Array.isArray(rows) && rows.length > 0) return false;
    return recordCost({
      uid, kind: "composio_poll", quantity: 1, unit: "day", estUsd: 0,
      meta: { day: dayStart.toISOString().slice(0, 10) },
    }, { supaUrl, supaKey, fetchImpl, log });
  } catch (error) {
    log("[ledger] composio daily aggregation failed", error && error.message ? error.message : error);
    return false;
  }
}

async function monthlyComposioCallCount(opts = {}) {
  const supaUrl = opts.supaUrl || process.env.SUPABASE_URL;
  const supaKey = opts.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY;
  const fetchImpl = opts.fetchImpl || globalThis.fetch;
  const log = opts.log || console.error;
  try {
    if (!supaUrl || !supaKey || typeof fetchImpl !== "function") return null;
    const now = new Date(opts.nowMs == null ? Date.now() : opts.nowMs);
    const monthStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
    const nextMonth = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1));
    const query = ["select=id", "kind=eq.composio_call",
      `ts=gte.${encodeURIComponent(monthStart.toISOString())}`,
      `ts=lt.${encodeURIComponent(nextMonth.toISOString())}`, "limit=1"].join("&");
    const response = await fetchImpl(`${supaUrl}/rest/v1/lm_api_cost?${query}`, {
      headers: headers(supaKey, { Prefer: "count=exact" }),
    });
    if (!response.ok) throw new Error(`Supabase monthly count failed (${response.status})`);
    const range = response.headers && response.headers.get("content-range");
    const match = String(range || "").match(/\/(\d+)$/);
    return match ? Number(match[1]) : 0;
  } catch (error) {
    log("[ledger] monthly Composio count failed", error && error.message ? error.message : error);
    return null;
  }
}

function finite(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function rounded(value) {
  return Number(value.toFixed(12));
}

// Pure rows -> JSON summary. `rows` and `nowMs` are injected; no DB, clock, or mutation occurs here.
function businessSummary(daysBack, rows, nowMs) {
  const days = Math.max(0, finite(daysBack));
  const now = finite(nowMs);
  const since = now - days * 86400000;
  const summary = { calls: 0, call_minutes: 0, est_cost_usd: 0, per_uid: {} };
  for (const row of Array.isArray(rows) ? rows : []) {
    const ts = Date.parse(row && row.ts);
    if (!Number.isFinite(ts) || ts < since || ts > now) continue;
    const uid = row.uid == null || row.uid === "" ? "unknown" : String(row.uid);
    const item = summary.per_uid[uid] || { calls: 0, call_minutes: 0, est_cost_usd: 0 };
    if (row.kind === "telnyx_call") {
      summary.calls += 1;
      item.calls += 1;
      summary.call_minutes += finite(row.quantity) / 60;
      item.call_minutes += finite(row.quantity) / 60;
    }
    summary.est_cost_usd += finite(row.est_usd);
    item.est_cost_usd += finite(row.est_usd);
    summary.per_uid[uid] = item;
  }
  summary.call_minutes = rounded(summary.call_minutes);
  summary.est_cost_usd = rounded(summary.est_cost_usd);
  for (const item of Object.values(summary.per_uid)) {
    item.call_minutes = rounded(item.call_minutes);
    item.est_cost_usd = rounded(item.est_cost_usd);
  }
  return summary;
}

module.exports = {
  BILLING_STATUSES, recordCost, recordProviderCost, recordDailyComposioPoll,
  monthlyComposioCallCount, businessSummary,
};
