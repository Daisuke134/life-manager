"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { evaluateCfoObservationPeriods } = require("./cfo-observation-gate.js");

function row(date, overrides = {}) {
  return {
    reportingDate: date,
    delivery: { status: "sent", providerMessageId: `message-${date}` },
    sourceFreshness: {
      moneytree: { status: "fresh" },
      businessReadback: { status: "fresh" },
      googleBilling: { status: "fresh" },
    },
    providerCostSettlement: { status: "settled" },
    ...overrides,
  };
}

test("seven consecutive receipt-backed fresh periods become complete", () => {
  const periods = Array.from({ length: 7 }, (_, index) => (
    row(`2026-10-${String(index + 1).padStart(2, "0")}`)
  ));
  const result = evaluateCfoObservationPeriods(periods, { latestDate: "2026-10-07" });
  assert.equal(result.ready, true);
  assert.equal(result.complete, true);
  assert.equal(result.deliveryDays, 7);
  assert.deepEqual(result.failures, []);
});

test("a missing day cannot be papered over by duplicate receipts", () => {
  const periods = [
    row("2026-10-01"), row("2026-10-02"), row("2026-10-04"),
    row("2026-10-05"), row("2026-10-06"), row("2026-10-07"), row("2026-10-07"),
  ];
  const result = evaluateCfoObservationPeriods(periods, { latestDate: "2026-10-07" });
  assert.equal(result.ready, false);
  assert.equal(result.complete, false);
  assert.ok(result.failures.includes("duplicate_period:2026-10-07"));
  assert.ok(result.failures.includes("period_missing:2026-10-03"));
});

test("partial source periods are observable but never complete", () => {
  const periods = Array.from({ length: 7 }, (_, index) => row(
    `2026-10-${String(index + 1).padStart(2, "0")}`,
    index === 6 ? { sourceFreshness: { moneytree: { status: "partial" } } } : {},
  ));
  const result = evaluateCfoObservationPeriods(periods, { latestDate: "2026-10-07" });
  assert.equal(result.ready, true);
  assert.equal(result.complete, false);
  assert.equal(result.freshDays, 6);
  assert.ok(result.failures.includes("source_not_fresh:moneytree:2026-10-07"));
});

test("missing delivery receipt keeps the seven-day gate closed", () => {
  const periods = Array.from({ length: 7 }, (_, index) => row(
    `2026-10-${String(index + 1).padStart(2, "0")}`,
    index === 2 ? { delivery: { status: "failed", providerMessageId: null } } : {},
  ));
  const result = evaluateCfoObservationPeriods(periods, { latestDate: "2026-10-07" });
  assert.equal(result.ready, false);
  assert.equal(result.deliveryDays, 6);
  assert.ok(result.failures.includes("delivery_receipt_missing:2026-10-03"));
});
