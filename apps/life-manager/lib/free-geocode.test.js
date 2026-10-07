"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { geocodeAddress } = require("./travel.js");
const { recordUsageEvent } = require("./usage-event.js");
const geocodeFixtures = require("./fixtures/geocode-free-candidates.json");

const MAPS_KEY = "fixture-maps-key";
const EVENT_VERSION = "a".repeat(64);
const jsonResponse = (value, status = 200) => ({
  ok: status >= 200 && status < 300, status, json: async () => value,
});
const gsiFeature = (title, coordinates = [139.767, 35.681]) => ({
  type: "Feature",
  properties: { title },
  geometry: { type: "Point", coordinates },
});
const poiCandidate = (name, overrides = {}) => ({
  name,
  address: "東京都渋谷区 fixture",
  lat: 35.659,
  lng: 139.700,
  source: "fixture-poi-source",
  licenses: ["CC BY 4.0"],
  attributions: ["Fixture Data Provider", "Fixture City Office"],
  ...overrides,
});

async function runGeocode({
  query,
  gsi,
  openpoi,
  freeFetch,
  timeoutMs = 25,
  tenantId = "tenant-free-geocode",
  extraOptions = {},
} = {}) {
  const requests = [];
  const events = [];
  const rows = [];
  let googleCalls = 0;
  const oldFetch = globalThis.fetch;
  const providerFetch = freeFetch || (async (input, init = {}) => {
    const url = new URL(String(input));
    requests.push({ url, init });
    if (url.hostname === "msearch.gsi.go.jp") return jsonResponse(gsi);
    if (url.hostname === "api.openpoiapi.com") return jsonResponse(openpoi);
    throw new Error(`unexpected free-geocode URL: ${url.hostname}`);
  });
  globalThis.fetch = async (input) => {
    const url = new URL(String(input));
    if (url.hostname === "maps.googleapis.com" && url.pathname.endsWith("/geocode/json")) {
      googleCalls += 1;
      return jsonResponse({ status: "OK", results: [{
        geometry: { location: { lat: 35.680, lng: 139.760 } },
      }] });
    }
    throw new Error(`unexpected Google URL: ${url.hostname}${url.pathname}`);
  };
  try {
    const result = await geocodeAddress(query, MAPS_KEY, {
      tenantId,
      eventVersion: EVENT_VERSION,
      options: {
        _freeGeocodeFetch: async (input, init) => {
          if (freeFetch) return freeFetch(input, init);
          return providerFetch(input, init);
        },
        _freeGeocodeTimeoutMs: timeoutMs,
        _recordUsageEvent: async (event) => {
          events.push(event);
          await recordUsageEvent(event, { recordCost: async (row) => { rows.push(row); return true; } });
          return true;
        },
        ...extraOptions,
      },
    });
    return { result, requests, events, rows, googleCalls };
  } finally {
    globalThis.fetch = oldFetch;
  }
}

test("an exact GSI address candidate preserves house-number precision and avoids Google", async () => {
  const query = "東京都千代田区丸の内1-9-1";
  const result = await runGeocode({
    query,
    gsi: [gsiFeature("東京都千代田区丸の内１丁目９番１号")],
    extraOptions: {
      calendarTitle: "calendar title must not leave this process",
      description: "calendar description must not leave this process",
      attendees: ["calendar attendee must not leave this process"],
      eventId: "calendar event id must not leave this process",
      accountId: "calendar account id must not leave this process",
    },
  });

  assert.equal(result.result.provider, "gsi");
  assert.deepEqual([result.result.lat, result.result.lon], [35.681, 139.767]);
  assert.deepEqual(result.result.licenses, ["国土地理院コンテンツ利用規約 / PDL1.0"]);
  assert.equal(result.googleCalls, 0);
  assert.equal(result.requests.length, 1);
  assert.equal(result.requests[0].url.hostname, "msearch.gsi.go.jp");
  assert.deepEqual([...result.requests[0].url.searchParams.keys()], ["q"]);
  assert.equal(result.requests[0].url.searchParams.get("q"), query);
  assert.equal(JSON.stringify(result.events).includes(query), false);
  assert.equal(JSON.stringify(result.events).includes("calendar title"), false);
});

test("captured A4.1 provider fixtures reject coarse and ambiguous results before one Google fallback", async (t) => {
  const expectedFailures = {
    "gsi-full-address": "precision_loss",
    "openpoi-broad-search": "no_results",
    "openpoi-station-suggest": "ambiguous",
    "openpoi-branch-not-found": "no_results",
  };
  for (const fixture of geocodeFixtures.cases.filter((item) => expectedFailures[item.id])) {
    await t.test(fixture.id, async () => {
      const response = fixture.response;
      const payload = fixture.provider === "gsi"
        ? { count: response.count, truncated: response.truncated, features: response.captured_features }
        : { count: response.count, truncated: response.truncated,
          suggestions: response.captured_suggestions || response.captured_results };
      const result = await runGeocode({
        query: fixture.request.q,
        tenantId: `tenant-fixture-${fixture.id}`,
        [fixture.provider]: payload,
      });

      assert.equal(result.googleCalls, 1);
      assert.equal(result.events.find((event) => event.provider === fixture.provider)?.failureClass,
        expectedFailures[fixture.id]);
    });
  }
});

