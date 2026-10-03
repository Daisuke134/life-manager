"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { runRoutingBenchmark } = require("./provider-benchmark-routing.js");

const cases = [
  { caseId: "fresh", mode: "transit" },
  { caseId: "none", mode: "transit" },
  { caseId: "stale", mode: "transit" },
  { caseId: "timeout", mode: "transit" },
  { caseId: "unsupported", mode: "drive" },
];

function provider(name, parse = (payload) => payload, mode = "transit") {
  return {
    name, mode,
    feedVersion: "fixture-feed-1",
    licenseRefs: ["https://fixture.example/license"],
    resourceCost: { kind: "fixture", estimatedUsd: 0 },
    buildRequest: (item) => ({ url: `https://${name}.example/${item.caseId}` }),
    parse,
  };
}

test("runRoutingBenchmark preserves route duration, legs, fare, and feed freshness", async () => {
  const result = await runRoutingBenchmark({
    cases: [{ caseId: "fresh", mode: "transit" }],
    providers: [provider("fixture")],
    releaseSha: "release-test",
    now: () => "2026-10-03T00:00:00.000Z",
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({
      routeStatus: "fresh", durationSeconds: 1234, legCount: 3, farePresent: true,
      dataUpdatedAt: "2026-10-02T00:00:00.000Z", licenseRefs: ["CC BY 4.0"],
    }) }),
  });
  assert.deepEqual(result.rows[0], {
    provider: "fixture", mode: "transit", routeStatus: "fresh", durationSeconds: 1234,
    legCount: 3, farePresent: true, latencyMs: result.rows[0].latencyMs,
    dataUpdatedAt: "2026-10-02T00:00:00.000Z", resourceCost: { kind: "fixture", estimatedUsd: 0 },
    licenseRefs: ["CC BY 4.0"], errorClass: null, observedAt: "2026-10-03T00:00:00.000Z",
    releaseSha: "release-test", feedVersion: "fixture-feed-1", caseId: "fresh",
  });
});

test("runRoutingBenchmark classifies no-route, stale-feed, timeout, and unsupported mode", async () => {
  const result = await runRoutingBenchmark({
    cases,
    providers: [provider("fixture")],
    now: () => "2026-10-03T00:00:00.000Z",
    timeoutMs: 5,
    fetchImpl: async (url) => {
      const caseId = String(url).split("/").pop();
      if (caseId === "timeout") throw Object.assign(new Error("timeout"), { code: "ETIMEDOUT" });
      if (caseId === "none") return { ok: true, status: 200, json: async () => ({ routeStatus: "no_route" }) };
      if (caseId === "stale") return { ok: true, status: 200, json: async () => ({ routeStatus: "stale", errorClass: "feed_stale" }) };
      return { ok: true, status: 200, json: async () => ({ routeStatus: "fresh", durationSeconds: 1 }) };
    },
  });
  assert.deepEqual(result.rows.map((row) => [row.caseId, row.routeStatus]), [
    ["fresh", "fresh"], ["none", "no_route"], ["stale", "stale"],
    ["timeout", "timeout"], ["unsupported", "unsupported"],
  ]);
  assert.equal(result.summary.fresh, 1);
  assert.equal(result.summary.noRoute, 1);
  assert.equal(result.summary.stale, 1);
  assert.equal(result.summary.timeout, 1);
  assert.equal(result.summary.unsupported, 1);
});

test("runRoutingBenchmark digest is deterministic for the same clock and result", async () => {
  const options = {
    cases: [{ caseId: "fresh", mode: "transit" }], providers: [provider("fixture")],
    now: () => "2026-10-03T00:00:00.000Z",
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({ routeStatus: "fresh", durationSeconds: 1 }) }),
  };
  const first = await runRoutingBenchmark(options);
  const second = await runRoutingBenchmark(options);
  assert.equal(first.digest, second.digest);
});

test("runRoutingBenchmark classifies a provider that declines a case as not configured", async () => {
  const result = await runRoutingBenchmark({
    cases: [{ caseId: "declined", mode: "transit" }],
    providers: [{ name: "fixture", mode: "transit", buildRequest: () => null }],
    fetchImpl: async () => { throw new Error("must not fetch"); },
  });
  assert.equal(result.rows[0].routeStatus, "unavailable");
  assert.equal(result.rows[0].errorClass, "provider_not_configured");
});
