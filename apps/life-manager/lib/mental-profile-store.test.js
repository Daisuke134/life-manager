"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { readMentalProfile, recordMentalProfileTag } = require("./mental-profile-store.js");

test("profile store reads only closed source-backed columns", async () => {
  let request;
  const profile = await readMentalProfile("u1", Date.parse("2026-09-18T00:00:00Z"), { url: "https://supa", key: "service" }, async (url, init) => {
    request = { url, init };
    return { ok: true, json: async () => [{
      uid: "u1", kind: "theme", tag: "confidence", weight: 1,
      basis: "explicit_user_statement", explicit: true, source_ref_hash: "a".repeat(64),
      observed_at: "2026-09-17T00:00:00Z", expires_at: null, superseded_by: null,
    }] };
  });
  assert.deepEqual(profile.themes, ["confidence"]);
  assert.match(request.url, /select=uid,kind,tag,weight,basis,explicit,source_ref_hash,observed_at,expires_at,superseded_by/);
  assert.doesNotMatch(request.url, /body|subject|chat_id|name/);
  assert.deepEqual(request.init.headers, { apikey: "service", Authorization: "Bearer service" });
});

test("profile store fails closed on unreadable history", async () => {
  await assert.rejects(readMentalProfile("u1", Date.now(), { url: "https://supa", key: "service" }, async () => ({ ok: false, status: 503 })), /mental profile lookup failed/);
});

test("profile store writes one explicit correction tag with idempotent provenance", async () => {
  let request;
  const result = await recordMentalProfileTag({
    uid: "u1", kind: "tone", tag: "direct", weight: 1,
    basis: "explicit_correction", explicit: true,
    sourceRefHash: "b".repeat(64), observedAt: "2026-09-18T00:00:00Z",
    expiresAt: null, supersededBy: null,
  }, { url: "https://supa", key: "service" }, async (url, init) => {
    request = { url, init };
    return { ok: true, status: 201, json: async () => [{ id: 1 }] };
  });
  assert.deepEqual(result, { recorded: true, duplicate: false });
  assert.match(request.url, /lm_mental_profile_tags\?on_conflict=uid%2Ckind%2Ctag%2Csource_ref_hash/);
  assert.deepEqual(JSON.parse(request.init.body), {
    uid: "u1", kind: "tone", tag: "direct", weight: 1,
    basis: "explicit_correction", explicit: true, source_ref_hash: "b".repeat(64),
    observed_at: "2026-09-18T00:00:00.000Z", expires_at: null, superseded_by: null,
  });
});

test("profile store refuses malformed correction tags before network", async () => {
  let calls = 0;
  await assert.rejects(recordMentalProfileTag({ uid: "u1", kind: "tone", tag: "unknown", weight: 1,
    basis: "explicit_correction", explicit: true, sourceRefHash: "c".repeat(64),
    observedAt: "2026-09-18T00:00:00Z", expiresAt: null, supersededBy: null,
  }, { url: "https://supa", key: "service" }, async () => { calls += 1; return { ok: true, status: 201 }; }), /profile tag/);
  assert.equal(calls, 0);
});
