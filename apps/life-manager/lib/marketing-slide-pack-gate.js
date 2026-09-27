"use strict";

// Automated, auditable replacement for a human "approve this slideshow pack"
// review. Every check here is the same thing a human reviewer would look
// for before approving a Larry/native-carousel pack: right slide count and
// size, no blank slides, a caption that fits the platform and carries the
// App Store CTA, no disallowed claims, and a minimum content-quality bar.
// The result (passed/score/reasons) is written verbatim into the
// approval_ref object so the decision stays inspectable later -- see
// buildAutomatedApproval() in marketing-slide-pack-factory.js.

const { assertMarketingCarouselJpeg } = require("./marketing-native-carousel-publication-adapter.js");
const { platformCaptionLimit } = require("./marketing-app-store-cta.js");

const SLIDE_COUNT = 6;
const MAX_SLIDE_TEXT_LENGTH = 120;
const RUBRIC_THRESHOLD = 60;
const MIN_SLIDE_WIDTH = 1080;
const MIN_SLIDE_HEIGHT = 1350;
const DEFAULT_MAX_COST_USD = 0.30;

// Claims that go beyond skills/earn/marketing-engine/registry/products/*.json
// approved_claims -- absolute medical/financial/guarantee language a
// wellness-affirmation app must never post. Extend, never relax.
const BANNED_PHRASES = Object.freeze([
  "cure", "cures", "cured", "diagnose", "diagnosis", "guaranteed", "guarantee",
  "instant fix", "risk-free", "no side effects", "治る", "治療", "診断できます",
  "保証します", "絶対に治る", "必ず痩せる", "副作用なし",
]);

function textReasons(text, label) {
  const value = String(text == null ? "" : text).trim();
  const reasons = [];
  if (!value) reasons.push(`${label} is blank`);
  if (value.length > MAX_SLIDE_TEXT_LENGTH) reasons.push(`${label} exceeds ${MAX_SLIDE_TEXT_LENGTH} characters`);
  const lower = value.toLowerCase();
  for (const phrase of BANNED_PHRASES) {
    if (lower.includes(phrase.toLowerCase())) reasons.push(`${label} contains banned phrase "${phrase}"`);
  }
  return reasons;
}

// Deterministic heuristic standing in for an LLM rubric judge: rewards a
// short punchy hook slide, a numeral/question hook (proven slideshow
// pattern), and slide-to-slide text variety (no filler repeats).
// ponytail: swap the body for a real LLM judge call when one is wired in
// (inject as `scoreFn` below); this keeps gate/rotation/selection testable
// today without a network dependency.
function rubricScore(pack) {
  const texts = pack.slides.map((slide) => String(slide.text || "").trim());
  const [hook] = texts;
  let score = 50;
  if (hook && hook.length > 0 && hook.length <= 40) score += 15;
  if (/[0-9０-９]/.test(hook || "") || /[?？]/.test(hook || "")) score += 15;
  const distinct = new Set(texts).size;
  score += distinct === texts.length ? 20 : -10 * (texts.length - distinct);
  return Math.max(0, Math.min(100, score));
}

function hasAppStoreCta(captionText) {
  return /apps\.apple\.com|プロフィールのリンク|link in bio/i.test(captionText);
}

// pack: { slide_count, slides: [{ position, role, text, media_ref }] }
// caption: plain caption text (post-CTA)
// mediaFiles: local file paths for each slide image, in slide order (optional; JPEG dimension check)
// imageChecks: [{ present, contrastOk }] in slide order (optional; from render-slide-image.py's
//   luminance_std/text_contrast_ok -- catches a flat/blank background or unreadable text overlay
//   that a pure JPEG-dimension check would miss)
// totalCostUsd/maxCostUsd: enforces the per-pack image-generation cost cap
function runAutomatedGate({
  pack, caption, mediaFiles = [], imageChecks = [], totalCostUsd = 0, maxCostUsd = DEFAULT_MAX_COST_USD,
  platform = "instagram", scoreFn = rubricScore,
} = {}) {
  const reasons = [];
  const validShape = pack && pack.slide_count === SLIDE_COUNT && Array.isArray(pack.slides) && pack.slides.length === SLIDE_COUNT;
  if (!validShape) {
    reasons.push(`slide pack must have exactly ${SLIDE_COUNT} slides`);
  } else {
    pack.slides.forEach((slide, index) => reasons.push(...textReasons(slide && slide.text, `slide ${index + 1} text`)));
  }

  const captionLimit = platformCaptionLimit(platform);
  const captionText = String(caption || "").trim();
  reasons.push(...textReasons(captionText, "caption").filter((reason) => !reason.includes("exceeds")));
  if (captionText.length > captionLimit) reasons.push(`caption exceeds ${captionLimit} characters`);
  if (captionText && !hasAppStoreCta(captionText)) reasons.push("caption is missing the App Store CTA");

  mediaFiles.forEach((file, index) => {
    try {
      const dimensions = assertMarketingCarouselJpeg(file, `slide ${index + 1} image`, { maxWidth: MIN_SLIDE_WIDTH, maxHeight: MIN_SLIDE_HEIGHT });
      if (dimensions && (dimensions.width < MIN_SLIDE_WIDTH || dimensions.height < MIN_SLIDE_HEIGHT)) {
        reasons.push(`slide ${index + 1} image is smaller than ${MIN_SLIDE_WIDTH}x${MIN_SLIDE_HEIGHT}`);
      }
    } catch (error) {
      reasons.push(error.message);
    }
  });

  if (validShape && imageChecks.length !== pack.slides.length) {
    reasons.push(`slide pack must have an image check for all ${SLIDE_COUNT} slides`);
  }
  imageChecks.forEach((check, index) => {
    if (!check || !check.present) reasons.push(`slide ${index + 1} image is missing`);
    else if (!check.contrastOk) reasons.push(`slide ${index + 1} text does not have enough contrast against its background`);
  });

  if (Number(totalCostUsd) > Number(maxCostUsd)) {
    reasons.push(`slide pack image generation cost $${totalCostUsd} exceeds the $${maxCostUsd} cap`);
  }

  const score = validShape ? scoreFn(pack) : 0;
  if (score < RUBRIC_THRESHOLD) reasons.push(`rubric score ${score} is below threshold ${RUBRIC_THRESHOLD}`);

  return { passed: reasons.length === 0, score, reasons };
}

module.exports = {
  BANNED_PHRASES,
  MAX_SLIDE_TEXT_LENGTH,
  MIN_SLIDE_HEIGHT,
  MIN_SLIDE_WIDTH,
  RUBRIC_THRESHOLD,
  SLIDE_COUNT,
  rubricScore,
  runAutomatedGate,
};
