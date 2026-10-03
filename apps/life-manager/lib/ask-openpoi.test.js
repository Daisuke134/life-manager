"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { agentResolveLocation, placesSearch, recallOrResolve } = require("./ask.js");

test("Japan location resolution uses OpenPOI before Google Places and preserves attribution", async () => {
  let googleCalled = false;
  const search = await placesSearch("東京駅", "maps-key", {
    openPoiSearch: async () => ({
      candidates: [{ name: "東京駅", address: "東京都千代田区丸の内", lat: 35.681, lon: 139.767, licenses: ["CC BY 4.0"] }],
      attributions: ["OpenPOI API"],
    }),
  });
  assert.equal(search.provider, "openpoi");
  assert.equal(search.results[0].address, "東京都千代田区丸の内");
  assert.deepEqual(search.results[0].licenses, ["CC BY 4.0"]);
  assert.deepEqual(search.licenses, ["CC BY 4.0"]);
  assert.deepEqual(search.attributions, ["OpenPOI API"]);
  assert.equal(search.attributionUrl, "https://openpoiapi.com/attribution.html");
  assert.equal(googleCalled, false);
});

test("agent receives OpenPOI candidates without a Google fallback", async () => {
  const calls = [];
  const result = await agentResolveLocation({ summary: "東京駅で会議", location: "" }, {
    home: "東京都", mapsKey: "maps-key", geminiKey: "gemini-key",
    openPoiSearch: async () => ({ candidates: [{ name: "東京駅", address: "東京都千代田区丸の内", lat: 35.681, lon: 139.767, licenses: ["CC BY 4.0"] }], attributions: ["OpenPOI API"], attributionUrl: "https://openpoiapi.com/attribution.html" }),
    geminiRaw: async (body) => {
      calls.push(body);
      return calls.length === 1
        ? { candidates: [{ content: { parts: [{ functionCall: { name: "places_search", args: { query: "東京駅" } } }] } }] }
        : { candidates: [{ content: { parts: [{ functionCall: { name: "submit_answer", args: { online: false, confident: true, location: "東京都千代田区丸の内", source: "web_search" } } }] } }] };
    },
  });
  assert.equal(result.kind, "filled");
  assert.deepEqual(result.attributions, ["OpenPOI API"]);
  assert.deepEqual(result.licenses, ["CC BY 4.0"]);
  assert.equal(result.provider, "openpoi");
  assert.equal(result.attributionUrl, "https://openpoiapi.com/attribution.html");
  assert.equal(calls.length, 2);
});

test("remembered location returns as memory without invoking the provider resolver", async () => {
  let resolverCalled = false;
  const result = await recallOrResolve(
    { summary: "東京駅で会議", recurringEventId: "series-1" },
    {
      uid: "u1",
      recall: async () => "東京都千代田区丸の内",
      resolve: async () => { resolverCalled = true; return { kind: "ask" }; },
    },
  );
  assert.deepEqual(result, { kind: "filled", location: "東京都千代田区丸の内", fromMemory: true });
  assert.equal(resolverCalled, false);
});

test("Google Places fallback is denied when the provider budget is stopped", async () => {
  let googleCalled = false;
  const result = await placesSearch("店", "maps-key", {
    openPoiSearch: async () => ({ candidates: [], attributions: [] }),
    authorizeProviderOperation: async () => ({ allowed: false, state: "stopped", reason: "budget_stopped" }),
    fetchImpl: async () => { googleCalled = true; return { ok: true, json: async () => ({ results: [] }) }; },
  });
  assert.equal(result.provider, "budget");
  assert.equal(googleCalled, false);
});
