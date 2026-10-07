"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { agentResolveLocation, agentSearchCandidate } = require("./ask.js");

const LOCATION_EVENT = {
  id: "event-location-1",
  summary: "Lunch with Mai",
  description: "Meet in person for lunch.",
  location: "",
  start: { dateTime: "2026-10-08T12:00:00+09:00", timeZone: "Asia/Tokyo" },
  end: { dateTime: "2026-10-08T13:00:00+09:00", timeZone: "Asia/Tokyo" },
  organizer: { email: "organizer@example.test" },
};
const MAPS_QUERY_1 = "Kumo Cafe Shibuya";
const MAPS_QUERY_2 = "Kumo Coffee Tokyo";

function geminiResponse(parts, promptTokenCount) {
  const candidatesTokenCount = 20;
  return {
    candidates: [{ content: { role: "model", parts }, finishReason: "STOP" }],
    usageMetadata: {
      promptTokenCount,
      candidatesTokenCount,
      totalTokenCount: promptTokenCount + candidatesTokenCount,
    },
  };
}

function placesResponse(name, formattedAddress) {
  return {
    ok: true,
    status: 200,
    body: { results: [{ name, formatted_address: formattedAddress }], status: "OK" },
  };
}

function placesStatusResponse(providerStatus, { ok = true, httpStatus = 200 } = {}) {
  return { ok, status: httpStatus, body: { results: [], status: providerStatus } };
}

function assertPlacesUsageEvent(event, outcome, failureClass = null) {
  assert.equal(event.tenantId, "tenant-location-1");
  assert.equal(event.provider, "google_maps");
  assert.equal(event.feature, "ask_resolve_location");
  assert.equal(event.operation, "places_text_search");
  assert.equal(event.outcome, outcome);
  assert.equal(event.failureClass, failureClass);
  assert.equal(event.providerUnits, 1);
  assert.equal(event.providerUnit, "request");
  assert.equal(event.estimatedCostUsd, null);
  assert.deepEqual({
    estimate_status: event.meta.estimate_status,
    pricing_basis: event.meta.pricing_basis,
    pricing_version: event.meta.pricing_version,
  }, {
    estimate_status: "unavailable",
    pricing_basis: "unavailable",
    pricing_version: null,
  });
}

async function runAgentResolveLocation({ geminiResponses, placesResponses, recordUsageEvent }) {
  const placesQueries = [];
  const geminiRequests = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (input, options = {}) => {
    const url = new URL(String(input));
    if (url.hostname === "generativelanguage.googleapis.com") {
      assert.equal(options.method, "POST");
      geminiRequests.push(JSON.parse(options.body));
      const response = geminiResponses.shift();
      assert.ok(response, "unexpected Gemini request");
      return { ok: true, status: 200, json: async () => response };
    }
    if (url.hostname === "maps.googleapis.com") {
      assert.equal(url.pathname, "/maps/api/place/textsearch/json");
      assert.equal(url.searchParams.get("key"), "test-maps-key");
      placesQueries.push(url.searchParams.get("query"));
      const response = placesResponses.shift();
      assert.ok(response, "unexpected Places request");
      if (response instanceof Error) throw response;
      return { ok: response.ok, status: response.status, json: async () => response.body };
    }
    throw new Error(`unexpected fetch host: ${url.hostname}`);
  };

  try {
    const result = await agentResolveLocation(LOCATION_EVENT, {
      home: "Shibuya, Tokyo",
      mapsKey: "test-maps-key",
      geminiKey: "test-gemini-key",
      uid: "tenant-location-1",
      recordUsageEvent,
    });
    return { result, placesQueries, geminiRequests };
  } finally {
    globalThis.fetch = originalFetch;
  }
}

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

test("location resolution records one unpriced Places event per request without storing search queries", async () => {
  const geminiResponses = [
    geminiResponse([
      { functionCall: { id: "search-1", name: "places_search", args: { query: MAPS_QUERY_1 } } },
      { functionCall: { id: "search-2", name: "places_search", args: { query: MAPS_QUERY_2 } } },
    ], 120),
    geminiResponse([{
      functionCall: { id: "answer-1", name: "submit_answer", args: {
        online: false,
        confident: true,
        location: "1-5 Dogenzaka, Shibuya City, Tokyo 150-0043, Japan",
        source: "web_search",
      } },
    }], 160),
  ];
  const placesResponses = [
    placesResponse("Kumo Cafe", "2-1 Shibuya, Shibuya City, Tokyo 150-0002, Japan"),
    placesResponse("Kumo Coffee", "1-5 Dogenzaka, Shibuya City, Tokyo 150-0043, Japan"),
  ];
  const usage = [];
  const { result, placesQueries } = await runAgentResolveLocation({
    geminiResponses,
    placesResponses,
    recordUsageEvent: async (event) => { usage.push(event); return true; },
  });

  assert.deepEqual(placesQueries, [MAPS_QUERY_1, MAPS_QUERY_2]);
  assert.equal(geminiResponses.length, 0);
  assert.equal(placesResponses.length, 0);
  assert.deepEqual(result, {
    kind: "filled",
    location: "1-5 Dogenzaka, Shibuya City, Tokyo 150-0043, Japan",
    resolvedFrom: "web_search",
  });
  const placesEvents = usage.filter((event) => event.provider === "google_maps");
  assert.equal(placesEvents.length, placesQueries.length);
  for (const event of placesEvents) {
    assertPlacesUsageEvent(event, "success");
    assert.equal(JSON.stringify(event).includes("test-maps-key"), false);
    for (const query of [MAPS_QUERY_1, MAPS_QUERY_2]) {
      assert.equal(JSON.stringify(event).includes(query), false);
    }
  }
});

