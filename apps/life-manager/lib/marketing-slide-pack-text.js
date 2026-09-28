"use strict";

// Generates fresh Larry slide-pack TEXT (hook + 4 body lines) for one pack.
// Dais direction (2026-09-28): the approved background images are good and
// must be REUSED every pack (see getCachedBackground() in
// marketing-slide-background-image.js); only the text should be new each
// post, driven by the family's explore/exploit performance. This keeps the
// per-pack cost near-zero (a few hundred text tokens) instead of the
// previous per-pack image-generation cost.

const GEMINI_TEXT_MODEL = "gemini-2.5-flash";
const ENDPOINT = `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_TEXT_MODEL}:generateContent`;
// Published per-token pricing for gemini-2.5-flash (input/output), used only
// to record an audit-friendly cost estimate on the approval object -- not
// billed from here. thinkingConfig.thinkingBudget: 0 (below) keeps actual
// usage near the low end of this (~100-200 tokens/call, well under $0.001).
const INPUT_COST_PER_TOKEN = 0.30 / 1_000_000;
const OUTPUT_COST_PER_TOKEN = 2.50 / 1_000_000;

// One brief per hook/format family -- the explore/exploit unit rotation.js
// already scores. Add a family here + to marketing-slide-pack-factory.js's
// FAMILIES background sets to grow variety.
const FAMILY_BRIEFS = Object.freeze({
  "question-hook": "a question-hook style: slide 1 is a short, pointed rhetorical question that makes the reader feel seen; the next 4 slides give short, concrete, gentle reframes or small actions, one per slide.",
  listicle: "a numbered listicle style: slide 1 is a short, curiosity-driving list title (e.g. \"...習慣５選\"); the next 4 slides are short numbered items (ひとつめ/ふたつめ/みっつめ/よっつめ), one short concrete habit or tip per slide.",
  "myth-vs-fact": "a myth-vs-fact style: slide 1 states a common but flawed belief people hold about mental wellbeing; the next 4 slides gently contrast it with a healthier reframe, one short idea per slide.",
});

function buildPrompt(familyId, avoidTexts) {
  const brief = FAMILY_BRIEFS[familyId];
  if (!brief) throw new Error(`slide text family ${familyId} is not configured`);
  const avoid = avoidTexts.length
    ? `Avoid repeating or closely paraphrasing any of these already-used lines:\n${avoidTexts.map((line) => `- ${String(line).replace(/\n/g, " / ")}`).join("\n")}\n`
    : "";
  return `You are writing Japanese Instagram carousel slide copy for a mental-wellness affirmation app. Never make medical claims, diagnoses, or guarantees.
Write ${brief}
Each line must be short enough to read at a glance (aim for under 20 Japanese characters per line; you may use a single "\\n" inside a line to break it into two short lines for a slide).
${avoid}Return ONLY compact JSON, no markdown fencing, in exactly this shape: {"hook": "...", "body": ["...", "...", "...", "..."]} (the hook string plus exactly 4 body strings).`;
}

// Real network call, kept tiny and injectable (`fetchImpl`) so callers never
// have to hit the network (or spend money) in tests.
async function fetchGeminiText(prompt, { apiKey, fetchImpl = fetch } = {}) {
  if (!apiKey) throw new Error("GEMINI_API_KEY is required for slide text generation");
  const response = await fetchImpl(`${ENDPOINT}?key=${encodeURIComponent(apiKey)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: { responseMimeType: "application/json", thinkingConfig: { thinkingBudget: 0 } },
    }),
  });
  if (!response.ok) throw new Error(`Gemini text generation HTTP ${response.status}`);
  const body = await response.json();
  const text = body?.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) throw new Error("Gemini text generation returned no text");
  const usage = body.usageMetadata || {};
  const costUsd = (Number(usage.promptTokenCount || 0) * INPUT_COST_PER_TOKEN)
    + (Number(usage.candidatesTokenCount || 0) * OUTPUT_COST_PER_TOKEN);
  return { text, costUsd };
}

// Returns { hook, body: [4 strings], costUsd }.
async function generateSlideCopy({ familyId, apiKey, avoidTexts = [], generateText = fetchGeminiText }) {
  const prompt = buildPrompt(familyId, avoidTexts);
  const { text, costUsd } = await generateText(prompt, { apiKey });
  let parsed;
  try {
    parsed = JSON.parse(String(text).trim().replace(/^```(?:json)?\s*|\s*```$/g, ""));
  } catch {
    throw new Error("slide text generation returned invalid JSON");
  }
  if (
    !parsed || typeof parsed.hook !== "string" || !parsed.hook.trim()
    || !Array.isArray(parsed.body) || parsed.body.length !== 4
    || parsed.body.some((line) => typeof line !== "string" || !line.trim())
  ) {
    throw new Error("slide text generation returned an invalid shape");
  }
  return { hook: parsed.hook.trim(), body: parsed.body.map((line) => line.trim()), costUsd };
}

module.exports = { FAMILY_BRIEFS, buildPrompt, fetchGeminiText, generateSlideCopy };
