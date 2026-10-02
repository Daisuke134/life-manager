"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const { readBusinessReadback, summarizeCoverageGaps } = require("./financial-business-readback.js");

function fixtureScript(t, value) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "lm-business-readback-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const file = path.join(root, "collector.js");
  fs.writeFileSync(file, `process.stdout.write(${JSON.stringify(JSON.stringify(value))});\n`, { mode: 0o700 });
  return file;
}

function completeTable() {
  return {
    reporting_date: "2026-10-02",
    timezone: "Asia/Tokyo",
    economic_attribution: {
      snapshot_at: "2026-10-03T00:00:00.000000Z",
      trailing_start: "2026-09-03T00:00:00.000000Z",
      historical: { company: { status: "verified", currencies: { JPY: { settled_external_revenue: "12500" } }, coverage_gaps: [] } },
      trailing: { company: { status: "verified", currencies: { JPY: { settled_external_revenue: "12500" } }, coverage_gaps: [] } },
      mrr: { company: { status: "verified", currencies: {}, coverage_gaps: [] } },
      runway: { status: "unknown", reasons: ["liquid_balance_missing"] },
    },
  };
}

test("business readback returns an immutable table receipt and complete coverage", async (t) => {
  const script = fixtureScript(t, completeTable());
  const result = readBusinessReadback({
    reportingDate: "2026-10-02", pythonBin: process.execPath, scriptPath: script,
  });
  assert.equal(result.status, "fresh");
  assert.equal(result.observedAt, "2026-10-03T00:00:00.000000Z");
  assert.equal(result.table.reporting_date, "2026-10-02");
  assert.equal(result.sourceReceiptRefs.length, 1);
  assert.match(result.sourceReceiptRefs[0], /^loop-pnl:\/\/sha256\/[a-f0-9]{64}$/);
  assert.deepEqual(result.coverageGaps, []);
  assert.deepEqual(result.businessSourceCoverage, [{
    source: "loop-pnl", state: "fresh", observedAt: result.observedAt,
    receiptCount: 1, gapReason: null,
  }]);
});

test("business readback preserves source gaps instead of inventing zero revenue", async (t) => {
  const table = completeTable();
  table.economic_attribution.historical.company.coverage_gaps = [
    { product_loop_id: "self-build", source_id: "stripe-financial-record", reason: "source_unconnected" },
  ];
  const script = fixtureScript(t, table);
  const result = readBusinessReadback({
    reportingDate: "2026-10-02", pythonBin: process.execPath, scriptPath: script,
  });
  assert.equal(result.status, "partial");
  assert.deepEqual(result.coverageGaps, [{
    product_loop_id: "self-build", source_id: "stripe-financial-record", reason: "source_unconnected",
  }]);
  assert.equal(result.businessSourceCoverage[0].gapReason, "source_unconnected");
  assert.deepEqual(result.coverageSummary, [{
    sourceId: "stripe-financial-record", reason: "source_unconnected", count: 1,
    productLoopIds: ["self-build"], categories: [],
  }]);
});

test("coverage summary groups repeated category gaps into actionable source rows", () => {
  assert.deepEqual(summarizeCoverageGaps([
    { product_loop_id: "self-build", source_id: "stripe-financial-record", reason: "missing_category", category: "model_cost" },
    { product_loop_id: "self-build", source_id: "stripe-financial-record", reason: "missing_category", category: "infra_cost" },
    { product_loop_id: "mobile-apps", source_id: "revenuecat-mrr", reason: "missing_category", category: "mrr" },
    { product_loop_id: "self-build", source_id: "stripe-financial-record", reason: "missing_category", category: "model_cost" },
    { product_loop_id: "affiliate", source_id: "partnerstack", reason: "stale_readback" },
  ]), [
    {
      sourceId: "partnerstack", reason: "stale_readback", count: 1,
      productLoopIds: ["affiliate"], categories: [],
    },
    {
      sourceId: "revenuecat-mrr", reason: "missing_category", count: 1,
      productLoopIds: ["mobile-apps"], categories: ["mrr"],
    },
    {
      sourceId: "stripe-financial-record", reason: "missing_category", count: 3,
      productLoopIds: ["self-build"], categories: ["infra_cost", "model_cost"],
    },
  ]);
});

test("missing or malformed business artifact is unavailable, never an empty verified source", async (t) => {
  const missing = readBusinessReadback({
    reportingDate: "2026-10-02", pythonBin: process.execPath,
    scriptPath: "/tmp/lm-business-readback-does-not-exist.js",
  });
  assert.equal(missing.status, "unavailable");
  assert.equal(missing.sourceReceiptRefs.length, 0);
  assert.equal(missing.businessSourceCoverage[0].state, "unavailable");
  assert.equal(missing.businessSourceCoverage[0].gapReason, "read_failed");

  const malformed = fixtureScript(t, { reporting_date: "2026-10-01" });
  const result = readBusinessReadback({
    reportingDate: "2026-10-02", pythonBin: process.execPath, scriptPath: malformed,
  });
  assert.equal(result.status, "unavailable");
  assert.equal(result.businessSourceCoverage[0].gapReason, "reporting_date_mismatch");
});
