"use strict";

function dependencies(value) {
  if (!value || !value.client
      || typeof value.client.balance !== "function"
      || typeof value.client.createCanary !== "function"
      || typeof value.client.show !== "function"
      || typeof value.client.logs !== "function"
      || typeof value.client.remove !== "function"
      || typeof value.verifyReadOnlyOutcome !== "function") {
    throw new Error("DigitalOcean canary dependencies unavailable");
  }
  return value;
}

async function runDigitalOceanCompatibilityCanary(input = {}, injected = {}) {
  const deps = dependencies(injected);
  const before = await deps.client.balance();
  let sessionId = null;
  let primaryError = null;
  let proof = null;
  try {
    const created = await deps.client.createCanary(input);
    sessionId = created.session_id;
    const session = await deps.client.show(sessionId);
    const logs = await deps.client.logs(sessionId);
    proof = await deps.verifyReadOnlyOutcome({ sessionId, session, logs });
    if (!proof || proof.tenant_isolated !== true || proof.effect !== "none"
        || proof.human_input_count !== 0 || proof.no_ask !== true
        || proof.browser_continuity !== true || proof.official_readback !== true
        || proof.replay_zero !== true) {
      throw new Error("DigitalOcean compatibility proof incomplete");
    }
  } catch (error) {
    primaryError = error;
  }

  let removed = null;
  let after = null;
  if (sessionId) {
    try {
      removed = await deps.client.remove(sessionId);
      after = await deps.client.balance();
      if (typeof deps.recordCleanup === "function") {
        await deps.recordCleanup({ sessionId, removed, before, after, primaryError });
      }
    } catch (cleanupError) {
      if (!primaryError) throw cleanupError;
      if (typeof deps.recordCleanupFailure === "function") {
        await deps.recordCleanupFailure({ sessionId, primaryError, cleanupError });
      }
    }
  }

  if (primaryError) throw primaryError;
  return Object.freeze({
    provider: "digitalocean-managed-agents",
    session_id: sessionId,
    before_balance: before,
    after_balance: after,
    teardown: removed,
    proof: Object.freeze({ ...proof }),
  });
}

module.exports = { runDigitalOceanCompatibilityCanary };
