"use strict";

const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

const PRODUCT_REGISTRY = path.resolve(
  __dirname,
  "../../../skills/earn/marketing-engine/registry/products",
);
const APP_STORE_URLS = Object.freeze({
  "anicca-ios": "https://apps.apple.com/app/id6755129214",
  "honne-ai": "https://apps.apple.com/app/id6759667221",
});
// Existing Honne campaign token, verified against the same ASC account as Anicca.
const APP_STORE_PROVIDER_TOKEN = "93486075";
// App Store Connect campaign tokens are limited to 30 characters; ASCII slugs keep the boundary exact.
const APP_STORE_CAMPAIGN_TOKEN = /^[A-Za-z0-9][A-Za-z0-9_-]{0,29}$/;

// Keep a description URL for YouTube, but Shorts do not linkify it:
// their CTA directs viewers to the clickable channel profile link. TikTok
// website links are not available on every account, so app posts use search.
const LINKABLE_PLATFORMS = new Set(["youtube"]);
const APP_STORE_SEARCH_NAMES = Object.freeze({ "anicca-ios": "Anicca", "honne-ai": "Honne" });

// Conservative caption/description ceilings per platform (native ranges are
// 2200 for TikTok/Instagram, 5000 for YouTube descriptions).
const PLATFORM_CAPTION_LIMITS = Object.freeze({
  tiktok: 2200,
  instagram: 2200,
  youtube: 5000,
});

const CTA_COPY = Object.freeze({
  ja: {
    linked: (url) => `アプリはチャンネルのリンクから\n${url}`,
    bio: "アプリはプロフィールのリンクから",
    searchApp: (appName) => `App Storeで${appName}を検索`,
    webLinked: (url) => `Google Calendarに接続 → ${url}`,
    webBio: "Google Calendarへの接続はプロフィールのリンクから",
  },
  en: {
    linked: (url) => `Get the app from the link on our channel\n${url}`,
    bio: "Link in bio for the app",
    searchApp: (appName) => `Search ${appName} on the App Store`,
    webLinked: (url) => `Connect Google Calendar → ${url}`,
    webBio: "Connect Google Calendar through the link in bio",
  },
});

function ctaLanguage(locale) {
  const lang = String(locale || "").slice(0, 2).toLowerCase();
  return CTA_COPY[lang] ? lang : "en";
}

function webAppUrl(productId) {
  const id = String(productId || "").trim();
  if (id !== "life-manager-cloud") throw new Error(`marketing web destination is not configured for product ${id}`);
  const file = path.join(PRODUCT_REGISTRY, `${id}.json`);
  let row;
  try {
    row = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    throw new Error(`marketing product manifest is invalid for product ${id}`);
  }
  if (row.product_id !== id || row.type !== "web_app" || typeof row.destination_url !== "string") {
    throw new Error(`marketing product manifest is invalid for product ${id}`);
  }
  const destination = new URL(row.destination_url);
  if (destination.protocol !== "https:" || destination.username || destination.password) {
    throw new Error(`marketing product destination is invalid for product ${id}`);
  }
  return { ...row, destination_url: destination.toString() };
}

function appStoreUrl(productId) {
  const url = APP_STORE_URLS[String(productId || "")];
  if (!url) throw new Error(`marketing app store url is not configured for product ${productId}`);
  return url;
}

function appStoreCampaignUrl({ productId, campaignToken } = {}) {
  const token = String(campaignToken || "").trim();
  if (!APP_STORE_CAMPAIGN_TOKEN.test(token)) throw new Error("App Store campaign token is invalid");
  const url = new URL(appStoreUrl(productId));
  url.searchParams.set("pt", APP_STORE_PROVIDER_TOKEN);
  url.searchParams.set("ct", token);
  url.searchParams.set("mt", "8");
  return url.toString();
}

function appStoreCampaignUrlForDestination(target) {
  if (!target || typeof target !== "object" || Array.isArray(target)) {
    throw new Error("App Store campaign destination is invalid");
  }
  return appStoreCampaignUrl({
    productId: target.job_product_id,
    campaignToken: target.app_store_campaign_token,
  });
}

function platformCaptionLimit(platform) {
  const limit = PLATFORM_CAPTION_LIMITS[String(platform || "")];
  if (!limit) throw new Error(`marketing caption limit is not configured for platform ${platform}`);
  return limit;
}

function marketingCtaLine({ productId, platform, locale }) {
  const lang = ctaLanguage(locale);
  const copy = CTA_COPY[lang];
  if (String(productId || "") === "life-manager-cloud") {
    const product = webAppUrl(productId);
    if (!LINKABLE_PLATFORMS.has(String(platform || ""))) return copy.webBio;
    const url = new URL(product.destination_url);
    url.searchParams.set("utm_source", String(platform));
    url.searchParams.set("utm_medium", "video-description");
    url.searchParams.set("utm_campaign", product.product_id);
    return copy.webLinked(url.toString());
  }
  if (String(platform || "") === "tiktok") {
    appStoreUrl(productId);
    return copy.searchApp(APP_STORE_SEARCH_NAMES[String(productId)] || String(productId));
  }
  if (LINKABLE_PLATFORMS.has(String(platform || ""))) {
    return copy.linked(appStoreCampaignUrl({
      productId,
      campaignToken: `${productId}_${platform}_${lang}`,
    }));
  }
  return copy.bio;
}

// Appends the product/platform/locale CTA to a base caption, trimming the
// base text (never the CTA) so the result never exceeds the platform limit.
function buildMarketingCtaCaption(baseCaption, { productId, platform, locale }) {
  let base = String(baseCaption == null ? "" : baseCaption).replace(/\s+$/, "");
  if (String(platform || "") === "tiktok") {
    base = base.split(/\r?\n/)
      .filter((line) => !/^\s*(?:Link in bio for the app|アプリはプロフィールのリンクから)\s*$/i.test(line))
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .replace(/\s+$/, "");
  }
  const cta = marketingCtaLine({ productId, platform, locale });
  if (base === cta || base.endsWith(`\n\n${cta}`)) return `${base}\n`;
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
  appStoreCampaignUrl,
  appStoreCampaignUrlForDestination,
  appStoreUrl,
  platformCaptionLimit,
  marketingCtaLine,
  buildMarketingCtaCaption,
  buildMarketingCtaCaptionRef,
};
