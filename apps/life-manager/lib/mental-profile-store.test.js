"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { readMentalProfile } = require("./mental-profile-store.js");

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
