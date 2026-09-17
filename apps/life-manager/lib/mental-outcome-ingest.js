"use strict";

const crypto = require("node:crypto");

const ALLOWED_KINDS = new Set(["interview", "offer", "rejection"]);
const MAX_SKEW_MS = 5 * 60 * 1000;
const PAYLOAD_KEYS = Object.freeze(["company", "evidenceRef", "kind", "role", "sourceOutcomeId", "uid", "verifiedAt"]);

function signOutcomeEnvelope(rawBody, timestamp, secret) {
  return crypto.createHmac("sha256", String(secret))
    .update(`${timestamp}\n${rawBody}`, "utf8")
    .digest("base64url");
}

function verifyOutcomeEnvelope({ rawBody, timestamp, signature, secret, nowMs = Date.now() } = {}) {
  if (typeof rawBody !== "string" || Buffer.byteLength(rawBody, "utf8") > 16_384) throw new Error("outcome body invalid");
  if (!secret || typeof signature !== "string" || typeof timestamp !== "string") throw new Error("outcome signature missing");
  const timeMs = Date.parse(timestamp);
  if (!Number.isFinite(timeMs) || Math.abs(nowMs - timeMs) > MAX_SKEW_MS) throw new Error("outcome timestamp stale");
  const expected = signOutcomeEnvelope(rawBody, timestamp, secret);
  const actualBuf = Buffer.from(signature);
  const expectedBuf = Buffer.from(expected);
  if (actualBuf.length !== expectedBuf.length || !crypto.timingSafeEqual(actualBuf, expectedBuf)) throw new Error("outcome signature invalid");
  let value;
  try { value = JSON.parse(rawBody); } catch { throw new Error("outcome json invalid"); }
  if (!value || typeof value !== "object" || Array.isArray(value)
      || Object.keys(value).sort().join(",") !== [...PAYLOAD_KEYS].sort().join(",")) throw new Error("outcome schema invalid");
  if (!value.uid || !value.sourceOutcomeId || !value.evidenceRef || !value.company || !value.role
      || !ALLOWED_KINDS.has(value.kind) || !Number.isFinite(Date.parse(value.verifiedAt))) throw new Error("outcome fields invalid");
  return value;
}

function supaBase(url) { return String(url).replace(/\/$/, ""); }

async function persistVerifiedOutcome(outcome, { supaUrl, supaKey, fetchImpl = globalThis.fetch } = {}) {
  if (!supaUrl || !supaKey) throw new Error("outcome persistence unavailable");
  const response = await fetchImpl(`${supaBase(supaUrl)}/rest/v1/lm_verified_outcomes`, {
    method: "POST",
    headers: {
      apikey: supaKey,
      Authorization: `Bearer ${supaKey}`,
      "Content-Type": "application/json",
      Prefer: "return=representation,resolution=ignore-duplicates",
    },
    body: JSON.stringify({
      uid: outcome.uid,
      source_outcome_id: outcome.sourceOutcomeId,
      kind: outcome.kind,
      company: outcome.company,
      role: outcome.role,
      verified_at: outcome.verifiedAt,
      evidence_ref: outcome.evidenceRef,
    }),
  }).catch(() => null);
  if (response && response.status === 201) {
    const rows = typeof response.json === "function" ? await response.json().catch(() => null) : null;
    return Array.isArray(rows) && rows.length === 0 ? "duplicate" : "inserted";
  }
  if (response && response.status === 409) return "duplicate";
  throw new Error(`outcome persistence failed (${response ? response.status : "no response"})`);
}

module.exports = { MAX_SKEW_MS, signOutcomeEnvelope, verifyOutcomeEnvelope, persistVerifiedOutcome };
