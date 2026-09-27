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

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const { buildMarketingCtaCaption } = require("./marketing-app-store-cta.js");
const { runAutomatedGate, SLIDE_COUNT } = require("./marketing-slide-pack-gate.js");
const { resolveSlideBackground } = require("./marketing-slide-background-image.js");

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

// Content families encode proven short-form-slideshow structures (hook,
// then 4 value/context beats) for the affirmation-carousel brand voice
// already live on the JA lane. Each slide carries its own bgPrompt so the
// background is thematically tied to what the slide says (per-prompt image
// cache means every unique prompt is only ever paid for once). Add
// families/topics here to grow variety; selection/rotation/gate logic never
// needs to change. The 6th (CTA) slide is generated separately for every
// pack -- see ctaSlide().
const FAMILIES = {
  "question-hook": [
    {
      slides: [
        { text: "その口癖、\n自分を追い込んでない?", bgPrompt: `a person pausing mid-thought, hand on forehead, looking out a window in a quiet room${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "「まだ足りない」が\n口癖になっていないか", bgPrompt: `a to-do list notebook with many items crossed out, coffee cup beside it on a desk${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "比較する相手を\n減らすだけで楽になる", bgPrompt: `a person putting their phone face-down on a table and smiling softly, relaxed shoulders${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "できた日を\n先に数える習慣", bgPrompt: `a hand checking off boxes in a simple daily journal, morning light${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "疲れた日は\n基準を下げていい", bgPrompt: `someone wrapped in a soft blanket on a couch, tea nearby, resting in the evening${LIFESTYLE_STYLE_SUFFIX}` },
      ],
    },
    {
      slides: [
        { text: "朝の一言、\n何から始めてる?", bgPrompt: `a person waking up and stretching by a sunlit window, calm morning${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "「今日も大丈夫」\nから始める一言", bgPrompt: `a smartphone showing a gentle morning notification on a nightstand, soft light${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "予定を確認する前に\n気分を確認する", bgPrompt: `a person sitting quietly with closed eyes before checking a planner, calm home interior${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "焦りを感じたら\n深呼吸を合図にする", bgPrompt: `a person taking a slow deep breath outdoors near greenery, eyes closed${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "小さく整える練習が\n積み重なっていく", bgPrompt: `neatly folded laundry and a tidy desk corner, soft afternoon light${LIFESTYLE_STYLE_SUFFIX}` },
      ],
    },
  ],
  listicle: [
    {
      slides: [
        { text: "メンタルが勝手に\n安定する口癖５選", bgPrompt: `a person journaling with morning coffee by a window, soft warm light${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "ひとつめ:\n朝の一言を変える", bgPrompt: `a hand writing a short affirmation in a notebook at sunrise${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "ふたつめ:\n夜の振り返りを短くする", bgPrompt: `a bedside lamp glowing warmly next to a small closed notebook at night${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "みっつめ:\n比較をやめる合図を持つ", bgPrompt: `a person walking alone on a quiet path, headphones on, content expression${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "よっつめ:\n疲れた日は基準を下げる", bgPrompt: `a cozy blanket, dim lamp, and a cup of tea on a low table in the evening${LIFESTYLE_STYLE_SUFFIX}` },
      ],
    },
    {
      slides: [
        { text: "自己肯定感が\n整う習慣５つ", bgPrompt: `a person smiling gently while looking in a mirror in soft morning light${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "ひとつめ:\n寝る前に一言書く", bgPrompt: `a small notebook and pen on a nightstand beside a warm reading lamp${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "ふたつめ:\nできたことを数える", bgPrompt: `a hand ticking a short checklist with a satisfied smile, desk lit warmly${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "みっつめ:\n誰かと比べない時間を作る", bgPrompt: `a person reading a book alone in a sunlit armchair, peaceful${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "よっつめ:\n休む日を先に決める", bgPrompt: `a calendar with one day circled in soft pastel colors on a wooden desk${LIFESTYLE_STYLE_SUFFIX}` },
      ],
    },
  ],
  "myth-vs-fact": [
    {
      slides: [
        { text: "「気合いで直す」は\n実は逆効果", bgPrompt: `a tired person rubbing their eyes at a cluttered desk late at night${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "根性論より\n小さな合図の積み重ね", bgPrompt: `small sticky notes with short reminders on a bright window, gentle light${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "無理に前向きになるより\nまず認めること", bgPrompt: `a person sitting calmly with a warm drink, gentle contemplative expression${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "完璧を目指すより\n続けやすさを優先する", bgPrompt: `a simple half-finished sketch in a notebook, relaxed creative desk${LIFESTYLE_STYLE_SUFFIX}` },
        { text: "ひとりで抱えるより\n仕組みに頼っていい", bgPrompt: `a smartphone with a soft glowing reminder screen resting on a pillow${LIFESTYLE_STYLE_SUFFIX}` },
      ],
    },
  ],
};

function identifier(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!text) throw new Error(`${label} is required`);
  return text;
}

function ctaSlideSpec(productId, locale) {
  const appName = APP_DISPLAY_NAMES[productId] || productId;
  const ctaLine = CTA_LINE_BY_LOCALE[locale] || CTA_LINE_BY_LOCALE.en;
  return {
    text: `${appName}\n${ctaLine}`,
    bgPrompt: `a smartphone resting on a soft peach and lavender gradient surface showing a calming, minimalist wellness app home screen, no readable text on the phone screen${LIFESTYLE_STYLE_SUFFIX}`,
  };
}

// Deterministic per (productId, locale, familyId, topicIndex) id so the same
// authored topic always yields the same familyId for metrics joins/rotation,
// and a stable slug for readability in logs.
function candidateId(productId, locale, familyId, topicIndex) {
  return `${familyId}-${topicIndex}`;
}

function buildSlideSpecs(topic, productId, locale) {
  const specs = [...topic.slides, ctaSlideSpec(productId, locale)];
  if (specs.length !== SLIDE_COUNT) {
    throw new Error(`slide pack template must produce exactly ${SLIDE_COUNT} slides`);
  }
  return specs;
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

// Generates every configured candidate for a lane (one per authored topic
// across all families), renders images, imports pack/caption/media into the
// content object store, runs the automated gate, and returns only the
// candidates that passed (each carrying its approval_ref already written).
// Candidates that fail the gate are logged (reasons) and skipped, never
// silently posted.
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
  geminiApiKey,
  resolveBackground = resolveSlideBackground,
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
      const specs = buildSlideSpecs(topic, productId, locale);

      let totalCostUsd = 0;
      const mediaFiles = [];
      const imageChecks = [];
      let overBudget = false;
      for (const spec of specs) {
        const background = await resolveBackground({ prompt: spec.bgPrompt, cacheDir: imageCacheDir, apiKey: geminiApiKey });
        totalCostUsd += background.costUsd;
        if (totalCostUsd > MAX_PACK_COST_USD) { overBudget = true; break; }
        const outFile = path.join(workspaceDir, `.slide-${id}-${mediaFiles.length}-${process.pid}-${crypto.randomUUID()}.jpg`);
        const renderResult = renderSlideImage(background.file, spec.text, outFile, { python });
        mediaFiles.push(outFile);
        imageChecks.push({ present: fs.existsSync(outFile), contrastOk: Boolean(renderResult.text_contrast_ok) });
      }
      if (overBudget) {
        mediaFiles.forEach((file) => fs.existsSync(file) && fs.unlinkSync(file));
        if (typeof onRejected === "function") onRejected({ id, familyId, reasons: [`slide pack image generation exceeded the $${MAX_PACK_COST_USD} cost cap`], score: 0 });
        continue;
      }

      const mediaRefs = mediaFiles.map((file) => objectStore.import(file).ref);
      mediaFiles.forEach((file) => fs.unlinkSync(file));

      const texts = specs.map((spec) => spec.text);
      const slides = texts.map((text, index) => ({
        position: index + 1,
        role: index === 0 ? "hook" : (index === SLIDE_COUNT - 1 ? (lastSlideRole || "body") : "body"),
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
        generation_cost_usd: Math.round(totalCostUsd * 1000) / 1000,
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
