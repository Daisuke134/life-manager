"use strict";

function headers(key, extra) {
  return Object.assign({ apikey: key, Authorization: `Bearer ${key}` }, extra || {});
}

const BILLING_STATUSES = new Set(["estimated", "settled", "unknown", "not_applicable"]);
const SAFE_LOG_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const SAFE_PRICING_VERSION = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$/;
const SAFE_LOG_KIND = /^[A-Za-z][A-Za-z0-9_.:-]{0,63}$/;
const SECRET_LOG_VALUE = /(?:token|secret|password|credential|api.?key)\s*[=:]|auth\.json|sk-[A-Za-z0-9_-]{16,}/i;
const PHONE_SHAPED = /^\+?\d{9,15}$/;

function finiteNonNegativeOrNull(value) {
  if (value == null || (typeof value === "string" && value.trim() === "")) return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function safeLogId(value) {
  return typeof value === "string" && SAFE_LOG_ID.test(value)
    && !SECRET_LOG_VALUE.test(value) && !PHONE_SHAPED.test(value)
    ? value : null;
}

function safeLogKind(value) {
  return typeof value === "string" && SAFE_LOG_KIND.test(value)
    && !SECRET_LOG_VALUE.test(value) && !PHONE_SHAPED.test(value) ? value : "unknown";
}

function normalizedCostMeta(kind, estUsd, suppliedMeta) {
  const source = suppliedMeta && typeof suppliedMeta === "object" && !Array.isArray(suppliedMeta)
    ? suppliedMeta : {};
  const cacheHit = source.cache_hit === true;
  let billingStatus = cacheHit ? "not_applicable"
    : (BILLING_STATUSES.has(source.billing_status) ? source.billing_status
      : (estUsd == null || estUsd === 0 ? "unknown" : "estimated"));
  let actualUsd = cacheHit ? 0 : finiteNonNegativeOrNull(source.actual_usd);
  if (billingStatus === "settled" && actualUsd == null) billingStatus = "unknown";
  if (billingStatus === "estimated" && estUsd == null) billingStatus = "unknown";
  if (billingStatus === "not_applicable" && actualUsd == null) actualUsd = 0;
  const estimateStatus = cacheHit || billingStatus === "not_applicable" ? "not_applicable"
    : (estUsd == null || source.estimate_status === "unavailable"
      || (estUsd === 0 && billingStatus === "unknown" && source.estimate_status !== "estimated")
      ? "unavailable" : "estimated");
  if (estimateStatus === "unavailable" && billingStatus === "estimated") billingStatus = "unknown";
  const pricingVersion = typeof source.pricing_version === "string"
    && SAFE_PRICING_VERSION.test(source.pricing_version) ? source.pricing_version : null;
  const provider = typeof source.provider === "string" ? source.provider : null;
  const sku = typeof source.sku === "string" ? source.sku : null;
  const currency = typeof source.currency === "string" && /^[A-Z]{3}$/.test(source.currency)
    ? source.currency : "USD";

  return {
    ...source,
    provider,
    sku,
    operation: typeof source.operation === "string" && source.operation.trim()
      ? source.operation : String(kind),
    currency,
    actual_usd: actualUsd,
    billing_status: billingStatus,
    pricing_version: pricingVersion,
    estimate_status: estimateStatus,
  };
}

function costWriteFailure({ status, requestStarted, supaUrl, supaKey, kind, meta }) {
  const trace = meta && meta.runtime_trace && typeof meta.runtime_trace === "object"
    ? meta.runtime_trace : {};
  const httpStatus = Number.isInteger(status) ? status : null;
  const knownNoEffect = !requestStarted || (httpStatus != null && httpStatus >= 400 && httpStatus < 500);
  const missingConfig = !supaUrl || !supaKey || !kind;
  const errorClass = missingConfig ? "configuration_missing"
    : httpStatus == null ? "fetch_error"
      : httpStatus >= 500 ? "supabase_http_5xx" : "supabase_http_4xx";
  return {
    event: "lm_api_cost_write_failed",
    kind: safeLogKind(kind),
    loop_id: safeLogId(trace.loop_id),
    owner_id: safeLogId(trace.owner_id),
    run_id: safeLogId(trace.run_id),
    occurrence_id: safeLogId(trace.occurrence_id),
    release_sha: typeof trace.release_sha === "string"
      && /^[a-f0-9]{40}(?:[a-f0-9]{24})?$/.test(trace.release_sha) ? trace.release_sha : null,
    phase: "cost_ledger_write",
    command: "supabase_post_lm_api_cost",
    loaded_env: {
      SUPABASE_URL: Boolean(supaUrl),
      SUPABASE_SERVICE_ROLE_KEY: Boolean(supaKey),
    },
    exit_code: httpStatus,
    effect: knownNoEffect ? "known_no_effect" : "effect_unknown",
    readback: "not_attempted",
    provider_receipt_id: safeLogId(meta && meta.provider_receipt_id),
    evidence_refs: [],
    error_class: errorClass,
    retryable: false,
    next_action: missingConfig ? "restore_supabase_configuration"
      : knownNoEffect ? "fix_cost_row_or_acl_before_retry" : "readback_before_retry",
  };
}

// Best-effort cost persistence. Ledger failures must never break a call or scheduler tick.
async function recordCost({ uid, kind, quantity, unit, estUsd, meta } = {}, opts = {}) {
  const supaUrl = opts.supaUrl || process.env.SUPABASE_URL;
  const supaKey = opts.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY;
  const fetchImpl = opts.fetchImpl || globalThis.fetch;
  const log = opts.log || console.error;
  let requestStarted = false;
  let status = null;
  let rowMeta = {};
  const normalizedQuantity = finiteNonNegativeOrNull(quantity);
  const normalizedEstimate = finiteNonNegativeOrNull(estUsd);
  try {
    if (!supaUrl || !supaKey || !kind || typeof fetchImpl !== "function") {
      throw new Error("Supabase credentials or ledger kind missing");
    }
    rowMeta = normalizedCostMeta(kind, normalizedEstimate, meta);
    const body = JSON.stringify({
      uid: uid == null ? null : String(uid),
      kind: String(kind),
      quantity: normalizedQuantity,
      unit: unit == null ? null : String(unit),
      est_usd: rowMeta.estimate_status === "unavailable" ? null : normalizedEstimate,
      meta: rowMeta,
    });
    requestStarted = true;
    const response = await fetchImpl(`${supaUrl}/rest/v1/lm_api_cost`, {
      method: "POST",
      headers: headers(supaKey, { "Content-Type": "application/json", Prefer: "return=minimal" }),
      body,
    });
    if (!response.ok) {
      status = Number(response.status) || null;
      throw new Error("Supabase insert failed");
    }
    return true;
  } catch (error) {
    log(JSON.stringify(costWriteFailure({
      status, requestStarted, supaUrl, supaKey, kind, meta: rowMeta.meta || meta,
    })));
    return false;
  }
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
      uid, kind: "composio_poll", quantity: 1, unit: "day", estUsd: null,
      meta: { provider: "composio", operation: "daily_usage_poll", day: dayStart.toISOString().slice(0, 10) },
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

module.exports = { recordCost, recordDailyComposioPoll, monthlyComposioCallCount, businessSummary };
