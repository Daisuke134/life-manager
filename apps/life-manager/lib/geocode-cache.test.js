"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { geocodeAddress } = require("./travel.js");
const { makeSupabaseGeocodeStore } = require("./geocode-cache.js");

const SUPA_URL = "https://db.example";
const SUPA_KEY = "fixture-service-role-key";
const MAPS_KEY = "fixture-maps-key";

function makeStoreFetch(now = () => Date.now()) {
  const rows = new Map();
  const requests = [];
  const fetchImpl = async (url, init = {}) => {
    const parsed = new URL(String(url));
    const body = JSON.parse(init.body || "{}");
    requests.push({ url: String(url), body });
    if (parsed.pathname.endsWith("/rpc/lm_geocode_cache_get")) {
      const key = JSON.stringify([body.p_uid, body.p_provider, body.p_address_digest]);
      const row = rows.get(key);
      const live = row && now() - Date.parse(row.computed_at) < row.ttl_secs * 1000;
      return { ok: true, json: async () => live ? [{
        lat: row.lat, lon: row.lon, computed_at: row.computed_at, ttl_secs: row.ttl_secs,
      }] : [] };
    }
    if (parsed.pathname.endsWith("/rpc/lm_geocode_cache_upsert")) {
      const key = JSON.stringify([body.p_uid, body.p_provider, body.p_address_digest]);
      rows.set(key, {
        ...body, lat: body.p_lat, lon: body.p_lon,
        computed_at: body.p_computed_at, ttl_secs: body.p_ttl_secs,
      });
      return { ok: true };
    }
    throw new Error(`unexpected cache request: ${parsed.pathname}`);
  };
  return { rows, requests, fetchImpl };
}

function successfulGeocode(lat = 35.681, lon = 139.767) {
  return { ok: true, status: 200, json: async () => ({
    status: "OK", results: [{ geometry: { location: { lat, lng: lon } } }],
  }) };
}

function reloadTravelModule() {
  const path = require.resolve("./travel.js");
  delete require.cache[path];
  return require(path);
}

test("successful geocodes persist only a keyed normalized digest and survive a fresh travel module", async () => {
  const oldFetch = globalThis.fetch;
  const oldNow = Date.now;
  let now = 1_000, providerCalls = 0;
  Date.now = () => now;
  globalThis.fetch = async (url) => {
    assert.match(String(url), /maps\.googleapis\.com/);
    providerCalls += 1;
    return successfulGeocode();
  };
  const store = makeStoreFetch(() => now);
  const events = [];
  const usage = {
    tenantId: "tenant-geocode-persist",
    eventVersion: "a".repeat(64),
    options: {
      supaUrl: SUPA_URL, supaKey: SUPA_KEY, _cacheFetch: store.fetchImpl,
      _recordUsageEvent: async (event) => { events.push(event); return true; },
    },
  };

  try {
    assert.deepEqual(await geocodeAddress("\u3000Tokyo   Station ", MAPS_KEY, usage), { lat: 35.681, lon: 139.767 });
    assert.deepEqual(await reloadTravelModule().geocodeAddress("Tokyo Station", MAPS_KEY, usage), {
      lat: 35.681, lon: 139.767,
    });
  } finally {
    Date.now = oldNow;
    globalThis.fetch = oldFetch;
    delete require.cache[require.resolve("./travel.js")];
  }

  assert.equal(providerCalls, 1);
  assert.equal(store.rows.size, 1);
  const persisted = [...store.rows.values()][0];
  assert.equal(persisted.p_provider, "google_maps");
  assert.match(persisted.p_address_digest, /^[a-f0-9]{64}$/);
  assert.equal(persisted.p_ttl_secs, 86_400);
  const databaseRequests = JSON.stringify(store.requests);
  assert.equal(databaseRequests.includes("Tokyo"), false);
  assert.equal(databaseRequests.includes(MAPS_KEY), false);
  assert.equal(databaseRequests.includes("calendar-event"), false);
  assert.deepEqual(events.map((event) => ({ outcome: event.outcome, units: event.providerUnits,
    eventVersion: event.meta.event_version })), [
    { outcome: "success", units: 1, eventVersion: "a".repeat(64) },
    { outcome: "cache_hit", units: 0, eventVersion: "a".repeat(64) },
  ]);
});

