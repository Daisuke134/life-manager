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

test("provider lanes require fresh primaries and bounded fallback before complete", () => {
  const periods = Array.from({ length: 7 }, (_, index) => row(
    `2026-10-${String(index + 1).padStart(2, "0")}`,
    {
      providerLanes: {
        poi: { status: "fresh", primary: "openpoi", fallbackCalls: 0, fallbackCap: 100 },
        transit: { status: "fresh", primary: "transit-api", fallbackCalls: 1, fallbackCap: 100 },
        geocoder: { status: index === 6 ? "partial" : "fresh", primary: "cache", fallbackCalls: 1, fallbackCap: 200 },
      },
    },
  ));
  const partial = evaluateCfoObservationPeriods(periods, {
    latestDate: "2026-10-07", requiredProviderLanes: ["poi", "transit", "geocoder"],
  });
  assert.equal(partial.ready, true);
  assert.equal(partial.complete, false);
  assert.ok(partial.failures.includes("provider_lane_not_fresh:geocoder:2026-10-07"));

  periods[6].providerLanes.geocoder.status = "fresh";
  periods[6].providerLanes.transit.fallbackCalls = 101;
  const overCap = evaluateCfoObservationPeriods(periods, {
    latestDate: "2026-10-07", requiredProviderLanes: ["poi", "transit", "geocoder"],
  });
  assert.equal(overCap.complete, false);
  assert.ok(overCap.failures.includes("provider_lane_cap_exceeded:transit:2026-10-07"));
});

test("missing provider fallback cap evidence keeps the seven-day gate incomplete", () => {
  const periods = Array.from({ length: 7 }, (_, index) => row(
    `2026-10-${String(index + 1).padStart(2, "0")}`,
    { providerLanes: {
      poi: { status: "fresh", primary: "openpoi" },
      transit: { status: "fresh", primary: "transit-api", fallbackCalls: 0 },
      geocoder: { status: "fresh", primary: "cache", fallbackCalls: 0, fallbackCap: 200 },
    } },
  ));
  const result = evaluateCfoObservationPeriods(periods, {
    latestDate: "2026-10-07", requiredProviderLanes: ["poi", "transit", "geocoder"],
  });
  assert.equal(result.complete, false);
  assert.ok(result.failures.includes("provider_lane_cap_evidence_missing:poi:2026-10-07"));
});

test("positive provider unknown-cost evidence keeps the seven-day gate incomplete", () => {
  const periods = Array.from({ length: 7 }, (_, index) => row(
    `2026-10-${String(index + 1).padStart(2, "0")}`,
    { providerLanes: {
      poi: { status: "fresh", primary: "openpoi", fallbackCalls: 0, fallbackCap: 100, unknownCount: 1 },
      transit: { status: "fresh", primary: "transit-api", fallbackCalls: 0, fallbackCap: 100, unknownCount: 0 },
      geocoder: { status: "fresh", primary: "cache", fallbackCalls: 0, fallbackCap: 200, unknownCount: 0 },
    } },
  ));
  const result = evaluateCfoObservationPeriods(periods, {
    latestDate: "2026-10-07", requiredProviderLanes: ["poi", "transit", "geocoder"],
  });
  assert.equal(result.complete, false);
  assert.ok(result.failures.includes("provider_lane_unknown_cost:poi:2026-10-01"));
});
