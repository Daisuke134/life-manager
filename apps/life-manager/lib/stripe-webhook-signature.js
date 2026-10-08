"use strict";

function stripeWebhookSecrets(env = {}) {
  const key = String(env.STRIPE_SECRET_KEY || "").trim();
  const live = key.startsWith("sk_live_") || key.startsWith("rk_live_");
  const test = key.startsWith("sk_test_") || key.startsWith("rk_test_");
  const candidate = live
    ? env.STRIPE_WEBHOOK_SECRET
    : test
      ? env.STRIPE_TEST_WEBHOOK_SECRET
      : env.STRIPE_WEBHOOK_SECRET;
  return [...new Set([String(candidate || "").trim()].filter(Boolean))];
}

function stripeWebhookAllowed(env = {}) {
  if (String(env.STRIPE_DEV || "").trim() === "1") return true;
  return stripeWebhookSecrets(env).length > 0;
}

function constructStripeWebhookEvent(raw, signature, env, stripeClient) {
  const secrets = stripeWebhookSecrets(env);
  if (secrets.length === 0) return stripeClient.webhooks.constructEvent(raw, signature, "");
  let lastError;
  for (const secret of secrets) {
    try {
      return stripeClient.webhooks.constructEvent(raw, signature, secret);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

module.exports = { constructStripeWebhookEvent, stripeWebhookAllowed, stripeWebhookSecrets };