test("successful geocodes expire after 24 hours", async () => {
  const oldFetch = globalThis.fetch;
  const oldNow = Date.now;
  let now = 10_000, providerCalls = 0;
  Date.now = () => now;
  globalThis.fetch = async () => { providerCalls += 1; return successfulGeocode(); };
  const store = makeStoreFetch(() => now);
  const usage = { tenantId: "tenant-geocode-ttl", options: {
    supaUrl: SUPA_URL, supaKey: SUPA_KEY, _cacheFetch: store.fetchImpl,
  } };
  try {
    assert.deepEqual(await geocodeAddress("TTL unique address", MAPS_KEY, usage), { lat: 35.681, lon: 139.767 });
    now += 86_400_001;
    assert.deepEqual(await reloadTravelModule().geocodeAddress("TTL unique address", MAPS_KEY, usage), {
      lat: 35.681, lon: 139.767,
    });
  } finally {
    Date.now = oldNow;
    globalThis.fetch = oldFetch;
    delete require.cache[require.resolve("./travel.js")];
  }
  assert.equal(providerCalls, 2);
});

test("geocode cache GET parses its row while a successful 204 upsert needs no response body", async () => {
  const oldNow = Date.now;
  Date.now = () => 1_000;
  let jsonCalls = 0;
  const store = makeSupabaseGeocodeStore({
    supaUrl: SUPA_URL,
    supaKey: SUPA_KEY,
    timeoutMs: 25,
    fetchImpl: async (url) => {
      if (String(url).endsWith("lm_geocode_cache_get")) {
        return {
          ok: true,
          status: 200,
          json: async () => {
            jsonCalls += 1;
            return [{ lat: 35.681, lon: 139.767, computed_at: new Date(1_000).toISOString(), ttl_secs: 86_400 }];
          },
        };
      }
      if (String(url).endsWith("lm_geocode_cache_upsert")) {
        return { ok: true, status: 204, json: async () => { throw new Error("204 response has no JSON body"); } };
      }
      throw new Error("unexpected geocode cache RPC");
    },
  });
  try {
    assert.deepEqual(await store.get("tenant-void-upsert", "google_maps", "fixture address"), {
      value: { lat: 35.681, lon: 139.767 }, computedAt: 1_000, ttlMs: 86_400_000,
    });
    assert.equal(await store.set("tenant-void-upsert", "google_maps", "fixture address", {
      lat: 35.681, lon: 139.767,
    }, 1_000), true);
  } finally {
    Date.now = oldNow;
  }
  assert.equal(jsonCalls, 1);
});

test("persistent geocode keys isolate both tenant and provider", async () => {
  const oldNow = Date.now;
  Date.now = () => 1_000;
  const harness = makeStoreFetch(() => 1_000);
  const store = makeSupabaseGeocodeStore({
    supaUrl: SUPA_URL, supaKey: SUPA_KEY, fetchImpl: harness.fetchImpl,
  });
  try {
    assert.equal(await store.set("tenant-scope", "google_maps", "Tokyo Station", {
      lat: 35.681, lon: 139.767,
    }, 1_000), true);
    assert.deepEqual(await store.get("tenant-scope", "google_maps", "Tokyo Station"), {
      value: { lat: 35.681, lon: 139.767 }, computedAt: 1_000, ttlMs: 86_400_000,
    });
    assert.equal(await store.get("other-tenant", "google_maps", "Tokyo Station"), null);
    assert.equal(await store.get("tenant-scope", "other-geocoder", "Tokyo Station"), null);
  } finally {
    Date.now = oldNow;
  }
  assert.equal(harness.rows.size, 1);
  const readScopes = harness.requests
    .filter((request) => request.url.endsWith("lm_geocode_cache_get"))
    .map((request) => [request.body.p_uid, request.body.p_provider]);
  assert.deepEqual(readScopes, [
    ["tenant-scope", "google_maps"], ["other-tenant", "google_maps"],
    ["tenant-scope", "other-geocoder"],
  ]);
});

