"use strict";

const { createHmac, timingSafeEqual } = require("node:crypto");

const WEB_ATTRIBUTION_COOKIE = "lm-web-attribution";
const WEB_ATTRIBUTION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;
const WEB_ATTRIBUTION_TTL_MS = WEB_ATTRIBUTION_MAX_AGE_SECONDS * 1000;
const MAX_COOKIE_LENGTH = 2048;
const UTM_LIMITS = Object.freeze({
  utm_source: 120,
  utm_medium: 120,
  utm_campaign: 200,
  utm_content: 200,
  utm_term: 120,
});
const WEB_ATTRIBUTION_UTM_KEYS = Object.freeze(Object.keys(UTM_LIMITS));

function valuesFor(query, key) {
  if (query && typeof query.getAll === "function") return query.getAll(key);
  if (!query || typeof query !== "object" || !Object.prototype.hasOwnProperty.call(query, key)) return [];
  const value = query[key];
  return Array.isArray(value) ? value : [value];
}

function boundedFields(query) {
  const fields = {};
  for (const [key, maxBytes] of Object.entries(UTM_LIMITS)) {
    const values = valuesFor(query, key);
    if (values.length !== 1 || values[0] == null) continue;
    const value = String(values[0]).trim();
    if (!value || Buffer.byteLength(value, "utf8") > maxBytes) continue;
    fields[key] = value;
  }
  return fields;
}

function captureWebAttribution(query, secret, nowMs = Date.now()) {
  const key = String(secret || "");
  const timestamp = Number(nowMs);
  if (!key || !Number.isFinite(timestamp) || timestamp < 0) return null;
  const attribution = boundedFields(query);
  if (!Object.keys(attribution).length) return null;
  const payload = Buffer.from(JSON.stringify({
    v: 1,
    iat: Math.floor(timestamp),
    exp: Math.floor(timestamp) + WEB_ATTRIBUTION_TTL_MS,
    attribution,
  })).toString("base64url");
  const signature = createHmac("sha256", key)
    .update(`life-manager-web-attribution:v1\0${payload}`)
    .digest("hex");
  const cookie = `${payload}.${signature}`;
  return cookie.length <= MAX_COOKIE_LENGTH ? cookie : null;
}

function consumeWebAttribution(cookie, secret, nowMs = Date.now()) {
  const key = String(secret || "");
  const token = String(cookie || "");
  const timestamp = Number(nowMs);
  if (!key || !token || token.length > MAX_COOKIE_LENGTH || !Number.isFinite(timestamp) || timestamp < 0) return null;
  const match = /^([A-Za-z0-9_-]+)\.([a-f0-9]{64})$/.exec(token);
  if (!match) return null;
  const expected = createHmac("sha256", key)
    .update(`life-manager-web-attribution:v1\0${match[1]}`)
    .digest();
  const received = Buffer.from(match[2], "hex");
  if (received.length !== expected.length || !timingSafeEqual(received, expected)) return null;

  let payload;
  try { payload = JSON.parse(Buffer.from(match[1], "base64url").toString("utf8")); }
  catch { return null; }
  if (!payload || payload.v !== 1 || !Number.isSafeInteger(payload.iat) || !Number.isSafeInteger(payload.exp)
    || payload.exp !== payload.iat + WEB_ATTRIBUTION_TTL_MS || payload.iat > timestamp || payload.exp <= timestamp) {
    return null;
  }
  const attribution = boundedFields(payload.attribution);
  return Object.keys(attribution).length ? attribution : null;
}

module.exports = {
  WEB_ATTRIBUTION_COOKIE,
  WEB_ATTRIBUTION_MAX_AGE_SECONDS,
  WEB_ATTRIBUTION_UTM_KEYS,
  sanitizeWebAttribution: boundedFields,
  captureWebAttribution,
  consumeWebAttribution,
};
