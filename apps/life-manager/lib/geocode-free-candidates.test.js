"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const fixturePath = path.join(__dirname, "fixtures/geocode-free-candidates.json");

function loadEvidence() {
  try {
    return JSON.parse(fs.readFileSync(fixturePath, "utf8"));
  } catch (error) {
    if (error && error.code === "ENOENT") return { schema_version: 0, cases: [] };
    throw error;
  }
}

const evidence = loadEvidence();
const caseById = (id) => evidence.cases.find((item) => item.id === id) || {};

test("free-geocode fixture records date, provenance, licensing, and privacy constraints", () => {
  assert.equal(evidence.schema_version, 1);
  assert.equal(evidence.captured_on, "2026-10-07");
  assert.equal(evidence.fixtures_only, true);
  assert.equal(evidence.life_manager_production_route_requests, 0);
  assert.equal(evidence.provider_notes.gsi.rate_sla, "unknown");
  assert.equal(evidence.provider_notes.gsi.license, "PDL1.0");
  assert.equal(evidence.provider_notes.openpoi.free_commercial_use, true);
  assert.equal(evidence.provider_notes.openpoi.request_content_logged, true);
});

test("GSI single-result full address snapshot retains dropped house-number precision", () => {
  const sample = caseById("gsi-full-address");
  const feature = sample.response?.captured_features?.[0] || {};
  const title = feature.properties?.title || "";

  assert.equal(sample.request?.q, "東京都千代田区丸の内1-9-1");
  assert.equal(sample.response?.count, 1);
  assert.equal(title, "東京都千代田区丸の内一丁目９番");
  assert.equal(title.includes("1-9-1"), false);
  assert.deepEqual(feature.geometry?.coordinates, [139.767242, 35.681252]);
});

test("GSI ambiguous place-name snapshot preserves its unrelated first result", () => {
  const sample = caseById("gsi-ambiguous");
  const first = sample.response?.captured_features?.[0] || {};

  assert.equal(sample.request?.q, "東京駅");
  assert.equal(sample.response?.count, 53);
  assert.equal(first.properties?.title, "北海道札幌市東区");
  assert.deepEqual(first.geometry?.coordinates, [141.363617, 43.076111]);
});

test("OpenPOI broad search snapshot does not treat a cross-locality first result as a geocode", () => {
  const sample = caseById("openpoi-broad-search");
  const first = sample.response?.captured_results?.[0] || {};

  assert.equal(sample.request?.q, "スターバックス");
  assert.equal(sample.request?.center, undefined);
  assert.equal(sample.response?.count, 5);
  assert.equal(sample.response?.truncated, true);
  assert.equal(first.name, "１Ｆ　スターバックスコーヒー");
  assert.match(first.address || "", /^東京都立川市/);
});

test("OpenPOI exact station-name suggestions preserve two conflicting coordinates", () => {
  const sample = caseById("openpoi-station-suggest");
  const exact = (sample.response?.captured_suggestions || []).filter((item) => item.name === "東京駅");

  assert.equal(sample.request?.q, "東京駅");
  assert.equal(sample.response?.count, 5);
  assert.equal(sample.response?.truncated, true);
  assert.equal(exact.length, 2);
  assert.deepEqual([exact[0].lat, exact[0].lng], [35.699383927107796, 139.77333040976976]);
  assert.deepEqual([exact[1].lat, exact[1].lng], [35.72119974584146, 139.77844276737827]);
  assert.ok(Math.abs(exact[0].lat - exact[1].lat) > 0.02);
});

test("zero-result and synthetic-timeout cases carry no candidate coordinates", () => {
  const gsi = caseById("gsi-not-found");
  const poi = caseById("openpoi-branch-not-found");
  const timeout = caseById("openpoi-timeout-simulated");

  assert.equal(gsi.response?.count, 0);
  assert.deepEqual(gsi.response?.captured_features, []);
  assert.equal(poi.response?.count, 0);
  assert.deepEqual(poi.response?.captured_suggestions, []);
  assert.equal(timeout.observation_kind, "synthetic");
  assert.equal(timeout.transport_outcome, "timeout");
  assert.equal(timeout.production_request, false);
  assert.equal(timeout.response, undefined);
});

test("every captured OpenPOI result retains its complete license and attribution arrays", () => {
  const openpoiCases = evidence.cases.filter((item) => item.provider === "openpoi");
  const records = openpoiCases.flatMap((item) => [
    ...(item.response?.captured_results || []),
    ...(item.response?.captured_suggestions || []),
  ]);

  assert.ok(records.length > 0);
  for (const record of records) {
    assert.ok(Array.isArray(record.licenses) && record.licenses.length > 0, record.name);
    assert.ok(Array.isArray(record.attributions) && record.attributions.length > 0, record.name);
  }
});

test("OpenPOI fixture distinguishes weekly JFF data from its fixed Overture release", () => {
  const dataSources = evidence.provider_notes?.openpoi?.data_sources || {};
  assert.equal(dataSources.overture_release, "2026-08-19.0");
  assert.equal(dataSources.jff_rebuild_cadence, "weekly");
});
