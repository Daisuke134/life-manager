"use strict";

// Autonomous slide-pack factory: generates fresh native-carousel (Larry)
// packs, renders their slide images, runs them through the automated gate
// (marketing-slide-pack-gate.js), and -- when the gate passes -- writes an
// auditable "approved by the gate, not a human" approval object into the
// same content-object-store the canary (anicca-larry-ja-canary.js) and the
// publication adapter (marketing-native-carousel-publication-adapter.js)
// already validate. No schema is weakened: assertPack/assertApproval in the
// adapter still run unchanged at publish time; this module only produces
// objects that satisfy them instead of a human pasting them in.
//
// Marketing packs use only existing cached backgrounds and deterministic
// local copy variants. Missing assets fail closed; this path makes no model
// or image-generation calls.

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const { buildMarketingCtaCaption } = require("./marketing-app-store-cta.js");
const { runAutomatedGate, SLIDE_COUNT } = require("./marketing-slide-pack-gate.js");
const { getCachedBackground } = require("./marketing-slide-background-image.js");
const { generateSlideCopy } = require("./marketing-slide-pack-text.js");

const RENDERER_SCRIPT = path.join(__dirname, "..", "scripts", "render-slide-image.py");
const APPROVED_BY = "automated-slide-pack-gate";
const MAX_PACK_COST_USD = 0.30;
const LIFESTYLE_STYLE_SUFFIX = ", warm cozy soft natural light, photorealistic lifestyle photography, shallow depth of field, no text, no watermark, no logos, portrait orientation";

// App display name per product, for the CTA (last) slide's on-image text.
// Mirrors the pattern in marketing-app-store-cta.js's APP_STORE_URLS.
const APP_DISPLAY_NAMES = Object.freeze({
  "anicca-ios": "Anicca",
  "honne-ai": "Honne",
});

const CTA_LINE_BY_LOCALE = Object.freeze({
  ja: "プロフィールのリンクから",
  en: "Link in bio",
});