test("captured truncated GSI response is ambiguous for an address-shaped query", async () => {
  const fixture = geocodeFixtures.cases.find((item) => item.id === "gsi-ambiguous");
  const result = await runGeocode({
    query: "東京都千代田区丸の内3-8-1",
    tenantId: "tenant-fixture-gsi-truncated",
    gsi: {
      count: fixture.response.count,
      truncated: fixture.response.truncated,
      features: fixture.response.captured_features,
    },
  });

  assert.equal(result.googleCalls, 1);
  assert.equal(result.events.find((event) => event.provider === "gsi")?.failureClass, "ambiguous");
});

test("non-Japanese missing-address fixture bypasses free providers", async () => {
  const fixture = geocodeFixtures.cases.find((item) => item.id === "gsi-not-found");
  const result = await runGeocode({
    query: fixture.request.q,
    tenantId: "tenant-fixture-non-japanese",
    gsi: { count: fixture.response.count, truncated: fixture.response.truncated,
      features: fixture.response.captured_features },
  });

  assert.equal(result.requests.length, 0);
  assert.equal(result.googleCalls, 1);
  assert.equal(result.events.some((event) => event.provider === "gsi" || event.provider === "openpoi"), false);
});

test("a GSI title that drops part of the requested address falls back to one Google geocode", async () => {
  const query = "東京都千代田区丸の内1-9-2";
  const result = await runGeocode({
    query,
    gsi: [gsiFeature("東京都千代田区丸の内一丁目９番")],
  });

  assert.deepEqual(result.result, { lat: 35.680, lon: 139.760 });
  assert.equal(result.googleCalls, 1);
  assert.equal(result.requests.length, 1);
  assert.equal(result.requests[0].url.hostname, "msearch.gsi.go.jp");
  assert.equal(result.events.find((event) => event.provider === "gsi")?.failureClass, "precision_loss");
});

test("one exact OpenPOI name with complete provenance is accepted and preserved", async () => {
  const query = "渋谷ヒカリエ";
  const candidate = poiCandidate("　渋谷ヒカリエ ", {
    licenses: ["CC BY 4.0", "CDLA-Permissive-2.0"],
    attributions: ["Fixture POI source", "Fixture municipality source"],
  });
  const result = await runGeocode({ query, openpoi: { suggestions: [candidate] } });

  assert.equal(result.result.provider, "openpoi");
  assert.deepEqual([result.result.lat, result.result.lon], [35.659, 139.700]);
  assert.deepEqual(result.result.licenses, candidate.licenses);
  assert.deepEqual(result.result.attributions, candidate.attributions);
  assert.deepEqual(result.result.sourceRecord, {
    source: candidate.source,
    licenses: candidate.licenses,
    attributions: candidate.attributions,
  });
  assert.equal(result.result.attributionUrl, "https://openpoiapi.com/attribution.html");
  assert.equal(result.googleCalls, 0);
  assert.equal(result.requests[0].url.pathname, "/v1/suggest");
  assert.deepEqual([...result.requests[0].url.searchParams.keys()].sort(), ["limit", "q"]);
  assert.equal(result.requests[0].url.searchParams.get("q"), query);
});

test("a named place with a prefecture and ward still uses OpenPOI Suggest", async () => {
  const query = "東京都台東区浅草寺";
  const result = await runGeocode({ query, openpoi: { suggestions: [poiCandidate(query)] } });

  assert.equal(result.result.provider, "openpoi");
  assert.equal(result.googleCalls, 0);
  assert.equal(result.requests.length, 1);
  assert.equal(result.requests[0].url.hostname, "api.openpoiapi.com");
  assert.equal(result.requests[0].url.pathname, "/v1/suggest");
});

test("Kanji-number and municipality-scoped addresses use only GSI before Google fallback", async (t) => {
  const queries = [
    "渋谷区神南一丁目十九番十一号",
    "渋谷区神南",
    "東京都渋谷区神南一丁目十九番十一号 神南ビル",
  ];
  for (const [index, query] of queries.entries()) {
    await t.test(query, async () => {
      const result = await runGeocode({
        query,
        tenantId: `tenant-kanji-address-${index}`,
        gsi: [gsiFeature(query, [181, 35.661])],
      });

      assert.equal(result.requests.length, 1);
      assert.equal(result.requests[0].url.hostname, "msearch.gsi.go.jp");
      assert.equal(result.googleCalls, 1);
      assert.equal(result.events.some((event) => event.provider === "openpoi"), false);
      assert.equal(result.events.find((event) => event.provider === "gsi")?.failureClass, "invalid_coordinates");
    });
  }
});

