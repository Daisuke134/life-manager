"use strict";

const CONTEXT_KEYS = Object.freeze([
  "account_refs", "boundary_refs", "consent_refs", "fact_refs",
  "revision", "schema_version", "tenant_id",
]);
const IDENTIFIER = /^[a-z0-9][a-z0-9._-]{0,199}$/u;
const POLICY_REF = "policy://life-manager/J4";

function invalid() {
  throw new Error("goal context invalid");
}

function exactKeys(value) {
  return value && typeof value === "object" && !Array.isArray(value)
    && Object.keys(value).length === CONTEXT_KEYS.length
    && Object.keys(value).sort().every((key, index) => key === CONTEXT_KEYS[index]);
}

function deepFreeze(value) {
  if (!value || typeof value !== "object" || Object.isFrozen(value)) return value;
  Object.values(value).forEach(deepFreeze);
  return Object.freeze(value);
}

function referenceList(value, scheme, tenantId) {
  if (!Array.isArray(value) || value.length > 100 || new Set(value).size !== value.length) {
    return false;
  }
  return value.every((ref) => {
    if (typeof ref !== "string" || !ref || ref.length > 1024 || /\s/u.test(ref)) return false;
    let parsed;
    try { parsed = new URL(ref); } catch { return false; }
    return parsed.protocol === `${scheme}:`
      && !parsed.username && !parsed.password && !parsed.port && !parsed.search && !parsed.hash
      && parsed.hostname === tenantId
      && parsed.pathname.startsWith("/") && parsed.pathname.length > 1
      && ref.startsWith(`${scheme}://${tenantId}/`);
  });
}

function validateGoalContext(value, expectedTenantId) {
  if (!exactKeys(value)
    || value.schema_version !== "life-manager.goal-context.v1"
    || !IDENTIFIER.test(value.tenant_id)
    || value.tenant_id !== expectedTenantId
    || !Number.isInteger(value.revision) || value.revision < 1 || value.revision > 100
    || !referenceList(value.fact_refs, "fact", value.tenant_id)
    || !referenceList(value.account_refs, "account", value.tenant_id)
    || !referenceList(value.consent_refs, "consent", value.tenant_id)
    || !referenceList(value.boundary_refs, "boundary", value.tenant_id)) {
    return invalid();
  }
  return deepFreeze(value);
}

function goalContextReference(value) {
  const context = validateGoalContext(value, value && value.tenant_id);
  return `goal-context://${context.tenant_id}?revision=${context.revision}`;
}

function goalSynthesisRefs(value) {
  const context = validateGoalContext(value, value && value.tenant_id);
  return deepFreeze({
    factRefs: [...context.fact_refs],
    evidenceRefs: [POLICY_REF, ...context.account_refs, ...context.consent_refs],
    boundaryRefs: [...context.boundary_refs],
  });
}

module.exports = {
  goalContextReference,
  goalSynthesisRefs,
  validateGoalContext,
};
