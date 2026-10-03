"use strict";

const { createHash } = require("node:crypto");

const DEFAULT_TIMEOUT_MS = 5_000;
const DEFAULT_ATTRIBUTION_URL = "https://openpoiapi.com/attribution.html";

function uniqueStrings(values) {
  return [...new Set((Array.isArray(values) ? values : []).map((value) => String(value || "").trim()).filter(Boolean))].sort();
}

function supportedLicense(value) {
  return /(?:apache|bsd|cc\s*(?:by|0)|cdla|gpl|mit|odbl|odc|pdl|public\s+domain|unlicense)/iu.test(String(value || ""));
}

function precisionRank(value) {
  const ranks = { rooftop: 5, exact: 5, address: 4, street: 3, city: 2, coarse: 1, none: 0 };
  return ranks[String(value || "none").toLowerCase()] || 0;
}

function distanceMeters(aLat, aLon, bLat, bLon) {
  const rad = Math.PI / 180;
  const dLat = (bLat - aLat) * rad; const dLon = (bLon - aLon) * rad;
  const a = Math.sin(dLat / 2) ** 2
    + Math.cos(aLat * rad) * Math.cos(bLat * rad) * Math.sin(dLon / 2) ** 2;
  return 6371000 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(Math.max(0, 1 - a)));
}

function normalizeParsedResult(parsed, response, provider) {
  const value = parsed && typeof parsed === "object" ? parsed : {};
  const httpStatus = Number(response && response.status);
  if (httpStatus === 429 || value.status === "quota") return { status: "quota", errorClass: "quota" };
  if (Number.isFinite(httpStatus) && httpStatus >= 400) {
    return { status: httpStatus >= 500 ? "provider_5xx" : "provider_4xx", errorClass: `http_${httpStatus}` };
  }
  if (value.status === "no_result" || value.status === "ZERO_RESULTS" || value.status === "zero_results") {
    return { status: "no_result", precision: "none", errorClass: null };
  }
  const lat = Number(value.lat); const lon = Number(value.lon ?? value.lng);
  if (value.status === "fresh" || value.status === "OK" || (Number.isFinite(lat) && Number.isFinite(lon))) {
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return { status: "invalid", errorClass: "coordinates_missing" };
    const terms = provider && provider.terms && typeof provider.terms === "object" ? provider.terms : {};
    return {
      status: "fresh",
      lat,
      lon,
      precision: String(value.precision || "coarse"),
      attributionRefs: uniqueStrings(value.attributionRefs),
      licenseRefs: uniqueStrings(value.licenseRefs),
      termsAttributionRefs: uniqueStrings(terms.attributionRefs),
      termsLicenseRefs: uniqueStrings(terms.licenseRefs),
      errorClass: null,
    };
  }
  return { status: "invalid", precision: "none", errorClass: String(value.errorClass || "response_unrecognized") };
}

function rowFor({ item, provider, observedAt, releaseSha, latencyMs, result }) {
  const groundTruth = item && item.groundTruth;
  const distance = groundTruth && result.lat != null && result.lon != null
    ? distanceMeters(Number(groundTruth.lat), Number(groundTruth.lon), Number(result.lat), Number(result.lon)) : null;
  const accuracyStatus = groundTruth
    ? result.status === "fresh" && distance != null && distance <= Number(groundTruth.toleranceMeters || 0) ? "pass" : "fail"
    : null;
  return {
    caseId: String(item.caseId),
    provider: String(provider.name),
    status: result.status,
    precision: result.precision || "none",
    latencyMs: Math.max(0, Math.round(Number(latencyMs) || 0)),
    distanceMeters: distance == null ? null : Number(distance.toFixed(3)),
    accuracyStatus,
    attributionRefs: uniqueStrings(result.attributionRefs),
    licenseRefs: uniqueStrings(result.licenseRefs),
    termsAttributionRefs: uniqueStrings(result.termsAttributionRefs || provider.terms?.attributionRefs),
    termsLicenseRefs: uniqueStrings(result.termsLicenseRefs || provider.terms?.licenseRefs),
    errorClass: result.errorClass || null,
    observedAt,
    releaseSha,
  };
}

function digestRows(rows) {
  const stable = rows.map((row) => {
    const { latencyMs, ...withoutLatency } = row;
    return withoutLatency;
  });
  return createHash("sha256").update(JSON.stringify(stable)).digest("hex");
}

