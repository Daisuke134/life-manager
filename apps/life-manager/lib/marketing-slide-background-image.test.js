"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { GEMINI_IMAGE_COST_USD, promptCacheKey, resolveSlideBackground } = require("./marketing-slide-background-image.js");

function tempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "slide-bg-cache-"));
}

test("resolveSlideBackground calls fetchImage and writes the cache file on a cold cache", async () => {
  const cacheDir = tempDir();
  let calls = 0;
  const result = await resolveSlideBackground({
    prompt: "a cozy lifestyle photo",
    cacheDir,
    apiKey: "test-key",
    fetchImage: async (prompt, { apiKey }) => {
      calls += 1;
      assert.equal(prompt, "a cozy lifestyle photo");
      assert.equal(apiKey, "test-key");
      return { buffer: Buffer.from("fake-png-bytes"), extension: "png" };
    },
  });
  assert.equal(calls, 1);
  assert.equal(result.cached, false);
  assert.equal(result.costUsd, GEMINI_IMAGE_COST_USD);
  assert.ok(fs.existsSync(result.file));
  assert.equal(fs.readFileSync(result.file, "utf8"), "fake-png-bytes");
});

test("resolveSlideBackground is free and network-free on a warm cache (same prompt)", async () => {
  const cacheDir = tempDir();
  let calls = 0;
  const fetchImage = async () => { calls += 1; return { buffer: Buffer.from("x"), extension: "png" }; };
  const first = await resolveSlideBackground({ prompt: "same prompt", cacheDir, apiKey: "k", fetchImage });
  const second = await resolveSlideBackground({ prompt: "same prompt", cacheDir, apiKey: "k", fetchImage });
  assert.equal(calls, 1);
  assert.equal(second.cached, true);
  assert.equal(second.costUsd, 0);
  assert.equal(second.file, first.file);
});

test("resolveSlideBackground uses a different cache entry per distinct prompt", async () => {
  const cacheDir = tempDir();
  const fetchImage = async () => ({ buffer: Buffer.from("x"), extension: "png" });
  const a = await resolveSlideBackground({ prompt: "prompt A", cacheDir, apiKey: "k", fetchImage });
  const b = await resolveSlideBackground({ prompt: "prompt B", cacheDir, apiKey: "k", fetchImage });
  assert.notEqual(a.file, b.file);
});

test("resolveSlideBackground rejects a missing prompt or cache dir", async () => {
  await assert.rejects(resolveSlideBackground({ prompt: "", cacheDir: "/tmp/x" }), /prompt/);
  await assert.rejects(resolveSlideBackground({ prompt: "p", cacheDir: "" }), /cache dir/);
});

test("promptCacheKey is a stable sha256 hex digest", () => {
  const key = promptCacheKey("hello");
  assert.match(key, /^[0-9a-f]{64}$/);
  assert.equal(key, promptCacheKey("hello"));
  assert.notEqual(key, promptCacheKey("hello2"));
});

const { getCachedBackground } = require("./marketing-slide-background-image.js");

test("getCachedBackground returns the cached file at $0 cost and never calls the network", async () => {
  const cacheDir = tempDir();
  const cached = await resolveSlideBackground({
    prompt: "a fixed approved background",
    cacheDir,
    apiKey: "k",
    fetchImage: async () => ({ buffer: Buffer.from("x"), extension: "png" }),
  });
  const result = getCachedBackground({ prompt: "a fixed approved background", cacheDir });
  assert.equal(result.file, cached.file);
  assert.equal(result.costUsd, 0);
  assert.equal(result.cached, true);
});

test("getCachedBackground throws (never fetches) when the prompt was never cached", () => {
  const cacheDir = tempDir();
  assert.throws(() => getCachedBackground({ prompt: "never generated", cacheDir }), /not in the approved cache/);
});
