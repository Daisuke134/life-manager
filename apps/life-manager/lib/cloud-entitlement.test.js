"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { LAUNCH_PLANS, decideAdmission } = require("./cloud-entitlement.js");

test("launch plan versions encode the published Free and Founding Pro hard limits", () => {
  assert.deepEqual(LAUNCH_PLANS["free-v1"], {
    plan: "free",
    active_goals: 1,
    scheduled_wakes_per_day: 1,
    browser_minutes_per_month: 10,
    monthly_cost_cap_usd_micros: 500_000,
    activation_credit_usd_micros: 1_000_000,
    external_spend_usd_micros: 0,
  });
  assert.deepEqual(LAUNCH_PLANS["founding-pro-v1"], {
    plan: "founding_pro",
    active_goals: 3,
    scheduled_wakes_per_day: 12,
    browser_minutes_per_month: null,
    monthly_cost_cap_usd_micros: 12_000_000,
    activation_credit_usd_micros: 0,
    external_spend_usd_micros: 0,
  });
});

test("admission is pure, fail-closed, and has no human approval state", () => {
  const allowed = decideAdmission({
    planVersion: "free-v1",
    tenantStatus: "active",
    manualHold: false,
    settledCostUsdMicros: 100_000,
    reservedCostUsdMicros: 50_000,
    requestedCostUsdMicros: 25_000,
    activationCreditRemainingUsdMicros: 0,
  });
  assert.deepEqual(allowed, { decision: "allow", hard_cap_usd_micros: 500_000 });

  assert.equal(decideAdmission({
    planVersion: "free-v1", tenantStatus: "active", manualHold: false,
    settledCostUsdMicros: 450_000, reservedCostUsdMicros: 25_000,
    requestedCostUsdMicros: 25_001, activationCreditRemainingUsdMicros: 0,
  }).decision, "budget_exhausted");
  assert.equal(decideAdmission({
    planVersion: "free-v1", tenantStatus: "inactive", manualHold: false,
    settledCostUsdMicros: 0, reservedCostUsdMicros: 0,
    requestedCostUsdMicros: 1, activationCreditRemainingUsdMicros: 0,
  }).decision, "plan_inactive");
  assert.equal(decideAdmission({
    planVersion: "free-v1", tenantStatus: "active", manualHold: true,
    settledCostUsdMicros: 0, reservedCostUsdMicros: 0,
    requestedCostUsdMicros: 1, activationCreditRemainingUsdMicros: 0,
  }).decision, "manual_hold");

  assert.throws(() => decideAdmission({
    planVersion: "unknown-v1", tenantStatus: "active", manualHold: false,
    settledCostUsdMicros: 0, reservedCostUsdMicros: 0,
    requestedCostUsdMicros: 1, activationCreditRemainingUsdMicros: 0,
  }), /plan version/i);
  assert.throws(() => decideAdmission({
    planVersion: "free-v1", tenantStatus: "active", manualHold: false,
    settledCostUsdMicros: 0, reservedCostUsdMicros: 0,
    requestedCostUsdMicros: 0.5, activationCreditRemainingUsdMicros: 0,
  }), /integer|micros/i);
});

test("one-time activation credit enlarges only the current Free admission ceiling", () => {
  const result = decideAdmission({
    planVersion: "free-v1",
    tenantStatus: "active",
    manualHold: false,
    settledCostUsdMicros: 490_000,
    reservedCostUsdMicros: 0,
    requestedCostUsdMicros: 500_000,
    activationCreditRemainingUsdMicros: 500_000,
  });
  assert.deepEqual(result, { decision: "allow", hard_cap_usd_micros: 1_000_000 });
});
