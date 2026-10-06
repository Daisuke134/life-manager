"use strict";

const PRICES = Object.freeze({
  "gemini-2.5-flash": { input: 0.30, output: 2.50, grounding: 0.035 },
  "gemini-3.7-flash": { input: 0.75, output: 3.75, grounding: 0.014 },
});
const PRICING_VERSION = "lm-gemini-estimate-2026-10-06-v1";
const { recordUsageEvent } = require("./usage-event.js");

function count(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function geminiUsageEvents(response, context = {}) {
  const usage = response && response.usageMetadata || {};
  const model = context.model || "gemini-2.5-flash";
  const prices = PRICES[model];
  const input = count(usage.promptTokenCount);
  const output = count(usage.candidatesTokenCount);
  const total = count(usage.totalTokenCount) ?? (input != null && output != null ? input + output : null);
  const rawEstimated = input == null || output == null || !prices
    ? null : input / 1_000_000 * prices.input + output / 1_000_000 * prices.output;
  const estimated = rawEstimated == null ? null : Number(rawEstimated.toFixed(12));
  const success = context.success == null
    ? Boolean(response && Array.isArray(response.candidates) && response.candidates.length)
    : context.success === true;
  const common = { tenantId: context.tenantId || "unknown", feature: context.feature || "unknown" };
  const events = [{
    ...common, provider: "gemini", operation: "generate_content", outcome: success ? "success" : "failure",
    failureClass: success ? null : (context.failureClass || "empty_response"),
    providerUnits: total, providerUnit: "tokens", estimatedCostUsd: estimated,
    meta: { model: prices ? model : null, pricing_version: prices ? PRICING_VERSION : null, input_tokens: input,
      output_tokens: output, estimate_status: estimated == null ? "unavailable" : "estimated" },
  }];
  if (context.grounded) events.push({
    ...common, provider: "google_search_grounding", operation: "search_grounding",
    outcome: success ? "success" : "failure",
    failureClass: success ? null : (context.failureClass || "empty_response"),
    providerUnits: 1, providerUnit: "grounded_prompt", estimatedCostUsd: prices ? prices.grounding : null,
    meta: { model, pricing_version: prices ? PRICING_VERSION : null,
      pricing_basis: prices ? "list_price_after_free_rpd" : "unavailable" },
  });
  return events;
}

async function persistGeminiUsage(response, context = {}, options = {}) {
  const injected = options.recordUsageEvent;
  if (!injected && (!process.env.SUPABASE_URL || !process.env.SUPABASE_SERVICE_ROLE_KEY)) return false;
  const write = injected || recordUsageEvent;
  let ok = true;
  for (const event of geminiUsageEvents(response, context)) {
    try { if (await write(event) === false) ok = false; } catch { ok = false; }
  }
  return ok;
}

async function persistGeminiFailure(context = {}, options = {}) {
  return persistGeminiUsage({}, {
    ...context, success: false, grounded: false,
    failureClass: context.failureClass || "provider_failure",
  }, options);
}

module.exports = { geminiUsageEvents, persistGeminiUsage, persistGeminiFailure };
