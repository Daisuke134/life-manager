"use strict";

const { isValidGeocode, normalizeAddress } = require("./geocode-cache.js");
const { isJapanGeo } = require("./transit.js");

const GSI_ENDPOINT = "https://msearch.gsi.go.jp/address-search/AddressSearch";
const OPENPOI_ENDPOINT = "https://api.openpoiapi.com/v1/suggest";
const GSI_TERMS_URL = "https://www.gsi.go.jp/kikakuchousei/kikakuchousei40182.html";
const GSI_SOURCE_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch";
const OPENPOI_ATTRIBUTION_URL = "https://openpoiapi.com/attribution.html";
const FREE_GEOCODE_TIMEOUT_MS = 2500;
const FREE_GEOCODE_SUCCESS_TTL_MS = 24 * 60 * 60_000;
const FREE_GEOCODE_FAILURE_TTL_MS = 2 * 60_000;
const JAPANESE_POI_SUFFIX = /(?:駅|寺|神社|ホテル|店|ビル|館|大学|空港|公園|美術館|博物館|病院|会館|役所|タワー|ヒカリエ)$/u;
const PRIVATE_HOME_HINT = /(?:自宅|実家|[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]{1,8}の家)/u;
const freeCache = new Map();
const freeInFlight = new Map();

function normalizeName(value) {
  return normalizeAddress(value).toLowerCase();
}

function isJapaneseText(value) {
  return /[\u3040-\u30ff\u3400-\u9fff]/u.test(String(value || ""));
}

function isJapaneseAddress(value) {
  const query = normalizeAddress(value);
  if (!query || !isJapaneseText(query)) return false;
  const compact = query.replace(/\s+/gu, "");
  if (/\d{3}-?\d{4}/u.test(query)) return true;
  if (/\d+\s*[-‐‑‒–—−－]\s*\d+/u.test(query)) return true;
  const number = "(?:\\d+|[〇零一二三四五六七八九十百千]+)";
  const addressMarker = new RegExp(`${number}\\s*(?:丁目|番地|番|号)(?=$|[\\s0-9０-９〇零一二三四五六七八九十百千‐‑‒–—−－、,\\-])`, "u");
  if (addressMarker.test(query)) return true;
  if (JAPANESE_POI_SUFFIX.test(compact)) return false;
  if (/^(?:北海道|東京都|(?:京都|大阪)府|[\u4e00-\u9fff]{2,3}県).*(?:市|区|町|村)/u.test(compact)) return true;
  return /^[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]{1,10}(?:市|区|町|村)(?:[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}0-9０-９]*)?$/u.test(compact);
}

function kanjiNumber(value) {
  const digit = { 〇: "0", 零: "0", 一: "1", 二: "2", 三: "3", 四: "4", 五: "5",
    六: "6", 七: "7", 八: "8", 九: "9" };
  let total = 0;
  let pending = "";
  for (const char of value) {
    if (Object.hasOwn(digit, char)) {
      pending += digit[char];
    } else if (char === "十" || char === "百" || char === "千") {
      const unit = char === "十" ? 10 : char === "百" ? 100 : 1000;
      total += Number(pending || "1") * unit;
      pending = "";
    }
  }
  return String(total + Number(pending || "0"));
}

function canonicalAddress(value) {
  return normalizeAddress(value)
    .replace(/[〇零一二三四五六七八九十百千]+/gu, kanjiNumber)
    .replace(/(\d+)丁目/gu, "$1-")
    .replace(/(\d+)(?:番地|番)/gu, "$1-")
    .replace(/(\d+)号/gu, "$1")
    .replace(/[‐‑‒–—−－]/gu, "-")
    .replace(/\s+/gu, "")
    .replace(/-+/gu, "-")
    .replace(/-$/u, "")
    .toLowerCase();
}

function preservesAddressPrecision(query, title) {
  const normalizedQuery = canonicalAddress(query);
  const normalizedTitle = canonicalAddress(title);
  if (!normalizedQuery || normalizedQuery !== normalizedTitle) return false;
  const queryNumbers = normalizedQuery.match(/\d+/gu) || [];
  const titleNumbers = normalizedTitle.match(/\d+/gu) || [];
  return queryNumbers.length === titleNumbers.length
    && queryNumbers.every((number, index) => number === titleNumbers[index]);
}

