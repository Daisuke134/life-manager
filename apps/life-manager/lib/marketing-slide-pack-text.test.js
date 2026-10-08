"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { FAMILY_BRIEFS_BY_LOCALE, familyForStyleHint, generateSlideCopy, generateVideoHookText } = require("./marketing-slide-pack-text.js");

test("slide copy uses deterministic local variants with zero model calls and zero cost", async () => {
  const originalFetch = globalThis.fetch;
  let requests = 0;
  globalThis.fetch = async () => {
    requests += 1;
    throw new Error("model HTTP call is forbidden in mobile marketing copy");
  };
  try {
    const first = await generateSlideCopy({ familyId: "listicle", locale: "ja", variantSeed: "slot-a" });
    const retry = await generateSlideCopy({ familyId: "listicle", locale: "ja", variantSeed: "slot-a" });
    const next = await generateSlideCopy({ familyId: "listicle", locale: "ja", variantSeed: "slot-b" });

    assert.deepEqual(first, retry, "a retry of one slot must produce the same local copy");
    assert.notDeepEqual(first, next, "different slots should rotate the local copy");
    assert.equal(first.body.length, 4);
    assert.ok(first.hook.length > 0);
    assert.equal(first.costUsd, 0);
    assert.equal(next.costUsd, 0);
    assert.equal(requests, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("local copy bank covers JA and EN for each supported family", async () => {
  assert.deepEqual(Object.keys(FAMILY_BRIEFS_BY_LOCALE).sort(), ["en", "ja"]);
  assert.deepEqual(Object.keys(FAMILY_BRIEFS_BY_LOCALE.en).sort(), ["listicle", "myth-vs-fact", "question-hook"]);
  for (const locale of ["ja", "en"]) {
    for (const familyId of Object.keys(FAMILY_BRIEFS_BY_LOCALE[locale])) {
      const result = await generateSlideCopy({ familyId, locale, variantSeed: `${locale}:${familyId}` });
      assert.equal(result.body.length, 4);
      assert.equal(result.costUsd, 0);
      assert.ok(result.hook.length > 0);
      assert.ok(result.body.every((line) => line.length > 0));
    }
  }
});

test("slide copy rejects an unconfigured local family", async () => {
  await assert.rejects(generateSlideCopy({ familyId: "unknown-family", locale: "ja", variantSeed: "slot" }), /family unknown-family is not configured/);
});

test("familyForStyleHint deterministically maps a style hint to a configured local family", () => {
  const family = familyForStyleHint("5 affirmations to tell yourself every morning", "en");
  assert.ok(Object.keys(FAMILY_BRIEFS_BY_LOCALE.en).includes(family));
  assert.equal(family, familyForStyleHint("5 affirmations to tell yourself every morning", "en"));
});

test("video hook text is selected locally without an API key", async () => {
  const first = await generateVideoHookText({ styleHint: "first type", locale: "en", variantSeed: "slot-a" });
  const second = await generateVideoHookText({ styleHint: "first type", locale: "en", variantSeed: "slot-b" });
  assert.ok(first.hook.length > 0);
  assert.ok(second.hook.length > 0);
  assert.equal(first.costUsd, 0);
  assert.equal(second.costUsd, 0);
});
