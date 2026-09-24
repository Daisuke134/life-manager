"use strict";

const RECOVERY_CLASSES = Object.freeze([
  "browser",
  "continuous_service",
  "deterministic",
  "external_effect_owner",
  "model",
  "read_only_external_owner",
]);

const RECOVERY_PROMOTION_HOOKS = Object.freeze([
  "immutable_release",
  "isolated_canary",
  "exact_health",
  "rollback",
]);

// Task 7 proves these primitives in an isolated test-owned installation.  It
// does not create a production promotion path for any whole recovery class.
// Keep that distinction machine-readable: a marked recovery PR cannot inherit
// the app guard's Railway deployment path, and no class becomes promotable
// until a separate runtime path invokes every hook below.
const RECOVERY_PROMOTION_POLICY = Object.freeze(Object.fromEntries(
  RECOVERY_CLASSES.map((recoveryClass) => [recoveryClass, Object.freeze({
    recovery_class: recoveryClass,
    runtime_path: "unbound",
    required_hooks: RECOVERY_PROMOTION_HOOKS,
  })]),
));

function isReadOnlyExternalOwner(entry = {}) {
  const entrypoint = String(entry.entrypoint || "");
  return entry.priority === "critical_paid"
    || entrypoint.endsWith("/paid-owner")
    || entrypoint.endsWith("/paid-direct-owner");
}

function classifyRecoveryJob(entry) {
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) {
    throw new Error("recovery registry entry invalid");
  }
  if (isReadOnlyExternalOwner(entry)) return "read_only_external_owner";
  if (entry.effect_class !== "none") return "external_effect_owner";
  if (entry.cadence && entry.cadence.keep_alive === true) return "continuous_service";
  if (entry.resource_class === "browser") return "browser";
  if (entry.provider_route === "shared-agent-runner") return "model";
  if (entry.provider_route === "deterministic") return "deterministic";
  throw new Error("recovery provider route unclassified");
}

function evaluateRecoveryPromotion(recoveryClass, suppliedHooks = {}) {
  if (!RECOVERY_CLASSES.includes(recoveryClass)) {
    return Object.freeze({ eligible: false, reason: "recovery_class_invalid", missing_hooks: [] });
  }
  const policy = RECOVERY_PROMOTION_POLICY[recoveryClass];
  const missingHooks = policy.required_hooks.filter((hook) => suppliedHooks?.[hook] !== true);
  if (missingHooks.length > 0) {
    return Object.freeze({
      eligible: false,
      reason: "recovery_promotion_hooks_incomplete",
      missing_hooks: Object.freeze(missingHooks),
    });
  }
  if (policy.runtime_path !== "loop_runtime") {
    return Object.freeze({
      eligible: false,
      reason: "recovery_runtime_promotion_unbound",
      missing_hooks: Object.freeze([]),
    });
  }
  return Object.freeze({ eligible: true, reason: null, missing_hooks: Object.freeze([]) });
}

module.exports = {
  RECOVERY_CLASSES,
  RECOVERY_PROMOTION_HOOKS,
  RECOVERY_PROMOTION_POLICY,
  classifyRecoveryJob,
  evaluateRecoveryPromotion,
  isReadOnlyExternalOwner,
};
