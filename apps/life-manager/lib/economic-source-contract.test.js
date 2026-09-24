"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  buildEconomicSourceCoverage,
  joinEconomicFunnelObservation,
  validateEconomicFunnelObservation,
  validateEconomicSourceObservation,
} = require("./economic-source-contract.js");
const { readProductLoopCatalog } = require("./product-onboarding.js");

const HASH = "a".repeat(64);

function source(overrides = {}) {
  return {
    schema_version: 1,
    record_type: "economic_source_observation",
    observation_id: "source-affiliate-1",
    product_loop_id: "affiliate",
    subject_id: "tenant-a",
    source_kind: "funnel",
    adapter: "affiliate-money-funnel",
    implementation: "implemented",
    state: "observed_verified",
    observed_at: "2026-09-24T00:00:00.000Z",
    provider_receipt_ids: ["affiliate-snapshot-1"],
    evidence_refs: ["affiliate://snapshot/sha256-a"],
    ...overrides,
  };
}

function funnel(overrides = {}) {
  return {
    schema_version: 1,
    record_type: "economic_funnel_observation",
    funnel_observation_id: "funnel-affiliate-click-1",
    source_observation_id: "source-affiliate-1",
    product_loop_id: "affiliate",
    subject_id: "tenant-a",
    stage: "click",
    cohort_sha256: HASH,
    state: "observed_verified",
    count: 12,
    observed_at: "2026-09-24T00:00:00.000Z",
    provider_receipt_ids: ["affiliate-snapshot-1"],
    evidence_refs: ["affiliate://snapshot/sha256-a"],
    ...overrides,
  };
}

test("source and funnel observations are exact frozen records", () => {
  const checkedSource = validateEconomicSourceObservation(source());
  const checkedFunnel = validateEconomicFunnelObservation(funnel());
  assert.equal(Object.isFrozen(checkedSource), true);
  assert.equal(Object.isFrozen(checkedSource.provider_receipt_ids), true);
  assert.equal(Object.isFrozen(checkedFunnel), true);
  assert.equal(checkedFunnel.count, 12);
  assert.throws(() => validateEconomicSourceObservation({ ...source(), amount_minor: 100 }), /source/i);
  assert.throws(() => validateEconomicFunnelObservation({ ...funnel(), estimated_revenue: 9.99 }), /funnel/i);
});

test("missing and unavailable funnel values stay null instead of becoming zero", () => {
  const unavailable = funnel({ state: "unavailable", count: null, provider_receipt_ids: [] });
  assert.equal(validateEconomicFunnelObservation(unavailable).count, null);
  assert.throws(() => validateEconomicFunnelObservation({ ...unavailable, count: 0 }), /count/i);
  assert.equal(validateEconomicFunnelObservation(funnel({ state: "empty", count: 0 })).count, 0);
  assert.throws(() => validateEconomicFunnelObservation(funnel({ state: "empty", count: null })), /count/i);
});

test("official observed and empty funnel rows require provider receipts and evidence", () => {
  for (const state of ["observed_verified", "empty"]) {
    assert.throws(() => validateEconomicFunnelObservation(funnel({
      state, count: state === "empty" ? 0 : 1, provider_receipt_ids: [],
    })), /receipt/i);
    assert.throws(() => validateEconomicFunnelObservation(funnel({
      state, count: state === "empty" ? 0 : 1, evidence_refs: [],
    })), /evidence/i);
  }
});

test("a funnel joins only to the same loop, subject, source id, receipt and evidence", () => {
  const joined = joinEconomicFunnelObservation(source(), funnel());
  assert.equal(joined.source.observation_id, "source-affiliate-1");
  assert.equal(joined.funnel.funnel_observation_id, "funnel-affiliate-click-1");
  assert.equal(Object.isFrozen(joined), true);
  const mutations = [
    { product_loop_id: "mobile-apps" },
    { subject_id: "tenant-b" },
    { source_observation_id: "source-other" },
    { provider_receipt_ids: ["affiliate-snapshot-other"] },
    { evidence_refs: ["affiliate://snapshot/sha256-b"] },
  ];
  for (const mutation of mutations) {
    assert.throws(() => joinEconomicFunnelObservation(source(), funnel(mutation)), /join/i);
  }
});

test("unavailable source evidence can join only an unavailable null-count funnel", () => {
  const unavailableSource = source({
    state: "unavailable", provider_receipt_ids: [],
    evidence_refs: ["catalog://economic-source/affiliate/funnel"],
  });
  const unavailableFunnel = funnel({
    state: "unavailable", count: null, provider_receipt_ids: [],
    evidence_refs: ["catalog://economic-source/affiliate/funnel"],
  });
  assert.equal(joinEconomicFunnelObservation(unavailableSource, unavailableFunnel).funnel.count, null);
  assert.throws(() => joinEconomicFunnelObservation(
    unavailableSource, funnel(),
  ), /join/i);
});

test("coverage exposes every catalog loop without leaking receipt or evidence references", () => {
  const catalog = readProductLoopCatalog();
  const coverage = buildEconomicSourceCoverage({
    catalogLoops: catalog.loops,
    subjectId: "tenant-a",
    observations: [source()],
  });

  assert.equal(coverage.schema_version, 1);
  assert.equal(coverage.subject_id, "tenant-a");
  assert.equal(coverage.loops.length, 14);
  assert.equal(Object.isFrozen(coverage), true);
  assert.equal(Object.isFrozen(coverage.loops), true);
  const affiliate = coverage.loops.find((loop) => loop.product_loop_id === "affiliate");
  assert.deepEqual(affiliate.sources.funnel, {
    adapter: "affiliate-money-funnel",
    implementation: "implemented",
    state: "observed_verified",
    observation_id: "source-affiliate-1",
    observed_at: "2026-09-24T00:00:00.000Z",
  });
  assert.equal(affiliate.sources.financial.state, "not_configured");
  assert.equal(affiliate.sources.financial.implementation, "missing");
  assert.equal(affiliate.complete, false);
  const connector = coverage.loops.find((loop) => loop.product_loop_id === "connector");
  assert.equal(connector.complete, true);
  assert.deepEqual(Object.values(connector.sources).map((entry) => entry.state), [
    "not_applicable", "not_applicable", "not_applicable",
  ]);
  assert.equal(coverage.complete, false);
  assert.doesNotMatch(JSON.stringify(coverage), /affiliate-snapshot-1|affiliate:\/\/snapshot/);
});

test("coverage selects the latest exact observation and rejects catalog mismatches", () => {
  const catalogLoops = readProductLoopCatalog().loops;
  const latest = source({
    observation_id: "source-affiliate-2",
    state: "empty",
    observed_at: "2026-09-24T01:00:00.000Z",
  });
  const coverage = buildEconomicSourceCoverage({
    catalogLoops, subjectId: "tenant-a", observations: [latest, source()],
  });
  assert.equal(
    coverage.loops.find((loop) => loop.product_loop_id === "affiliate").sources.funnel.state,
    "empty",
  );
  assert.throws(() => buildEconomicSourceCoverage({
    catalogLoops, subjectId: "tenant-a",
    observations: [source({ adapter: "other-adapter" })],
  }), /catalog/i);
  assert.throws(() => buildEconomicSourceCoverage({
    catalogLoops, subjectId: "tenant-a",
    observations: [source({ subject_id: "tenant-b" })],
  }), /subject/i);
});
