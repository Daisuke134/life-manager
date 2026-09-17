"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { validateProfileTag, projectMentalProfile } = require("./mental-profile.js");

const HASH = "a".repeat(64);

test("profile tag accepts only explicit closed source-backed facts", () => {
  assert.deepEqual(validateProfileTag({
    uid: "u1", kind: "theme", tag: "self-worth", weight: 1,
    basis: "explicit_user_statement", explicit: true, sourceRefHash: HASH,
    observedAt: "2026-09-18T00:00:00.000Z", expiresAt: null, supersededBy: null,
  }), {
    uid: "u1", kind: "theme", tag: "self-worth", weight: 1,
    basis: "explicit_user_statement", explicit: true, sourceRefHash: HASH,
    observedAt: "2026-09-18T00:00:00.000Z", expiresAt: null, supersededBy: null,
  });
  assert.throws(() => validateProfileTag({ uid: "u1", kind: "theme", tag: "mood:depressed", weight: 1, basis: "inferred", explicit: false, sourceRefHash: HASH, observedAt: "2026-09-18T00:00:00.000Z" }), /profile tag/);
  assert.throws(() => validateProfileTag({ uid: "u1", kind: "theme", tag: "self-worth", weight: 1, basis: "explicit_user_statement", explicit: true, sourceRefHash: "raw telegram text", observedAt: "2026-09-18T00:00:00.000Z" }), /source/);
});

test("profile projection weights repeated explicit themes and excludes expired/superseded rows", () => {
  const result = projectMentalProfile([
    { uid: "u1", kind: "theme", tag: "self-worth", weight: 1, basis: "explicit_user_statement", explicit: true, source_ref_hash: HASH, observed_at: "2026-09-16T00:00:00.000Z", expires_at: null, superseded_by: null },
    { uid: "u1", kind: "theme", tag: "self-worth", weight: 1.5, basis: "explicit_user_statement", explicit: true, source_ref_hash: HASH, observed_at: "2026-09-17T00:00:00.000Z", expires_at: null, superseded_by: null },
    { uid: "u1", kind: "theme", tag: "courage", weight: 1, basis: "explicit_user_statement", explicit: true, source_ref_hash: HASH, observed_at: "2026-09-17T00:00:00.000Z", expires_at: "2026-09-17T00:00:00.000Z", superseded_by: null },
    { uid: "u1", kind: "theme", tag: "rest", weight: 1, basis: "explicit_user_statement", explicit: true, source_ref_hash: HASH, observed_at: "2026-09-17T00:00:00.000Z", expires_at: null, superseded_by: "tag-2" },
    { uid: "u1", kind: "tone", tag: "gentle", weight: 1, basis: "explicit_user_statement", explicit: true, source_ref_hash: HASH, observed_at: "2026-09-17T00:00:00.000Z", expires_at: null, superseded_by: null },
  ], Date.parse("2026-09-18T00:00:00.000Z"));
  assert.deepEqual(result.themes, ["self-worth"]);
  assert.deepEqual(result.tones, ["gentle"]);
  assert.deepEqual(result.avoidThemes, []);
  assert.equal(result.weights["self-worth"], 2.5);
});

test("profile projection never carries raw source text", () => {
  const result = projectMentalProfile([{ uid: "u1", kind: "theme", tag: "mindfulness", weight: 1, basis: "explicit_goal", explicit: true, source_ref_hash: HASH, observed_at: "2026-09-18T00:00:00.000Z", raw_text: "private", superseded_by: null }], Date.now());
  assert.doesNotMatch(JSON.stringify(result), /private|raw_text|chat_id|name/);
});
