"use strict";

const { createHmac } = require("node:crypto");

const GEOCODE_SUCCESS_TTL_MS = 24 * 60 * 60_000;

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

function makeSupabaseGeocodeStore({ supaUrl, supaKey, fetchImpl = global.fetch } = {}) {
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
        const response = await fetchImpl(`${base}/rest/v1/rpc/lm_geocode_cache_get`, {
          method: "POST", headers,
          body: JSON.stringify({
            p_uid: String(tenantId), p_provider: String(provider), p_address_digest: digest,
          }),
        });
        if (!response || response.ok !== true) return null;
        const rows = await response.json();
        const row = Array.isArray(rows) ? rows[0] : null;
        const value = row && { lat: row.lat, lon: row.lon };
        const computedAt = Date.parse(row && row.computed_at);
        const ttlMs = Number(row && row.ttl_secs) * 1000;
        if (!row || !isValidGeocode(value) || !Number.isFinite(computedAt)
            || ttlMs !== GEOCODE_SUCCESS_TTL_MS || Date.now() - computedAt >= ttlMs) return null;
        return { value, computedAt, ttlMs };
      } catch { return null; }
    },
    async set(tenantId, provider, address, value, computedAt = Date.now()) {
      const digest = digestFor(tenantId, provider, address);
      if (!base || !supaKey || !digest || !isValidGeocode(value) || typeof fetchImpl !== "function") return false;
      try {
        const response = await fetchImpl(`${base}/rest/v1/rpc/lm_geocode_cache_upsert`, {
          method: "POST",
          headers: { ...headers, Prefer: "return=minimal" },
          body: JSON.stringify({
            p_uid: String(tenantId), p_provider: String(provider), p_address_digest: digest,
            p_lat: value.lat, p_lon: value.lon,
            p_computed_at: new Date(computedAt).toISOString(),
            p_ttl_secs: GEOCODE_SUCCESS_TTL_MS / 1000,
          }),
        });
        return Boolean(response && response.ok === true);
      } catch { return false; }
    },
  };
}

module.exports = {
  GEOCODE_SUCCESS_TTL_MS, normalizeAddress, isValidGeocode, addressDigest, makeSupabaseGeocodeStore,
};
