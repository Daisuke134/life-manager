"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { directionsRoute, geocodeAddress } = require("./travel.js");
const { makeRouteCache } = require("./route-cache.js");
const { recordUsageEvent } = require("./usage-event.js");

const ROUTE_RUNTIME_ENV = {
  LIFE_MANAGER_LOOP_ID: "life-manager-cfo-hourly",
  LIFE_MANAGER_OWNER_ID: "managed-travel-owner",
  LIFE_MANAGER_RUN_ID: "managed-travel-run",
  LIFE_MANAGER_OCCURRENCE_ID: "life-manager-cfo-hourly:managed-travel-run",
  LIFE_MANAGER_RELEASE_SHA: "f".repeat(40),
};

async function runRouteWithFakeFetch({
  src = "geo:35.681,139.767",
  dst = "geo:35.659,139.700",
  geocode,
  transitFetch,
  timeoutMs,
} = {}) {
  const requests = [];
  const events = [];
  const rows = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    const requestUrl = String(url);
    requests.push(requestUrl);
    if (requestUrl.includes("api.transit.ls8h.com")) {
      return transitFetch ? transitFetch(requestUrl, options) : {
        ok: true,
        status: 200,
        json: async () => ({ date: "20260827", timezone: "Asia/Tokyo", journeys: [] }),
      };
    }
    if (requestUrl.includes("maps.googleapis.com/maps/api/directions")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ status: "OK", routes: [{ legs: [{ duration: { value: 1800 } }] }] }),
      };
    }
    throw new Error("unexpected fake fetch URL");
  };
  try {
    const options = {
      uid: "tenant-transit-fallback",
      timezone: "Asia/Tokyo",
      _routeCache: makeRouteCache({ store: new Map(), ttlMs: 600000, now: () => 1000 }),
      _runtimeEnv: ROUTE_RUNTIME_ENV,
      _recordUsageEvent: async (event, writeOptions) => {
        events.push(event);
        return recordUsageEvent(event, {
          ...writeOptions,
          recordCost: async (row) => { rows.push(row); return true; },
        });
      },
    };
    if (geocode) options._geocode = geocode;
    if (Number.isFinite(timeoutMs)) options._transitTimeoutMs = timeoutMs;
    const route = await directionsRoute(
      src, dst, "fake-maps-key", Date.parse("2026-08-27T18:30:00+09:00"),
      Date.parse("2026-08-26T00:00:00Z"), false, options,
    );
    return { route, requests, events, rows };
  } finally {
    globalThis.fetch = originalFetch;
  }
}

test("JP Transit outcomes map to fixed Google fallback metadata on the same runtime trace", async () => {
  const scenarios = [
    {
      name: "explicit no route",
      transitFetch: async () => ({ ok: true, status: 200,
        json: async () => ({ date: "20260827", timezone: "Asia/Tokyo", journeys: [] }) }),
      fallbackReason: "transit_no_route",
    },
    {
      name: "empty journeys with invalid service date",
      transitFetch: async () => ({ ok: true, status: 200,
        json: async () => ({ date: "20260230", timezone: "Asia/Tokyo", journeys: [] }) }),
      fallbackReason: "transit_invalid_response",
    },
    {
      name: "empty journeys with invalid timezone",
      transitFetch: async () => ({ ok: true, status: 200,
        json: async () => ({ date: "20260827", timezone: "Not/AZone", journeys: [] }) }),
      fallbackReason: "transit_invalid_response",
    },
    {
      name: "provider 4xx",
      transitFetch: async () => ({ ok: false, status: 429, json: async () => ({}) }),
      fallbackReason: "transit_provider_4xx",
    },
    {
      name: "provider 5xx",
      transitFetch: async () => ({ ok: false, status: 503, json: async () => ({}) }),
      fallbackReason: "transit_provider_5xx",
    },
    {
      name: "invalid response shape",
      transitFetch: async () => ({ ok: true, status: 200, json: async () => ({ error: "bad response" }) }),
      fallbackReason: "transit_invalid_response",
    },
    {
      name: "invalid service date",
      transitFetch: async () => ({ ok: true, status: 200, json: async () => ({
        date: "20260230", timezone: "Asia/Tokyo", type: "arrival",
        journeys: [{ departureSecs: 18 * 3600 + 31 * 60, arrivalSecs: 18 * 3600 + 40 * 60,
          durationSecs: 9 * 60, transferCount: 0, legs: [{ mode: "rail" }] }],
      }) }),
      fallbackReason: "transit_invalid_response",
    },
    {
      name: "invalid timezone",
      transitFetch: async () => ({ ok: true, status: 200, json: async () => ({
        date: "20260827", timezone: "Not/AZone", type: "arrival",
        journeys: [{ departureSecs: 18 * 3600 + 31 * 60, arrivalSecs: 18 * 3600 + 40 * 60,
          durationSecs: 9 * 60, transferCount: 0, legs: [{ mode: "rail" }] }],
      }) }),
      fallbackReason: "transit_invalid_response",
    },
    {
      name: "invalid response body",
      transitFetch: async () => ({ ok: true, status: 200, json: async () => { throw new Error("bad JSON body"); } }),
      fallbackReason: "transit_invalid_response",
    },
    {
      name: "network error",
      transitFetch: async () => { throw new Error("Authorization: Bearer fixture-transit-secret"); },
      fallbackReason: "transit_network",
    },
    {
      name: "timeout",
      transitFetch: async () => new Promise(() => {}),
      timeoutMs: 5,
      fallbackReason: "transit_timeout",
    },
  ];

  for (const scenario of scenarios) {
    const result = await runRouteWithFakeFetch(scenario);
    assert.equal(result.route.provider, "google", scenario.name);
    assert.equal(result.requests.filter((url) => url.includes("api.transit.ls8h.com")).length, 1, scenario.name);
    assert.equal(result.requests.filter((url) => url.includes("maps.googleapis.com/maps/api/directions")).length, 1,
      scenario.name);
    assert.equal(result.rows.length, 1, scenario.name);
    assert.equal(result.rows[0].meta.route_mode, "transit", scenario.name);
    assert.equal(result.rows[0].meta.fallback_reason, scenario.fallbackReason, scenario.name);
    assert.deepEqual(result.rows[0].meta.runtime_trace, {
      schema_version: 1,
      status: "linked",
      tenant_id: "tenant-transit-fallback",
      loop_id: "life-manager-cfo-hourly",
      owner_id: "managed-travel-owner",
      run_id: "managed-travel-run",
      occurrence_id: "life-manager-cfo-hourly:managed-travel-run",
      release_sha: "f".repeat(40),
    }, scenario.name);
    assert.equal(JSON.stringify(result.rows[0].meta).includes("fixture-transit-secret"), false, scenario.name);
  }
});

