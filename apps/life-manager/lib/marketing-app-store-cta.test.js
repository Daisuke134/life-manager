"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createContentObjectStore } = require("./content-object-store.js");
const {
  appStoreCampaignUrl,
  appStoreCampaignUrlForDestination,
  appStoreUrl,
  buildMarketingCtaCaption,
  buildMarketingCtaCaptionRef,
  marketingCtaLine,
  platformCaptionLimit,
} = require("./marketing-app-store-cta.js");

test("YouTube App Store links identify the developer, app, channel and language", () => {
  assert.equal(marketingCtaLine({ productId: "anicca-ios", platform: "youtube", locale: "en" }), "Get the app from the link on our channel\nhttps://apps.apple.com/app/id6755129214?pt=93486075&ct=anicca-ios_youtube_en&mt=8");
  assert.equal(marketingCtaLine({ productId: "anicca-ios", platform: "youtube", locale: "ja" }), "アプリはチャンネルのリンクから\nhttps://apps.apple.com/app/id6755129214?pt=93486075&ct=anicca-ios_youtube_ja&mt=8");
  assert.equal(marketingCtaLine({ productId: "honne-ai", platform: "youtube", locale: "en" }), "Get the app from the link on our channel\nhttps://apps.apple.com/app/id6759667221?pt=93486075&ct=honne-ai_youtube_en&mt=8");
});

test("TikTok uses an App Store search CTA when its profile has no website link", () => {
  assert.equal(marketingCtaLine({ productId: "anicca-ios", platform: "tiktok", locale: "en" }), "Search Anicca on the App Store");
  assert.equal(marketingCtaLine({ productId: "anicca-ios", platform: "tiktok", locale: "ja" }), "App StoreでAniccaを検索");
  assert.doesNotMatch(marketingCtaLine({ productId: "anicca-ios", platform: "tiktok", locale: "en" }), /link in bio/i);
  assert.equal(marketingCtaLine({ productId: "anicca-ios", platform: "instagram", locale: "en" }), "Link in bio for the app");
});

test("Unconfigured product or platform fails loudly instead of silently omitting the CTA", () => {
  assert.throws(() => marketingCtaLine({ productId: "unknown-app", platform: "youtube", locale: "en" }), /app store url/i);
  assert.throws(() => platformCaptionLimit("mastodon"), /caption limit/i);
});

test("buildMarketingCtaCaption appends the CTA under the platform limit", () => {
  const caption = buildMarketingCtaCaption("hook line\n\n#tag", { productId: "honne-ai", platform: "tiktok", locale: "ja" });
  assert.equal(caption, "hook line\n\n#tag\n\nApp StoreでHonneを検索\n");
  assert.ok(caption.length <= platformCaptionLimit("tiktok"));
});

test("buildMarketingCtaCaption does not duplicate a TikTok CTA already approved with the pack", () => {
  const options = { productId: "anicca-ios", platform: "tiktok", locale: "en" };
  const generated = buildMarketingCtaCaption("What would make this morning gentler?", options);
  const published = buildMarketingCtaCaption(generated, options);
  assert.equal(published, generated);
  assert.equal((published.match(/Search Anicca on the App Store/g) || []).length, 1);
});

test("TikTok caption replaces a retired link-in-bio CTA before publication", () => {
  const caption = buildMarketingCtaCaption(
    "What would make this morning gentler?\n\nLink in bio for the app\n",
    { productId: "anicca-ios", platform: "tiktok", locale: "en" },
  );
  assert.equal(caption, "What would make this morning gentler?\n\nSearch Anicca on the App Store\n");
  assert.doesNotMatch(caption, /link in bio/i);
});

test("buildMarketingCtaCaption trims the base text so the CTA always survives and the limit holds", () => {
  const longBase = "x".repeat(3000);
  const caption = buildMarketingCtaCaption(longBase, { productId: "anicca-ios", platform: "tiktok", locale: "en" });
  assert.ok(caption.length <= platformCaptionLimit("tiktok"));
  assert.ok(caption.endsWith("Search Anicca on the App Store\n"));
});

test("buildMarketingCtaCaptionRef writes a new content object distinct from the base caption", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-marketing-cta-ref-"));
  const objectStore = createContentObjectStore({ objectDir: path.join(dataDir, "objects") });
  const basePath = path.join(dataDir, "base-copy.txt");
  fs.writeFileSync(basePath, "affirmation hook\n\n#anicca\n");
  const baseCaptionRef = objectStore.import(basePath).ref;
  const workspaceDir = path.join(dataDir, "workspace");
  const result = buildMarketingCtaCaptionRef({
    objectStore, workspaceDir, baseCaptionRef, productId: "anicca-ios", platform: "youtube", locale: "en",
  });
  assert.notEqual(result, baseCaptionRef);
  const caption = fs.readFileSync(objectStore.resolve(result), "utf8");
  assert.equal(caption, "affirmation hook\n\n#anicca\n\nGet the app from the link on our channel\nhttps://apps.apple.com/app/id6755129214?pt=93486075&ct=anicca-ios_youtube_en&mt=8");
  assert.equal(caption.endsWith("\n"), false);
});

test("appStoreUrl matches the App Store Connect app ids for both products", () => {
  assert.equal(appStoreUrl("anicca-ios"), "https://apps.apple.com/app/id6755129214");
  assert.equal(appStoreUrl("honne-ai"), "https://apps.apple.com/app/id6759667221");
});

test("profile campaign links use the destination's stable Apple campaign token", () => {
  const target = {
    job_product_id: "anicca-ios",
    platform: "instagram",
    locale: "en",
    app_store_campaign_token: "anicca-ios_ig_anicca-en_en",
  };
  assert.equal(
    appStoreCampaignUrlForDestination(target),
    "https://apps.apple.com/app/id6755129214?pt=93486075&ct=anicca-ios_ig_anicca-en_en&mt=8",
  );
});

test("profile campaign links reject missing or invalid campaign tokens", () => {
  assert.throws(
    () => appStoreCampaignUrlForDestination({ job_product_id: "anicca-ios", platform: "instagram", locale: "en" }),
    /campaign token/i,
  );
  assert.throws(
    () => appStoreCampaignUrl({ productId: "anicca-ios", campaignToken: "a".repeat(31) }),
    /campaign token/i,
  );
});

test("web product YouTube CTA uses its registered destination with channel attribution", () => {
  assert.equal(
    marketingCtaLine({ productId: "life-manager-cloud", platform: "youtube", locale: "ja" }),
    "Google Calendarに接続 → https://aniccaai.com/lm?utm_source=youtube&utm_medium=video-description&utm_campaign=life-manager-cloud",
  );
});

test("web product TikTok CTA points viewers to the profile link", () => {
  assert.equal(
    marketingCtaLine({ productId: "life-manager-cloud", platform: "tiktok", locale: "ja" }),
    "Google Calendarへの接続はプロフィールのリンクから",
  );
});

// Shorts descriptions cannot linkify external URLs: direct viewers to the channel.
test("YouTube keeps the channel instruction and complete campaign URL under its caption limit", () => {
  const caption = buildMarketingCtaCaption("x".repeat(5000), { productId: "anicca-ios", platform: "youtube", locale: "en" });
  assert.ok(caption.length <= 5000);
  assert.ok(caption.includes("Get the app from the link on our channel\n"));
  assert.ok(caption.endsWith("https://apps.apple.com/app/id6755129214?pt=93486075&ct=anicca-ios_youtube_en&mt=8\n"));
});