function providerForQuery(query) {
  const normalized = normalizeAddress(query).replace(/\s+/gu, "");
  if (PRIVATE_HOME_HINT.test(normalized)) return null;
  if (isJapaneseAddress(query)) return { provider: "gsi", operation: "AddressSearch" };
  if (isJapaneseText(normalized) && JAPANESE_POI_SUFFIX.test(normalized)) {
    return { provider: "openpoi", operation: "Suggest" };
  }
  return null;
}

function gsiFeatures(body) {
  return Array.isArray(body) ? body : (body && Array.isArray(body.features) ? body.features : null);
}

function suggestions(body) {
  if (Array.isArray(body)) return body;
  if (!body || typeof body !== "object") return null;
  for (const key of ["suggestions", "captured_suggestions", "results", "places"]) {
    if (Array.isArray(body[key])) return body[key];
  }
  if (body.data && typeof body.data === "object") {
    for (const key of ["suggestions", "results", "places"]) {
      if (Array.isArray(body.data[key])) return body.data[key];
    }
  }
  return null;
}

function hasCompleteProvenance(record) {
  return [record && record.licenses, record && record.attributions].every((values) =>
    Array.isArray(values) && values.length > 0
      && values.every((value) => typeof value === "string" && value.trim().length > 0));
}

function gsiCandidate(query, body) {
  const features = gsiFeatures(body);
  if (!features) return { candidate: null, failureClass: "invalid_response" };
  if (!features.length) return { candidate: null, failureClass: "no_results" };
  if (features.length !== 1 || body.truncated === true
      || (Number.isFinite(Number(body.count)) && Number(body.count) > features.length)) {
    return { candidate: null, failureClass: "ambiguous" };
  }
  const feature = features[0];
  const title = feature && feature.properties && feature.properties.title;
  if (typeof title !== "string" || !preservesAddressPrecision(query, title)) {
    return { candidate: null, failureClass: "precision_loss" };
  }
  const coordinates = feature && feature.geometry && feature.geometry.type === "Point"
    && feature.geometry.coordinates;
  if (!Array.isArray(coordinates) || coordinates.length !== 2
      || !coordinates.every((value) => typeof value === "number" && Number.isFinite(value))) {
    return { candidate: null, failureClass: "invalid_coordinates" };
  }
  const [lon, lat] = coordinates;
  const point = { lat, lon };
  if (!isValidGeocode(point)) return { candidate: null, failureClass: "invalid_coordinates" };
  if (!isJapanGeo(lat, lon)) return { candidate: null, failureClass: "outside_japan" };
  return {
    candidate: {
      ...point,
      provider: "gsi",
      operation: "AddressSearch",
      source: "国土地理院 AddressSearch",
      sourceRecord: {
        type: "Feature",
        ...(feature.properties && feature.properties.addressCode
          ? { addressCode: String(feature.properties.addressCode) } : {}),
      },
      licenses: ["国土地理院コンテンツ利用規約 / PDL1.0"],
      attributions: ["国土地理院ウェブサイト"],
      attributionUrl: GSI_TERMS_URL,
      sourceUrl: GSI_SOURCE_URL,
    },
    failureClass: null,
  };
}

function openPoiCandidate(query, body) {
  const records = suggestions(body);
  if (!records) return { candidate: null, failureClass: "invalid_response" };
  const exact = records.filter((record) => normalizeName(record && record.name) === normalizeName(query));
  if (!exact.length) return { candidate: null, failureClass: "no_results" };
  if (exact.length !== 1 || body.truncated === true
      || (Number.isFinite(Number(body.count)) && Number(body.count) > records.length)) {
    return { candidate: null, failureClass: "ambiguous" };
  }
  const record = exact[0];
  if (!hasCompleteProvenance(record)) return { candidate: null, failureClass: "missing_provenance" };
  if (record.licenses.some((license) => /Apache-2\.0/i.test(license))) {
    return { candidate: null, failureClass: "unsupported_license" };
  }
  const point = { lat: Number(record.lat), lon: Number(record.lng ?? record.lon) };
  if (!isValidGeocode(point)) return { candidate: null, failureClass: "invalid_coordinates" };
  if (!isJapanGeo(point.lat, point.lon)) return { candidate: null, failureClass: "outside_japan" };
  return {
    candidate: {
      ...point,
      provider: "openpoi",
      operation: "Suggest",
      source: String(record.source || "OpenPOI Suggest"),
      sourceRecord: {
        ...(record.source ? { source: record.source } : {}),
        ...(record.category ? { category: record.category } : {}),
        ...(record.business_type ? { business_type: record.business_type } : {}),
        ...(record.level !== undefined ? { level: record.level } : {}),
        licenses: record.licenses.slice(),
        attributions: record.attributions.slice(),
      },
      licenses: record.licenses.slice(),
      attributions: record.attributions.slice(),
      attributionUrl: OPENPOI_ATTRIBUTION_URL,
      sourceUrl: OPENPOI_ENDPOINT,
    },
    failureClass: null,
  };
}