test("process-local geocode reuse stays tenant scoped", async () => {
  const oldFetch = globalThis.fetch;
  let providerCalls = 0;
  globalThis.fetch = async () => { providerCalls += 1; return successfulGeocode(); };
  try {
    const address = "tenant isolation unique address";
    await geocodeAddress(address, MAPS_KEY, { tenantId: "tenant-one" });
    await geocodeAddress(address, MAPS_KEY, { tenantId: "tenant-two" });
  } finally {
    globalThis.fetch = oldFetch;
  }
  assert.equal(providerCalls, 2);
});

test("concurrent same-tenant geocodes collapse to one provider call", async () => {
  const oldFetch = globalThis.fetch;
  let providerCalls = 0, release;
  const gate = new Promise((resolve) => { release = resolve; });
  globalThis.fetch = async () => {
    providerCalls += 1;
    await gate;
    return successfulGeocode();
  };
  try {
    const first = geocodeAddress("concurrent unique address", MAPS_KEY, { tenantId: "tenant-concurrent" });
    const second = geocodeAddress("concurrent unique address", MAPS_KEY, { tenantId: "tenant-concurrent" });
    await new Promise((resolve) => setImmediate(resolve));
    assert.equal(providerCalls, 1);
    release();
    assert.deepEqual(await Promise.all([first, second]), [
      { lat: 35.681, lon: 139.767 }, { lat: 35.681, lon: 139.767 },
    ]);
  } finally {
    release();
    globalThis.fetch = oldFetch;
  }
});

test("cache-store read and write failures keep successful provider results available", async () => {
  const oldFetch = globalThis.fetch;
  let providerCalls = 0;
  globalThis.fetch = async () => { providerCalls += 1; return successfulGeocode(); };
  const failingCacheFetch = async () => ({ ok: false, status: 503 });
  try {
    const result = await geocodeAddress("store outage unique address", MAPS_KEY, {
      tenantId: "tenant-store-outage",
      options: { supaUrl: SUPA_URL, supaKey: SUPA_KEY, _cacheFetch: failingCacheFetch },
    });
    assert.deepEqual(result, { lat: 35.681, lon: 139.767 });
  } finally {
    globalThis.fetch = oldFetch;
  }
  assert.equal(providerCalls, 1);
});

test("invalid provider coordinates are rejected and never persisted", async () => {
  const oldFetch = globalThis.fetch;
  let writes = 0;
  const store = makeStoreFetch();
  const cacheFetch = async (url, init) => {
    if (String(url).endsWith("lm_geocode_cache_upsert")) writes += 1;
    return store.fetchImpl(url, init);
  };
  globalThis.fetch = async () => successfulGeocode(91, 181);
  try {
    const result = await geocodeAddress("invalid coordinate unique address", MAPS_KEY, {
      tenantId: "tenant-invalid-geo",
      options: { supaUrl: SUPA_URL, supaKey: SUPA_KEY, _cacheFetch: cacheFetch },
    });
    assert.equal(result, null);
  } finally {
    globalThis.fetch = oldFetch;
  }
  assert.equal(writes, 0);
});

