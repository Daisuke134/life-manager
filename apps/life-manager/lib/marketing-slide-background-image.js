"use strict";

// Fetches (and caches) a photorealistic lifestyle background image for one
// slide, via Gemini's image model (gemini-2.5-flash-image, aka "nano
// banana") -- the cheapest decent image model we already hold a key for
// (checked ~/.config/fal/api_key and OPENAI_*/FAL_* in
// ~/.local/state/life-manager/.env + private/marketing.env: neither exists;
// GEMINI_API_KEY does). $0.039/image per Google's published per-image
// pricing for this model as of 2026-09; cached per prompt so a repeated
// topic/family never re-pays.

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const MODEL = "gemini-2.5-flash-image";
const ENDPOINT = `https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`;
const GEMINI_IMAGE_COST_USD = 0.039;

function promptCacheKey(prompt) {
  return crypto.createHash("sha256").update(String(prompt || "")).digest("hex");
}

// Real network call, kept tiny and injectable (`fetchImpl`) so callers never
// have to hit the network (or spend money) in tests.
async function fetchGeminiImage(prompt, { apiKey, fetchImpl = fetch, aspectRatio = "4:5" } = {}) {
  if (!apiKey) throw new Error("GEMINI_API_KEY is required for slide background generation");
  const response = await fetchImpl(`${ENDPOINT}?key=${encodeURIComponent(apiKey)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { imageConfig: { aspectRatio } },
    }),
  });
  if (!response.ok) {
    throw new Error(`Gemini image generation HTTP ${response.status}`);
  }
  const body = await response.json();
  const parts = body?.candidates?.[0]?.content?.parts || [];
  const imagePart = parts.find((part) => part.inlineData?.data);
  if (!imagePart) throw new Error("Gemini image generation returned no image");
  return {
    buffer: Buffer.from(imagePart.inlineData.data, "base64"),
    extension: imagePart.inlineData.mimeType === "image/jpeg" ? "jpg" : "png",
  };
}

// Returns { file, costUsd, cached }. Never calls the network for a prompt
// already in cacheDir.
async function resolveSlideBackground({ prompt, cacheDir, apiKey, fetchImpl, fetchImage = fetchGeminiImage }) {
  if (!prompt || !String(prompt).trim()) throw new Error("slide background prompt is required");
  if (!cacheDir) throw new Error("slide background cache dir is required");
  fs.mkdirSync(cacheDir, { recursive: true, mode: 0o700 });
  const key = promptCacheKey(prompt);
  const existing = ["png", "jpg"]
    .map((ext) => path.join(cacheDir, `${key}.${ext}`))
    .find((file) => fs.existsSync(file));
  if (existing) return { file: existing, costUsd: 0, cached: true };

  const { buffer, extension } = await fetchImage(prompt, { apiKey, fetchImpl });
  const file = path.join(cacheDir, `${key}.${extension}`);
  const temp = `${file}.tmp-${process.pid}-${crypto.randomUUID()}`;
  fs.writeFileSync(temp, buffer, { mode: 0o600 });
  fs.renameSync(temp, file);
  return { file, costUsd: GEMINI_IMAGE_COST_USD, cached: false };
}

// Returns { file, costUsd, cached } for an already-cached prompt only --
// NEVER calls the network. Dais direction (2026-09-28): the approved
// background set is fixed and must be reused forever; only the composited
// text changes per pack. Use this (not resolveSlideBackground) in the
// factory's normal generation path so per-pack image cost is always exactly
// $0. resolveSlideBackground stays available for deliberately seeding a new
// background into the approved set (a separate, explicit action).
function getCachedBackground({ prompt, cacheDir }) {
  if (!prompt || !String(prompt).trim()) throw new Error("slide background prompt is required");
  if (!cacheDir) throw new Error("slide background cache dir is required");
  const key = promptCacheKey(prompt);
  const file = ["png", "jpg"]
    .map((ext) => path.join(cacheDir, `${key}.${ext}`))
    .find((candidate) => fs.existsSync(candidate));
  if (!file) throw new Error(`slide background is not in the approved cache for this prompt (${key})`);
  return { file, costUsd: 0, cached: true };
}

module.exports = { GEMINI_IMAGE_COST_USD, fetchGeminiImage, getCachedBackground, promptCacheKey, resolveSlideBackground };
