"use strict";

const { test } = require("node:test");
const assert = require("node:assert/strict");
const { paymentLink } = require("./payment-link.js");

test("paymentLink allows only tenant-scoped buy.stripe.com HTTPS", () => {
  assert.equal(
    paymentLink({ stripePaymentLink: "https://buy.stripe.com/test_life_manager" }, { uid: "tenant-a", firstVerifiedResult: true }),
    "https://buy.stripe.com/test_life_manager?client_reference_id=tenant-a",
  );
  assert.equal(paymentLink({ stripePaymentLink: "https://evil.example/pay" }, { uid: "tenant-a", firstVerifiedResult: true }), "");
  assert.equal(paymentLink({ stripePaymentLink: "https://buy.stripe.com/test" }, {}), "");
});

test("paymentLink stays hidden until this tenant has a verified first result", () => {
  const opts = { stripePaymentLink: "https://buy.stripe.com/test_life_manager" };
  assert.equal(paymentLink(opts, { uid: "tenant-a", firstVerifiedResult: false }), "");
  assert.equal(paymentLink(opts, { uid: "tenant-a" }), "");
});
