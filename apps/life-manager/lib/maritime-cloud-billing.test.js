"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { resolveMaritimeCloudPriceId } = require("./maritime-cloud-billing.js");

test("Cloud billing requires a dedicated price and never falls back to the legacy Calendar price", () => {
  for (const env of [
    {},
    { LM_CLOUD_STRIPE_PRICE_ID: "not-a-price" },
    { LM_CLOUD_STRIPE_PRICE_ID: "price_legacy123", LM_STRIPE_PRICE_ID: "price_legacy123" },
  ]) {
    assert.throws(() => resolveMaritimeCloudPriceId(env), {
      code: "billing_cloud_price_unavailable",
      status: 503,
    });
  }

  assert.equal(resolveMaritimeCloudPriceId({
    LM_CLOUD_STRIPE_PRICE_ID: "price_cloud123",
    LM_STRIPE_PRICE_ID: "price_legacy123",
  }), "price_cloud123");
});
