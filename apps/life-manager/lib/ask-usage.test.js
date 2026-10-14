"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { agentResolveLocation, agentResolveTravelOrigin, agentMatchTravelOriginReply, agentSearchCandidate } = require("./ask.js");

test("travel-origin agent selects only a supplied candidate with high confidence", async () => {
  const oldFetch = globalThis.fetch;
  const usage = [];
  let requestBody;
  globalThis.fetch = async (url, init) => {
    assert.match(String(url), /generativelanguage\.googleapis\.com/);
    requestBody = JSON.parse(init.body);
    return { ok: true, status: 200, json: async () => ({
      usageMetadata: { promptTokenCount: 60, candidatesTokenCount: 10, totalTokenCount: 70 },
      candidates: [{ content: { parts: [{ text: JSON.stringify({ candidateId: "previous-0", confidence: "high" }) }] } }],
    }) };
  };
  try {
    const result = await agentResolveTravelOrigin({
      summary: "Dinner", location: "Venue", startIso: "2030-01-01T19:00:00+09:00", timezone: "Asia/Tokyo",
    }, {
      geminiKey: "fixture-gemini-key", uid: "tenant-origin",
      candidates: [
        { id: "home", location: "Home" },
        { id: "previous-0", location: "Office" },
      ],
      scheduledEvents: [{ summary: "Work", location: "Office", startIso: "2030-01-01T09:00:00+09:00",
        endIso: "2030-01-01T17:00:00+09:00" }],
      recordUsageEvent: async (event) => { usage.push(event); return true; },
    });
    assert.deepEqual(result, { kind: "selected", candidateId: "previous-0" });
    assert.match(requestBody.contents[0].parts[0].text, /Do not treat saved home as the user's live location/);
    assert.match(requestBody.contents[0].parts[0].text, /repeatedly used office, 09:00–17:00/);
    assert.ok(usage.some((event) => event.tenantId === "tenant-origin" && event.feature === "travel_origin"));
    assert.equal(JSON.stringify(usage).includes("Office"), false, "usage metadata must not retain Calendar places");
  } finally { globalThis.fetch = oldFetch; }
});

test("travel-origin agent abstains on low confidence or an invented candidate id", async () => {
  const oldFetch = globalThis.fetch;
  const answers = [
    { candidateId: "home", confidence: "low" },
    { candidateId: "invented", confidence: "high" },
  ];
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({
    candidates: [{ content: { parts: [{ text: JSON.stringify(answers.shift()) }] } }],
  }) });
  try {
    const event = { summary: "Dinner", location: "Venue", startIso: "2030-01-01T19:00:00+09:00" };
    const options = { geminiKey: "fixture", candidates: [{ id: "home", location: "Home" }] };
    assert.deepEqual(await agentResolveTravelOrigin(event, options), { kind: "unresolved" });
    assert.deepEqual(await agentResolveTravelOrigin(event, options), { kind: "unresolved" });
  } finally { globalThis.fetch = oldFetch; }
});

test("travel-origin reply selects only a supplied candidate and rejects invented ids", async () => {
  const oldFetch = globalThis.fetch;
  const answers = [
    { candidateId: "office", confidence: "high" },
    { candidateId: "invented", confidence: "high" },
  ];
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({
    candidates: [{ content: { parts: [{ text: JSON.stringify(answers.shift()) }] } }],
  }) });
  try {
    const options = {
      geminiKey: "fixture-gemini-key", uid: "tenant-origin-reply",
      candidates: [
        { id: "home", location: "Home", source: "saved_home" },
        { id: "office", location: "MUIT 生駒", source: "repeated_calendar_location" },
      ],
    };
    assert.deepEqual(await agentMatchTravelOriginReply("office", options), {
      kind: "selected", candidateId: "office", location: "MUIT 生駒",
    });
    assert.deepEqual(await agentMatchTravelOriginReply("somewhere else", options), { kind: "unresolved" });
  } finally { globalThis.fetch = oldFetch; }
});

test("travel-origin reply accepts only a location phrase present in the user's message", async () => {
  const oldFetch = globalThis.fetch;
  const answers = [
    { candidateId: null, newLocation: "渋谷駅", confidence: "high" },
    { candidateId: null, newLocation: "invented address", confidence: "high" },
  ];
  globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => ({
    candidates: [{ content: { parts: [{ text: JSON.stringify(answers.shift()) }] } }],
  }) });
  try {
    const options = {
      geminiKey: "fixture-gemini-key", uid: "tenant-origin-reply",
      candidates: [{ id: "home", location: "Home", source: "saved_home" }],
    };
    assert.deepEqual(await agentMatchTravelOriginReply("渋谷駅から向かいます", options), {
      kind: "selected", candidateId: null, location: "渋谷駅",
    });
    assert.deepEqual(await agentMatchTravelOriginReply("別の場所", options), { kind: "unresolved" });
  } finally { globalThis.fetch = oldFetch; }
});

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
