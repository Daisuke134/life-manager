"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

function promptCacheKey(prompt) {
  return crypto.createHash("sha256").update(String(prompt || "")).digest("hex");
}

// Marketing publication never creates image assets. It may only reuse a
// background that was already approved and stored in the local cache.
function getCachedBackground({ prompt, cacheDir }) {
  if (!prompt || !String(prompt).trim()) throw new Error("slide background prompt is required");
  if (!cacheDir) throw new Error("slide background cache dir is required");
  const key = promptCacheKey(prompt);
  const file = ["png", "jpg"]
    .map((ext) => path.join(cacheDir, `${key}.${ext}`))
    .find((candidate) => fs.existsSync(candidate) && fs.statSync(candidate).isFile());
  if (!file) throw new Error(`slide background is not in the approved cache for this prompt (${key})`);
  return { file, costUsd: 0, cached: true };
}

// Retain the old function name for existing callers, but make it cache-only.
async function resolveSlideBackground(options) {
  return getCachedBackground(options);
}

module.exports = { getCachedBackground, promptCacheKey, resolveSlideBackground };
