"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { FAMILY_BRIEFS, FAMILY_BRIEFS_BY_LOCALE, buildPrompt, generateSlideCopy } = require("./marketing-slide-pack-text.js");

function fakeGenerateText(response) {
  return async () => ({ text: JSON.stringify(response), costUsd: 0.0005 });
}

test("generateSlideCopy parses a well-formed Gemini JSON response", async () => {
  const result = await generateSlideCopy({
    familyId: "listicle",
    apiKey: "k",
    generateText: fakeGenerateText({ hook: "見出し", body: ["ひとつめ", "ふたつめ", "みっつめ", "よっつめ"] }),
  });
  assert.equal(result.hook, "見出し");
  assert.deepEqual(result.body, ["ひとつめ", "ふたつめ", "みっつめ", "よっつめ"]);
  assert.equal(result.costUsd, 0.0005);
});

test("generateSlideCopy strips a markdown code fence if the model adds one", async () => {
  const generateText = async () => ({ text: "```json\n{\"hook\":\"h\",\"body\":[\"a\",\"b\",\"c\",\"d\"]}\n```", costUsd: 0.0004 });
  const result = await generateSlideCopy({ familyId: "question-hook", apiKey: "k", generateText });
  assert.equal(result.hook, "h");
});

test("generateSlideCopy rejects a response missing the required shape", async () => {
  await assert.rejects(
    generateSlideCopy({ familyId: "listicle", apiKey: "k", generateText: fakeGenerateText({ hook: "h", body: ["only one"] }) }),
    /invalid shape/,
  );
  await assert.rejects(
    generateSlideCopy({ familyId: "listicle", apiKey: "k", generateText: async () => ({ text: "not json", costUsd: 0 }) }),
    /invalid JSON/,
  );
});

test("generateSlideCopy rejects an unconfigured family", async () => {
  await assert.rejects(
    generateSlideCopy({ familyId: "nonexistent-family", apiKey: "k", generateText: fakeGenerateText({ hook: "h", body: ["a", "b", "c", "d"] }) }),
    /family nonexistent-family is not configured/,
  );
});

test("buildPrompt includes an avoid-repeating instruction with prior texts when supplied", () => {
  const withAvoid = buildPrompt("listicle", ["古いフック"]);
  assert.match(withAvoid, /Avoid repeating/);
  assert.match(withAvoid, /古いフック/);
  const withoutAvoid = buildPrompt("listicle", []);
  assert.doesNotMatch(withoutAvoid, /Avoid repeating/);
});

test("FAMILY_BRIEFS covers the three rotation families used by the factory", () => {
  assert.deepEqual(Object.keys(FAMILY_BRIEFS).sort(), ["listicle", "myth-vs-fact", "question-hook"]);
});

test("FAMILY_BRIEFS_BY_LOCALE covers ja and en with the same families (EN lanes reuse this module, not a fork)", () => {
  assert.deepEqual(Object.keys(FAMILY_BRIEFS_BY_LOCALE).sort(), ["en", "ja"]);
  assert.deepEqual(Object.keys(FAMILY_BRIEFS_BY_LOCALE.en).sort(), Object.keys(FAMILY_BRIEFS_BY_LOCALE.ja).sort());
});

test("buildPrompt writes English instructions for locale en and Japanese for locale ja (default)", () => {
  const en = buildPrompt("listicle", [], "en");
  assert.match(en, /English carousel slide copy/);
  assert.doesNotMatch(en, /Japanese carousel slide copy/);
  const ja = buildPrompt("listicle", []);
  assert.match(ja, /Japanese carousel slide copy/);
});

test("generateSlideCopy passes locale through to the prompt", async () => {
  let seenPrompt = null;
  await generateSlideCopy({
    familyId: "listicle",
    apiKey: "k",
    locale: "en",
    generateText: async (prompt) => { seenPrompt = prompt; return { text: JSON.stringify({ hook: "h", body: ["a", "b", "c", "d"] }), costUsd: 0.0004 }; },
  });
  assert.match(seenPrompt, /English carousel slide copy/);
});
