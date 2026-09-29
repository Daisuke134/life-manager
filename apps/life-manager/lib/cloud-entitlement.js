"use strict";

function freezePlan(plan) {
  return Object.freeze({ ...plan });
}

const LAUNCH_PLANS = Object.freeze({
  "free-v1": freezePlan({
    plan: "free",
    active_goals: 1,
    scheduled_wakes_per_day: 1,
    browser_minutes_per_month: 10,
    monthly_cost_cap_usd_micros: 500_000,
    activation_credit_usd_micros: 1_000_000,
    external_spend_usd_micros: 0,
  }),
  "founding-pro-v1": freezePlan({
    plan: "founding_pro",
    active_goals: 3,
    scheduled_wakes_per_day: 12,
    browser_minutes_per_month: null,
    monthly_cost_cap_usd_micros: 12_000_000,
    activation_credit_usd_micros: 0,
    external_spend_usd_micros: 0,
  }),
});

function micros(value, label) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${label} must use non-negative integer micros`);
  }
  return value;
}

function decideAdmission(input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new Error("admission input invalid");
  }
  const planVersion = String(input.planVersion || "").trim();
  const plan = LAUNCH_PLANS[planVersion];
  if (!plan) throw new Error("cloud plan version invalid");

  const settled = micros(input.settledCostUsdMicros, "settled cost");
  const reserved = micros(input.reservedCostUsdMicros, "reserved cost");
  const requested = micros(input.requestedCostUsdMicros, "requested cost");
  const activationRemaining = micros(
    input.activationCreditRemainingUsdMicros,
    "activation credit remaining",
  );
  if (activationRemaining > plan.activation_credit_usd_micros) {
    throw new Error("activation credit remaining exceeds plan version");
  }

  const hardCap = plan.monthly_cost_cap_usd_micros + activationRemaining;
  if (input.manualHold === true) {
    return Object.freeze({ decision: "manual_hold", hard_cap_usd_micros: hardCap });
  }
  if (input.manualHold !== false) throw new Error("manual hold flag invalid");
  if (input.tenantStatus !== "active") {
    return Object.freeze({ decision: "plan_inactive", hard_cap_usd_micros: hardCap });
  }
  if (settled + reserved + requested > hardCap) {
    return Object.freeze({ decision: "budget_exhausted", hard_cap_usd_micros: hardCap });
  }
  return Object.freeze({ decision: "allow", hard_cap_usd_micros: hardCap });
}

module.exports = { LAUNCH_PLANS, decideAdmission };
