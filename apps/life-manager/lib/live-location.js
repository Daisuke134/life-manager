"use strict";

const MAX_LIVE_LOCATION_AGE_MS = 120_000;

function timestampMs(value) {
  if (value instanceof Date) return value.getTime();
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim()) {
    const parsed = Date.parse(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function inspectTelegramLiveLocation(location, nowValue = Date.now()) {
  if (!location || typeof location !== "object") return { fresh: false, reason: "missing" };
  const rawLatitude = location.latitude;
  const rawLongitude = location.longitude;
  if (rawLatitude == null || rawLongitude == null
    || (typeof rawLatitude === "string" && !rawLatitude.trim())
    || (typeof rawLongitude === "string" && !rawLongitude.trim())) return { fresh: false, reason: "invalid" };
  const latitude = Number(location.latitude);
  const longitude = Number(location.longitude);
  const observedAt = timestampMs(location.observedAtMs ?? location.observedAt ?? location.observed_at);
  const expiresAt = timestampMs(location.expiresAtMs ?? location.expiresAt ?? location.expires_at);
  const nowMs = timestampMs(nowValue);
  if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90
    || !Number.isFinite(longitude) || longitude < -180 || longitude > 180
    || observedAt === null || expiresAt === null || nowMs === null
    || expiresAt <= observedAt) return { fresh: false, reason: "invalid" };
  if (observedAt > nowMs) return { fresh: false, reason: "future" };
  if (expiresAt <= nowMs) return { fresh: false, reason: "expired" };
  if (nowMs - observedAt > MAX_LIVE_LOCATION_AGE_MS) return { fresh: false, reason: "stale" };
  return { fresh: true, latitude, longitude, observedAt, expiresAt };
}

module.exports = { MAX_LIVE_LOCATION_AGE_MS, inspectTelegramLiveLocation };
