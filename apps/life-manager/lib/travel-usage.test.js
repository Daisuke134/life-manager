"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { directionsRoute, geocodeAddress } = require("./travel.js");
const { makeRouteCache } = require("./route-cache.js");
const { recordUsageEvent } = require("./usage-event.js");

test("Google Directions success and later cache hit emit separate usage facts", async () => {
  const events = [];
  const cache = makeRouteCache({ store: new Map(), ttlMs: 600000, now: () => 1000 });
  const oldFetch = globalThis.fetch;
  let providerCalls = 0;
  globalThis.fetch = async () => {
    providerCalls += 1;
    return { ok: true, status: 200, json: async () => ({
      status: "OK", routes: [{ legs: [{ duration: { value: 900 } }] }],
    }) };
  };
  const opts = {
    uid: "tenant-1", _routeCache: cache,
    _recordUsageEvent: async (event) => { events.push(event); return true; },
  };
  try {
    await directionsRoute("geo:40.730,-73.930", "geo:40.740,-73.980", "key", 2000000, 1000, false, opts);
    await directionsRoute("geo:40.730,-73.930", "geo:40.740,-73.980", "key", 2000000, 1000, false, opts);
    await directionsRoute("geo:40.730,-73.930", "geo:40.740,-73.980", "key", 2000000, 1000, false, opts);
  } finally {
    globalThis.fetch = oldFetch;
  }
  assert.equal(providerCalls, 1);
  assert.deepEqual(events.map((event) => ({
    provider: event.provider, feature: event.feature, outcome: event.outcome,
    units: event.providerUnits, cost: event.estimatedCostUsd,
  })), [
    { provider: "google_maps", feature: "directions", outcome: "success", units: 1, cost: 0.005 },
    { provider: "google_maps", feature: "travel_route", outcome: "cache_hit", units: 0, cost: 0 },
  ]);
});

test("life-call travel passes safe route runtime context separately to the usage writer", async () => {
  const writes = [];
  const rows = [];
  const cache = makeRouteCache({ store: new Map(), ttlMs: 600000, now: () => 1000 });
  const oldFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({
    status: "OK", routes: [{ legs: [{ duration: { value: 900 } }] }],
  }) });
  try {
    await directionsRoute("geo:40.730,-73.930", "geo:40.740,-73.980", "key", 2000000, 1000, false, {
      uid: "tenant-1",
      _routeCache: cache,
      _runtimeEnv: {
        RAILWAY_SERVICE_NAME: "life-call",
        RAILWAY_GIT_COMMIT_SHA: "c".repeat(40),
        STRIPE_SECRET_KEY: "must-not-enter-runtime-metadata",
      },
      _recordUsageEvent: async (event, options) => {
        writes.push({ event, options });
        return recordUsageEvent(event, {
          ...options,
          recordCost: async (row) => { rows.push(row); return true; },
        });
      },
    });
  } finally {
    globalThis.fetch = oldFetch;
  }

  assert.ok(writes.length > 0);
  assert.ok(rows.length > 0);
  assert.equal(Object.hasOwn(writes[0].event, "runtimeEnv"), false);
  assert.equal(Object.hasOwn(writes[0].event, "runtime_trace"), false);
  const runtimeEnv = writes[0].options && writes[0].options.runtimeEnv;
  assert.equal(runtimeEnv && Object.hasOwn(runtimeEnv, "RAILWAY_SERVICE_NAME"), false);
  assert.equal(runtimeEnv && runtimeEnv.LIFE_MANAGER_OWNER_ID, "life-call-travel");
  assert.equal(runtimeEnv && Object.hasOwn(runtimeEnv, "LIFE_MANAGER_LOOP_ID"), false);
  assert.equal(runtimeEnv && runtimeEnv.LIFE_MANAGER_RUN_ID.startsWith("route-"), true);
  assert.match(runtimeEnv && runtimeEnv.LIFE_MANAGER_OCCURRENCE_ID,
    /^life-call-travel:route-[0-9a-f-]{36}$/);
  assert.equal(runtimeEnv && runtimeEnv.LIFE_MANAGER_RELEASE_SHA, "c".repeat(40));
  assert.equal(runtimeEnv && Object.hasOwn(runtimeEnv, "RAILWAY_GIT_COMMIT_SHA"), false);
  assert.equal(runtimeEnv && Object.hasOwn(runtimeEnv, "STRIPE_SECRET_KEY"), false);
  assert.deepEqual(rows[0].meta.runtime_trace, {
    schema_version: 1,
    status: "partial",
    tenant_id: "tenant-1",
    owner_id: "life-call-travel",
    run_id: runtimeEnv.LIFE_MANAGER_RUN_ID,
    occurrence_id: runtimeEnv.LIFE_MANAGER_OCCURRENCE_ID,
    release_sha: "c".repeat(40),
    missing_fields: ["loop_id"],
  });
  assert.equal(JSON.stringify(rows).includes("must-not-enter-runtime-metadata"), false);
});

