// lib/travel-transit-wire.test.js — C2/C3 WIRE (integration into travel.js). directionsMinutes must
// try the FREE JP transit path first (geocode src/dst → JP bbox → api.transit.ls8h.com /plan, cached),
// and fall back to Google only when transit doesn't resolve. Uses injected seams (no network).
"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const travel = require("./travel.js");
const { makeRouteCache } = require("./route-cache.js");
const freshCache = () => makeRouteCache({ store: new Map(), ttlMs: 600000 });

const NOW = Date.parse("2026-08-26T00:00:00Z");
const EVENT_START = Date.parse("2026-08-27T18:30:00+09:00");
const EVENT_END = Date.parse("2026-08-27T20:00:00+09:00");

test("directionsRoute keeps the measured 25-second default Transit budget", () => {
  assert.equal(travel.DEFAULT_TRANSIT_TIMEOUT_MS, 25_000);
});

test("geocodeAddress reads persistent cache before any paid Google request", async () => {
  const originalFetch = global.fetch;
  let calls = 0;
  global.fetch = async () => { calls += 1; throw new Error("Google geocode must not run"); };
  try {
    const value = await travel.geocodeAddress("東京都 渋谷区", "mapsKey", {
      options: { _geocodeStore: { get: async () => ({ lat: 35.6, lon: 139.7, provider: "openpoi" }) } },
    });
    assert.deepEqual(value, { lat: 35.6, lon: 139.7, provider: "openpoi" });
    assert.equal(calls, 0);
  } finally { global.fetch = originalFetch; }
});

test("Google route fallback is denied by provider budget after cache miss", async () => {
  let googleCalls = 0;
  const route = await travel.directionsRoute("geo:35.681,139.767", "geo:35.659,139.700", "mapsKey", EVENT_START, NOW, false, {
    _transitFetch: async () => ({ date: "20260827", timezone: "Asia/Tokyo", journeys: [] }),
    _directionsMinutesGoogle: async () => { googleCalls += 1; return 30; },
    _authorizeProviderOperation: async () => ({ allowed: false, state: "stopped", reason: "budget_stopped" }),
    _routeCache: freshCache(),
  });
  assert.equal(route, null);
  assert.equal(googleCalls, 0);
});

test("parseGeoLiteral accepts only finite in-range coordinate literals", () => {
  assert.deepEqual(travel.parseGeoLiteral("geo:35.681,139.767"), { lat: 35.681, lon: 139.767 });
  for (const value of [
    " geo:35.681,139.767", "geo:35.681, 139.767", "geo:35.681,139.767 ",
    "geo:35.681", "geo:35.681,", "geo:NaN,139.767", "geo:Infinity,139.767",
    "geo:91,139.767", "geo:-91,139.767", "geo:35.681,181", "geo:35.681,-181", "geo:0x10,139.767",
  ]) assert.equal(travel.parseGeoLiteral(value), null, `untrusted literal: ${value}`);
});

// A fake geocoder: JP addresses → JP geo; "NYC" → non-JP geo; "" → null.
const fakeGeocode = async (addr) => {
  if (!addr) return null;
  if (addr.includes("NYC")) return { lat: 40.73, lon: -73.93 };
  return { lat: 35.681, lon: 139.767 }; // any JP-ish address
};
// A fake transit fetch returning the committed fixture shape (17-min 中央線快速).
const fakeTransitFetch = async (_src, _dst, query = {}) => ({
  date: query.date || "20260827",
  timezone: query.timezone || "Asia/Tokyo",
  journeys: [{
    departureSecs: (() => {
      const [h, m] = String(query.time || "18:00").split(":").map(Number);
      const anchor = (h * 3600) + (m * 60);
      return query.type === "departure" ? anchor + 60 : anchor - 1029;
    })(),
    arrivalSecs: (() => {
      const [h, m] = String(query.time || "18:00").split(":").map(Number);
      const anchor = (h * 3600) + (m * 60);
      return query.type === "departure" ? anchor + 1089 : anchor;
    })(),
    durationSecs: 1029, transferCount: 0, legs: [{ mode: "rail", routeName: "中央線快速" }],
  }],
});

test("directionsRoute: JP query is anchored to event wall time and accepted transit skips Google", async () => {
  const originalFetch = global.fetch;
  let transitUrl = "";
  let googleCalled = false;
  global.fetch = async (url) => {
    transitUrl = String(url);
    return { ok: true, json: async () => fakeTransitFetch(null, null, { date: "20260827", time: "18:30", type: "arrival" }) };
  };
  try {
    const route = await travel.directionsRoute("新宿区A", "渋谷区B", "mapsKey", EVENT_START, NOW, false, {
      timezone: "Asia/Tokyo",
      _geocode: fakeGeocode,
      _directionsMinutesGoogle: async () => { googleCalled = true; return 45; },
      _routeCache: freshCache(),
    });
    const query = new URL(transitUrl).searchParams;
    assert.equal(query.get("date"), "20260827");
    assert.equal(query.get("time"), "18:30");
    assert.equal(query.get("type"), "arrival");
    assert.equal(query.get("numItineraries"), "3");
    assert.equal(route.provider, "transit");
    assert.equal(route.durationSeconds, 1029);
    assert.equal(googleCalled, false);
  } finally { global.fetch = originalFetch; }
});

