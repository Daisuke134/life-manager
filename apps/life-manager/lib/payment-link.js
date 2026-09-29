"use strict";

function paymentLink(opts = {}, scope = {}) {
  if (scope.firstVerifiedResult !== true) return "";
  const value = String(
    opts.stripePaymentLink || opts.paymentLink
      || process.env.LM_STRIPE_PAYMENT_LINK || process.env.STRIPE_PAYMENT_LINK || "",
  ).trim();
  try {
    const url = new URL(value);
    if (url.protocol !== "https:" || url.hostname !== "buy.stripe.com"
      || !scope.uid || url.username || url.password || url.pathname.length <= 1) return "";
    url.searchParams.set("client_reference_id", String(scope.uid));
    return url.toString();
  } catch { return ""; }
}

module.exports = { paymentLink };
