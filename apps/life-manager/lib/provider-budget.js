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

function evaluateProviderBudget({ measuredUsd = 0, estimatedUsd = 0, unknownCount = 0, thresholds = {} } = {}) {
  const totalUsd = Math.max(0, finite(measuredUsd)) + Math.max(0, finite(estimatedUsd));
  const warningUsd = Math.max(0, finite(thresholds.warningUsd ?? thresholds.warning ?? 1));
  const degradedUsd = Math.max(warningUsd, finite(thresholds.degradedUsd ?? thresholds.degraded ?? warningUsd * 1.25));
  const stoppedUsd = Math.max(degradedUsd, finite(thresholds.stoppedUsd ?? thresholds.stopped ?? degradedUsd * 1.25));
  const unknown = Math.max(0, Math.floor(finite(unknownCount)));
  const reasons = [];
  if (unknown > 0) reasons.push("unknown_cost");
  let state = "normal";
  if (totalUsd >= stoppedUsd) { state = "stopped"; reasons.push("stopped_threshold"); }
  else if (totalUsd >= degradedUsd) { state = "degraded"; reasons.push("degraded_threshold"); }
  else if (totalUsd >= warningUsd) { state = "warning"; reasons.push("warning_threshold"); }
  else if (unknown > 0) state = "degraded";
  return { state, totalUsd, measuredUsd: Math.max(0, finite(measuredUsd)), estimatedUsd: Math.max(0, finite(estimatedUsd)), unknownCount: unknown, reasons };
}

function authorizeProviderOperation({ tenantId, provider, operation, essential = false, cacheHit = false } = {}, deps = {}) {
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
  const reason = cacheHit ? "cache_hit"
    : state === "stopped" ? "budget_stopped"
      : state === "degraded" && !essential ? "budget_degraded"
        : "allowed";
  const allowed = reason === "cache_hit" || reason === "allowed";
  if (typeof deps.record === "function") {
    try { deps.record({ tenantId: tenant, provider: name, operation: String(operation || "unknown"), state, allowed, reason, cacheHit }); } catch { /* observability is best effort */ }
  }
  return { allowed, state, reason };
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

module.exports = { authorizeProviderOperation, evaluateProviderBudget, summarizeProviderBudget };
