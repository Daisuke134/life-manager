"use strict";

const { BILLING_STATUSES, recordCost, recordProviderCost } = require("./ledger.js");

const OUTCOMES = new Set(["success", "failure", "cache_hit"]);
const SECRET_KEY = /(api[_-]?key|authorization|credential|password|secret|token)/i;

function requiredText(value, name) {
  const text = value == null ? "" : String(value).trim();
  if (!text) throw new Error(`${name} is required`);
  return text;
}

function safeMeta(meta) {
  const source = meta == null ? {} : meta;
  if (!source || typeof source !== "object" || Array.isArray(source)) {
    throw new Error("meta must be an object");
  }
  for (const key of Object.keys(source)) {
    if (SECRET_KEY.test(key)) throw new Error(`secret-shaped metadata key: ${key}`);
  }
  return { ...source };
}

function finiteNonNegative(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : 0;
}

function normalizeUsageEvent(event = {}) {
  const tenantId = requiredText(event.tenantId, "tenantId");
  const provider = requiredText(event.provider, "provider");
  const feature = requiredText(event.feature, "feature");
  const outcome = requiredText(event.outcome, "outcome");
  if (!OUTCOMES.has(outcome)) throw new Error(`invalid outcome: ${outcome}`);

  const cacheHit = outcome === "cache_hit" || event.cacheHit === true;
  const quantity = cacheHit ? 0 : finiteNonNegative(event.providerUnits);
  const estUsd = cacheHit ? 0 : finiteNonNegative(event.estimatedCostUsd);
  const meta = safeMeta(event.meta);

  const normalized = {
    uid: tenantId,
    kind: "provider_usage",
    quantity,
    unit: event.providerUnit == null ? "request" : String(event.providerUnit),
    estUsd,
    meta: {
      ...meta,
      provider,
      feature,
      outcome,
      failure_class: event.failureClass == null ? null : String(event.failureClass),
      cache_hit: cacheHit,
      // Stripe/customer allowance is a later, separate acceptance boundary (COST-06).
      customer_usage: false,
    },
  };
  if (event.billingStatus != null || event.actualCostUsd != null || event.sourceReceiptRef != null) {
    const billingStatus = String(event.billingStatus || "estimated");
    if (!BILLING_STATUSES.has(billingStatus)) throw new Error(`invalid billing status: ${billingStatus}`);
    const actualUsd = event.actualCostUsd == null ? null : Number(event.actualCostUsd);
    if (actualUsd !== null && (!Number.isFinite(actualUsd) || actualUsd < 0)) {
      throw new Error("actualCostUsd invalid");
    }
    normalized.billingStatus = billingStatus;
    normalized.actualUsd = actualUsd;
    normalized.pricingVersion = event.pricingVersion == null ? null : String(event.pricingVersion);
    normalized.sourceReceiptRef = requiredText(event.sourceReceiptRef, "sourceReceiptRef");
  }
  return normalized;
}

async function recordUsageEvent(event, opts = {}) {
  const normalized = normalizeUsageEvent(event);
  if (normalized.billingStatus) {
    const write = opts.recordProviderCost || recordProviderCost;
    return write({
      uid: normalized.uid, provider: normalized.meta.provider, product: normalized.meta.feature,
      sku: event.sku || normalized.meta.feature, operation: event.operation || normalized.meta.feature,
      quantity: normalized.quantity, unit: normalized.unit, estimatedUsd: normalized.estUsd,
      actualUsd: normalized.actualUsd, billingStatus: normalized.billingStatus,
      pricingVersion: normalized.pricingVersion, sourceReceiptRef: normalized.sourceReceiptRef,
      meta: normalized.meta,
    }, opts);
  }
  const write = opts.recordCost || recordCost;
  return write(normalized, opts);
}

module.exports = { normalizeUsageEvent, recordUsageEvent, OUTCOMES };
