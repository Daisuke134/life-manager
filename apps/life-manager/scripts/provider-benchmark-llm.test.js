"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { runLlmProviderBenchmark } = require("./provider-benchmark-llm.js");

const cases = [
  { caseId: "online-call", expected: { kind: "online" } },
  { caseId: "physical-venue", expected: { kind: "filled", location: "東京都千代田区丸の内" } },
  { caseId: "vague-meetup", expected: { kind: "ask" } },
  { caseId: "solo-routine", expected: { kind: "online" } },
];

function goodResult(item, extra = {}) {
  return { ...item.expected, latencyMs: 100, estimatedCostUsd: 0.1, privacyStatus: "approved_cloud", receiptComplete: true, ...extra };
}

test("cheaper but lower-quality candidate stays keep_current", async () => {
  const result = await runLlmProviderBenchmark({
    cases,
    candidates: [{ name: "gemini-current" }, { name: "local-cheap" }],
    now: () => "2026-10-03T00:00:00.000Z",
    runner: async (candidate, item) => candidate.name === "gemini-current"
      ? goodResult(item)
      : goodResult(item, { kind: "ask", location: undefined, estimatedCostUsd: 0.001, privacyStatus: "local" }),
  });
  assert.equal(result.recommendation, "keep_current");
  assert.equal(result.scores.find((score) => score.candidate === "local-cheap").accuracy, 0.25);
});

test("missing receipts fail closed even when quality is equal", async () => {
  const result = await runLlmProviderBenchmark({
    cases,
    candidates: [{ name: "gemini-current" }, { name: "local-no-receipt" }],
    now: () => "2026-10-03T00:00:00.000Z",
    runner: async (candidate, item) => goodResult(item, {
      estimatedCostUsd: candidate.name === "local-no-receipt" ? 0.001 : 0.1,
      receiptComplete: candidate.name !== "local-no-receipt",
      privacyStatus: "local",
    }),
  });
  assert.equal(result.recommendation, "keep_current");
  assert.equal(result.scores.find((score) => score.candidate === "local-no-receipt").receiptCompleteness, 0);
});

test("non-inferior lower-cost candidate is eligible for shadow only", async () => {
  const result = await runLlmProviderBenchmark({
    cases,
    candidates: [{ name: "gemini-current" }, { name: "local-equal" }],
    now: () => "2026-10-03T00:00:00.000Z",
    runner: async (candidate, item) => goodResult(item, {
      estimatedCostUsd: candidate.name === "local-equal" ? 0.001 : 0.1,
      privacyStatus: candidate.name === "local-equal" ? "local" : "approved_cloud",
    }),
  });
  assert.equal(result.recommendation, "eligible_for_shadow");
  assert.equal(result.scores.find((score) => score.candidate === "local-equal").eligible, true);
  assert.match(result.digest, /^[a-f0-9]{64}$/);
});
