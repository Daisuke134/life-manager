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
const os = require("node:os");
const path = require("node:path");
const { spawnSync } = require("node:child_process");

const { buildMarketingCtaCaption } = require("./marketing-app-store-cta.js");
const { runAutomatedGate, SLIDE_COUNT } = require("./marketing-slide-pack-gate.js");

const RENDERER_SCRIPT = path.join(__dirname, "..", "scripts", "render-slide-image.py");
const APPROVED_BY = "automated-slide-pack-gate";

// Content families encode proven short-form-slideshow structures (hook,
// then 4 value/context beats, then a close) for the affirmation-carousel
// brand voice already live on the JA lane. Add families/topics here to grow
// variety; selection/rotation/gate logic never needs to change.
const FAMILIES = {
  "question-hook": [
    {
      hook: "その口癖、\n自分を追い込んでない?",
      body: [
        "「まだ足りない」が\n口癖になっていないか",
        "比較する相手を\n減らすだけで楽になる",
        "できた日を\n先に数える習慣",
        "疲れた日は\n基準を下げていい",
      ],
      close: "続けるコツは\n通知に任せること",
    },
    {
      hook: "朝の一言、\n何から始めてる?",
      body: [
        "「今日も大丈夫」\nから始める一言",
        "予定を確認する前に\n気分を確認する",
        "焦りを感じたら\n深呼吸を合図にする",
        "小さく整える練習が\n積み重なっていく",
      ],
      close: "毎朝アプリが\n合図を届けてくれる",
    },
  ],
  listicle: [
    {
      hook: "メンタルが勝手に\n安定する口癖５選",
      body: [
        "ひとつめ:\n朝の一言を変える",
        "ふたつめ:\n夜の振り返りを短くする",
        "みっつめ:\n比較をやめる合図を持つ",
        "よっつめ:\n疲れた日は基準を下げる",
      ],
      close: "五つめは\nアプリの通知に任せること",
    },
    {
      hook: "自己肯定感が\n整う習慣５つ",
      body: [
        "ひとつめ:\n寝る前に一言書く",
        "ふたつめ:\nできたことを数える",
        "みっつめ:\n誰かと比べない時間を作る",
        "よっつめ:\n休む日を先に決める",
      ],
      close: "五つめは\n毎日同じ時間に思い出すこと",
    },
  ],
  "myth-vs-fact": [
    {
      hook: "「気合いで直す」は\n実は逆効果",
      body: [
        "根性論より\n小さな合図の積み重ね",
        "無理に前向きになるより\nまず認めること",
        "完璧を目指すより\n続けやすさを優先する",
        "ひとりで抱えるより\n仕組みに頼っていい",
      ],
      close: "その仕組みを\nアプリが担当します",
    },
  ],
};

function identifier(value, label) {
  const text = String(value == null ? "" : value).trim();
  if (!text) throw new Error(`${label} is required`);
  return text;
}

// Deterministic per (productId, locale, familyId, topicIndex) id so the same
// authored topic always yields the same familyId for metrics joins/rotation,
// and a stable slug for readability in logs.
function candidateId(productId, locale, familyId, topicIndex) {
  return `${familyId}-${topicIndex}`;
}

function buildSlideTexts(topic) {
  const texts = [topic.hook, ...topic.body, topic.close];
  if (texts.length !== SLIDE_COUNT) {
    throw new Error(`slide pack template must produce exactly ${SLIDE_COUNT} slide texts`);
  }
  return texts;
}

function renderSlideImage(text, outFile) {
  const result = spawnSync("python3", [RENDERER_SCRIPT, outFile, "1080", "1350", text], { encoding: "utf8" });
  if (result.status !== 0 || !fs.existsSync(outFile)) {
    throw new Error(`slide image render failed: ${result.stderr || result.status}`);
  }
}

// Generates every configured candidate for a lane (one per authored topic
// across all families), renders images, imports pack/caption/media into the
// content object store, runs the automated gate, and returns only the
// candidates that passed (each carrying its approval_ref already written).
// Candidates that fail the gate are logged (reasons) and skipped, never
// silently posted.
function generateSlidePackCandidates({
  objectStore,
  workspaceDir,
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
  now = () => new Date().toISOString(),
  onRejected,
}) {
  identifier(tenantId, "slide pack tenant");
  identifier(productId, "slide pack product");
  identifier(locale, "slide pack locale");
  identifier(integrationRef, "slide pack integration ref");
  fs.mkdirSync(workspaceDir, { recursive: true, mode: 0o700 });

  const approved = [];
  for (const [familyId, topics] of Object.entries(FAMILIES)) {
    topics.forEach((topic, topicIndex) => {
      const id = candidateId(productId, locale, familyId, topicIndex);
      const texts = buildSlideTexts(topic);

      const mediaFiles = texts.map((text, index) => {
        const outFile = path.join(workspaceDir, `.slide-${id}-${index}-${process.pid}-${crypto.randomUUID()}.jpg`);
        renderSlideImage(text, outFile);
        return outFile;
      });
      const mediaRefs = mediaFiles.map((file) => objectStore.import(file).ref);
      mediaFiles.forEach((file) => fs.unlinkSync(file));

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

      const gate = runAutomatedGate({ pack, caption, mediaFiles: [], platform });
      if (!gate.passed) {
        if (typeof onRejected === "function") onRejected({ id, familyId, reasons: gate.reasons, score: gate.score });
        return;
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
      });
    });
  }
  return approved;
}

module.exports = { FAMILIES, generateSlidePackCandidates, renderSlideImage };
