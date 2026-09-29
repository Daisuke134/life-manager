"use strict";

const { LAUNCH_PLANS } = require("./cloud-entitlement.js");

function micros(value, label) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${label} must use non-negative integer micros`);
  }
  return value;
}

function decideCostReservation(input = {}) {
  const plan = LAUNCH_PLANS[String(input.planVersion || "")];
  if (!plan) throw new Error("cloud plan version invalid");
  const settled = micros(input.settledBillableUsdMicros, "settled cost");
  const reserved = micros(input.activeReservedUsdMicros, "reserved cost");
  const estimated = micros(input.estimatedMaxUsdMicros, "estimated cost");
  const activation = micros(input.activationCreditRemainingUsdMicros, "activation credit");
  if (activation > plan.activation_credit_usd_micros
      || (plan.activation_credit_usd_micros === 0 && activation !== 0)) {
    throw new Error("activation credit invalid for plan");
  }
  const hardCap = plan.monthly_cost_cap_usd_micros + activation;
  if (input.costStateKnown !== true) {
    return Object.freeze({ decision: "cost_unknown", hard_cap_usd_micros: hardCap });
  }
  if (input.tenantStatus !== "active") {
    return Object.freeze({ decision: "plan_inactive", hard_cap_usd_micros: hardCap });
  }
  if (settled + reserved + estimated > hardCap) {
    return Object.freeze({ decision: "budget_exhausted", hard_cap_usd_micros: hardCap });
  }
  return Object.freeze({ decision: "allow", hard_cap_usd_micros: hardCap });
}

module.exports = { decideCostReservation };
