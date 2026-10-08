"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { getCachedBackground, promptCacheKey, resolveSlideBackground } = require("./marketing-slide-background-image.js");

function tempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "slide-bg-cache-"));
}

test("background resolver reuses an approved cached image without calling a provider", async () => {
  const cacheDir = tempDir();
  const prompt = "a fixed approved background";
  const file = path.join(cacheDir, `${promptCacheKey(prompt)}.png`);
  fs.writeFileSync(file, Buffer.from("cached-image"));
  let providerCalls = 0;

  const result = await resolveSlideBackground({
    prompt,
    cacheDir,
    apiKey: "fixture-key-that-must-not-be-used",
    fetchImage: async () => { providerCalls += 1; throw new Error("paid image provider called"); },
  });

  assert.equal(result.file, file);
  assert.equal(result.costUsd, 0);
  assert.equal(result.cached, true);
  assert.equal(providerCalls, 0);
});

test("background resolver fails closed on a cache miss instead of generating a paid image", async () => {
  const cacheDir = tempDir();
  let providerCalls = 0;

  await assert.rejects(resolveSlideBackground({
    prompt: "not in approved cache",
    cacheDir,
    apiKey: "fixture-key-that-must-not-be-used",
    fetchImage: async () => { providerCalls += 1; throw new Error("paid image provider called"); },
  }), /not in the approved cache/);

  assert.equal(providerCalls, 0);
});

test("getCachedBackground requires an existing approved asset", () => {
  const cacheDir = tempDir();
  assert.throws(() => getCachedBackground({ prompt: "missing", cacheDir }), /not in the approved cache/);
});

test("promptCacheKey is a stable sha256 hex digest", () => {
  const key = promptCacheKey("hello");
  assert.match(key, /^[0-9a-f]{64}$/);
  assert.equal(key, promptCacheKey("hello"));
  assert.notEqual(key, promptCacheKey("hello2"));
});
