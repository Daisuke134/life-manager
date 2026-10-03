"use strict";

const { defaultProviderCaps } = require("./provider-budget.js");

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const TENANT_ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const LANE_DEFINITIONS = Object.freeze({
  poi: Object.freeze({ feature: "places_search", primary: ["openpoi"], capKey: "google_maps:places_search" }),
  transit: Object.freeze({ feature: "travel_route", primary: ["transit_api"], capKey: "google_maps:route" }),
  geocoder: Object.freeze({ feature: "geocoding", primary: ["geocoder_cache", "openpoi"], capKey: "google_maps:geocode" }),
});

function requiredText(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!text) throw new Error(`${label} is required`);
  return text;
}

function finite(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : fallback;
}

function reportingPeriodBounds(reportingDate) {
  const date = requiredText(reportingDate, "provider lane reporting date");
  if (!DATE.test(date)) throw new Error("provider lane reporting date invalid");
  const start = new Date(`${date}T00:00:00+09:00`);
  if (!Number.isFinite(start.getTime())) throw new Error("provider lane reporting date invalid");
  const end = new Date(start.getTime() + 24 * 60 * 60 * 1000);
  return { start: start.toISOString(), end: end.toISOString() };
}

function rowTimestamp(row) {
  const value = row?.last_observed_at || row?.usage_day || row?.observed_at;
  const parsed = Date.parse(String(value || ""));
  return Number.isFinite(parsed) ? parsed : null;
}

function normalizeRow(row) {
  if (!row || typeof row !== "object" || Array.isArray(row)) return null;
  const provider = String(row.provider || "").trim();
  const feature = String(row.feature || "").trim();
  const outcome = String(row.outcome || "").trim();
  if (!provider || !feature || !outcome) return null;
  const numericFields = ["event_count", "provider_units", "estimated_cost_usd"];
  const numericInvalid = numericFields.some((key) => row[key] == null
    || !Number.isFinite(Number(row[key])) || Number(row[key]) < 0)
    || row.unknown_count == null
    || !Number.isFinite(Number(row.unknown_count)) || Number(row.unknown_count) < 0;
  return {
    provider,
    feature,
    outcome,
    eventCount: Math.max(0, Math.floor(finite(row.event_count, 0))),
    providerUnits: finite(row.provider_units, 0),
    estimatedUsd: finite(row.estimated_cost_usd, 0),
    unknownCount: numericInvalid ? null : Math.max(0, Math.floor(Number(row.unknown_count))),
    numericInvalid,
    cacheHit: row.cache_hit === true || outcome === "cache_hit",
    observedAt: rowTimestamp(row),
  };
}

function laneFromRows(name, rows, definition, bounds, caps) {
  const matching = rows.filter((row) => row.feature === definition.feature);
  const fallbackRows = matching.filter((row) => row.provider === "google_maps" && !row.cacheHit);
  const fallbackCalls = fallbackRows.reduce((sum, row) => sum + row.providerUnits, 0);
  const eventCount = matching.reduce((sum, row) => sum + row.eventCount, 0);
  const providerUnits = matching.reduce((sum, row) => sum + row.providerUnits, 0);
  const estimatedUsd = matching.reduce((sum, row) => sum + row.estimatedUsd, 0);
  const unknownCount = matching.reduce((sum, row) => sum + (row.unknownCount || 0), 0);
  const periodStart = Date.parse(bounds.start);
  const periodEnd = Date.parse(bounds.end);
  const inPeriod = matching.filter((row) => row.observedAt != null
    // lm_usage_cost_summary groups at UTC midnight; accept a bucket when its 24h
    // interval overlaps the requested JST reporting day.
    && row.observedAt < periodEnd && row.observedAt + 24 * 60 * 60 * 1000 > periodStart);
  const successful = inPeriod.filter((row) => row.outcome === "success" || row.cacheHit);
  const primaryRow = successful.find((row) => definition.primary.includes(row.provider));
  const cacheRow = successful.find((row) => row.cacheHit);
  const primary = primaryRow?.provider || (cacheRow ? "cache" : null);
  const failures = [];
  if (matching.length === 0) failures.push(`provider_lane_readback_missing:${name}`);
  else if (inPeriod.length === 0) failures.push(`provider_lane_readback_stale:${name}`);
  else if (successful.length === 0) failures.push(`provider_lane_no_success:${name}`);
  if (matching.some((row) => row.numericInvalid)) failures.push(`provider_lane_numeric_invalid:${name}`);
  if (matching.some((row) => row.unknownCount == null)) failures.push(`provider_lane_unknown_cost:${name}`);
  if (!primaryRow && !cacheRow) failures.push(`provider_lane_primary_missing:${name}`);
  const cap = caps[definition.capKey] || {};
  return {
    lane: {
      status: failures.length ? "partial" : "fresh",
      primary,
      fallbackCalls,
      fallbackCap: finite(cap.monthlyUnits, 0),
      eventCount,
      providerUnits,
      estimatedUsd: Number(estimatedUsd.toFixed(12)),
      unknownCount,
    },
    failures,
  };
}

function normalizeProviderLanes(rawRows, { reportingDate, nowMs = Date.now() } = {}) {
  const bounds = reportingPeriodBounds(reportingDate);
  const rows = (Array.isArray(rawRows) ? rawRows : []).map(normalizeRow).filter(Boolean);
  const caps = defaultProviderCaps();
  const lanes = {};
  const failures = [];
  for (const [name, definition] of Object.entries(LANE_DEFINITIONS)) {
    const result = laneFromRows(name, rows, definition, bounds, caps);
    lanes[name] = result.lane;
    failures.push(...result.failures);
  }
  const now = Number(nowMs);
  if (!Number.isFinite(now)) throw new Error("provider lane clock invalid");
  return Object.freeze({
    schemaVersion: 1,
    status: failures.length ? "partial" : "fresh",
    observedAt: new Date(now).toISOString(),
    reportingDate: String(reportingDate),
    lanes: Object.freeze(lanes),
    failures: Object.freeze([...new Set(failures)].sort()),
  });
}

async function readProviderLanes({
  supaUrl, supaKey, tenantId, reportingDate, nowMs = Date.now(), fetchImpl = globalThis.fetch,
} = {}) {
  const base = requiredText(supaUrl, "provider lane Supabase URL").replace(/\/+$/, "");
  const key = requiredText(supaKey, "provider lane Supabase key");
  const tenant = requiredText(tenantId, "provider lane tenant");
  if (!TENANT_ID.test(tenant)) throw new Error("provider lane tenant invalid");
  if (typeof fetchImpl !== "function") throw new Error("provider lane fetch unavailable");
  const bounds = reportingPeriodBounds(reportingDate);
  const response = await fetchImpl(`${base}/rest/v1/rpc/lm_provider_lane_summary`, {
    method: "POST",
    headers: { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({ p_period_start: bounds.start, p_period_end: bounds.end, p_tenant_id: tenant }),
  });
  if (!response || response.ok !== true) throw new Error("provider lane readback failed");
  const rows = await response.json();
  if (!Array.isArray(rows)) throw new Error("provider lane readback failed");
  if (rows.some((row) => String(row?.tenant_id || "") !== tenant)) {
    throw new Error("provider lane tenant mismatch");
  }
  return normalizeProviderLanes(rows, { reportingDate, nowMs });
}

module.exports = { LANE_DEFINITIONS, normalizeProviderLanes, readProviderLanes, reportingPeriodBounds };
