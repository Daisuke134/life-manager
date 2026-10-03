"use strict";

const { createHash } = require("node:crypto");

const DEFAULT_TIMEOUT_MS = 5_000;

function uniqueStrings(values) {
  return [...new Set((Array.isArray(values) ? values : []).map((value) => String(value || "").trim()).filter(Boolean))].sort();
}

function digestRows(rows) {
  const stable = rows.map((row) => {
    const { latencyMs, ...withoutLatency } = row;
    return withoutLatency;
  });
  return createHash("sha256").update(JSON.stringify(stable)).digest("hex");
}

function summaryFor(rows) {
  const summary = { total: rows.length, fresh: 0, noRoute: 0, stale: 0, timeout: 0, unsupported: 0, error: 0 };
  for (const row of rows) {
    if (row.routeStatus === "fresh") summary.fresh += 1;
    else if (row.routeStatus === "no_route") summary.noRoute += 1;
    else if (row.routeStatus === "stale") summary.stale += 1;
    else if (row.routeStatus === "timeout") summary.timeout += 1;
    else if (row.routeStatus === "unsupported") summary.unsupported += 1;
    else summary.error += 1;
  }
  return summary;
}

function normalizeResult(parsed, response) {
  const value = parsed && typeof parsed === "object" ? parsed : {};
  const httpStatus = Number(response && response.status);
  if (httpStatus === 429 || value.routeStatus === "quota") return { routeStatus: "quota", errorClass: "quota" };
  if (Number.isFinite(httpStatus) && httpStatus >= 400) {
    return { routeStatus: httpStatus >= 500 ? "provider_5xx" : "provider_4xx", errorClass: `http_${httpStatus}` };
  }
  const routeStatus = String(value.routeStatus || "error");
  if (routeStatus === "fresh") {
    const durationSeconds = Number(value.durationSeconds);
    return {
      routeStatus,
      durationSeconds: Number.isFinite(durationSeconds) && durationSeconds >= 0 ? durationSeconds : null,
      legCount: Number.isInteger(value.legCount) && value.legCount >= 0 ? value.legCount : null,
      farePresent: typeof value.farePresent === "boolean" ? value.farePresent : null,
      dataUpdatedAt: value.dataUpdatedAt ? String(value.dataUpdatedAt) : null,
      licenseRefs: uniqueStrings(value.licenseRefs),
      errorClass: null,
    };
  }
  if (["no_route", "stale", "unsupported", "quota"].includes(routeStatus)) {
    return { routeStatus, errorClass: value.errorClass ? String(value.errorClass) : null };
  }
  return { routeStatus: "error", errorClass: String(value.errorClass || "response_unrecognized") };
}

function rowFor({ item, provider, observedAt, releaseSha, latencyMs, result }) {
  return {
    caseId: String(item.caseId),
    provider: String(provider.name),
    mode: String(item.mode || provider.mode || "unknown"),
    routeStatus: result.routeStatus,
    durationSeconds: result.durationSeconds == null ? null : result.durationSeconds,
    legCount: result.legCount == null ? null : result.legCount,
    farePresent: result.farePresent == null ? null : result.farePresent,
    latencyMs: Math.max(0, Math.round(Number(latencyMs) || 0)),
    dataUpdatedAt: result.dataUpdatedAt || null,
    resourceCost: provider.resourceCost == null ? null : provider.resourceCost,
    licenseRefs: uniqueStrings(result.licenseRefs || provider.licenseRefs),
    errorClass: result.errorClass || null,
    observedAt,
    releaseSha,
    feedVersion: provider.feedVersion || null,
  };
}

async function withTimeout(task, timeoutMs) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(Object.assign(new Error("provider timeout"), { code: "ETIMEDOUT" })), timeoutMs);
  });
  try { return await Promise.race([Promise.resolve().then(task), timeout]); }
  finally { clearTimeout(timer); }
}

async function runRoutingBenchmark({
  cases = [], providers = [], fetchImpl = globalThis.fetch, timeoutMs = DEFAULT_TIMEOUT_MS,
  now = () => new Date().toISOString(), releaseSha = process.env.LIFE_MANAGER_RELEASE_SHA || "unreleased",
} = {}) {
  const observedAt = String(now());
  const rows = [];
  for (const provider of Array.isArray(providers) ? providers : []) {
    for (const item of Array.isArray(cases) ? cases : []) {
      const started = Date.now();
      let result;
      if (provider.mode && item.mode && provider.mode !== item.mode) {
        result = { routeStatus: "unsupported", errorClass: "mode_unsupported" };
      } else {
        try {
          if (typeof provider.buildRequest !== "function" || typeof fetchImpl !== "function") {
            result = { routeStatus: "unavailable", errorClass: "provider_not_configured" };
          } else {
            const request = provider.buildRequest(item) || {};
            if (!request.url) {
              result = { routeStatus: "unavailable", errorClass: "provider_not_configured" };
            } else {
              const response = await withTimeout(() => fetchImpl(request.url, request.options), timeoutMs);
              const payload = response && typeof response.json === "function" ? await response.json() : null;
              const parsed = typeof provider.parse === "function" ? provider.parse(payload, response, item) : payload;
              result = normalizeResult(parsed, response);
            }
          }
        } catch (error) {
          const timeout = error && (error.code === "ETIMEDOUT" || error.name === "TimeoutError");
          result = { routeStatus: timeout ? "timeout" : "network_error", errorClass: timeout ? "timeout" : "network_error" };
        }
      }
      rows.push(rowFor({ item, provider, observedAt, releaseSha, latencyMs: Date.now() - started, result }));
    }
  }
  return { schemaVersion: 1, digest: digestRows(rows), rows, summary: summaryFor(rows) };
}

module.exports = { DEFAULT_TIMEOUT_MS, digestRows, normalizeResult, runRoutingBenchmark };
