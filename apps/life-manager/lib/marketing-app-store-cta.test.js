"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createContentObjectStore } = require("./content-object-store.js");
const {
  appStoreUrl,
  buildMarketingCtaCaption,
  buildMarketingCtaCaptionRef,
  marketingCtaLine,
  platformCaptionLimit,
} = require("./marketing-app-store-cta.js");

test("YouTube gets the exact App Store URL, localized ja/en", () => {
  assert.equal(marketingCtaLine({ productId: "anicca-ios", platform: "youtube", locale: "en" }), "Get the app → https://apps.apple.com/app/id6755129214");
  assert.equal(marketingCtaLine({ productId: "anicca-ios", platform: "youtube", locale: "ja" }), "アプリはこちら → https://apps.apple.com/app/id6755129214");
  assert.equal(marketingCtaLine({ productId: "honne-ai", platform: "youtube", locale: "en" }), "Get the app → https://apps.apple.com/app/id6759667221");
});

test("TikTok and Instagram get a link-in-bio CTA, not a raw URL", () => {
  assert.equal(marketingCtaLine({ productId: "anicca-ios", platform: "tiktok", locale: "ja" }), "アプリはプロフィールのリンクから");
  assert.equal(marketingCtaLine({ productId: "anicca-ios", platform: "instagram", locale: "en" }), "Link in bio for the app");
});

test("Unconfigured product or platform fails loudly instead of silently omitting the CTA", () => {
  assert.throws(() => marketingCtaLine({ productId: "unknown-app", platform: "youtube", locale: "en" }), /app store url/i);
  assert.throws(() => platformCaptionLimit("mastodon"), /caption limit/i);
});

test("buildMarketingCtaCaption appends the CTA under the platform limit", () => {
  const caption = buildMarketingCtaCaption("hook line\n\n#tag", { productId: "honne-ai", platform: "tiktok", locale: "ja" });
  assert.equal(caption, "hook line\n\n#tag\n\nアプリはプロフィールのリンクから\n");
  assert.ok(caption.length <= platformCaptionLimit("tiktok"));
});

test("buildMarketingCtaCaption trims the base text so the CTA always survives and the limit holds", () => {
  const longBase = "x".repeat(3000);
  const caption = buildMarketingCtaCaption(longBase, { productId: "anicca-ios", platform: "tiktok", locale: "en" });
  assert.ok(caption.length <= platformCaptionLimit("tiktok"));
  assert.ok(caption.endsWith("Link in bio for the app\n"));
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
  assert.equal(caption, "affirmation hook\n\n#anicca\n\nGet the app → https://apps.apple.com/app/id6755129214\n");
});

test("appStoreUrl matches the App Store Connect app ids for both products", () => {
  assert.equal(appStoreUrl("anicca-ios"), "https://apps.apple.com/app/id6755129214");
  assert.equal(appStoreUrl("honne-ai"), "https://apps.apple.com/app/id6759667221");
});
