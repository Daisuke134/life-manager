"use strict";

const { createHmac } = require("node:crypto");

const GEOCODE_SUCCESS_TTL_MS = 24 * 60 * 60_000;
const GEOCODE_CACHE_RPC_TIMEOUT_MS = 1500;

function normalizeAddress(address) {
  return String(address == null ? "" : address).normalize("NFKC").trim().replace(/\s+/g, " ");
}

function isValidGeocode(value) {
  return Boolean(value && Number.isFinite(value.lat) && value.lat >= -90 && value.lat <= 90
    && Number.isFinite(value.lon) && value.lon >= -180 && value.lon <= 180);
}

function addressDigest({ tenantId, provider, address, digestKey }) {
  const normalized = normalizeAddress(address);
  if (!normalized || !digestKey) return null;
  return createHmac("sha256", String(digestKey))
    .update(JSON.stringify([String(tenantId || ""), String(provider || ""), normalized]))
    .digest("hex");
}

async function boundedRpc(fetchImpl, url, init, timeoutMs) {
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  let timer;
  const request = Promise.resolve().then(async () => {
    const response = await fetchImpl(url, controller ? { ...init, signal: controller.signal } : init);
    if (!response || response.ok !== true) {
      const status = Number(response && response.status);
      return { failureClass: Number.isFinite(status) && status >= 400 && status < 500 ? "provider_4xx"
        : Number.isFinite(status) && status >= 500 ? "provider_5xx" : "network" };
    }
    if (typeof response.json !== "function") return { response };
    try { return { response, body: await response.json() }; }
    catch { return { failureClass: "invalid_response" }; }
  }).catch(() => ({ failureClass: "network" }));
  const timeout = new Promise((resolve) => {
    timer = setTimeout(() => {
      if (controller) controller.abort();
      resolve({ failureClass: "timeout" });
    }, timeoutMs);
  });
  try { return await Promise.race([request, timeout]); }
  finally { clearTimeout(timer); }
}

async function notify(onObservation, observation) {
  if (typeof onObservation !== "function") return;
  try { await onObservation(observation); } catch { /* Cache telemetry is best-effort. */ }
}

function makeSupabaseGeocodeStore({
  supaUrl, supaKey, fetchImpl = global.fetch,
  timeoutMs = GEOCODE_CACHE_RPC_TIMEOUT_MS, onObservation,
} = {}) {
  const requestTimeoutMs = Number.isFinite(Number(timeoutMs)) && Number(timeoutMs) >= 0
    ? Number(timeoutMs) : GEOCODE_CACHE_RPC_TIMEOUT_MS;
  const base = String(supaUrl || "").replace(/\/$/, "");
  const headers = {
    apikey: String(supaKey || ""),
    Authorization: `Bearer ${String(supaKey || "")}`,
    "Content-Type": "application/json",
  };
  const digestFor = (tenantId, provider, address) => addressDigest({
    tenantId, provider, address, digestKey: supaKey,
  });

  return {
    digestFor,
    async get(tenantId, provider, address) {
      const digest = digestFor(tenantId, provider, address);
      if (!base || !supaKey || !digest || typeof fetchImpl !== "function") return null;
      try {
        const result = await boundedRpc(fetchImpl, `${base}/rest/v1/rpc/lm_geocode_cache_get`, {
          method: "POST", headers,
          body: JSON.stringify({
            p_uid: String(tenantId), p_provider: String(provider), p_address_digest: digest,
          }),
        }, requestTimeoutMs);
        if (result.failureClass) {
          await notify(onObservation, {
            operation: "lm_geocode_cache_get", outcome: "failure", result: "failure",
            failureClass: result.failureClass, providerUnits: 1,
          });
          return null;
        }
        const rows = result.body;
        const row = Array.isArray(rows) ? rows[0] : null;
        const value = row && { lat: row.lat, lon: row.lon };
        const computedAt = Date.parse(row && row.computed_at);
        const ttlMs = Number(row && row.ttl_secs) * 1000;
        if (!row || !isValidGeocode(value) || !Number.isFinite(computedAt)
            || ttlMs !== GEOCODE_SUCCESS_TTL_MS || Date.now() - computedAt >= ttlMs) {
          return null;
        }
        return { value, computedAt, ttlMs };
      } catch {
        await notify(onObservation, {
          operation: "lm_geocode_cache_get", outcome: "failure", result: "failure",
          failureClass: "network", providerUnits: 1,
        });
        return null;
      }
    },
    async set(tenantId, provider, address, value, computedAt = Date.now()) {
      const digest = digestFor(tenantId, provider, address);
      if (!base || !supaKey || !digest || !isValidGeocode(value) || typeof fetchImpl !== "function") return false;
      try {
        const result = await boundedRpc(fetchImpl, `${base}/rest/v1/rpc/lm_geocode_cache_upsert`, {
          method: "POST",
          headers: { ...headers, Prefer: "return=minimal" },
          body: JSON.stringify({
            p_uid: String(tenantId), p_provider: String(provider), p_address_digest: digest,
            p_lat: value.lat, p_lon: value.lon,
            p_computed_at: new Date(computedAt).toISOString(),
            p_ttl_secs: GEOCODE_SUCCESS_TTL_MS / 1000,
          }),
        }, requestTimeoutMs);
        const ok = !result.failureClass && Boolean(result.response && result.response.ok === true);
        if (!ok) await notify(onObservation, {
          operation: "lm_geocode_cache_upsert", outcome: "failure", result: "failure",
          failureClass: result.failureClass || "network", providerUnits: 1,
        });
        return ok;
      } catch {
        await notify(onObservation, {
          operation: "lm_geocode_cache_upsert", outcome: "failure", result: "failure",
          failureClass: "network", providerUnits: 1,
        });
        return false;
      }
    },
  };
}

module.exports = {
  GEOCODE_SUCCESS_TTL_MS, GEOCODE_CACHE_RPC_TIMEOUT_MS,
  normalizeAddress, isValidGeocode, addressDigest, makeSupabaseGeocodeStore,
};
