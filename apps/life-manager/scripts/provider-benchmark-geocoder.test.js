"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
  runGeocoderBenchmark,
  selectBenchmarkWinner,
} = require("./provider-benchmark-geocoder.js");

const cases = [
  { caseId: "exact", query: "東京駅", expectedPrecision: "exact" },
  { caseId: "city", query: "東京都", expectedPrecision: "city" },
  { caseId: "none", query: "存在しない", expectedPrecision: "none" },
  { caseId: "timeout", query: "timeout", expectedPrecision: "none" },
  { caseId: "quota", query: "quota", expectedPrecision: "none" },
];

function provider(name, parse = (payload) => payload) {
  return {
    name,
    terms: { attributionRefs: [`https://${name}.example/attribution`], licenseRefs: [`https://${name}.example/license`] },
    buildRequest: (item) => ({ url: `https://${name}.example/${item.caseId}` }),
    parse,
  };
}

test("runGeocoderBenchmark normalizes exact, city, empty, timeout, and quota results", async () => {
  const result = await runGeocoderBenchmark({
    cases,
    providers: [provider("fixture")],
    releaseSha: "release-test",
    now: () => "2026-10-03T00:00:00.000Z",
    timeoutMs: 5,
    fetchImpl: async (url) => {
      const caseId = String(url).split("/").pop();
      if (caseId === "timeout") throw Object.assign(new Error("timed out"), { code: "ETIMEDOUT" });
      if (caseId === "quota") return { ok: false, status: 429, json: async () => ({}) };
      if (caseId === "none") return { ok: true, status: 200, json: async () => ({ status: "ZERO_RESULTS" }) };
      return {
        ok: true,
        status: 200,
        json: async () => ({
          status: "fresh", lat: 35.681, lon: 139.767,
          precision: caseId === "city" ? "city" : "exact",
          attributionRefs: ["https://fixture.example/attribution"],
          licenseRefs: ["https://fixture.example/license"],
        }),
      };
    },
  });
  assert.deepEqual(result.rows.map((row) => [row.caseId, row.status]), [
    ["exact", "fresh"], ["city", "fresh"], ["none", "no_result"],
    ["timeout", "timeout"], ["quota", "quota"],
  ]);
  assert.equal(result.rows[0].releaseSha, "release-test");
  assert.equal(result.rows[0].query, undefined);
  assert.equal(result.summary.fresh, 2);
  assert.equal(result.summary.noResult, 1);
  assert.equal(result.summary.timeout, 1);
  assert.equal(result.summary.quota, 1);
});

test("runGeocoderBenchmark digest is deterministic for the same clock and results", async () => {
  const options = {
    cases: [{ caseId: "exact", query: "東京駅" }],
    providers: [provider("fixture")],
    releaseSha: "release-test",
    now: () => "2026-10-03T00:00:00.000Z",
    fetchImpl: async () => ({ ok: true, status: 200, json: async () => ({
      status: "fresh", lat: 35.681, lon: 139.767, precision: "exact",
      attributionRefs: ["https://fixture.example/attribution"],
      licenseRefs: ["https://fixture.example/license"],
    }) }),
  };
  const first = await runGeocoderBenchmark(options);
  const second = await runGeocoderBenchmark(options);
  assert.equal(first.digest, second.digest);
});

test("selectBenchmarkWinner rejects missing attribution or unsupported license", () => {
  const rows = [
    { provider: "missing-attribution", status: "fresh", precision: "exact", attributionRefs: [], licenseRefs: ["MIT"] },
    { provider: "unsupported-license", status: "fresh", precision: "exact", attributionRefs: ["source"], licenseRefs: ["UNKNOWN-LICENSE"] },
    { provider: "valid", status: "fresh", precision: "city", attributionRefs: ["source"], licenseRefs: ["CC BY 4.0"] },
  ];
  assert.deepEqual(selectBenchmarkWinner(rows), { provider: "valid", decision: "eligible_for_shadow" });
});
