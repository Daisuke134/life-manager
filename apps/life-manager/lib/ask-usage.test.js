"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { agentResolveLocation, agentSearchCandidate } = require("./ask.js");

test("resolved-location search caps Places calls and meters each tenant request without query data", async () => {
  const usage = [];
  const placesRequests = [];
  const geminiResponses = [
    { usageMetadata: { promptTokenCount: 100, candidatesTokenCount: 20, totalTokenCount: 120 },
      candidates: [{ content: { parts: [1, 2, 3, 4, 5].map((n) => ({ functionCall: {
        name: "places_search", args: { query: `private venue variation ${n}` },
      } })) } }] },
    { usageMetadata: { promptTokenCount: 80, candidatesTokenCount: 15, totalTokenCount: 95 },
      candidates: [{ content: { parts: [{ functionCall: { name: "submit_answer", args: {
        online: false, confident: true, location: "1 Example Street", source: "web_search",
      } } }] } }] },
  ];
  const oldFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const requestUrl = String(url);
    if (requestUrl.includes("generativelanguage.googleapis.com")) {
      return { ok: true, status: 200, json: async () => geminiResponses.shift() };
    }
    if (requestUrl.includes("maps.googleapis.com/maps/api/place/textsearch")) {
      placesRequests.push(requestUrl);
      return { ok: true, status: 200, json: async () => ({ status: "OK", results: [] }) };
    }
    throw new Error("unexpected fake fetch URL");
  };
  try {
    const result = await agentResolveLocation({
      id: "private-event-id", summary: "private calendar title", location: "private room",
      description: "private event description", start: { dateTime: "2030-01-01T10:00:00Z" },
    }, {
      home: "private home address", mapsKey: "fixture-maps-key", geminiKey: "fixture-gemini-key",
      uid: "tenant-1",
      recordUsageEvent: async (event) => { usage.push(event); throw new Error("cost ledger unavailable"); },
    });

    assert.equal(result.kind, "filled");
  } finally {
    globalThis.fetch = oldFetch;
  }

  assert.equal(placesRequests.length, 3, "one event can trigger at most three billable Places searches");
  const placesUsage = usage.filter((event) => event.provider === "google_maps");
  assert.equal(placesUsage.length, 3);
  assert.ok(placesUsage.every((event) => event.tenantId === "tenant-1"));
  assert.ok(placesUsage.every((event) => event.providerUnits === 1 && event.providerUnit === "request"));
  assert.ok(placesUsage.every((event) => event.estimatedCostUsd === 0.04));
  assert.ok(placesUsage.every((event) => event.meta.sku === "Places - Text Search"));
  assert.ok(placesUsage.every((event) => event.meta.pricing_version === "lm-google-maps-estimate-2026-10-08-v1"));
  const serializedUsage = JSON.stringify(usage);
  for (const privateValue of ["private venue variation", "private calendar title", "private room", "private home address"]) {
    assert.equal(serializedUsage.includes(privateValue), false);
  }
});

test("candidate research meters tenant-scoped Gemini and Search grounding separately", async () => {
  const usage = [];
  const responses = [
    { usageMetadata: { promptTokenCount: 100, candidatesTokenCount: 20, totalTokenCount: 120 },
      candidates: [{ content: { parts: [{ text: "venue evidence" }] } }] },
    { usageMetadata: { promptTokenCount: 50, candidatesTokenCount: 10, totalTokenCount: 60 },
      candidates: [{ content: { parts: [{ functionCall: { name: "submit_candidate",
        args: { found: true, candidate: "Tokyo Station", source: "web_search" } } }] } }] },
  ];
  const oldFetch = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => responses.shift() });
  try {
    const result = await agentSearchCandidate({ summary: "meeting", description: "" }, {
      uid: "tenant-1", geminiKey: "test-key", mailAvailable: async () => false,
      recordUsageEvent: async (event) => { usage.push(event); return true; },
    });
    assert.equal(result.found, true);
  } finally {
    globalThis.fetch = oldFetch;
  }
  assert.deepEqual(usage.map((event) => [event.tenantId, event.provider, event.feature]), [
    ["tenant-1", "gemini", "ask_candidate_search"],
    ["tenant-1", "google_search_grounding", "ask_candidate_search"],
    ["tenant-1", "gemini", "ask_candidate_extract"],
  ]);
});