test("location resolution succeeds when the Places usage writer fails", async () => {
  const geminiResponses = [
    geminiResponse([{ functionCall: {
      id: "search-1", name: "places_search", args: { query: MAPS_QUERY_1 },
    } }], 120),
    geminiResponse([{ functionCall: {
      id: "answer-1", name: "submit_answer", args: {
        online: false,
        confident: true,
        location: "2-1 Shibuya, Shibuya City, Tokyo 150-0002, Japan",
        source: "web_search",
      },
    } }], 160),
  ];
  const placesResponseBody = placesResponse(
    "Kumo Cafe", "2-1 Shibuya, Shibuya City, Tokyo 150-0002, Japan",
  );
  const failedWrites = [];
  const { result, placesQueries, geminiRequests } = await runAgentResolveLocation({
    geminiResponses,
    placesResponses: [placesResponseBody],
    recordUsageEvent: async (event) => {
      if (event.provider === "google_maps") {
        failedWrites.push(event);
        throw new Error("usage writer unavailable");
      }
      return true;
    },
  });

  assert.deepEqual(placesQueries, [MAPS_QUERY_1]);
  assert.deepEqual(result, {
    kind: "filled",
    location: "2-1 Shibuya, Shibuya City, Tokyo 150-0002, Japan",
    resolvedFrom: "web_search",
  });
  assert.equal(failedWrites.length, placesQueries.length);
  assertPlacesUsageEvent(failedWrites[0], "success");
  assert.deepEqual(geminiRequests[1].contents.at(-1).parts[0].functionResponse, {
    name: "places_search",
    response: { results: [{ name: "Kumo Cafe", address: "2-1 Shibuya, Shibuya City, Tokyo 150-0002, Japan" }] },
  });
});

test("Places network failure records one failure event and preserves the ask outcome", async () => {
  const geminiResponses = [
    geminiResponse([{ functionCall: {
      id: "search-1", name: "places_search", args: { query: MAPS_QUERY_1 },
    } }], 120),
    geminiResponse([{ functionCall: {
      id: "answer-1", name: "submit_answer", args: {
        online: false,
        confident: false,
        location: "",
        source: "web_search",
      },
    } }], 160),
  ];
  const usage = [];
  const { result, placesQueries } = await runAgentResolveLocation({
    geminiResponses,
    placesResponses: [new TypeError("fetch failed")],
    recordUsageEvent: async (event) => { usage.push(event); return true; },
  });

  assert.deepEqual(placesQueries, [MAPS_QUERY_1]);
  assert.deepEqual(result, { kind: "ask" });
  const placesEvents = usage.filter((event) => event.provider === "google_maps");
  assert.equal(placesEvents.length, placesQueries.length);
  assertPlacesUsageEvent(placesEvents[0], "failure", "transport");
  assert.equal(JSON.stringify(placesEvents[0]).includes(MAPS_QUERY_1), false);
  assert.equal(JSON.stringify(placesEvents[0]).includes("test-maps-key"), false);
});

for (const { name, response, outcome, failureClass } of [
  { name: "ZERO_RESULTS", response: placesStatusResponse("ZERO_RESULTS"), outcome: "success", failureClass: null },
  { name: "provider denial", response: placesStatusResponse("REQUEST_DENIED"), outcome: "failure", failureClass: "provider" },
  { name: "HTTP error", response: placesStatusResponse("OK", { ok: false, httpStatus: 403 }), outcome: "failure", failureClass: "provider" },
]) {
  test(`Places ${name} records one provider usage event`, async () => {
    const geminiResponses = [
      geminiResponse([{ functionCall: {
        id: "search-1", name: "places_search", args: { query: MAPS_QUERY_1 },
      } }], 120),
      geminiResponse([{ functionCall: {
        id: "answer-1", name: "submit_answer", args: {
          online: false, confident: false, location: "", source: "web_search",
        },
      } }], 160),
    ];
    const usage = [];
    const { result, placesQueries } = await runAgentResolveLocation({
      geminiResponses,
      placesResponses: [response],
      recordUsageEvent: async (event) => { usage.push(event); return true; },
    });

    assert.deepEqual(placesQueries, [MAPS_QUERY_1]);
    assert.deepEqual(result, { kind: "ask" });
    const placesEvents = usage.filter((event) => event.provider === "google_maps");
    assert.equal(placesEvents.length, placesQueries.length);
    assertPlacesUsageEvent(placesEvents[0], outcome, failureClass);
  });
}
