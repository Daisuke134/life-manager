"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { inspectTelegramLiveLocation, MAX_LIVE_LOCATION_AGE_MS } = require("./live-location.js");

const NOW = Date.parse("2026-10-09T12:00:00.000Z");
const fresh = (overrides = {}) => ({
  latitude: 35.681236,
  longitude: 139.767125,
  observed_at: new Date(NOW - 1000).toISOString(),
  expires_at: new Date(NOW + 60_000).toISOString(),
  ...overrides,
});

test("Telegram live location accepts the exact 120-second boundary and rejects older fixes", () => {
  const atBoundary = fresh({ observed_at: new Date(NOW - MAX_LIVE_LOCATION_AGE_MS).toISOString() });
  assert.equal(inspectTelegramLiveLocation(atBoundary, NOW).fresh, true);

  const stale = fresh({ observed_at: new Date(NOW - MAX_LIVE_LOCATION_AGE_MS - 1).toISOString() });
  assert.deepEqual(inspectTelegramLiveLocation(stale, NOW), { fresh: false, reason: "stale" });
});

test("Telegram live location rejects future, expired, and out-of-range fixes", () => {
  assert.deepEqual(inspectTelegramLiveLocation(fresh({ observed_at: new Date(NOW + 1).toISOString() }), NOW), {
    fresh: false, reason: "future",
  });
  assert.deepEqual(inspectTelegramLiveLocation(fresh({ expires_at: new Date(NOW).toISOString() }), NOW), {
    fresh: false, reason: "expired",
  });
  assert.deepEqual(inspectTelegramLiveLocation(fresh({ latitude: 91 }), NOW), {
    fresh: false, reason: "invalid",
  });
  assert.deepEqual(inspectTelegramLiveLocation(fresh({ latitude: null }), NOW), {
    fresh: false, reason: "invalid",
  });
  assert.deepEqual(inspectTelegramLiveLocation(fresh({ longitude: -181 }), NOW), {
    fresh: false, reason: "invalid",
  });
});
