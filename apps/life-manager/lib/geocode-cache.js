"use strict";

const crypto = require("node:crypto");

function normalizeGeocodeAddress(value) {
  return String(value == null ? "" : value).normalize("NFKC").trim().replace(/\s+/g, " ");
}

function addressKey(value) {
  return crypto.createHash("sha256").update(normalizeGeocodeAddress(value).toLowerCase()).digest("hex");
}

function headers(key) {
  return { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json" };
}

function createSupabaseGeocodeStore({ supaUrl, supaKey, fetchImpl = globalThis.fetch } = {}) {
  const base = String(supaUrl || "").replace(/\/+$/, "");
  return Object.freeze({
    async get(address) {
      const normalized = normalizeGeocodeAddress(address);
      if (!base || !supaKey || !normalized || typeof fetchImpl !== "function") return null;
      try {
        const key = addressKey(normalized);
        const response = await fetchImpl(`${base}/rest/v1/lm_geocode_cache?address_key=eq.${key}`
          + "&select=lat,lon,provider,status,computed_at,ttl_secs&limit=1", { headers: headers(supaKey) });
        if (!response || response.ok !== true) return null;
        const rows = await response.json();
        const row = Array.isArray(rows) ? rows[0] : null;
        const computedAt = Date.parse(row && row.computed_at);
        const ttlMs = Number(row && row.ttl_secs) * 1000;
        if (!row || !Number.isFinite(computedAt) || !Number.isFinite(ttlMs)
          || Date.now() - computedAt >= ttlMs) return null;
        if (row.status === "negative") return null;
        if (row.status !== "success") return null;
        const lat = Number(row.lat); const lon = Number(row.lon);
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return null;
        return { lat, lon, provider: String(row.provider || "unknown") };
      } catch { return null; }
    },
    async put(address, value = {}) {
      const normalized = normalizeGeocodeAddress(address);
      if (!base || !supaKey || !normalized || typeof fetchImpl !== "function") return false;
      const payload = value || {};
      const negative = value == null || payload.status === "negative";
      const lat = Number(payload.lat); const lon = Number(payload.lon);
      if (!negative && (!Number.isFinite(lat) || !Number.isFinite(lon))) return false;
      const ttlMs = Number.isFinite(Number(payload.ttlMs)) ? Math.max(1, Number(payload.ttlMs)) : 86_400_000;
      const computedAt = payload.computedAt ? new Date(payload.computedAt) : new Date();
      if (!Number.isFinite(computedAt.getTime())) return false;
      const body = {
        address_key: addressKey(normalized), lat: negative ? null : lat, lon: negative ? null : lon,
        provider: String(payload.provider || "unknown"), status: negative ? "negative" : "success",
        computed_at: computedAt.toISOString(), ttl_secs: Math.round(ttlMs / 1000),
      };
      try {
        const response = await fetchImpl(`${base}/rest/v1/lm_geocode_cache?on_conflict=address_key`, {
          method: "POST", headers: { ...headers(supaKey), Prefer: "resolution=merge-duplicates,return=minimal" },
          body: JSON.stringify(body),
        });
        return Boolean(response && response.ok === true);
      } catch { return false; }
    },
  });
}

module.exports = { addressKey, createSupabaseGeocodeStore, normalizeGeocodeAddress };
