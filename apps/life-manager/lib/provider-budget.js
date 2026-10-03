"use strict";

function finite(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function nullableFinite(value) {
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

const DEFAULT_PROVIDER_CAPS = Object.freeze({
  "google_maps:places_search": Object.freeze({ dailyUsd: 0.5, monthlyUsd: 5, monthlyUnits: 100 }),
  "google_maps:route": Object.freeze({ dailyUsd: 0.5, monthlyUsd: 5, monthlyUnits: 100 }),
  "google_maps:geocode": Object.freeze({ dailyUsd: 0.5, monthlyUsd: 5, monthlyUnits: 200 }),
  "gemini:nonessential": Object.freeze({ monthlyUsd: 5 }),
});

function defaultProviderCaps() {
  return Object.fromEntries(Object.entries(DEFAULT_PROVIDER_CAPS).map(([key, value]) => [key, { ...value }]));
}

function providerCapKey(provider, operation, essential) {
  if (String(provider) === "gemini" && !essential) return "gemini:nonessential";
  return `${String(provider || "")}:${String(operation || "")}`;
}

function evaluateProviderBudget({ measuredUsd = 0, estimatedUsd = 0, unknownCount = 0, units = 0, thresholds = {}, caps = null, period = "monthly" } = {}) {
  const totalUsd = Math.max(0, finite(measuredUsd)) + Math.max(0, finite(estimatedUsd));
  const warningUsd = Math.max(0, finite(thresholds.warningUsd ?? thresholds.warning ?? 1));
  const degradedUsd = Math.max(warningUsd, finite(thresholds.degradedUsd ?? thresholds.degraded ?? warningUsd * 1.25));
  const stoppedUsd = Math.max(degradedUsd, finite(thresholds.stoppedUsd ?? thresholds.stopped ?? degradedUsd * 1.25));
  const unknown = Math.max(0, Math.floor(finite(unknownCount)));
  const totalUnits = Math.max(0, finite(units));
  const reasons = [];
  if (unknown > 0) reasons.push("unknown_cost");
  let state = "normal";
  if (totalUsd >= stoppedUsd) { state = "stopped"; reasons.push("stopped_threshold"); }
  else if (totalUsd >= degradedUsd) { state = "degraded"; reasons.push("degraded_threshold"); }
  else if (totalUsd >= warningUsd) { state = "warning"; reasons.push("warning_threshold"); }
  else if (unknown > 0) state = "degraded";
  const cap = caps && typeof caps === "object" ? caps : null;
  const capUsd = cap && cap[`${period}Usd`] != null ? Math.max(0, finite(cap[`${period}Usd`])) : null;
  const capUnits = cap && cap[`${period}Units`] != null ? Math.max(0, finite(cap[`${period}Units`])) : null;
  const capExceeded = (capUsd != null && totalUsd >= capUsd) || (capUnits != null && totalUnits >= capUnits);
  if (capExceeded) { state = "stopped"; reasons.push("cap_exceeded"); }
  const result = {
    state, totalUsd, measuredUsd: Math.max(0, finite(measuredUsd)), estimatedUsd: Math.max(0, finite(estimatedUsd)),
    unknownCount: unknown, reasons,
  };
  if (cap) result.cap = { period, usd: capUsd, units: capUnits, totalUnits };
  return result;
}

function authorizeProviderOperation({ tenantId, provider, operation, essential = false, cacheHit = false,
  estimatedUsd = 0, providerUnits = 0, period = "monthly" } = {}, deps = {}) {
  const tenant = String(tenantId || "").trim();
  const name = String(provider || "").trim();
  if (!tenant || !name) return { allowed: false, state: "stopped", reason: "budget_identity_missing" };
  let state = "normal";
  try {
    state = typeof deps.getState === "function" ? deps.getState(tenant, name)
      : deps.states instanceof Map ? deps.states.get(`${tenant}:${name}`)
        : deps.state || "normal";
  } catch { state = "stopped"; }
  state = ["normal", "warning", "degraded", "stopped"].includes(state) ? state : "degraded";
  const capInput = Object.hasOwn(arguments[0] || {}, "estimatedUsd") || Object.hasOwn(arguments[0] || {}, "providerUnits")
    || deps.caps != null || typeof deps.getUsage === "function";
  const capKey = providerCapKey(name, operation, essential);
  const capDefinitions = deps.caps || defaultProviderCaps();
  const capDefinition = capDefinitions[capKey] || null;
  const usage = typeof deps.getUsage === "function"
    ? (deps.getUsage(tenant, name, operation, period) || {}) : {};
  const capBudget = capInput && capDefinition
    ? evaluateProviderBudget({
      measuredUsd: usage.measuredUsd ?? usage.actualUsd ?? 0,
      estimatedUsd: finite(usage.estimatedUsd ?? usage.estUsd) + Math.max(0, finite(estimatedUsd)),
      unknownCount: usage.unknownCount || 0,
      units: finite(usage.units ?? usage.quantity) + Math.max(0, finite(providerUnits)),
      caps: capDefinition, period,
    }) : null;
  const reason = cacheHit ? "cache_hit"
    : capBudget && capBudget.state === "stopped" ? "cap_exceeded"
    : state === "stopped" ? "budget_stopped"
      : state === "degraded" && !essential ? "budget_degraded"
      : "allowed";
  const allowed = reason === "cache_hit" || reason === "allowed";
  const nextAction = reason === "cache_hit" ? "read_cache"
    : reason === "cap_exceeded" || reason === "budget_stopped" ? "use_cache_or_stop"
      : reason === "budget_degraded" ? "reduce_or_cache" : "continue";
  if (typeof deps.record === "function") {
    try {
      deps.record({ tenantId: tenant, provider: name, operation: String(operation || "unknown"), state,
        allowed, reason, cacheHit, capKey, capState: capBudget?.state || state,
        nextAction, providerUnits: Math.max(0, finite(providerUnits)), estimatedUsd: Math.max(0, finite(estimatedUsd)),
        actualStatus: "unknown" });
    } catch { /* observability is best effort */ }
  }
  if (!capInput) return { allowed, state, reason };
  return { allowed, state, reason, capKey, capState: capBudget?.state || state, nextAction };
}

function summarizeProviderBudget(rows, { since = null, now = new Date() } = {}) {
  const end = Date.parse(now);
  const start = since == null ? -Infinity : Date.parse(since);
  let eventCount = 0; let providerUnits = 0; let cacheHits = 0;
  let estimatedUsd = 0; let settledUsd = 0; let unknownCount = 0; let lastObservedAt = null;
  for (const row of Array.isArray(rows) ? rows : []) {
    const parsed = Date.parse(row && row.ts);
    if (!Number.isFinite(parsed) || parsed < start || parsed > end) continue;
    eventCount += 1;
    providerUnits += Math.max(0, finite(row.units ?? row.quantity));
    if (row.cacheHit === true || row.cache_hit === true) cacheHits += 1;
    const estimate = nullableFinite(row.estimatedUsd ?? row.est_usd);
    const actual = nullableFinite(row.actualUsd ?? row.actual_usd);
    if (estimate !== null) estimatedUsd += Math.max(0, estimate);
    if (actual !== null) settledUsd += Math.max(0, actual);
    if (estimate === null && actual === null && !row.cacheHit && !row.cache_hit) unknownCount += 1;
    const iso = new Date(parsed).toISOString();
    if (!lastObservedAt || iso > lastObservedAt) lastObservedAt = iso;
  }
  return {
    eventCount, providerUnits, cacheHits,
    estimatedUsd: Number(estimatedUsd.toFixed(12)), settledUsd: Number(settledUsd.toFixed(12)),
    unknownCount, lastObservedAt,
  };
}

function periodBounds(nowMs, period) {
  const now = new Date(nowMs == null ? Date.now() : nowMs);
  if (!Number.isFinite(now.getTime())) throw new Error("budget clock invalid");
  const start = period === "daily"
    ? new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))
    : new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
  const end = period === "daily"
    ? new Date(start.getTime() + 86400000)
    : new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1));
  return { start: start.toISOString(), end: end.toISOString() };
}