test("directionsRoute: valid live geo origin bypasses geocoding while the address destination is geocoded once", async () => {
  const geocoded = [];
  let transitEndpoints = null;
  const route = await travel.directionsRoute("geo:35.681,139.767", "渋谷区B", "mapsKey", EVENT_START, NOW, false, {
    timezone: "Asia/Tokyo",
    _geocode: async (address) => {
      geocoded.push(address);
      return { lat: 35.659, lon: 139.700 };
    },
    _transitFetch: async (from, to, query) => {
      transitEndpoints = { from, to, query };
      return fakeTransitFetch(from, to, query);
    },
    _routeCache: freshCache(),
  });
  assert.deepEqual(geocoded, ["渋谷区B"]);
  assert.deepEqual(transitEndpoints.from, { lat: 35.681, lon: 139.767 });
  assert.deepEqual(transitEndpoints.to, { lat: 35.659, lon: 139.700 });
  assert.equal(route.provider, "transit");
  assert.equal(route.durationSeconds, 1029);
});

test("directionsRoute: non-JP live geo selects Google with a provider-safe coordinate", async () => {
  const geocoded = [];
  const googleArgs = [];
  const route = await travel.directionsRoute("geo:40.730,-73.930", "NYC place", "mapsKey", EVENT_START, NOW, false, {
    _geocode: async (address) => {
      geocoded.push(address);
      return { lat: 40.7128, lon: -74.0060 };
    },
    _directionsMinutesGoogle: async (...args) => { googleArgs.push(args); return 45; },
    _routeCache: freshCache(),
  });
  assert.deepEqual(geocoded, ["NYC place"]);
  assert.equal(googleArgs.length, 1);
  assert.deepEqual(googleArgs[0].slice(0, 2), ["40.73,-73.93", "NYC place"]);
  assert.equal(route.provider, "google");
  assert.equal(route.durationSeconds, 45 * 60);
});

test("directionsRoute: unusable JP Transit falls back once with a provider-safe geo coordinate", async () => {
  let transitCalls = 0;
  const googleArgs = [];
  const route = await travel.directionsRoute("geo:35.681,139.767", "渋谷区B", "mapsKey", EVENT_START, NOW, false, {
    timezone: "Asia/Tokyo",
    _geocode: async () => ({ lat: 35.659, lon: 139.700 }),
    _transitFetch: async () => { transitCalls++; return { date: "20260827", timezone: "Asia/Tokyo", journeys: [] }; },
    _directionsMinutesGoogle: async (...args) => { googleArgs.push(args); return 30; },
    _routeCache: freshCache(),
  });
  assert.equal(transitCalls, 1);
  assert.equal(googleArgs.length, 1);
  assert.deepEqual(googleArgs[0].slice(0, 2), ["35.681,139.767", "渋谷区B"]);
  assert.equal(route.provider, "google");
  assert.equal(route.durationSeconds, 30 * 60);
});

test("directionsRoute: return query uses event end wall time and departure type", async () => {
  const originalFetch = global.fetch;
  let transitUrl = "";
  global.fetch = async (url) => {
    transitUrl = String(url);
    return { ok: true, json: async () => fakeTransitFetch(null, null, { date: "20260827", time: "20:00", type: "departure" }) };
  };
  try {
    const route = await travel.directionsRoute("新宿区A", "渋谷区B", "mapsKey", EVENT_END, NOW, true, {
      timezone: "Asia/Tokyo",
      _geocode: fakeGeocode,
      _routeCache: freshCache(),
    });
    const query = new URL(transitUrl).searchParams;
    assert.equal(query.get("date"), "20260827");
    assert.equal(query.get("time"), "20:00");
    assert.equal(query.get("type"), "departure");
    assert.equal(query.get("numItineraries"), "3");
    assert.equal(route.provider, "transit");
  } finally { global.fetch = originalFetch; }
});

test("directionsMinutes: structured transit duration remains a minutes compatibility adapter", async () => {
  let googleCalled = false;
  const mins = await travel.directionsMinutes("新宿区A", "渋谷区B", "mapsKey", EVENT_START, NOW, false, {
    timezone: "Asia/Tokyo",
    _geocode: fakeGeocode,
    _transitFetch: fakeTransitFetch,
    _directionsMinutesGoogle: async () => { googleCalled = true; return 45; },
    _routeCache: freshCache(),
  });
  assert.equal(mins, 17);
  assert.equal(googleCalled, false);
});

test("directionsRoute: non-JP dst → falls back to Google", async () => {
  let googleCalled = false;
  const route = await travel.directionsRoute("新宿区A", "NYC place", "mapsKey", EVENT_START, NOW, false, {
    _geocode: fakeGeocode,
    _transitFetch: async () => { throw new Error("transit must not run outside JP"); },
    _directionsMinutesGoogle: async () => { googleCalled = true; return 45; },
    _routeCache: freshCache(),
  });
  assert.equal(googleCalled, true);
  assert.equal(route.provider, "google");
  assert.equal(route.durationSeconds, 45 * 60);
});