test("complete managed loop runtime context stays authoritative on life-call travel", async () => {
  const writes = [];
  const cache = makeRouteCache({ store: new Map(), ttlMs: 600000, now: () => 1000 });
  const oldFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({
    status: "OK", routes: [{ legs: [{ duration: { value: 900 } }] }],
  }) });
  try {
    await directionsRoute("geo:40.730,-73.930", "geo:40.740,-73.980", "key", 2000000, 1000, false, {
      uid: "tenant-1",
      _routeCache: cache,
      _runtimeEnv: {
        LIFE_MANAGER_LOOP_ID: "life-manager-cfo-hourly",
        LIFE_MANAGER_OWNER_ID: "managed-owner",
        LIFE_MANAGER_RUN_ID: "managed-run-1",
        LIFE_MANAGER_OCCURRENCE_ID: "life-manager-cfo-hourly:managed-run-1",
        LIFE_MANAGER_RELEASE_SHA: "d".repeat(40),
        RAILWAY_SERVICE_NAME: "life-call",
        RAILWAY_GIT_COMMIT_SHA: "e".repeat(40),
      },
      _recordUsageEvent: async (_event, options) => { writes.push(options); return true; },
    });
  } finally {
    globalThis.fetch = oldFetch;
  }

  assert.ok(writes.length > 0);
  const runtimeEnv = writes[0] && writes[0].runtimeEnv;
  assert.equal(runtimeEnv && runtimeEnv.LIFE_MANAGER_LOOP_ID, "life-manager-cfo-hourly");
  assert.equal(writes[0].runtimeEnv.LIFE_MANAGER_OWNER_ID, "managed-owner");
  assert.equal(writes[0].runtimeEnv.LIFE_MANAGER_RUN_ID, "managed-run-1");
  assert.equal(writes[0].runtimeEnv.LIFE_MANAGER_OCCURRENCE_ID,
    "life-manager-cfo-hourly:managed-run-1");
  assert.equal(writes[0].runtimeEnv.LIFE_MANAGER_RELEASE_SHA, "d".repeat(40));
});

test("Google Directions 4xx response is recorded as paid failure work", async () => {
  const events = [];
  const oldFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false, status: 400, json: async () => ({ status: "INVALID_REQUEST" }) });
  try {
    const route = await directionsRoute(
      "geo:40.730,-73.930", "geo:40.740,-73.980", "key", 2000000, 1000, false,
      { uid: "tenant-1", _routeCache: makeRouteCache({ store: new Map(), now: () => 1000 }),
        _recordUsageEvent: async (event) => { events.push(event); return true; } },
    );
    assert.equal(route, null);
  } finally {
    globalThis.fetch = oldFetch;
  }
  assert.equal(events.length, 1);
  assert.equal(events[0].outcome, "failure");
  assert.equal(events[0].failureClass, "provider_4xx");
  assert.equal(events[0].providerUnits, 1);
  assert.equal(events[0].estimatedCostUsd, 0.005);
});

