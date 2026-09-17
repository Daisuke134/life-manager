"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { signOutcomeEnvelope } = require("./mental-outcome-ingest.js");
const { ingestMentalOutcome } = require("./mental-outcome-http.js");

const SECRET = "s".repeat(40);
const PAYLOAD = {
  uid: "u1", sourceOutcomeId: "job-search:outcome-1", kind: "interview",
  company: "Example社", role: "Engineer", verifiedAt: "2026-09-17T01:01:00.000Z",
  evidenceRef: "job-search-outcome://outcome-1",
};

test("HTTP outcome handler accepts signed structured projection and persists once", async () => {
  let persisted;
  const rawBody = JSON.stringify(PAYLOAD);
  const timestamp = "2026-09-17T01:01:30.000Z";
  const result = await ingestMentalOutcome({
    rawBody, timestamp, signature: signOutcomeEnvelope(rawBody, timestamp, SECRET), secret: SECRET,
    nowMs: Date.parse("2026-09-17T01:02:00.000Z"),
    persist: async (payload) => { persisted = payload; return "inserted"; },
  });
  assert.deepEqual(result, { status: 200, body: { ok: true, result: "inserted", sourceOutcomeId: PAYLOAD.sourceOutcomeId } });
  assert.deepEqual(persisted, PAYLOAD);
});

test("HTTP outcome handler rejects bad signature and does not persist", async () => {
  let calls = 0;
  const rawBody = JSON.stringify(PAYLOAD);
  const result = await ingestMentalOutcome({
    rawBody, timestamp: "2026-09-17T01:01:30.000Z", signature: "bad", secret: SECRET,
    nowMs: Date.parse("2026-09-17T01:02:00.000Z"),
    persist: async () => { calls += 1; return "inserted"; },
  });
  assert.equal(result.status, 401);
  assert.equal(calls, 0);
});

