"use strict";

const {
  buildErrorIntake,
  persistErrorIntake,
} = require("./error-intake.js");


async function observeFailure(probe) {
  if (typeof probe !== "function") throw new Error("controlled_failure_dependencies_required");
  let failed = false;
  try {
    const result = await probe();
    failed = result === false
      || (result && typeof result === "object" && (result.ok === false || result.sent === false));
  } catch {
    failed = true;
  }
  if (!failed) throw new Error("controlled_failure_missing");
}


async function runControlledErrorInjection(options = {}) {
  if (!options.provenanceKey || typeof options.persist !== "function") {
    throw new Error("controlled_failure_dependencies_required");
  }
  await observeFailure(options.timeoutProbe);
  await observeFailure(options.sideEffectProbe);
  await observeFailure(options.runtimeProbe);

  const definitions = [
    {
      signal: "provider_timeout",
      component: "calendar",
      fingerprint: "controlled-provider-deadline",
    },
    {
      signal: "email_failed",
      component: "delivery",
      fingerprint: "controlled-delivery-failure",
    },
    {
      signal: "http_5xx",
      component: "production-health",
      fingerprint: "controlled-service-regression",
    },
  ];
  const results = [];
  for (const definition of definitions) {
    const intake = buildErrorIntake({
      ...definition,
      provenanceKey: options.provenanceKey,
    });
    const stored = await persistErrorIntake(intake, { persist: options.persist });
    results.push(Object.freeze({
      incidentClass: intake.labels[1],
      rowId: stored.id,
      duplicate: stored.duplicate,
    }));
  }
  return Object.freeze(results);
}


module.exports = {
  runControlledErrorInjection,
};
