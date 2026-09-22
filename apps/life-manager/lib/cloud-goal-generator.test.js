"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { generateCloudGoalPortfolio } = require("./cloud-goal-generator.js");

function modelInput(overrides = {}) {
  return {
    instruction: "Life Manager owns goal synthesis.",
    examples: [],
    policy: {
      schema_version: "life-manager.goal-policy.v1",
      authority: "life_manager",
      requires_user_authored_goal: false,
      human_inputs: ["facts", "accounts", "credentials", "consent", "boundaries"],
      objective_order: ["safety", "continuity", "financial_surplus", "marginal_outcome"],
      human_gates: ["kyc"],
    },
    tenant_id: "tenant-a",
    fact_refs: ["fact://tenant-a/income"],
    evidence_refs: ["policy://life-manager/J4"],
    boundary_refs: ["boundary://tenant-a/no-owner-spend"],
    ...overrides,
  };
}

function candidate(overrides = {}) {
  return {
    goal_id: "financial-continuity",
    statement: "Increase verified financial surplus within delegated boundaries",
    expected_outcome: "One attributable settled revenue receipt",
    confidence: 0.8,
    evidence_refs: ["policy://life-manager/J4"],
    cost_budget: { currency: "USD", minor_units: "0" },
    risk_budget: "low",
    dependencies: [],
    expires_at: null,
    success_receipt: null,
    status: "active",
    ...overrides,
  };
}

function response(value, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() {
      return {
        candidates: [{ content: { parts: [{ text: typeof value === "string" ? value : JSON.stringify(value) }] } }],
      };
    },
  };
}

test("strict Goal generator sends bounded JSON request and returns only validated candidates", async () => {
  const calls = [];
  const generated = await generateCloudGoalPortfolio(modelInput(), {
    apiKey: "test-key",
    fetchImpl: async (url, init) => {
      calls.push({ url, init, body: JSON.parse(init.body) });
      return response({ goals: [candidate()] });
    },
  });

  assert.deepEqual(generated, { goals: [candidate()] });
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /gemini-2\.5-flash:generateContent$/);
  assert.equal(calls[0].init.headers["x-goog-api-key"], "test-key");
  assert.equal(calls[0].body.generationConfig.responseMimeType, "application/json");
  assert.equal(calls[0].body.generationConfig.temperature, 0);
  assert.deepEqual(calls[0].body.generationConfig.responseSchema.required, ["goals"]);
  assert.doesNotMatch(JSON.stringify(generated), /tenant-a|origin|revision/);
});

test("strict Goal generator fails closed on missing key, transport, HTTP, and malformed model JSON", async () => {
  await assert.rejects(
    generateCloudGoalPortfolio(modelInput(), { apiKey: "", fetchImpl: async () => response({}) }),
    /cloud goal generator unavailable/,
  );
  await assert.rejects(
    generateCloudGoalPortfolio(modelInput(), { apiKey: "key", fetchImpl: async () => { throw new Error("secret network detail"); } }),
    /cloud goal generator unavailable/,
  );
  await assert.rejects(
    generateCloudGoalPortfolio(modelInput(), { apiKey: "key", fetchImpl: async () => response({}, 429) }),
    /cloud goal generator unavailable/,
  );
  await assert.rejects(
    generateCloudGoalPortfolio(modelInput(), { apiKey: "key", fetchImpl: async () => response("not-json") }),
    /cloud goal generator unavailable/,
  );
});

test("strict Goal generator rejects unknown fields, unauthorized evidence, and non-active output", async () => {
  const invalid = [
    { goals: [candidate({ tenant_id: "tenant-a" })] },
    { goals: [candidate({ evidence_refs: ["fact://tenant-a/not-authorized"] })] },
    { goals: [candidate({ status: "paused" })] },
    { goals: [candidate({ success_receipt: "provider-receipt://tenant-a/guessed" })] },
    { goals: [] },
    { goals: [candidate()], explanation: "extra" },
  ];
  for (const value of invalid) {
    await assert.rejects(
      generateCloudGoalPortfolio(modelInput(), {
        apiKey: "key",
        fetchImpl: async () => response(value),
      }),
      /cloud goal generator unavailable/,
    );
  }
});
