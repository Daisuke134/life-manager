"use strict";

const CLOUD_PRICE_ID_ENV = "LM_CLOUD_STRIPE_PRICE_ID";
const LEGACY_CALENDAR_PRICE_ID_ENV = "LM_STRIPE_PRICE_ID";
const PRICE_ID_RE = /^price_[A-Za-z0-9]+$/;

function billingCloudPriceUnavailable() {
  const error = new Error("billing_cloud_price_unavailable");
  error.code = "billing_cloud_price_unavailable";
  error.status = 503;
  return error;
}

// This is a pure configuration boundary; provider validation belongs to the
// future checkout path and must never substitute the legacy Calendar price.
function resolveMaritimeCloudPriceId(env = process.env) {
  const cloudPriceId = typeof env[CLOUD_PRICE_ID_ENV] === "string"
    ? env[CLOUD_PRICE_ID_ENV].trim() : "";
  const legacyCalendarPriceId = typeof env[LEGACY_CALENDAR_PRICE_ID_ENV] === "string"
    ? env[LEGACY_CALENDAR_PRICE_ID_ENV].trim() : "";

  if (!PRICE_ID_RE.test(cloudPriceId) || cloudPriceId === legacyCalendarPriceId) {
    throw billingCloudPriceUnavailable();
  }
  return cloudPriceId;
}

module.exports = { resolveMaritimeCloudPriceId };