test("failed provider responses never return or persist coordinates from their body", async () => {
  const oldFetch = globalThis.fetch;
  const scenarios = [
    { name: "http-503", ok: false, status: 503, providerStatus: "REQUEST_DENIED", failureClass: "provider_5xx" },
    { name: "provider-rejected", ok: true, status: 200, providerStatus: "REQUEST_DENIED", failureClass: "no_route" },
  ];
  try {
    for (const scenario of scenarios) {
      globalThis.fetch = async () => ({
        ok: scenario.ok,
        status: scenario.status,
        json: async () => ({
          status: scenario.providerStatus,
          results: [{ geometry: { location: { lat: 35.681, lng: 139.767 } } }],
        }),
      });
      const store = makeStoreFetch();
      const events = [];
      const result = await geocodeAddress(`failed provider ${scenario.name}`, MAPS_KEY, {
        tenantId: `tenant-${scenario.name}`,
        options: {
          supaUrl: SUPA_URL,
          supaKey: SUPA_KEY,
          _cacheFetch: store.fetchImpl,
          _recordUsageEvent: async (event) => { events.push(event); return true; },
        },
      });
      assert.equal(result, null, scenario.name);
      assert.equal(store.rows.size, 0, scenario.name);
      assert.equal(events.length, 1, scenario.name);
      assert.equal(events[0].outcome, "failure", scenario.name);
      assert.equal(events[0].failureClass, scenario.failureClass, scenario.name);
    }
  } finally {
    globalThis.fetch = oldFetch;
  }
});

test("Supabase geocode cache RPCs bound a never-resolving injected fetch", async () => {
  const observations = [];
  const store = makeSupabaseGeocodeStore({
    supaUrl: SUPA_URL,
    supaKey: SUPA_KEY,
    fetchImpl: () => new Promise(() => {}),
    timeoutMs: 5,
    onObservation: async (observation) => { observations.push(observation); },
  });
  const pending = Promise.all([
    store.get("tenant-timeout", "google_maps", "cache timeout fixture"),
    store.set("tenant-timeout", "google_maps", "cache timeout fixture", { lat: 35.681, lon: 139.767 }),
  ]);
  const result = await Promise.race([
    pending,
    new Promise((resolve) => setTimeout(() => resolve("cache-rpc-hung"), 100)),
  ]);
  assert.deepEqual(result, [null, false]);
  assert.deepEqual(observations.map(({ operation, outcome, failureClass, providerUnits }) =>
    ({ operation, outcome, failureClass, providerUnits })), [
    { operation: "lm_geocode_cache_get", outcome: "failure", failureClass: "timeout", providerUnits: 1 },
    { operation: "lm_geocode_cache_upsert", outcome: "failure", failureClass: "timeout", providerUnits: 1 },
  ]);
});

test("a never-resolving injected cache fetch does not block Google geocode fallback", async () => {
  const oldFetch = globalThis.fetch;
  let googleCalls = 0;
  const usageEvents = [];
  globalThis.fetch = async (url) => {
    assert.match(String(url), /maps\.googleapis\.com\/maps\/api\/geocode\/json/);
    googleCalls += 1;
    return successfulGeocode();
  };
  try {
    const request = geocodeAddress("cache hang fallback unique fixture", MAPS_KEY, {
      tenantId: "tenant-cache-hang",
      options: {
        supaUrl: SUPA_URL,
        supaKey: SUPA_KEY,
        _cacheFetch: () => new Promise(() => {}),
        _geocodeCacheTimeoutMs: 5,
        _recordUsageEvent: async (event) => { usageEvents.push(event); return true; },
      },
      eventVersion: "c".repeat(64),
    });
    const result = await Promise.race([
      request,
      new Promise((resolve) => setTimeout(() => resolve("geocode-fallback-hung"), 100)),
    ]);
    assert.deepEqual(result, { lat: 35.681, lon: 139.767 });
  } finally {
    globalThis.fetch = oldFetch;
  }
  assert.equal(googleCalls, 1);
  const cacheEvents = usageEvents.filter((event) => event.provider === "supabase");
  assert.deepEqual(cacheEvents.map((event) => [event.operation, event.outcome, event.failureClass,
    event.providerUnits, event.estimatedCostUsd]), [
    ["lm_geocode_cache_get", "failure", "timeout", 1, 0],
    ["lm_geocode_cache_upsert", "failure", "timeout", 1, 0],
  ]);
  assert.ok(cacheEvents.every((event) => event.meta.event_version === "c".repeat(64)));
  assert.equal(JSON.stringify(usageEvents).includes("cache hang fallback unique fixture"), false);
});
