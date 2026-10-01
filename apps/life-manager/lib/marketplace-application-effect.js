"use strict";

const {
  marketplaceApplicationContract,
} = require("./marketplace-application-job.js");
const {
  qualifyHumanRequirement,
} = require("./human-required-qualification.js");

class MarketplaceApplicationEffectError extends Error {
  constructor(message, code, unknownEffect) {
    super(message);
    this.name = "MarketplaceApplicationEffectError";
    this.code = code;
    this.unknownEffect = unknownEffect === true;
  }
}

function proof(value) {
  if (!value || !["absent", "present", "unknown", "human_required"].includes(value.state)) {
    throw new Error("marketplace application readback invalid");
  }
  return value;
}

function verifiedReceipt(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("verified application receipt invalid");
  }
  return value;
}

async function runMarketplaceApplicationEffect(job, deps = {}) {
  const contract = marketplaceApplicationContract(job);
  for (const name of ["inspectApplication", "executeOnce", "verifyReceipt"]) {
    if (typeof deps[name] !== "function") {
      throw new Error(`application dependency missing: ${name}`);
    }
  }
  const before = proof(await deps.inspectApplication(contract));
  if (before.state === "human_required") {
    const decision = qualifyHumanRequirement(before);
    const failure = new MarketplaceApplicationEffectError(
      "Application requires human work and was held before effect",
      "APPLICATION_HUMAN_REQUIRED",
      false,
    );
    failure.disposition = decision.disposition;
    failure.reasonCodes = decision.reason_codes;
    failure.qualificationId = decision.qualification_id;
    failure.delegateToHuman = decision.delegate_to_human;
    failure.bypassAllowed = decision.bypass_allowed;
    failure.bootstrapBoundary = decision.bootstrap_boundary;
    throw failure;
  }
  if (before.state === "unknown") {
    throw new MarketplaceApplicationEffectError(
      "Application state is unknown",
      "APPLICATION_EFFECT_UNKNOWN",
      true,
    );
  }
  if (before.state === "present") {
    return Object.freeze({
      receipt: verifiedReceipt(deps.verifyReceipt(before.receipt, contract)),
      effect_started: false,
      replayed: true,
    });
  }
  try {
    await deps.executeOnce(contract);
  } catch (error) {
    const failure = new MarketplaceApplicationEffectError(
      "Application execution failed",
      "APPLICATION_EXECUTION_FAILED",
      error && error.unknownEffect !== false,
    );
    failure.cause = error;
    throw failure;
  }
  let after;
  try {
    after = proof(await deps.inspectApplication(contract));
  } catch (error) {
    const failure = new MarketplaceApplicationEffectError(
      "Application post-readback failed",
      "APPLICATION_EFFECT_UNKNOWN",
      true,
    );
    failure.cause = error;
    throw failure;
  }
  if (after.state === "present") {
    return Object.freeze({
      receipt: verifiedReceipt(deps.verifyReceipt(after.receipt, contract)),
      effect_started: true,
      replayed: false,
    });
  }
  throw new MarketplaceApplicationEffectError(
    "Application post-readback did not confirm the effect",
    after.state === "absent" ? "APPLICATION_EFFECT_ABSENT" : "APPLICATION_EFFECT_UNKNOWN",
    after.state !== "absent",
  );
}

module.exports = {
  MarketplaceApplicationEffectError,
  runMarketplaceApplicationEffect,
};