test("directionsRoute: unusable Transit output makes exactly one sequential Google fallback", async () => {
  const calls = [];
  const route = await travel.directionsRoute("新宿区A", "渋谷区B", "mapsKey", EVENT_START, NOW, false, {
    timezone: "Asia/Tokyo",
    _geocode: fakeGeocode,
    _transitFetch: async () => { calls.push("transit"); return { date: "20260827", timezone: "Asia/Tokyo", journeys: [] }; },
    _directionsMinutesGoogle: async () => { calls.push("google"); return 30; },
    _routeCache: freshCache(),
  });
  assert.deepEqual(calls, ["transit", "google"]);
  assert.equal(route.provider, "google");
  assert.equal(route.durationSeconds, 30 * 60);
});

test("directionsMinutes: repeated ticks (same event) call the provider ONCE — FIND-002 cache", async () => {
  let transitCalls = 0;
  const cache = freshCache();
  const opts = {
    timezone: "Asia/Tokyo",
    _geocode: fakeGeocode,
    _transitFetch: async (...args) => { transitCalls++; return fakeTransitFetch(...args); },
    _directionsMinutesGoogle: async () => 45,
    _routeCache: cache,
  };
  const at = EVENT_START; // ev.startMs is CONSTANT across the 60s ticks
  await travel.directionsMinutes("新宿区A", "渋谷区B", "k", at, NOW, false, opts);
  await travel.directionsMinutes("新宿区A", "渋谷区B", "k", at, NOW + 60000, false, opts); // next tick, same event
  assert.equal(transitCalls, 1); // second tick is a cache hit
});

test("directionsRoute: missing anchor uses explicit now wall time", async () => {
  let querySeen = null;
  const route = await travel.directionsRoute("新宿区A", "渋谷区B", "k", undefined, NOW, false, {
    timezone: "Asia/Tokyo",
    _geocode: fakeGeocode,
    _transitFetch: async (_src, _dst, query) => {
      querySeen = query;
      return fakeTransitFetch(_src, _dst, query);
    },
    _routeCache: freshCache(),
  });
  assert.equal(querySeen.date, "20260826");
  assert.equal(querySeen.time, "09:00");
  assert.equal(querySeen.type, "arrival");
  assert.equal(route.provider, "transit");
});

test("directionsRoute: a never-settling Transit injection times out and falls back once", async () => {
  let googleCalls = 0;
  const timeoutSentinel = Symbol("transit-timeout");
  const routePromise = travel.directionsRoute("新宿区A", "渋谷区B", "k", EVENT_START, NOW, false, {
    timezone: "Asia/Tokyo",
    _geocode: fakeGeocode,
    _transitFetch: () => new Promise(() => {}),
    _transitTimeoutMs: 5,
    _directionsMinutesGoogle: async () => { googleCalls++; return 30; },
    _routeCache: freshCache(),
  });
  const route = await Promise.race([
    routePromise,
    new Promise((resolve) => setTimeout(() => resolve(timeoutSentinel), 50)),
  ]);
  assert.notEqual(route, timeoutSentinel, "Transit timeout must settle instead of waiting forever");
  assert.equal(route.provider, "google");
  assert.equal(googleCalls, 1);
});

test("transitFetchPlan: timeout aborts the real fetch and structured fallback makes one Google HTTP request", async () => {
  const originalFetch = global.fetch;
  const requests = [];
  let transitSignal = null;
  global.fetch = async (url, options = {}) => {
    const requestUrl = String(url);
    requests.push(requestUrl);
    if (requestUrl.includes("api.transit.ls8h.com")) {
      transitSignal = options.signal;
      return new Promise(() => {});
    }
    if (requestUrl.includes("maps.googleapis.com/maps/api/directions")) {
      return { ok: true, json: async () => ({ status: "OK", routes: [{ legs: [{ duration: { value: 1200 } }] }] }) };
    }
    if (requestUrl.includes("routes.googleapis.com")) {
      return { ok: true, json: async () => ({ routes: [{ duration: "2700s" }] }) };
    }
    throw new Error("unexpected url " + requestUrl);
  };
  try {
    const timeoutSentinel = Symbol("transit-fetch-timeout");
    const route = await Promise.race([
      travel.directionsRoute("新宿区A", "渋谷区B", "k", EVENT_START, NOW, false, {
        timezone: "Asia/Tokyo",
        _geocode: fakeGeocode,
        _transitTimeoutMs: 5,
        _routeCache: freshCache(),
      }),
      new Promise((resolve) => setTimeout(() => resolve(timeoutSentinel), 50)),
    ]);
    assert.notEqual(route, timeoutSentinel, "real Transit fetch must be bounded");
    assert.equal(route.provider, "google");
    assert.equal(route.durationSeconds, 1200);
    assert.equal(transitSignal && transitSignal.aborted, true);
    assert.equal(requests.filter((url) => url.includes("maps.googleapis.com/maps/api/directions")).length, 1);
    assert.equal(requests.filter((url) => url.includes("routes.googleapis.com")).length, 0);
  } finally { global.fetch = originalFetch; }
});