test("Geocoding 4xx is not replayed during negative TTL and a later valid response recovers", async () => {
  const oldFetch = globalThis.fetch;
  const oldNow = Date.now;
  let now = 1_000, calls = 0;
  Date.now = () => now;
  globalThis.fetch = async () => {
    calls += 1;
    if (calls === 1) return { ok: false, status: 400, json: async () => ({ status: "INVALID_REQUEST" }) };
    return { ok: true, status: 200, json: async () => ({ status: "OK", results: [{
      geometry: { location: { lat: 35.68, lng: 139.76 } },
    }] }) };
  };
  const usage = { tenantId: "tenant-geocode", options: { _recordUsageEvent: async () => true } };
  try {
    assert.equal(await geocodeAddress("COST-02 unique address", "key", usage), null);
    assert.equal(await geocodeAddress("COST-02 unique address", "key", usage), null);
    assert.equal(calls, 1);
    now += 30 * 60_000 + 1;
    assert.deepEqual(await geocodeAddress("COST-02 unique address", "key", usage), {
      lat: 35.68, lon: 139.76,
    });
    assert.equal(calls, 2);
  } finally {
    Date.now = oldNow;
    globalThis.fetch = oldFetch;
  }
});

test("un-geocodable raw endpoints still negative-cache the paid Directions fallback", async () => {
  let calls = 0;
  const cache = makeRouteCache({ store: new Map(), now: () => 1000 });
  const options = {
    uid: "tenant-raw-negative",
    _routeCache: cache,
    _geocode: async () => null,
    _directionsMinutesGoogle: async () => { calls += 1; return null; },
    _recordUsageEvent: async () => true,
  };
  const first = await directionsRoute("raw start", "raw destination", "key", 2_000_000, 1000, false, options);
  const second = await directionsRoute("raw start", "raw destination", "key", 2_000_000, 1000, false, options);
  assert.equal(first, null);
  assert.equal(second, null);
  assert.equal(calls, 1);
});

test("Calendar, Telegram, and call consumers share one event-version route fact", async () => {
  let calls = 0;
  const cache = makeRouteCache({ store: new Map(), now: () => 1000 });
  const common = {
    uid: "tenant-shared", eventId: "calendar-event-1", purpose: "go", _routeCache: cache,
    _directionsMinutesGoogle: async () => { calls += 1; return 12; },
    _recordUsageEvent: async () => true,
  };
  for (const consumer of ["calendar", "telegram", "call"]) {
    await directionsRoute("geo:40.730,-73.930", "geo:40.740,-73.980", "key",
      2_000_000, 1000, false, { ...common, consumer });
  }
  assert.equal(calls, 1);
});

test("persisted event cache hit runs before geocoding or route provider work", async () => {
  let geocodes = 0, providerCalls = 0, lookup;
  const cachedRoute = { provider: "google", durationSeconds: 720 };
  const route = await directionsRoute("raw home", "raw venue", "key", 2_000_000, 1000, false, {
    uid: "tenant-cached", eventId: "event-cached", purpose: "go",
    _routeCache: {
      getByEvent: async (uid, eventVersion, purpose) => {
        lookup = { uid, eventVersion, purpose };
        return { hit: true, value: cachedRoute };
      },
    },
    _geocode: async () => { geocodes += 1; return null; },
    _directionsMinutesGoogle: async () => { providerCalls += 1; return 12; },
  });
  assert.deepEqual(route, cachedRoute);
  assert.equal(lookup.uid, "tenant-cached");
  assert.equal(lookup.purpose, "go");
  assert.ok(lookup.eventVersion);
  assert.equal(geocodes, 0);
  assert.equal(providerCalls, 0);
});

test("exact schedule, location, event, and purpose changes invalidate the shared route fact", async () => {
  let calls = 0;
  const cache = makeRouteCache({ store: new Map(), now: () => 1000 });
  const route = (dst, anchor, eventId, purpose = "go") => directionsRoute(
    "geo:40.730,-73.930", dst, "key", anchor, 1000, false,
    { uid: "tenant-version", eventId, purpose, _routeCache: cache,
      _directionsMinutesGoogle: async () => { calls += 1; return 12; },
      _recordUsageEvent: async () => true },
  );
  await route("geo:40.740,-73.980", 2_000_000, "event-1");
  await route("geo:40.740,-73.980", 2_060_000, "event-1"); // same 10-minute bucket, exact time changed
  await route("geo:40.741,-73.980", 2_060_000, "event-1");
  await route("geo:40.741,-73.980", 2_060_000, "event-2");
  await route("geo:40.741,-73.980", 2_060_000, "event-2", "return");
  assert.equal(calls, 5);
});