function summaryFor(rows) {
  const summary = { total: rows.length, fresh: 0, noResult: 0, timeout: 0, quota: 0, error: 0 };
  for (const row of rows) {
    if (row.status === "fresh") summary.fresh += 1;
    else if (row.status === "no_result") summary.noResult += 1;
    else if (row.status === "timeout") summary.timeout += 1;
    else if (row.status === "quota") summary.quota += 1;
    else summary.error += 1;
  }
  return summary;
}

function selectBenchmarkWinner(rows) {
  const grouped = new Map();
  for (const row of Array.isArray(rows) ? rows : []) {
    if (row && row.provider) (grouped.get(row.provider) || (grouped.set(row.provider, []), grouped.get(row.provider))).push(row);
  }
  const eligible = [];
  for (const [provider, providerRows] of grouped.entries()) {
    const measurable = providerRows.filter((row) => row.accuracyStatus != null);
    if (!measurable.length) continue;
    const fresh = measurable.filter((row) => row.status === "fresh");
    const sourceBacked = fresh.every((row) => Array.isArray(row.attributionRefs) && row.attributionRefs.length > 0
      && Array.isArray(row.licenseRefs) && row.licenseRefs.length > 0
      && row.licenseRefs.every(supportedLicense));
    const coverage = measurable.length ? fresh.length / measurable.length : 0;
    const accuracy = measurable.length ? measurable.filter((row) => row.accuracyStatus === "pass").length / measurable.length : 0;
    if (sourceBacked && coverage === 1 && accuracy === 1) eligible.push({ provider, coverage, accuracy });
  }
  if (!eligible.length) {
    return { decision: "no_winner", reason: grouped.size ? "provider_accuracy_or_coverage_below_threshold" : "no_source_backed_candidate" };
  }
  eligible.sort((a, b) => b.accuracy - a.accuracy || b.coverage - a.coverage || a.provider.localeCompare(b.provider));
  return { provider: eligible[0].provider, decision: "eligible_for_shadow", accuracy: eligible[0].accuracy, coverage: eligible[0].coverage };
}

async function withTimeout(task, timeoutMs) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(Object.assign(new Error("provider timeout"), { code: "ETIMEDOUT" })), timeoutMs);
  });
  try { return await Promise.race([Promise.resolve().then(task), timeout]); }
  finally { clearTimeout(timer); }
}

async function runGeocoderBenchmark({
  cases = [], providers = [], fetchImpl = globalThis.fetch, timeoutMs = DEFAULT_TIMEOUT_MS,
  now = () => new Date().toISOString(), releaseSha = process.env.LIFE_MANAGER_RELEASE_SHA || "unreleased",
} = {}) {
  const observedAt = String(now());
  const rows = [];
  for (const provider of Array.isArray(providers) ? providers : []) {
    for (const item of Array.isArray(cases) ? cases : []) {
      const started = Date.now();
      let result;
      try {
        if (typeof provider.buildRequest !== "function" || typeof fetchImpl !== "function") {
          result = { status: "unavailable", errorClass: "provider_not_configured" };
        } else {
          const request = provider.buildRequest(item) || {};
          const response = await withTimeout(() => fetchImpl(request.url, request.options), timeoutMs);
          const payload = response && typeof response.json === "function" ? await response.json() : null;
          const parsed = typeof provider.parse === "function" ? provider.parse(payload, response, item) : payload;
          result = normalizeParsedResult(parsed, response, provider);
        }
      } catch (error) {
        const timeout = error && (error.code === "ETIMEDOUT" || error.name === "TimeoutError");
        result = { status: timeout ? "timeout" : "network_error", errorClass: timeout ? "timeout" : "network_error" };
      }
      rows.push(rowFor({ item, provider, observedAt, releaseSha, latencyMs: Date.now() - started, result }));
    }
  }
  return {
    schemaVersion: 1,
    digest: digestRows(rows),
    rows,
    summary: summaryFor(rows),
    winner: selectBenchmarkWinner(rows),
  };
}

module.exports = {
  DEFAULT_ATTRIBUTION_URL,
  DEFAULT_TIMEOUT_MS,
  digestRows,
  normalizeParsedResult,
  runGeocoderBenchmark,
  selectBenchmarkWinner,
  supportedLicense,
};
