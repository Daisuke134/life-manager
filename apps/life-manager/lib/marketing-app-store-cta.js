"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

// Single place for the App Store destination per product. Values verified
// against skills/earn/marketing-engine/registry/products/*.json and the
// campaign URL already live in honne-en-cycle.js (id6759667221).
const APP_STORE_URLS = Object.freeze({
  "anicca-ios": "https://apps.apple.com/app/id6755129214",
  "honne-ai": "https://apps.apple.com/app/id6759667221",
});

// Platforms whose UI renders a caption/description link as clickable.
// TikTok and Instagram captions do not linkify URLs, so they get a
// "link in bio" CTA instead of the raw URL.
const LINKABLE_PLATFORMS = new Set(["youtube"]);

// Conservative caption/description ceilings per platform (native ranges are
// 2200 for TikTok/Instagram, 5000 for YouTube descriptions).
const PLATFORM_CAPTION_LIMITS = Object.freeze({
  tiktok: 2200,
  instagram: 2200,
  youtube: 5000,
});

const CTA_COPY = Object.freeze({
  ja: {
    linked: (url) => `アプリはこちら → ${url}`,
    bio: "アプリはプロフィールのリンクから",
  },
  en: {
    linked: (url) => `Get the app → ${url}`,
    bio: "Link in bio for the app",
  },
});

function ctaLanguage(locale) {
  const lang = String(locale || "").slice(0, 2).toLowerCase();
  return CTA_COPY[lang] ? lang : "en";
}

function appStoreUrl(productId) {
  const url = APP_STORE_URLS[String(productId || "")];
  if (!url) throw new Error(`marketing app store url is not configured for product ${productId}`);
  return url;
}

function platformCaptionLimit(platform) {
  const limit = PLATFORM_CAPTION_LIMITS[String(platform || "")];
  if (!limit) throw new Error(`marketing caption limit is not configured for platform ${platform}`);
  return limit;
}

function marketingCtaLine({ productId, platform, locale }) {
  const lang = ctaLanguage(locale);
  const copy = CTA_COPY[lang];
  if (LINKABLE_PLATFORMS.has(String(platform || ""))) {
    return copy.linked(appStoreUrl(productId));
  }
  return copy.bio;
}

// Appends the product/platform/locale CTA to a base caption, trimming the
// base text (never the CTA) so the result never exceeds the platform limit.
function buildMarketingCtaCaption(baseCaption, { productId, platform, locale }) {
  const base = String(baseCaption == null ? "" : baseCaption).replace(/\s+$/, "");
  const cta = marketingCtaLine({ productId, platform, locale });
  const limit = platformCaptionLimit(platform);
  const ctaBlock = `\n\n${cta}\n`;
  if (base.length + ctaBlock.length <= limit) return `${base}${ctaBlock}`;
  const maxBase = Math.max(0, limit - ctaBlock.length);
  const trimmedBase = base.slice(0, maxBase).replace(/\s+$/, "");
  return `${trimmedBase}${ctaBlock}`;
}

// Wraps an existing caption content-object with the CTA and imports the
// result as a new content object, mirroring the pattern already proven in
// honne-en-cycle.js's campaignCaptionRef. `workspaceDir` is caller-owned
// (each cycle script already keeps a private, mode-0700 workspace under its
// own data directory) so this stays agnostic of any one script's layout.
function buildMarketingCtaCaptionRef({ objectStore, workspaceDir, baseCaptionRef, productId, platform, locale }) {
  const baseCaption = fs.readFileSync(objectStore.resolve(baseCaptionRef), "utf8");
  // Video publication uses postiz_video.read_caption(), which strips edge whitespace.
  // Store the exact on-wire caption so identity and provider hashes stay aligned.
  const caption = buildMarketingCtaCaption(baseCaption, { productId, platform, locale }).trim();
  fs.mkdirSync(workspaceDir, { recursive: true, mode: 0o700 });
  const candidate = path.join(workspaceDir, `.marketing-cta-${process.pid}-${crypto.randomUUID()}.txt`);
  fs.writeFileSync(candidate, caption, { mode: 0o600, flag: "wx" });
  try {
    return objectStore.import(candidate).ref;
  } finally {
    fs.unlinkSync(candidate);
  }
}

module.exports = {
  APP_STORE_URLS,
  LINKABLE_PLATFORMS,
  PLATFORM_CAPTION_LIMITS,
  appStoreUrl,
  platformCaptionLimit,
  marketingCtaLine,
  buildMarketingCtaCaption,
  buildMarketingCtaCaptionRef,
};