async function readProviderBudgetSummary({ supaUrl, supaKey, fetchImpl, tenantId, provider, period, nowMs }) {
  const base = String(supaUrl || "").replace(/\/+$/, "");
  if (!base || !supaKey || typeof fetchImpl !== "function") throw new Error("budget_store_unconfigured");
  const bounds = periodBounds(nowMs, period);
  const response = await fetchImpl(`${base}/rest/v1/rpc/lm_provider_budget_summary`, {
    method: "POST",
    headers: { apikey: supaKey, Authorization: `Bearer ${supaKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({ p_period_start: bounds.start, p_period_end: bounds.end, p_tenant_id: String(tenantId) }),
  });
  if (!response || response.ok !== true) throw new Error("budget_store_read_failed");
  const rows = await response.json();
  if (!Array.isArray(rows)) throw new Error("budget_store_malformed");
  for (const row of rows) {
    if (!row || typeof row !== "object" || String(row.tenant_id || "") !== String(tenantId)) {
      throw new Error("budget_store_tenant_mismatch");
    }
    for (const field of ["provider_units", "estimated_cost_usd", "unknown_count"]) {
      const value = Number(row[field]);
      if (!Number.isFinite(value) || value < 0) throw new Error("budget_store_malformed");
    }
  }
  const matching = rows.filter((row) => String(row.provider || "") === String(provider || ""));
  return matching.reduce((sum, row) => ({
    estimatedUsd: sum.estimatedUsd + Math.max(0, finite(row.estimated_cost_usd)),
    units: sum.units + Math.max(0, finite(row.provider_units)),
    unknownCount: sum.unknownCount + Math.max(0, finite(row.unknown_count)),
  }), { estimatedUsd: 0, units: 0, unknownCount: 0 });
}

function createSupabaseProviderBudgetAuthorizer({ supaUrl, supaKey, fetchImpl = globalThis.fetch, nowMs = Date.now } = {}) {
  return async (input = {}) => {
    const tenantId = String(input.tenantId || "").trim();
    if (input.cacheHit === true) {
      return authorizeProviderOperation(input, { state: "degraded", caps: defaultProviderCaps() });
    }
    if (!tenantId) return { allowed: false, state: "stopped", reason: "budget_identity_missing", nextAction: "use_cache_or_stop" };
    try {
      const [daily, monthly] = await Promise.all([
        readProviderBudgetSummary({ supaUrl, supaKey, fetchImpl, tenantId, provider: input.provider, period: "daily", nowMs }),
        readProviderBudgetSummary({ supaUrl, supaKey, fetchImpl, tenantId, provider: input.provider, period: "monthly", nowMs }),
      ]);
      // A missing provider row is a legitimate zero usage snapshot, not an implicit billing receipt.
      const caps = defaultProviderCaps();
      const monthlyDecision = authorizeProviderOperation({ ...input, period: "monthly" }, {
        state: "normal", caps, getUsage: () => monthly,
      });
      if (monthlyDecision.allowed !== true) return monthlyDecision;
      const dailyDecision = authorizeProviderOperation({ ...input, period: "daily" }, {
        state: "normal", caps, getUsage: () => daily,
      });
      if (dailyDecision.allowed !== true) return dailyDecision;
      return { ...monthlyDecision, dailyCapState: dailyDecision.capState || dailyDecision.state };
    } catch {
      const capKey = providerCapKey(input.provider, input.operation, input.essential === true);
      return { allowed: false, state: "degraded", reason: "budget_read_failed", capKey, capState: "degraded", nextAction: "use_cache_or_stop" };
    }
  };
}

module.exports = {
  authorizeProviderOperation, createSupabaseProviderBudgetAuthorizer, defaultProviderCaps,
  evaluateProviderBudget, summarizeProviderBudget,
};
