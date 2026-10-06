"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { geminiUsageEvents, persistGeminiUsage, persistGeminiFailure } = require("./gemini-usage.js");
const { normalizeUsageEvent, recordUsageEvent } = require("./usage-event.js");

test("separates Gemini token cost from Search grounding cost", () => {
  const events = geminiUsageEvents({
    usageMetadata: { promptTokenCount: 1000, candidatesTokenCount: 200, totalTokenCount: 1200 },
    candidates: [{ content: { parts: [{ text: "ok" }] } }],
  }, { tenantId: "t1", feature: "ask_location", grounded: true });
  assert.equal(events.length, 2);
  assert.deepEqual(events.map((e) => [e.provider, e.providerUnits, e.estimatedCostUsd]), [
    ["gemini", 1200, 0.0008],
    ["google_search_grounding", 1, 0.035],
  ]);
  assert.equal(events[0].meta.input_tokens, 1000);
  assert.equal(events[0].meta.output_tokens, 200);
});

test("missing usage metadata stays explicitly unestimated", () => {
  const [event] = geminiUsageEvents({}, { tenantId: "t1", feature: "ask_location" });
  assert.equal(event.outcome, "failure");
  assert.equal(event.providerUnits, null);
  assert.equal(event.estimatedCostUsd, null);
  assert.equal(event.meta.estimate_status, "unavailable");
});

test("unknown model pricing stays unavailable instead of inventing a zero estimate", () => {
  const [event] = geminiUsageEvents({
    usageMetadata: { promptTokenCount: 10, candidatesTokenCount: 5, totalTokenCount: 15 },
  }, { tenantId: "t1", feature: "ask_location", model: "future-model" });

  assert.equal(event.providerUnits, 15);
  assert.equal(event.estimatedCostUsd, null);
  assert.equal(event.meta.model, null);
  assert.equal(event.meta.estimate_status, "unavailable");
  assert.equal(event.meta.pricing_version, null);
  assert.equal(normalizeUsageEvent(event).meta.pricing_version, null);
});

test("persistGeminiUsage writes every normalized event through an injected writer", async () => {
  const rows = [];
  assert.equal(await persistGeminiUsage({
    usageMetadata: { promptTokenCount: 10, candidatesTokenCount: 5, totalTokenCount: 15 },
    candidates: [{}],
  }, { tenantId: "t1", feature: "specialist", grounded: true }, {
    recordUsageEvent: async (row) => { rows.push(row); return true; },
  }), true);
  assert.equal(rows.length, 2);
  assert.deepEqual(rows.map((row) => row.provider), ["gemini", "google_search_grounding"]);
});

test("persistGeminiUsage accepts token metadata through the real usage normalizer", async () => {
  const rows = [];
  const ok = await persistGeminiUsage({
    usageMetadata: { promptTokenCount: 10, candidatesTokenCount: 5, totalTokenCount: 15 },
    candidates: [{}],
  }, { tenantId: "t1", feature: "specialist" }, {
    recordUsageEvent: (event) => recordUsageEvent(event, {
      recordCost: async (row) => { rows.push(row); return true; },
      runtimeEnv: {},
    }),
  });

  assert.equal(ok, true);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].meta.input_tokens, 10);
  assert.equal(rows[0].meta.output_tokens, 5);
});

test("uses the 2026 Gemini 3.7 Flash and grounding rates", () => {
  const events = geminiUsageEvents({ status: "completed",
    usageMetadata: { promptTokenCount: 1000, candidatesTokenCount: 100, totalTokenCount: 1100 },
  }, { tenantId: "t1", feature: "scout", model: "gemini-3.7-flash", grounded: true, success: true });
  assert.deepEqual(events.map((event) => event.estimatedCostUsd), [0.001125, 0.014]);
  assert.equal(events[0].operation, "generate_content");
  assert.equal(events[0].meta.pricing_version, "lm-gemini-estimate-2026-10-06-v1");
  assert.equal(events[1].operation, "search_grounding");
});

test("provider failure is observable without inventing token or grounding cost", async () => {
  const rows = [];
  await persistGeminiFailure({ tenantId: "t1", feature: "scout", model: "gemini-3.7-flash",
    grounded: true, failureClass: "provider_5xx" }, {
    recordUsageEvent: async (row) => { rows.push(row); return true; },
  });
  assert.equal(rows.length, 1);
  assert.equal(rows[0].provider, "gemini");
  assert.equal(rows[0].outcome, "failure");
  assert.equal(rows[0].failureClass, "provider_5xx");
  assert.equal(rows[0].providerUnits, null);
  assert.equal(rows[0].estimatedCostUsd, null);
  assert.equal(rows[0].meta.estimate_status, "unavailable");
});