test("JP Transit success emits no Google fallback usage row", async () => {
  const result = await runRouteWithFakeFetch({
    transitFetch: async (requestUrl) => {
      const query = new URL(requestUrl).searchParams;
      const [hours, minutes] = query.get("time").split(":").map(Number);
      const anchorSecs = hours * 3600 + minutes * 60;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          date: query.get("date"),
          timezone: "Asia/Tokyo",
          type: query.get("type"),
          journeys: [{
            departureSecs: anchorSecs - 1029,
            arrivalSecs: anchorSecs,
            durationSecs: 1029,
            transferCount: 0,
            legs: [],
          }],
        }),
      };
    },
  });

  assert.equal(result.route.provider, "transit");
  assert.equal(result.requests.filter((url) => url.includes("api.transit.ls8h.com")).length, 1);
  assert.equal(result.requests.filter((url) => url.includes("maps.googleapis.com/maps/api/directions")).length, 0);
  assert.equal(result.rows.length, 0);
});

test("valid Transit journeys after the requested arrival anchor classify fallback as no route", async () => {
  const result = await runRouteWithFakeFetch({
    transitFetch: async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        date: "20260827",
        timezone: "Asia/Tokyo",
        type: "arrival",
        journeys: [{
          departureSecs: 18 * 3600 + 31 * 60,
          arrivalSecs: 18 * 3600 + 40 * 60,
          durationSecs: 9 * 60,
          transferCount: 0,
          legs: [{ mode: "rail" }],
        }],
      }),
    }),
  });

  assert.equal(result.route.provider, "google");
  assert.equal(result.requests.filter((url) => url.includes("api.transit.ls8h.com")).length, 1);
  assert.equal(result.requests.filter((url) => url.includes("maps.googleapis.com/maps/api/directions")).length, 1);
  assert.equal(result.rows.length, 1);
  assert.equal(result.rows[0].meta.route_mode, "transit");
  assert.equal(result.rows[0].meta.fallback_reason, "transit_no_route");
});

test("non-JP direct Google usage records only the safe non-JP fallback reason", async () => {
  const result = await runRouteWithFakeFetch({
    src: "New York origin",
    dst: "New York destination",
    geocode: async () => ({ lat: 40.7128, lon: -74.0060 }),
  });

  assert.equal(result.route.provider, "google");
  assert.equal(result.requests.filter((url) => url.includes("api.transit.ls8h.com")).length, 0);
  assert.equal(result.requests.filter((url) => url.includes("maps.googleapis.com/maps/api/directions")).length, 1);
  assert.equal(result.rows.length, 1);
  assert.equal(result.rows[0].meta.route_mode, "google");
  assert.equal(result.rows[0].meta.fallback_reason, "non_jp");
});

