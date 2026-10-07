"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { constructStripeWebhookEvent, stripeWebhookAllowed, stripeWebhookSecrets } = require("./stripe-webhook-signature.js");

test("live Stripe credentials never accept the test endpoint signing secret", () => {
  const env = {
    STRIPE_SECRET_KEY: "sk_live_fixture",
    STRIPE_WEBHOOK_SECRET: "whsec_live",
    STRIPE_TEST_WEBHOOK_SECRET: "whsec_test",
  };
  assert.equal(stripeWebhookAllowed(env), true);
  assert.deepEqual(stripeWebhookSecrets(env), ["whsec_live"]);

  const attempts = [];
  assert.throws(() => constructStripeWebhookEvent(
    Buffer.from("payload"),
    "signature",
    env,
    { webhooks: { constructEvent(_raw, _signature, secret) {
      attempts.push(secret);
      if (secret === "whsec_test") return { id: "evt_test" };
      throw new Error("signature mismatch");
    } } },
  ), /signature mismatch/);
  assert.deepEqual(attempts, ["whsec_live"]);
});

test("test Stripe credentials use only the test endpoint signing secret", () => {
  const env = {
    STRIPE_SECRET_KEY: "sk_test_fixture",
    STRIPE_WEBHOOK_SECRET: "whsec_live",
    STRIPE_TEST_WEBHOOK_SECRET: "whsec_test",
  };
  assert.deepEqual(stripeWebhookSecrets(env), ["whsec_test"]);
  const attempts = [];
  const event = constructStripeWebhookEvent(
    Buffer.from("payload"),
    "signature",
    env,
    { webhooks: { constructEvent(_raw, _signature, secret) {
      attempts.push(secret);
      if (secret === "whsec_test") return { id: "evt_test" };
      throw new Error("signature mismatch");
    } } },
  );
  assert.equal(event.id, "evt_test");
  assert.deepEqual(attempts, ["whsec_test"]);
});

test("fails closed when every configured secret rejects the signature", () => {
  assert.throws(() => constructStripeWebhookEvent(
    Buffer.from("payload"),
    "signature",
    { STRIPE_WEBHOOK_SECRET: "whsec_live", STRIPE_TEST_WEBHOOK_SECRET: "whsec_test" },
    { webhooks: { constructEvent() { throw new Error("signature mismatch"); } } },
  ), /signature mismatch/);
});
