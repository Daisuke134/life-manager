"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { agentResolveLocation, placesSearch } = require("./ask.js");

test("Japan location resolution uses OpenPOI before Google Places and preserves attribution", async () => {
  let googleCalled = false;
  const search = await placesSearch("東京駅", "maps-key", {
    openPoiSearch: async () => ({
      candidates: [{ name: "東京駅", address: "東京都千代田区丸の内", lat: 35.681, lon: 139.767 }],
      attributions: ["OpenPOI API"],
    }),
  });
  assert.equal(search.provider, "openpoi");
  assert.equal(search.results[0].address, "東京都千代田区丸の内");
  assert.deepEqual(search.attributions, ["OpenPOI API"]);
  assert.equal(googleCalled, false);
});

test("agent receives OpenPOI candidates without a Google fallback", async () => {
  const calls = [];
  const result = await agentResolveLocation({ summary: "東京駅で会議", location: "" }, {
    home: "東京都", mapsKey: "maps-key", geminiKey: "gemini-key",
    openPoiSearch: async () => ({ candidates: [{ name: "東京駅", address: "東京都千代田区丸の内", lat: 35.681, lon: 139.767 }], attributions: ["OpenPOI API"] }),
    geminiRaw: async (body) => {
      calls.push(body);
      return calls.length === 1
        ? { candidates: [{ content: { parts: [{ functionCall: { name: "places_search", args: { query: "東京駅" } } }] } }] }
        : { candidates: [{ content: { parts: [{ functionCall: { name: "submit_answer", args: { online: false, confident: true, location: "東京都千代田区丸の内", source: "web_search" } } }] } }] };
    },
  });
  assert.equal(result.kind, "filled");
  assert.deepEqual(result.attributions, ["OpenPOI API"]);
  assert.equal(calls.length, 2);
});