test("an unresolved geocode keeps Google mode without inventing a non-JP reason", async () => {
  const result = await runRouteWithFakeFetch({
    src: "Resolved Tokyo origin",
    dst: "Unresolved destination",
    geocode: async (address) => address === "Resolved Tokyo origin"
      ? { lat: 35.681, lon: 139.767 } : null,
  });

  assert.equal(result.route.provider, "google");
  assert.equal(result.requests.filter((url) => url.includes("maps.googleapis.com/maps/api/directions")).length, 1);
  assert.equal(result.rows.length, 1);
  assert.equal(result.rows[0].meta.route_mode, "google");
  assert.equal(Object.hasOwn(result.rows[0].meta, "fallback_reason"), false);
});

test("fallback usage metadata excludes endpoint text and raw Transit errors", async () => {
  const address = "住所秘密-42";
  const destination = "目的地秘密-84";
  const rawError = "Authorization: Bearer fixture-transit-secret";
  const result = await runRouteWithFakeFetch({
    src: address,
    dst: destination,
    geocode: async () => ({ lat: 35.681, lon: 139.767 }),
    transitFetch: async () => { throw new Error(rawError); },
  });

  assert.equal(result.rows.length, 1);
  assert.equal(result.rows[0].meta.fallback_reason, "transit_network");
  const metadata = JSON.stringify(result.rows[0].meta);
  assert.equal(metadata.includes(address), false);
  assert.equal(metadata.includes(destination), false);
  assert.equal(metadata.includes(rawError), false);
  assert.equal(metadata.includes("fixture-transit-secret"), false);
});

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
    uid: "tenant-1", eventId: "event-for-route-usage", _routeCache: cache,
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
  assert.match(events[0].meta.event_version, /^[a-f0-9]{64}$/);
  assert.equal(events[1].meta.event_version, events[0].meta.event_version);
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
  let geocodes = 0, providerCalls = 0, reservations = 0, lookup;
  const allowanceState = {};
  const usageEvents = [];
  const cachedRoute = { provider: "google", durationSeconds: 720 };
  const route = await directionsRoute("raw home", "raw venue", "key", 2_000_000, 1000, false, {
    uid: "tenant-cached", eventId: "event-cached", purpose: "go",
    _routeCache: {
      getByEvent: async (uid, eventVersion, purpose, onCacheHit) => {
        lookup = { uid, eventVersion, purpose };
        await onCacheHit(cachedRoute, { failureClass: null });
        return { hit: true, value: cachedRoute };
      },
    },
    _geocode: async () => { geocodes += 1; return null; },
    _directionsMinutesGoogle: async () => { providerCalls += 1; return 12; },
    _allowanceState: allowanceState,
    _reserveManagedAction: async () => { reservations += 1; return { allowed: true }; },
    _recordUsageEvent: async (event) => { usageEvents.push(event); return true; },
  });
  assert.deepEqual(route, cachedRoute);
  assert.equal(lookup.uid, "tenant-cached");
  assert.equal(lookup.purpose, "go");
  assert.match(lookup.eventVersion, /^[a-f0-9]{64}$/);
  assert.equal(geocodes, 0);
  assert.equal(providerCalls, 0);
  assert.equal(reservations, 0);
  assert.equal(usageEvents[0].meta.event_version, lookup.eventVersion);
  assert.equal(JSON.stringify(usageEvents).includes("event-cached"), false);
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

test("route event versions bind timezone and arrival/departure routing direction", async () => {
  const versions = [];
  const events = [];
  const oldFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({
    status: "OK", routes: [{ legs: [{ duration: { value: 900 } }] }],
  }) });
  const cache = {
    getByEvent: async (_uid, eventVersion) => {
      versions.push(eventVersion);
      return { hit: false, value: null };
    },
    getOrCompute: async (_uid, _src, _dst, _bucket, compute) => compute(),
  };
  const common = {
    uid: "tenant-version-dimensions", eventId: "calendar-private-event", purpose: "go",
    _routeCache: cache,
    _recordUsageEvent: async (event) => { events.push(event); return true; },
  };
  try {
    await directionsRoute("geo:40.730,-73.930", "geo:40.740,-73.980", "key", 2_000_000, 1000, false,
      { ...common, timezone: "Asia/Tokyo" });
    await directionsRoute("geo:40.730,-73.930", "geo:40.740,-73.980", "key", 2_000_000, 1000, false,
      { ...common, timezone: "UTC" });
    await directionsRoute("geo:40.730,-73.930", "geo:40.740,-73.980", "key", 2_000_000, 1000, true,
      { ...common, timezone: "Asia/Tokyo" });
  } finally {
    globalThis.fetch = oldFetch;
  }
  assert.equal(new Set(versions).size, 3);
  assert.ok(versions.every((version) => /^[a-f0-9]{64}$/.test(version)));
  assert.deepEqual(events.map((event) => event.meta.event_version), versions);
  assert.equal(JSON.stringify(events).includes("calendar-private-event"), false);
});
