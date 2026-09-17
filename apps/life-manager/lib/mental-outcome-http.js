"use strict";

const { verifyOutcomeEnvelope, persistVerifiedOutcome } = require("./mental-outcome-ingest.js");

async function ingestMentalOutcome({ rawBody, timestamp, signature, secret, nowMs = Date.now(), persist } = {}) {
  let payload;
  try {
    payload = verifyOutcomeEnvelope({ rawBody, timestamp, signature, secret, nowMs });
  } catch (error) {
    const status = /signature|timestamp/.test(String(error && error.message)) ? 401 : 400;
    return { status, body: { ok: false, error: "invalid_outcome" } };
  }
  try {
    const result = await (persist || ((value) => persistVerifiedOutcome(value, {
      supaUrl: process.env.SUPABASE_URL,
      supaKey: process.env.SUPABASE_SERVICE_ROLE_KEY,
    })))(payload);
    return { status: 200, body: { ok: true, result, sourceOutcomeId: payload.sourceOutcomeId } };
  } catch {
    return { status: 503, body: { ok: false, error: "outcome_persistence_unavailable" } };
  }
}

module.exports = { ingestMentalOutcome };