// Fixed, approved background sets, one per family/slot combination -- these
// prompts are only ever used as content-addressed cache keys now (see
// getCachedBackground()); the images behind them were generated once and
// must be reused forever, never regenerated. Each family holds a few
// pre-approved background "slots" (one per slide position 1-5); which slot a
// given pack draws from is chosen deterministically (see backgroundSlot()),
// giving visual variety across packs of the same family without ever
// calling an image API again. Add a slot's five bgPrompts here once and seed
// it via resolveSlideBackground() as a one-time explicit action; this module
// never fetches images itself.
const FAMILIES = {
  "question-hook": [
    {
      slides: [
        { bgPrompt: `a person pausing mid-thought, hand on forehead, looking out a window in a quiet room${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a to-do list notebook with many items crossed out, coffee cup beside it on a desk${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a person putting their phone face-down on a table and smiling softly, relaxed shoulders${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a hand checking off boxes in a simple daily journal, morning light${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `someone wrapped in a soft blanket on a couch, tea nearby, resting in the evening${LIFESTYLE_STYLE_SUFFIX}` },
      ],
    },
    {
      slides: [
        { bgPrompt: `a person waking up and stretching by a sunlit window, calm morning${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a smartphone showing a gentle morning notification on a nightstand, soft light${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a person sitting quietly with closed eyes before checking a planner, calm home interior${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a person taking a slow deep breath outdoors near greenery, eyes closed${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `neatly folded laundry and a tidy desk corner, soft afternoon light${LIFESTYLE_STYLE_SUFFIX}` },
      ],
    },
  ],
  listicle: [
    {
      slides: [
        { bgPrompt: `a person journaling with morning coffee by a window, soft warm light${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a hand writing a short affirmation in a notebook at sunrise${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a bedside lamp glowing warmly next to a small closed notebook at night${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a person walking alone on a quiet path, headphones on, content expression${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a cozy blanket, dim lamp, and a cup of tea on a low table in the evening${LIFESTYLE_STYLE_SUFFIX}` },
      ],
    },
    {
      slides: [
        { bgPrompt: `a person smiling gently while looking in a mirror in soft morning light${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a small notebook and pen on a nightstand beside a warm reading lamp${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a hand ticking a short checklist with a satisfied smile, desk lit warmly${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a person reading a book alone in a sunlit armchair, peaceful${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a calendar with one day circled in soft pastel colors on a wooden desk${LIFESTYLE_STYLE_SUFFIX}` },
      ],
    },
  ],
  "myth-vs-fact": [
    {
      slides: [
        { bgPrompt: `a tired person rubbing their eyes at a cluttered desk late at night${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `small sticky notes with short reminders on a bright window, gentle light${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a person sitting calmly with a warm drink, gentle contemplative expression${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a simple half-finished sketch in a notebook, relaxed creative desk${LIFESTYLE_STYLE_SUFFIX}` },
        { bgPrompt: `a smartphone with a soft glowing reminder screen resting on a pillow${LIFESTYLE_STYLE_SUFFIX}` },
      ],
    },
  ],
};

function identifier(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!text) throw new Error(`${label} is required`);
  return text;
}

function ctaBackgroundPrompt() {
  return `a smartphone resting on a soft peach and lavender gradient surface showing a calming, minimalist wellness app home screen, no readable text on the phone screen${LIFESTYLE_STYLE_SUFFIX}`;
}

function ctaText(productId, locale) {
  const appName = APP_DISPLAY_NAMES[productId] || productId;
  const ctaLine = CTA_LINE_BY_LOCALE[locale] || CTA_LINE_BY_LOCALE.en;
  return `${appName}\n${ctaLine}`;
}

// Deterministic per (productId, locale, familyId, topicIndex) id so the same
// authored background set always yields the same familyId for metrics
// joins/rotation, and a stable slug for readability in logs.
function candidateId(productId, locale, familyId, topicIndex) {
  return `${familyId}-${topicIndex}`;
}

function backgroundPrompts(topic) {
  const prompts = [...topic.slides.map((slide) => slide.bgPrompt), ctaBackgroundPrompt()];
  if (prompts.length !== SLIDE_COUNT) {
    throw new Error(`slide pack background set must have exactly ${SLIDE_COUNT} slides`);
  }
  return prompts;
}

// Composites `text` onto the already-resolved background image at bgFile.
// Returns the render script's contrast/quality signals so the gate can
// verify legibility without re-decoding the JPEG.
function renderSlideImage(bgFile, text, outFile, { python = "python3" } = {}) {
  const result = spawnSync(python, [RENDERER_SCRIPT, bgFile, outFile, "1080", "1350", text], { encoding: "utf8" });
  if (result.status !== 0 || !fs.existsSync(outFile)) {
    throw new Error(`slide image render failed: ${result.stderr || result.status}`);
  }
  try {
    return JSON.parse(String(result.stdout || "").trim().split(/\r?\n/).pop());
  } catch {
    throw new Error("slide image render returned invalid JSON");
  }
}

// Generates one fresh-text candidate per configured background set (one per
// family/topic), reusing the fixed approved backgrounds, imports pack/
// caption/media into the content object store, runs the automated gate, and
// returns only the candidates that passed (each carrying its approval_ref
// already written). Candidates that fail generation or the gate are logged
// (reasons) and skipped, never silently posted.
async function generateSlidePackCandidates({
  objectStore,
  workspaceDir,
  imageCacheDir,
  tenantId,
  productId,
  locale,
  platform,
  accountId,
  integrationRef,
  rendererId,
  packFormat,
  form,
  lastSlideRole,
  variantSeed,
  resolveBackground = getCachedBackground,
  avoidTextsByFamily = {},
  python,
  now = () => new Date().toISOString(),
  onRejected,
}) {
  identifier(tenantId, "slide pack tenant");
  identifier(productId, "slide pack product");
  identifier(locale, "slide pack locale");
  identifier(integrationRef, "slide pack integration ref");
  identifier(imageCacheDir, "slide pack image cache dir");
  fs.mkdirSync(workspaceDir, { recursive: true, mode: 0o700 });

  const approved = [];
  for (const [familyId, topics] of Object.entries(FAMILIES)) {
    for (const [topicIndex, topic] of topics.entries()) {
      const id = candidateId(productId, locale, familyId, topicIndex);
      const bgPrompts = backgroundPrompts(topic);

      let copy;
      try {
        copy = await generateSlideCopy({
          familyId,
          avoidTexts: avoidTextsByFamily[familyId] || [],
          locale,
          variantSeed: `${variantSeed || now()}:${id}`,
        });
      } catch (error) {
        if (typeof onRejected === "function") onRejected({ id, familyId, reasons: [error.message], score: 0 });
        continue;
      }
      const texts = [copy.hook, ...copy.body, ctaText(productId, locale)];
      const totalCostUsd = copy.costUsd;
      if (totalCostUsd > MAX_PACK_COST_USD) {
        if (typeof onRejected === "function") onRejected({ id, familyId, reasons: [`slide pack text generation exceeded the $${MAX_PACK_COST_USD} cost cap`], score: 0 });
        continue;
      }

      const mediaFiles = [];
      const imageChecks = [];
      for (const [index, prompt] of bgPrompts.entries()) {
        const background = await resolveBackground({ prompt, cacheDir: imageCacheDir });
        const outFile = path.join(workspaceDir, `.slide-${id}-${index}-${process.pid}-${crypto.randomUUID()}.jpg`);
        const renderResult = renderSlideImage(background.file, texts[index], outFile, { python });
        mediaFiles.push(outFile);
        imageChecks.push({ present: fs.existsSync(outFile), contrastOk: Boolean(renderResult.text_contrast_ok) });
      }

      const mediaRefs = mediaFiles.map((file) => objectStore.import(file).ref);
      mediaFiles.forEach((file) => fs.unlinkSync(file));

      // Mirrors the adapter's own assertPack default exactly (see
      // marketing-native-carousel-publication-adapter.js) so a freshly
      // generated pack always satisfies whichever lane consumes it, whether
      // or not that lane overrides lastSlideRole.
      const resolvedLastSlideRole = lastSlideRole || (platform === "tiktok" ? "cta" : "body");
      const slides = texts.map((text, index) => ({
        position: index + 1,
        role: index === 0 ? "hook" : (index === SLIDE_COUNT - 1 ? resolvedLastSlideRole : "body"),
        text,
        media_ref: mediaRefs[index],
      }));

      const baseCaption = texts[0].replace(/\n/g, " ");
      const caption = buildMarketingCtaCaption(baseCaption, { productId, platform, locale });
      const captionFile = path.join(workspaceDir, `.caption-${id}-${process.pid}-${crypto.randomUUID()}.txt`);
      fs.writeFileSync(captionFile, caption, { mode: 0o600, flag: "wx" });
      const captionRef = objectStore.import(captionFile).ref;
      fs.unlinkSync(captionFile);

      const pack = {
        schema_version: 1,
        kind: "marketing_native_carousel_pack",
        product_id: productId,
        locale,
        platform,
        account_id: accountId,
        renderer_id: rendererId,
        format_id: packFormat,
        form,
        media_type: "image/jpeg",
        slide_count: SLIDE_COUNT,
        caption,
        slides,
      };

      const gate = runAutomatedGate({ pack, caption, imageChecks, totalCostUsd, maxCostUsd: MAX_PACK_COST_USD, platform });
      if (!gate.passed) {
        if (typeof onRejected === "function") onRejected({ id, familyId, reasons: gate.reasons, score: gate.score });
        continue;
      }

      const packFile = path.join(workspaceDir, `.pack-${id}-${process.pid}-${crypto.randomUUID()}.json`);
      fs.writeFileSync(packFile, JSON.stringify(pack), { mode: 0o600, flag: "wx" });
      const packRef = objectStore.import(packFile).ref;
      fs.unlinkSync(packFile);

      const approval = {
        schema_version: 1,
        kind: "marketing_native_carousel_publication_approval",
        status: "approved",
        approved_by: APPROVED_BY,
        approved_at: now(),
        gate_score: gate.score,
        gate_checks_passed: true,
        generation_cost_usd: Math.round(totalCostUsd * 100000) / 100000,
        tenant_id: tenantId,
        product_id: productId,
        locale,
        platform,
        account_id: accountId,
        integration_ref: integrationRef,
        pack_ref: packRef,
        media_refs: mediaRefs,
        caption_sha256: crypto.createHash("sha256").update(caption).digest("hex"),
      };
      const approvalFile = path.join(workspaceDir, `.approval-${id}-${process.pid}-${crypto.randomUUID()}.json`);
      fs.writeFileSync(approvalFile, JSON.stringify(approval), { mode: 0o600, flag: "wx" });
      const approvalRef = objectStore.import(approvalFile).ref;
      fs.unlinkSync(approvalFile);

      approved.push({
        packRef,
        mediaRefs,
        captionRef,
        approvalRef,
        familyId,
        createdAt: now(),
        gateScore: gate.score,
        generationCostUsd: totalCostUsd,
      });
    }
  }
  return approved;
}

module.exports = { FAMILIES, MAX_PACK_COST_USD, generateSlidePackCandidates, renderSlideImage };
