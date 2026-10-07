"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { directionsRoute, fillTravel } = require("./travel.js");
const { makeRouteCache } = require("./route-cache.js");

const NOW = Date.parse("2030-01-01T08:00:00+09:00");
const START = Date.parse("2030-01-01T10:00:00+09:00");
const END = Date.parse("2030-01-01T11:00:00+09:00");
const poiCandidate = {
  name: "ルートcache対象ビル",
  address: "東京都 fixture",
  lat: 35.659,
  lng: 139.700,
  source: "fixture-poi-source",
  licenses: ["CC BY 4.0"],
  attributions: ["Fixture POI attribution"],
};

test("route cache keeps full free-geocode provenance on fresh and cached routes", async () => {
  const routeCache = makeRouteCache({ store: new Map(), ttlMs: 600_000, now: () => 1000 });
  let freeProviderCalls = 0;
  let googleGeocodeCalls = 0;
  const oldFetch = globalThis.fetch;
  globalThis.fetch = async (input) => {
    const url = new URL(String(input));
    assert.equal(url.hostname, "maps.googleapis.com");
    assert.equal(url.pathname, "/maps/api/geocode/json");
    googleGeocodeCalls += 1;
    return { ok: true, status: 200, json: async () => ({ status: "OK", results: [{
      geometry: { location: { lat: 35.659, lng: 139.700 } },
    }] }) };
  };
  const freeFetch = async (input) => {
    const url = new URL(String(input));
    assert.equal(url.hostname, "api.openpoiapi.com");
    assert.equal(url.pathname, "/v1/suggest");
    freeProviderCalls += 1;
    return { ok: true, status: 200, json: async () => ({ suggestions: [poiCandidate] }) };
  };
  const options = {
    uid: "tenant-route-attribution",
    eventId: "opaque-fixture-event",
    timezone: "Asia/Tokyo",
    _routeCache: routeCache,
    _freeGeocodeFetch: freeFetch,
    _transitFetch: async (_src, _dst, query) => ({
      date: query.date,
      timezone: query.timezone,
      type: query.type,
      journeys: [{
        departureSecs: query.anchorSecs - 600,
        arrivalSecs: query.anchorSecs,
        durationSecs: 600,
        transferCount: 0,
        legs: [{ mode: "rail" }],
      }],
    }),
    _recordUsageEvent: async () => true,
  };
  const args = ["geo:35.681,139.767", poiCandidate.name, "fixture-map-key", START, NOW, false, options];
  let fresh;
  let cached;
  try {
    fresh = await directionsRoute(...args);
    cached = await directionsRoute(...args);
  } finally {
    globalThis.fetch = oldFetch;
  }

  assert.equal(fresh.provider, "transit");
  assert.deepEqual(fresh.geocodeSources?.destination?.sourceRecord, {
    source: poiCandidate.source,
    licenses: poiCandidate.licenses,
    attributions: poiCandidate.attributions,
  });
  assert.deepEqual(fresh.geocodeSources?.destination?.licenses, poiCandidate.licenses);
  assert.deepEqual(fresh.geocodeSources?.destination?.attributions, poiCandidate.attributions);
  assert.deepEqual(cached.geocodeSources, fresh.geocodeSources);
  assert.equal(freeProviderCalls, 1);
  assert.equal(googleGeocodeCalls, 0);
});

async function createTravelEvent(route) {
  const created = [];
  const event = {
    id: "fixture-travel-event",
    summary: "会議",
    location: "ルート対象ビル",
    start: { dateTime: new Date(START).toISOString(), timeZone: "Asia/Tokyo" },
    end: { dateTime: new Date(END).toISOString(), timeZone: "Asia/Tokyo" },
  };
  const calendar = {
    async listEventsRaw() { return [event]; },
    async createEvent(_uid, args) { created.push(args); return { successful: true }; },
  };
  await fillTravel("tenant-travel-attribution", {
    mapsKey: "fixture-map-key",
    home: "Home",
    nowMs: NOW,
    calendar,
    _directionsRoute: async (...args) => args[6]?.purpose === "return" ? null : route,
  });
  return created;
}

test("new travel event description shows free source attribution and link", async () => {
  const created = await createTravelEvent({
    provider: "transit",
    durationSeconds: 600,
    geocodeSources: {
      destination: {
        provider: "openpoi",
        source: "fixture-poi-source",
        sourceRecord: poiCandidate,
        licenses: poiCandidate.licenses,
        attributions: poiCandidate.attributions,
        attributionUrl: "https://openpoiapi.com/attribution.html",
      },
    },
  });

  assert.equal(created.length, 1);
  assert.match(created[0].description, /Auto-inserted by Life Manager/);
  assert.match(created[0].description, /Fixture POI attribution/);
  assert.match(created[0].description, /CC BY 4\.0/);
  assert.match(created[0].description, /https:\/\/openpoiapi\.com\/attribution\.html/);
});

test("Google-only travel event keeps the existing description", async () => {
  const created = await createTravelEvent({ provider: "google", durationSeconds: 600 });

  assert.equal(created.length, 1);
  assert.equal(created[0].description, "Auto-inserted by Life Manager — adjust if the route is wrong.");
});
