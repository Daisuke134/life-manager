"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
  signOutcomeEnvelope,
  verifyOutcomeEnvelope,
  persistVerifiedOutcome,
} = require("./mental-outcome-ingest.js");

const SECRET = "s".repeat(40);
const PAYLOAD = {
  sourceOutcomeId: "job-search:outcome-1",
  kind: "rejection",
  company: "Example社",
  role: "Software Engineer",
  verifiedAt: "2026-09-17T01:01:00.000Z",
  evidenceRef: "job-search-outcome://outcome-1",
  uid: "u1",
};
const NOW = Date.parse("2026-09-17T01:02:00.000Z");

test("signed outcome envelope verifies exact bytes and timestamp", () => {
  const timestamp = "2026-09-17T01:01:30.000Z";
  const rawBody = JSON.stringify(PAYLOAD);
  const signature = signOutcomeEnvelope(rawBody, timestamp, SECRET);
  assert.deepEqual(verifyOutcomeEnvelope({ rawBody, timestamp, signature, secret: SECRET, nowMs: NOW }), PAYLOAD);
  assert.throws(() => verifyOutcomeEnvelope({ rawBody: JSON.stringify({ ...PAYLOAD, company: "Other" }), timestamp, signature, secret: SECRET, nowMs: NOW }), /signature/);
});

test("outcome envelope rejects raw mail fields and stale signatures", () => {
  const timestamp = "2026-09-17T01:01:30.000Z";
  const rawBody = JSON.stringify({ ...PAYLOAD, body: "raw gmail body" });
  const signature = signOutcomeEnvelope(rawBody, timestamp, SECRET);
  assert.throws(() => verifyOutcomeEnvelope({ rawBody, timestamp, signature, secret: SECRET, nowMs: NOW }), /raw|schema|field/i);
  assert.throws(() => verifyOutcomeEnvelope({ rawBody: JSON.stringify(PAYLOAD), timestamp: "2026-09-16T00:00:00.000Z", signature: signOutcomeEnvelope(JSON.stringify(PAYLOAD), "2026-09-16T00:00:00.000Z", SECRET), secret: SECRET, nowMs: NOW }), /timestamp|stale/i);
});

test("verified outcome persists structured fields only", async () => {
  let request;
  const fetchImpl = async (url, init) => { request = { url, init }; return { status: 201, ok: true }; };
  const result = await persistVerifiedOutcome(PAYLOAD, { supaUrl: "https://s", supaKey: "k", fetchImpl });
  assert.equal(result, "inserted");
  assert.deepEqual(JSON.parse(request.init.body), {
    uid: "u1", source_outcome_id: PAYLOAD.sourceOutcomeId, kind: "rejection",
    company: "Example社", role: "Software Engineer", verified_at: PAYLOAD.verifiedAt,
    evidence_ref: PAYLOAD.evidenceRef,
  });
  assert.doesNotMatch(request.init.body, /body|subject|snippet/);
});