async function notify(onObservation, observation) {
  if (typeof onObservation !== "function") return;
  try { await onObservation(observation); } catch { /* Usage recording must not break geocoding. */ }
}

async function fetchJson(fetchImpl, url, timeoutMs) {
  if (typeof fetchImpl !== "function") return { failureClass: "unavailable" };
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  let timer;
  const request = Promise.resolve().then(async () => {
    const response = await fetchImpl(url, controller ? { signal: controller.signal } : {});
    if (!response || response.ok !== true) {
      const status = Number(response && response.status);
      return { failureClass: Number.isFinite(status) && status >= 400 && status < 500 ? "provider_4xx"
        : Number.isFinite(status) && status >= 500 ? "provider_5xx" : "network" };
    }
    try { return { body: await response.json() }; }
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

function cacheKey(tenantId, provider, query) {
  return JSON.stringify([String(tenantId || "anonymous"), provider, normalizeAddress(query)]);
}

async function resolveFreeGeocode(query, {
  tenantId,
  fetchImpl = global.fetch,
  timeoutMs = FREE_GEOCODE_TIMEOUT_MS,
  now = Date.now,
  cache = freeCache,
  inFlight = freeInFlight,
  onObservation,
} = {}) {
  const scope = providerForQuery(query);
  if (!scope) return { attempted: false, candidate: null };
  const key = cacheKey(tenantId, scope.provider, query);
  const memo = cache.get(key);
  if (memo && now() - memo.computedAt < memo.ttlMs) {
    await notify(onObservation, {
      ...scope, outcome: "cache_hit", failureClass: memo.failureClass, providerUnits: 0,
    });
    return { attempted: true, ...scope, candidate: memo.candidate, failureClass: memo.failureClass };
  }
  if (memo) cache.delete(key);
  if (inFlight.has(key)) return inFlight.get(key);

  const run = (async () => {
    const url = new URL(scope.provider === "gsi" ? GSI_ENDPOINT : OPENPOI_ENDPOINT);
    url.searchParams.set("q", normalizeAddress(query));
    if (scope.provider === "openpoi") url.searchParams.set("limit", "5");
    const response = await fetchJson(fetchImpl, url, Math.max(0, Number(timeoutMs) || 0));
    const resolved = response.failureClass
      ? { candidate: null, failureClass: response.failureClass }
      : scope.provider === "gsi" ? gsiCandidate(query, response.body) : openPoiCandidate(query, response.body);
    await notify(onObservation, {
      ...scope,
      outcome: resolved.candidate ? "success" : "failure",
      failureClass: resolved.failureClass,
      providerUnits: 1,
    });
    const computedAt = now();
    cache.set(key, {
      candidate: resolved.candidate,
      failureClass: resolved.failureClass,
      computedAt,
      ttlMs: resolved.candidate ? FREE_GEOCODE_SUCCESS_TTL_MS : FREE_GEOCODE_FAILURE_TTL_MS,
    });
    return { attempted: true, ...scope, ...resolved };
  })();
  inFlight.set(key, run);
  try { return await run; }
  finally { if (inFlight.get(key) === run) inFlight.delete(key); }
}

module.exports = {
  FREE_GEOCODE_TIMEOUT_MS,
  FREE_GEOCODE_SUCCESS_TTL_MS,
  FREE_GEOCODE_FAILURE_TTL_MS,
  normalizeName,
  isJapaneseText,
  isJapaneseAddress,
  canonicalAddress,
  preservesAddressPrecision,
  resolveFreeGeocode,
};
