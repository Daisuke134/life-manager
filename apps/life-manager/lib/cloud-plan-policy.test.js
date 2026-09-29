"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { decideCostReservation } = require("./cloud-plan-policy.js");

function input(overrides = {}) {
  return {
    planVersion: "free-v1",
    tenantStatus: "active",
    settledBillableUsdMicros: 0,
    activeReservedUsdMicros: 0,
    estimatedMaxUsdMicros: 1,
    activationCreditRemainingUsdMicros: 0,
    costStateKnown: true,
    ...overrides,
  };
}

test("Free $0.50 and Founding Pro $12 caps are exact integer-micro hard limits", () => {
  assert.equal(decideCostReservation(input({
    settledBillableUsdMicros: 499_999,
  })).decision, "allow");
  assert.equal(decideCostReservation(input({
    settledBillableUsdMicros: 500_000,
  })).decision, "budget_exhausted");
  assert.equal(decideCostReservation(input({
    planVersion: "founding-pro-v1",
    settledBillableUsdMicros: 11_999_999,
  })).decision, "allow");
  assert.equal(decideCostReservation(input({
    planVersion: "founding-pro-v1",
    settledBillableUsdMicros: 12_000_000,
  })).decision, "budget_exhausted");
});

test("remaining one-time activation credit extends Free only and never resets by itself", () => {
  assert.deepEqual(decideCostReservation(input({
    settledBillableUsdMicros: 499_999,
    estimatedMaxUsdMicros: 1_000_001,
    activationCreditRemainingUsdMicros: 1_000_000,
  })), { decision: "allow", hard_cap_usd_micros: 1_500_000 });
  assert.equal(decideCostReservation(input({
    settledBillableUsdMicros: 499_999,
    estimatedMaxUsdMicros: 1_000_002,
    activationCreditRemainingUsdMicros: 1_000_000,
  })).decision, "budget_exhausted");
  assert.throws(() => decideCostReservation(input({
    planVersion: "founding-pro-v1", activationCreditRemainingUsdMicros: 1,
  })), /activation/i);
});

test("unknown cost state and fractional, negative, or unsafe micros fail closed", () => {
  assert.equal(decideCostReservation(input({ costStateKnown: false })).decision, "cost_unknown");
  for (const value of [0.5, -1, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => decideCostReservation(input({ estimatedMaxUsdMicros: value })), /integer|micros/i);
  }
});
