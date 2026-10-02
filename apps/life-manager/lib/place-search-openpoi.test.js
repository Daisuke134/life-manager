"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { searchOpenPoi } = require("./place-search-openpoi.js");

test("OpenPOI maps facility candidates and preserves licenses/attributions", async () => {
  let requested;
  const result = await searchOpenPoi("ラーメン", {
    center: { lng: 139.767052, lat: 35.681236 }, radius: 300, limit: 3,
    fetchImpl: async (url) => {
      requested = new URL(url);
      return { ok: true, json: async () => ({ count: 1, results: [{
        name: "店A", address: "東京都千代田区", prefecture: "東京都", city: "千代田区",
        lat: 35.681, lng: 139.767, category: "restaurant", source: "jff",
        licenses: ["CC BY 4.0"], attributions: ["東京都データ"],
      }] }) };
    },
  });
  assert.equal(requested.pathname, "/v1/search");
  assert.equal(requested.searchParams.get("q"), "ラーメン");
  assert.equal(requested.searchParams.get("center"), "139.767052,35.681236");
  assert.equal(requested.searchParams.get("radius"), "300");
  assert.deepEqual(result.candidates, [{
    name: "店A", address: "東京都千代田区", lat: 35.681, lon: 139.767,
    category: "restaurant", source: "jff", licenses: ["CC BY 4.0"], attributions: ["東京都データ"],
  }]);
  assert.deepEqual(result.attributions, ["東京都データ"]);
});

test("OpenPOI empty results are a safe no-candidate response", async () => {
  const result = await searchOpenPoi("存在しない店", { fetchImpl: async () => ({ ok: true, json: async () => ({ count: 0, results: [] }) }) });
  assert.deepEqual(result.candidates, []);
  assert.deepEqual(result.attributions, []);
});

test("OpenPOI provider failure is explicit and does not become Google success", async () => {
  const result = await searchOpenPoi("店", { fetchImpl: async () => ({ ok: false, status: 503, json: async () => ({}) }) });
  assert.equal(result.status, "unavailable");
  assert.deepEqual(result.candidates, []);
});
