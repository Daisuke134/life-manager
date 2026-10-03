"use strict";

const OPENPOI_BASE_URL = "https://api.openpoiapi.com";
const OPENPOI_ATTRIBUTION_URL = "https://openpoiapi.com/attribution.html";

function mapCandidate(row) {
  const lat = Number(row && row.lat); const lon = Number(row && row.lng);
  if (!row || !String(row.name || "").trim() || !Number.isFinite(lat) || !Number.isFinite(lon)) return null;
  return {
    name: String(row.name), address: String(row.address || ""), lat, lon,
    category: row.category == null ? null : String(row.category),
    source: row.source == null ? null : String(row.source),
    licenses: Array.isArray(row.licenses) ? row.licenses.map(String) : [],
    attributions: Array.isArray(row.attributions) ? row.attributions.map(String) : [],
  };
}

async function searchOpenPoi(query, {
  center = null, radius = 50_000, limit = 10, fetchImpl = globalThis.fetch,
  baseUrl = OPENPOI_BASE_URL,
} = {}) {
  const params = new URLSearchParams();
  if (String(query || "").trim()) params.set("q", String(query).trim());
  if (center && Number.isFinite(Number(center.lng)) && Number.isFinite(Number(center.lat))) {
    params.set("center", `${Number(center.lng)},${Number(center.lat)}`);
    params.set("radius", String(Math.max(1, Math.round(Number(radius) || 50_000))));
  }
  params.set("limit", String(Math.min(200, Math.max(1, Math.round(Number(limit) || 10)))));
  const observedAt = new Date().toISOString();
  if (typeof fetchImpl !== "function") {
    return { status: "unavailable", candidates: [], attributions: [], attributionUrl: OPENPOI_ATTRIBUTION_URL, observedAt };
  }
  try {
    const response = await fetchImpl(`${String(baseUrl).replace(/\/+$/, "")}/v1/search?${params}`);
    if (!response || response.ok === false) {
      return { status: "unavailable", candidates: [], attributions: [], attributionUrl: OPENPOI_ATTRIBUTION_URL, observedAt };
    }
    const payload = await response.json();
    const candidates = (Array.isArray(payload && payload.results) ? payload.results : [])
      .map(mapCandidate).filter(Boolean);
    const attributions = [...new Set(candidates.flatMap((candidate) => candidate.attributions))].sort();
    return { status: "fresh", candidates, attributions, attributionUrl: OPENPOI_ATTRIBUTION_URL, observedAt };
  } catch {
    return { status: "unavailable", candidates: [], attributions: [], attributionUrl: OPENPOI_ATTRIBUTION_URL, observedAt };
  }
}

module.exports = { OPENPOI_ATTRIBUTION_URL, OPENPOI_BASE_URL, mapCandidate, searchOpenPoi };