test("an OpenPOI name with two exact suggestions remains ambiguous and falls back once", async () => {
  const query = "東京駅";
  const first = poiCandidate(query, { lat: 35.699383927107796, lng: 139.77333040976976 });
  const second = poiCandidate(query, { address: "東京都台東区", lat: 35.72119974584146, lng: 139.77844276737827 });
  const result = await runGeocode({ query, openpoi: { suggestions: [first, second] } });

  assert.deepEqual(result.result, { lat: 35.680, lon: 139.760 });
  assert.equal(result.googleCalls, 1);
  assert.equal(result.events.find((event) => event.provider === "openpoi")?.failureClass, "ambiguous");
});

test("OpenPOI missing license or attribution provenance is rejected", async (t) => {
  const cases = [
    { name: "missing licenses", candidate: poiCandidate("出典不足会場", { licenses: [] }) },
    { name: "missing attributions", candidate: poiCandidate("帰属不足会場", { attributions: [] }) },
  ];
  for (const scenario of cases) {
    await t.test(scenario.name, async () => {
      const result = await runGeocode({
        query: scenario.candidate.name,
        openpoi: { suggestions: [scenario.candidate] },
      });
      assert.equal(result.googleCalls, 1);
      assert.equal(result.events.find((event) => event.provider === "openpoi")?.failureClass, "missing_provenance");
    });
  }
});

test("OpenPOI Apache-2.0 records are rejected until a NOTICE is available", async () => {
  const candidate = poiCandidate("Apache対象会場", { licenses: ["Apache-2.0"] });
  const result = await runGeocode({ query: candidate.name, openpoi: { suggestions: [candidate] } });

  assert.equal(result.googleCalls, 1);
  assert.equal(result.events.find((event) => event.provider === "openpoi")?.failureClass, "unsupported_license");
});

test("OpenPOI invalid and out-of-Japan coordinates are rejected", async (t) => {
  const scenarios = [
    { name: "invalid coordinate", candidate: poiCandidate("座標不正会場", { lat: 91, lng: 139.7 }) },
    { name: "outside Japan", candidate: poiCandidate("日本国外会場", { lat: 40.7, lng: -74.0 }) },
  ];
  for (const scenario of scenarios) {
    await t.test(scenario.name, async () => {
      const result = await runGeocode({
        query: scenario.candidate.name,
        openpoi: { suggestions: [scenario.candidate] },
      });
      assert.equal(result.googleCalls, 1);
      assert.equal(result.events.find((event) => event.provider === "openpoi")?.failureClass,
        scenario.name === "invalid coordinate" ? "invalid_coordinates" : "outside_japan");
    });
  }
});

test("zero free-provider results fall back to exactly one Google geocode", async () => {
  const result = await runGeocode({ query: "東京都新宿区fixture無結果1-2-3", gsi: [] });

  assert.equal(result.googleCalls, 1);
  assert.equal(result.events.find((event) => event.provider === "gsi")?.failureClass, "no_results");
});

test("free-provider timeout falls back to exactly one Google geocode", async () => {
  const result = await runGeocode({
    query: "タイムアウト会場",
    timeoutMs: 5,
    freeFetch: async () => new Promise(() => {}),
  });

  assert.equal(result.googleCalls, 1);
  assert.equal(result.events.find((event) => event.provider === "openpoi")?.failureClass, "timeout");
});

test("free candidate cache preserves provenance and isolates tenant plus normalized query", async () => {
  const query = "free-cache対象会場";
  const poi = { suggestions: [poiCandidate(query)] };
  const originalFetch = globalThis.fetch;
  let providerCalls = 0;
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({
    status: "OK", results: [{ geometry: { location: { lat: 35.68, lng: 139.76 } } }],
  }) });
  const run = (tenantId, value) => geocodeAddress(value, MAPS_KEY, {
    tenantId,
    options: { _freeGeocodeFetch: async () => { providerCalls += 1; return jsonResponse(poi); } },
  });
  try {
    const first = await run("free-cache-tenant-a", query);
    const normalizedHit = await run("free-cache-tenant-a", `\u3000${query}  `);
    const otherTenant = await run("free-cache-tenant-b", query);
    assert.deepEqual(normalizedHit.sourceRecord, first.sourceRecord);
    assert.deepEqual(otherTenant.sourceRecord, first.sourceRecord);
    assert.deepEqual(normalizedHit.attributions, first.attributions);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.equal(providerCalls, 2);
});

test("free-provider usage has operation, request/result, zero estimate, and no raw query", async () => {
  const query = "usage-private会場";
  const result = await runGeocode({ query, openpoi: { suggestions: [poiCandidate(query)] } });

  assert.equal(result.events.length, 1);
  assert.equal(result.events[0].provider, "openpoi");
  assert.equal(result.events[0].operation, "Suggest");
  assert.equal(result.events[0].outcome, "success");
  assert.equal(result.events[0].providerUnits, 1);
  assert.equal(result.events[0].estimatedCostUsd, 0);
  assert.equal(result.events[0].meta.event_version, EVENT_VERSION);
  assert.equal(JSON.stringify(result.events).includes(query), false);
  assert.equal(result.rows[0].estUsd, 0);
  assert.equal(result.rows[0].meta.actual_usd, null);
  assert.equal(result.rows[0].meta.billing_status, "unknown");
  assert.equal(result.rows[0].meta.operation, "Suggest");
});
