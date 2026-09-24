"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  joinEconomicFunnelObservation,
  validateEconomicFunnelObservation,
  validateEconomicSourceObservation,
} = require("./economic-source-contract.js");

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
