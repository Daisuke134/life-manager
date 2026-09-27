"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { capafyRowsToFinancialRecords } = require("./financial-record-capafy.js");
const { projectFinancialRecord } = require("./financial-record-contract.js");

test("capafy daily revenue and refunds become verified business records", () => {
  const records = capafyRowsToFinancialRecords([
    { date: "2026-09-26", revenue: 3.98, refundAmount: 0 },
    { date: "2026-09-25", revenue: 0, refundAmount: 1.5 },
    { date: "2026-09-24", revenue: 0, refundAmount: 0 },
  ], { subjectId: "tenant-1", observedAt: "2026-09-27T00:00:00Z" });

  const projected = records.map(projectFinancialRecord);
  assert.equal(records.length, 2);
  const revenue = projected.find((r) => r.kind === "business_revenue");
  assert.equal(revenue.amount_minor, 398);
  assert.equal(revenue.direction, "credit");
  assert.equal(revenue.currency, "USD");
  assert.equal(revenue.occurred_at, "2026-09-26T00:00:00.000Z");
  assert.equal(revenue.source.provider, "capafy");
  const refund = projected.find((r) => r.kind === "business_cost");
  assert.equal(refund.amount_minor, 150);
  assert.equal(refund.direction, "debit");
});

test("capafy rows without a date or with malformed input are skipped, not fabricated", () => {
  assert.deepEqual(capafyRowsToFinancialRecords([{ revenue: 5 }, null, {}], {
    subjectId: "tenant-1", observedAt: "2026-09-27T00:00:00Z",
  }), []);
  assert.deepEqual(capafyRowsToFinancialRecords(null, {
    subjectId: "tenant-1", observedAt: "2026-09-27T00:00:00Z",
  }), []);
});

test("re-running the same day is idempotent (stable record_id)", () => {
  const opts = { subjectId: "tenant-1", observedAt: "2026-09-27T00:00:00Z" };
  const first = capafyRowsToFinancialRecords([{ date: "2026-09-26", revenue: 3.98 }], opts);
  const second = capafyRowsToFinancialRecords([{ date: "2026-09-26", revenue: 3.98 }], opts);
  assert.equal(first[0].record_id, second[0].record_id);
});
