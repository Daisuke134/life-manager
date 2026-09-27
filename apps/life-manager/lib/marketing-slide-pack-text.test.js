"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { FAMILY_BRIEFS, buildPrompt, generateSlideCopy } = require("./marketing-slide-pack-text.js");

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
