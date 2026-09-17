#!/usr/bin/env node
"use strict";

const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { buildRuntimeJob } = require("./runtime-job-store.js");
const { createContentObjectStore, sha256File } = require("./content-object-store.js");
const { resolveRuntimePaths } = require("./runtime-paths.js");
const { writeMarketingEffectIdentity } = require("./marketing-effect-identity.js");

const ADAPTER_ID = "marketing-native-carousel-publication";
const LOOP_ID = "marketing.video.publish";
const CAPABILITY = "marketing.video.publish";
const PRODUCT_ID = "anicca-ios";
const FORMAT_ID = "larry";
const FORM_ID = "affirmation-carousel";
const LOCALE_ID = "ja";
const ACCOUNT_ID = "@ani.cca1234";
const ACCOUNT_REF = "account://instagram/@ani.cca1234";
const INTEGRATION_REF = "integration://postiz/instagram/cmq3sq7mc000eqp0y7azfm8yk";
const PACK_FORMAT_ID = "native-photo-carousel";
const SLIDE_COUNT = 6;
const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const HASH = /^[0-9a-f]{64}$/;
const OBJ = /^object:\/\/sha256\/([0-9a-f]{64})$/;
const DIRECT_INSTAGRAM_POST = /^https:\/\/www\.instagram\.com\/p\/(?=[A-Za-z0-9_-]*[A-Za-z_-])[A-Za-z0-9_-]+\/?$/;
const PROVIDER_ID = /^[A-Za-z0-9._:-]{1,200}$/;
const BASE_REF_KEYS = ["account_ref", "approval_ref", "caption_ref", "creative_ref", "form_ref", "format_ref", "locale_ref", "media_refs", "pack_ref", "platform_ref", "postiz_token_ref", "product_ref", "slot_ref"];
const EFFECT = /^marketing:carousel:anicca-ios:([A-Za-z0-9][A-Za-z0-9._-]{0,127}):([0-9a-f]{64}):([0-9a-f]{64}):([0-9a-f]{64})(?::([0-9a-f]{64}))?$/;

const fail = (message) => { throw new Error(message); };
const text = (value, label) => { const v = String(value == null ? "" : value).trim(); return v || fail(`${label} is required`); };
const objectRef = (value, label) => { const v = String(value || ""); return OBJ.test(v) ? v : fail(`${label} reference is invalid`); };
const objectHash = (value, label) => { const m = OBJ.exec(String(value || "")); return m ? m[1] : fail(`${label} reference is invalid`); };
const instant = (value, label) => { const v = String(value || ""); const d = new Date(v); return Number.isFinite(d.getTime()) && d.toISOString() === v ? v : fail(`${label} is invalid`); };
const digestJson = (value) => crypto.createHash("sha256").update(JSON.stringify(value)).digest("hex");
const mediaOrderHash = (hashes) => digestJson(hashes);
const sameArray = (left, right) => Array.isArray(left) && Array.isArray(right)
  && left.length === right.length && left.every((value, index) => value === right[index]);
const regexEscape = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const directPostPattern = (lane) => lane.platform === "instagram"
  ? DIRECT_INSTAGRAM_POST
  : new RegExp(`^https://www\\.tiktok\\.com/${regexEscape(lane.nativeOwner)}/video/[0-9]+/?$`);

const JA_LANE = Object.freeze({
  name: "JA",
  productId: PRODUCT_ID,
  formatId: FORMAT_ID,
  packFormat: PACK_FORMAT_ID,
  form: FORM_ID,
  locale: LOCALE_ID,
  platform: "instagram",
  accountId: ACCOUNT_ID,
  nativeOwner: ACCOUNT_ID,
  accountRef: ACCOUNT_REF,
  integrationRef: INTEGRATION_REF,
  integrationId: "cmq3sq7mc000eqp0y7azfm8yk",
  renderer: "larry",
  lane: "anicca-larry-ja-instagram",
  tokenRef: "secret://postiz/api-key",
  telegramTokenRef: "secret://telegram/bot-token",
  chatRef: "telegram-chat://owner",
  packEnv: "LM_ANICCA_LARRY_JA_PACK_REF",
  mediaEnv: "LM_ANICCA_LARRY_JA_MEDIA_REFS",
  captionEnv: "LM_ANICCA_LARRY_JA_CAPTION_REF",
  approvalEnv: "LM_ANICCA_LARRY_JA_APPROVAL_REF",
  verificationEnv: "LM_ANICCA_LARRY_JA_NATIVE_VERIFICATION_REF",
  workerLabel: "anicca-larry-ja-canary",
});

const EN_AFFIRMATION_LANE = Object.freeze({
  name: "EN_AFFIRMATION",
  productId: PRODUCT_ID,
  formatId: FORMAT_ID,
  packFormat: PACK_FORMAT_ID,
  form: FORM_ID,
  locale: "en",
  platform: "instagram",
  accountId: "@anicca.affirmation",
  nativeOwner: "@anicca.ios",
  accountRef: "account://instagram/@anicca.affirmation",
  integrationRef: "integration://postiz/instagram/cmp9pedr700ttqh0yj8o57fog",
  integrationId: "cmp9pedr700ttqh0yj8o57fog",
  manifestAccount: "anicca-ios-en-affirmation-instagram",
  renderer: "larry",
  lane: "anicca-en-affirmation-instagram",
  creativeId: "EN-AFFIRMATION-CAROUSEL-da8d8265",
  packRef: "object://sha256/e23cd41257832d2032fd889bd9a16ec95ea8dc213cdd7a2e3f820fbe1578669e",
  mediaRefs: Object.freeze([
    "object://sha256/da8d8265a1344b68a877d776b0cec5b599dc7b3bbd6abc833fcef06e7416df1f",
    "object://sha256/4fe9ab673f095d39368744974c677cbb5f8305dc2a9dcd1ef1b4b87759d8b42a",
    "object://sha256/1af8a8c790a733ff1cedca85aaf3de010671a03f54223205da0fd9575a242840",
    "object://sha256/d097d7b7254ee0a35c95844a89e1f8d1d644775dea134f960ac5e8cb80d230f9",
    "object://sha256/71ded59ff8a1de5251e607a6ba808945c85537bfca3fbd7f20c65f2912f00e34",
    "object://sha256/418ad1907d64e4835939bda677709aace44092a936e8a18a7cb8aeeca7652f4f",
  ]),
  captionRef: "object://sha256/bf90a15a5a615d2bb295c1829f7329f391a870fe4e950c8099972c20bf6e64a0",
  approvalRef: "object://sha256/7740cd09733d0cb7a5d8f32ff4614c3e07ebae27df0e3eae8bca8df80b968845",
  tokenRef: "secret://postiz/api-key",
  telegramTokenRef: "secret://telegram/bot-token",
  chatRef: "telegram-chat://owner",
  packEnv: "LM_ANICCA_EN_AFFIRMATION_INSTAGRAM_PACK_REF",
  mediaEnv: "LM_ANICCA_EN_AFFIRMATION_INSTAGRAM_MEDIA_REFS",
  captionEnv: "LM_ANICCA_EN_AFFIRMATION_INSTAGRAM_CAPTION_REF",
  approvalEnv: "LM_ANICCA_EN_AFFIRMATION_INSTAGRAM_APPROVAL_REF",
  verificationEnv: "LM_ANICCA_EN_AFFIRMATION_INSTAGRAM_NATIVE_VERIFICATION_REF",
  approvedPackName: "anicca-ios-larry-affirmation-en.pack.json",
  workerLabel: "anicca-en-affirmation-instagram-canary",
});

const EN_AFFIRMATION_TIKTOK_LANE = Object.freeze({
  ...EN_AFFIRMATION_LANE,
  name: "EN_AFFIRMATION_TIKTOK",
  platform: "tiktok",
  accountId: "@aniccaaffirmation",
  nativeOwner: "@aniccaaffirmation",
  accountRef: "account://tiktok/@aniccaaffirmation",
  integrationRef: "integration://postiz/tiktok/cmp93bkpu01uvoh0yd3aj560g",
  integrationId: "cmp93bkpu01uvoh0yd3aj560g",
  title: "read these 5 lines before you get out of bed",
  packRef: "object://sha256/b6a0445a5b6ca22c5d391b0db3af0486f3168f06b4711bc576386ad77465e282",
  approvalRef: "object://sha256/f372bae497776e316a50547139b11d173fca80c87ef1c8003e582bd3f25cb427",
  packEnv: "LM_ANICCA_EN_AFFIRMATION_TIKTOK_PACK_REF",
  mediaEnv: "LM_ANICCA_EN_AFFIRMATION_TIKTOK_MEDIA_REFS",
  captionEnv: "LM_ANICCA_EN_AFFIRMATION_TIKTOK_CAPTION_REF",
  approvalEnv: "LM_ANICCA_EN_AFFIRMATION_TIKTOK_APPROVAL_REF",
  verificationEnv: "LM_ANICCA_EN_AFFIRMATION_TIKTOK_NATIVE_VERIFICATION_REF",
  manifestAccount: "anicca-ios-en-affirmation-tiktok",
  manifestProfile: "@aniccaaffirmation",
  lane: "anicca-en-affirmation-tiktok",
  workerLabel: "anicca-en-affirmation-tiktok-canary",
});

const EN_SLIDESHOW_TIKTOK_LANE = Object.freeze({
  name: "EN_SLIDESHOW_TIKTOK",
  productId: PRODUCT_ID,
  formatId: "slideshow",
  packFormat: PACK_FORMAT_ID,
  form: "mental-health-carousel",
  locale: "en",
  platform: "tiktok",
  accountId: "@anicca_slideshow",
  nativeOwner: "@anicca_slideshow",
  accountRef: "account://tiktok/@anicca_slideshow",
  integrationRef: "integration://postiz/tiktok/cmnenjkff01j1pa0ysufmzhfr",
  integrationId: "cmnenjkff01j1pa0ysufmzhfr",
  manifestAccount: "anicca-ios-en-slideshow-tiktok",
  renderer: "slideshow",
  lane: "anicca-en-slideshow-tiktok",
  creativeId: "EN-SLIDESHOW-PROCRASTINATION-05090bf2b4ee-R2",
  title: "PROCRASTINATION ISN'T LAZINESS.",
  packRef: "object://sha256/3241653ecc9239663de3151426d01a6b1c34cfe7c130288e928fab6686de624c",
  mediaRefs: Object.freeze([
    "object://sha256/05090bf2b4ee4f616762a33d93d446afff8f06ad2675016210d0d8bc90b5b329",
    "object://sha256/cefca419882ce631dd02518f403137603475c8afb22f48d2b2dee9a3b282d338",
    "object://sha256/ebf0389d8b9a708bf719a540857a9d0192105a65b931ba086bbe6be7c6f2072d",
    "object://sha256/e35d34a79e35a924ec921c14bf419f4216dac1ad7ceeab21acb8d0e0bb79a05f",
    "object://sha256/2d95726f2dd1dfd625c75497aa0e935d84aa4f1fb2122c2cc4ae6a423b243b52",
    "object://sha256/6895c10dbe4427259151d778a62cacbaf9d3dce592330a5710338da7f5c3c9f7",
  ]),
  captionRef: "object://sha256/8e6f7cecee64454d906a787bad4b4c57736fff2668c1b9eea6c0d666140f2c6d",
  approvalRef: "object://sha256/6e69c242e75481d2d6a3f51fe2c07e5dc151bb33c9b29f30972e81aa5bf8f668",
  tokenRef: "secret://postiz/api-key",
  telegramTokenRef: "secret://telegram/bot-token",
  chatRef: "telegram-chat://owner",
  packEnv: "LM_ANICCA_EN_SLIDESHOW_TIKTOK_PACK_REF",
  mediaEnv: "LM_ANICCA_EN_SLIDESHOW_TIKTOK_MEDIA_REFS",
  captionEnv: "LM_ANICCA_EN_SLIDESHOW_TIKTOK_CAPTION_REF",
  approvalEnv: "LM_ANICCA_EN_SLIDESHOW_TIKTOK_APPROVAL_REF",
  verificationEnv: "LM_ANICCA_EN_SLIDESHOW_TIKTOK_NATIVE_VERIFICATION_REF",
  approvedPackName: "anicca-ios-slideshow-en.pack.json",
  workerLabel: "anicca-en-slideshow-tiktok-canary",
});

const JA_MAIN_TIKTOK_LANE = Object.freeze({
  name: "JA_MAIN_TIKTOK",
  productId: PRODUCT_ID,
  formatId: FORMAT_ID,
  packFormat: PACK_FORMAT_ID,
  form: FORM_ID,
  locale: LOCALE_ID,
  platform: "tiktok",
  accountId: "@anicca.jp",
  nativeOwner: "@anicca.jp",
  accountRef: "account://tiktok/@anicca.jp",
  integrationRef: "integration://postiz/tiktok/cmp9sdev5012voh0y58qs45xc",
  integrationId: "cmp9sdev5012voh0y58qs45xc",
  manifestAccount: "anicca-ios-ja-tiktok",
  renderer: "larry",
  lane: "anicca-main-ja-tiktok",
  creativeId: "JA-SUNSET-LARRY-20d53f17",
  title: "メンタルが強い人の口癖５選",
  packRef: "object://sha256/63e2b1b84342253b3d54eac4b428293572ee285906b38c5aacad614cd1a83664",
  mediaRefs: Object.freeze([
    "object://sha256/20d53f17ebcfa33d0952dc69c026c4580f9c1552e1b7329acbe4e17c33b83c97",
    "object://sha256/77df9f0c3fc37b3554f3a3ba59917f1c221c57a812bd573dc325b2b7ce1b1926",
    "object://sha256/86a543a4f6e426de3e464d2cef47e675302bb8b7ea1f2617460391f4b664f6f8",
    "object://sha256/f9dce0ce2cc0cfafdb28683c13973a3258165725e0f14db438ba9e3a778d220b",
    "object://sha256/a8c245f1516f945aa10c8d7029c065ccfdc9cc11ecebeb0efa236f10f6a839fd",
    "object://sha256/118340602dc9e7f4bd2983ab15c751c4c214ad5dee57adc044c0a381fc950be1",
  ]),
  captionRef: "object://sha256/04757a25b742f6b6d5bd60c0b6172f5762eb3d9bbdc2e1ff228cdc142fb9f856",
  approvalRef: "object://sha256/4f3994246a0322893d321bb86a39ec92dbe553ee2da3f93bb6a7affc0361f2a2",
  tokenRef: "secret://postiz/api-key",
  telegramTokenRef: "secret://telegram/bot-token",
  chatRef: "telegram-chat://owner",
  packEnv: "LM_ANICCA_MAIN_TIKTOK_LARRY_PACK_REF",
  mediaEnv: "LM_ANICCA_MAIN_TIKTOK_LARRY_MEDIA_REFS",
  captionEnv: "LM_ANICCA_MAIN_TIKTOK_LARRY_CAPTION_REF",
  approvalEnv: "LM_ANICCA_MAIN_TIKTOK_LARRY_APPROVAL_REF",
  verificationEnv: "LM_ANICCA_MAIN_TIKTOK_LARRY_NATIVE_VERIFICATION_REF",
  approvedPackName: "anicca-ios-larry-sunset-ja.pack.json",
  lastSlideRole: "body",
  workerLabel: "anicca-main-tiktok-canary",
});

const JA_JP1_TIKTOK_LANE = Object.freeze({
  ...JA_MAIN_TIKTOK_LANE,
  name: "JA_JP1_TIKTOK",
  accountId: "@anicca.jp1",
  nativeOwner: "@anicca.jp1",
  accountRef: "account://tiktok/@anicca.jp1",
  integrationRef: "integration://postiz/tiktok/cmlrv8jq000hun60yy57eaptx",
  integrationId: "cmlrv8jq000hun60yy57eaptx",
  manifestAccount: "anicca-ios-ja-jp1-tiktok",
  manifestProfile: "@anicca.jpx",
  lane: "anicca-jp1-ja-tiktok",
  creativeId: "JA-LARRY-V1-JP1-4695b946",
  title: "メンタルが勝手に安定する\n口癖５選",
  packRef: "object://sha256/4695b94628f24641c049f62388d207fe5e9ececd5b11f352aee9582d0b30561d",
  mediaRefs: Object.freeze([
    "object://sha256/d4f0030358eab3c89e36ea938ccfe1a3e33eadcc42d55f269a456fd72de08a3d",
    "object://sha256/ac47a0fbc783a5bde9160b85da29b513a7e36daa131c252384510753cb210a8f",
    "object://sha256/bbd5baa7f4463ac7c2d2e814705e702514e28db5f4760023d4fecdf924f0acd5",
    "object://sha256/366527448cc3b70dbc15cb42b0fc196f572c65b51730efbd6ea1d0c69ec91dae",
    "object://sha256/7d1ca4ebf4d2ede902ecb3251eefd8ab36fad8e4408133b9463f4edc56e8fc5f",
    "object://sha256/0525669aca914138a707ae782bb759b74c833eae90ff9cfefb2635a64e6b5a68",
  ]),
  captionRef: "object://sha256/ae3057315163e6cf234eb2b8f21c4fc2643526cb2e22fca7f20ea303aa3a64f0",
  approvalRef: "object://sha256/74521880c72452b66976e62de182b7864287daf58d37299b692b8f4f13ffb49f",
  packEnv: "LM_ANICCA_JP1_TIKTOK_LARRY_PACK_REF",
  mediaEnv: "LM_ANICCA_JP1_TIKTOK_LARRY_MEDIA_REFS",
  captionEnv: "LM_ANICCA_JP1_TIKTOK_LARRY_CAPTION_REF",
  approvalEnv: "LM_ANICCA_JP1_TIKTOK_LARRY_APPROVAL_REF",
  verificationEnv: "LM_ANICCA_JP1_TIKTOK_LARRY_NATIVE_VERIFICATION_REF",
  approvedPackName: "anicca-ios-larry-ja-v1.pack.json",
  lastSlideRole: "body",
  workerLabel: "anicca-jp1-tiktok-canary",
});

const JA_BUDDHA_TIKTOK_LANE = Object.freeze({
  ...JA_MAIN_TIKTOK_LANE,
  name: "JA_BUDDHA_TIKTOK",
  accountId: "@anicca_buddha",
  nativeOwner: "@anicca_buddha",
  accountRef: "account://tiktok/@anicca_buddha",
  integrationRef: "integration://postiz/tiktok/cmp9txjdp01c8oh0yb6dhlarr",
  integrationId: "cmp9txjdp01c8oh0yb6dhlarr",
  manifestAccount: "anicca-ios-ja-buddha-tiktok",
  lane: "anicca-buddha-ja-tiktok",
  creativeId: "JA-BUDDHA-MALE-32f25f0b",
  title: "メンタルが勝手に安定する口癖5選",
  packRef: "object://sha256/5459a68431e702ad95cea927552366ccd3c1e8be60aa55455b80f560e86e017e",
  mediaRefs: Object.freeze([
    "object://sha256/32f25f0b1da13eafebdf1fce436b6235ba7930194328e97d109085050cb1a849",
    "object://sha256/27f614eacf9e04d0b72f4d66b23e8745ee8d0ca8e20e127f5ef16875845d42a3",
    "object://sha256/d5705cb2ad73a8a1634bb18e76d3603edc27f0c25c222f88b7c3eedf8a6f1612",
    "object://sha256/7403cb47255449d11f69fd12db7cdc593939b51db4fccf31fbf0c908e334fe00",
    "object://sha256/1f5c97d49563eeb10b9bb3b26ec74991259f04535b19070a5358ca23817acf4b",
    "object://sha256/bcd00ead6e84b455621cfd34a497e1af5499e430cb70e691e90b96bd2b79dc82",
  ]),
  approvalRef: "object://sha256/25d2a75a0eb0b30c21cf5fa76962d3d6bd3c6eb39da9844386c00a314bad0050",
  packEnv: "LM_ANICCA_BUDDHA_TIKTOK_LARRY_PACK_REF",
  mediaEnv: "LM_ANICCA_BUDDHA_TIKTOK_LARRY_MEDIA_REFS",
  captionEnv: "LM_ANICCA_BUDDHA_TIKTOK_LARRY_CAPTION_REF",
  approvalEnv: "LM_ANICCA_BUDDHA_TIKTOK_LARRY_APPROVAL_REF",
  verificationEnv: "LM_ANICCA_BUDDHA_TIKTOK_LARRY_NATIVE_VERIFICATION_REF",
  approvedPackName: "anicca-ios-larry-buddha-male-ja.pack.json",
  workerLabel: "anicca-buddha-tiktok-canary",
});

const LANES = Object.freeze([JA_LANE, EN_AFFIRMATION_LANE, EN_AFFIRMATION_TIKTOK_LANE, EN_SLIDESHOW_TIKTOK_LANE, JA_MAIN_TIKTOK_LANE, JA_JP1_TIKTOK_LANE, JA_BUDDHA_TIKTOK_LANE]);

function selectMarketingNativeCarouselLane(input = {}) {
  const integrationRef = input.instagramIntegrationRef || input.integrationRef;
  const matches = LANES.filter((lane) => lane.productId === input.productId
    && lane.formatId === input.formatId && lane.form === input.form && lane.locale === input.locale
    && lane.accountId === input.accountId && lane.integrationRef === integrationRef);
  if (matches.length !== 1) fail("marketing native carousel lane identity is invalid");
  const lane = matches[0];
  if (input.lane !== undefined && input.lane !== lane) fail("marketing native carousel lane is not trusted");
  if (input.accountRef !== undefined && input.accountRef !== lane.accountRef) fail("marketing native carousel account reference is invalid");
  if (input.nativeOwner !== undefined && input.nativeOwner !== lane.nativeOwner) fail("marketing native carousel native owner is invalid");
  if (lane.creativeId && input.creativeId !== undefined && input.creativeId !== lane.creativeId) fail("marketing native carousel creative is not approved");
  if (lane.packRef && ((input.packRef !== undefined && input.packRef !== lane.packRef)
    || (input.mediaRefs !== undefined && !sameArray(input.mediaRefs, lane.mediaRefs))
    || (input.captionRef !== undefined && input.captionRef !== lane.captionRef)
    || (input.approvalRef !== undefined && input.approvalRef !== lane.approvalRef))) {
    fail("marketing native carousel lane references are not approved");
  }
  return lane;
}

const mediaRefs = (value) => {
  if (!Array.isArray(value) || value.length !== SLIDE_COUNT) fail("marketing native carousel media references are invalid");
  const refs = value.map((v) => objectRef(v, "marketing native carousel media"));
  if (new Set(refs).size !== refs.length) fail("marketing native carousel media references are invalid");
  return refs;
};

function buildMarketingNativeCarouselPublicationJob(input = {}) {
  const tenantId = text(input.tenantId, "marketing native carousel tenant");
  const productId = text(input.productId, "marketing native carousel product");
  const formatId = text(input.formatId, "marketing native carousel format");
  const form = text(input.form, "marketing native carousel form");
  const locale = text(input.locale, "marketing native carousel locale");
  const creativeId = text(input.creativeId, "marketing native carousel creative");
  const accountId = text(input.accountId, "marketing native carousel account");
  const integrationRef = text(input.instagramIntegrationRef || input.tiktokIntegrationRef || input.integrationRef, "platform integration");
  const lane = selectMarketingNativeCarouselLane({ ...input, productId, formatId, form, locale, accountId, integrationRef, creativeId });
  if (!ID.test(tenantId) || !ID.test(creativeId)) fail("marketing native carousel identity is invalid");
  const slot = instant(input.slot, "marketing native carousel slot");
  const packRef = objectRef(input.packRef, "marketing native carousel pack");
  const media = mediaRefs(input.mediaRefs);
  const captionRef = objectRef(input.captionRef, "marketing native carousel caption");
  const approvalRef = objectRef(input.approvalRef, "marketing native carousel approval");
  const tokenRef = text(input.postizTokenRef, "Postiz token");
  if (!/^secret:\/\/[a-z0-9][a-z0-9._-]*(?:\/[a-z0-9][a-z0-9._-]*)*$/i.test(tokenRef)) fail("Postiz token reference is invalid");
  const packHash = objectHash(packRef, "pack");
  const mediaHashes = media.map((ref) => objectHash(ref, "media"));
  const captionHash = objectHash(captionRef, "caption");
  const slotScope = input.slotScopedEffect === true ? `:${crypto.createHash("sha256").update(slot).digest("hex")}` : "";
  const effectKey = `marketing:carousel:${PRODUCT_ID}:${creativeId}:${packHash}:${mediaOrderHash(mediaHashes)}:${captionHash}${slotScope}`;
  const inputRefs = {
    product_ref: `product://${lane.productId}`,
    format_ref: `format://${lane.formatId}`,
    form_ref: `form://${lane.form}`,
    locale_ref: `locale://${lane.locale}`,
    slot_ref: `schedule-slot://${slot}`,
    creative_ref: `creative://${lane.productId}/${creativeId}`,
    platform_ref: `platform://${lane.platform}`,
    account_ref: lane.accountRef,
    ...(lane.platform === "tiktok" ? { tiktok_integration_ref: integrationRef } : { instagram_integration_ref: integrationRef }),
    pack_ref: packRef,
    media_refs: media,
    caption_ref: captionRef,
    approval_ref: approvalRef,
    postiz_token_ref: tokenRef,
  };
  const jobHash = crypto.createHash("sha256").update(JSON.stringify({ tenant_id: tenantId, effect_key: effectKey })).digest("hex");
  return buildRuntimeJob({ jobId: `marketing-native-carousel-publication:${jobHash}`, tenantId, loopId: LOOP_ID, capability: CAPABILITY, effectClass: "publish", effectKey, inputRefs, maxAttempts: 3 });
}

function normalizeJob(job) {
  const refs = job && job.input_refs;
  const integrationKeys = refs && ["instagram_integration_ref", "tiktok_integration_ref"].filter((key) => Object.hasOwn(refs, key));
  if (!refs || typeof refs !== "object" || Array.isArray(refs) || integrationKeys.length !== 1
    || JSON.stringify(Object.keys(refs).sort()) !== JSON.stringify([...BASE_REF_KEYS, integrationKeys[0]].sort())) fail("marketing native carousel publication job contract is invalid");
  const product = /^product:\/\/(.+)$/.exec(String(refs.product_ref || ""));
  const format = /^format:\/\/(.+)$/.exec(String(refs.format_ref || ""));
  const form = /^form:\/\/(.+)$/.exec(String(refs.form_ref || ""));
  const locale = /^locale:\/\/(.+)$/.exec(String(refs.locale_ref || ""));
  const slot = /^schedule-slot:\/\/(.+)$/.exec(String(refs.slot_ref || ""));
  const creative = /^creative:\/\/(.+)\/([A-Za-z0-9][A-Za-z0-9._-]{0,127})$/.exec(String(refs.creative_ref || ""));
  const platform = /^platform:\/\/(instagram|tiktok)$/.exec(String(refs.platform_ref || ""));
  const account = platform && new RegExp(`^account://${platform[1]}/(.+)$`).exec(String(refs.account_ref || ""));
  if (!product || !format || !form || !locale || !slot || !creative || !account || creative[1] !== product[1]
    || !platform || integrationKeys[0] !== `${platform[1]}_integration_ref`) fail("marketing native carousel publication job contract is invalid");
  const effect = EFFECT.exec(String(job.effect_key || ""));
  const input = { tenantId: job.tenant_id, productId: product[1], formatId: format[1], form: form[1], locale: locale[1], slot: slot[1], creativeId: creative[2], accountId: account[1], accountRef: refs.account_ref, integrationRef: refs[integrationKeys[0]], packRef: refs.pack_ref, mediaRefs: refs.media_refs, captionRef: refs.caption_ref, approvalRef: refs.approval_ref, postizTokenRef: refs.postiz_token_ref, ...(effect?.[5] ? { slotScopedEffect: true } : {}) };
  const lane = selectMarketingNativeCarouselLane(input);
  let expected;
  try { expected = buildMarketingNativeCarouselPublicationJob(input); } catch { fail("marketing native carousel publication job contract is invalid"); }
  if (job.loop_id !== LOOP_ID || job.capability !== CAPABILITY || job.effect_class !== "publish" || job.job_id !== expected.job_id || job.effect_key !== expected.effect_key) fail("marketing native carousel publication job contract is invalid");
  return { ...input, lane, integrationRef: lane.integrationRef, packHash: objectHash(input.packRef, "pack"), mediaHashes: input.mediaRefs.map((ref) => objectHash(ref, "media")), captionHash: objectHash(input.captionRef, "caption") };
}

function readJson(file, label) {
  try { const value = JSON.parse(fs.readFileSync(file, "utf8")); return value && typeof value === "object" && !Array.isArray(value) ? value : fail(`${label} is invalid`); } catch (error) { if (error.message === `${label} is invalid`) throw error; fail(`${label} is invalid`); }
}
function assertIntegrity(file, hash, label) {
  if (!file || !fs.statSync(file, { throwIfNoEntry: false })?.isFile()) fail(`${label} object is unavailable`);
  if (sha256File(file) !== hash) fail(`${label} object integrity verification failed`);
}
function assertPack(pack, contract, caption, lane) {
  if (pack.schema_version !== 1 || pack.kind !== "marketing_native_carousel_pack" || pack.product_id !== lane.productId || pack.locale !== lane.locale || pack.platform !== lane.platform || pack.account_id !== lane.accountId || pack.renderer_id !== lane.renderer || pack.format_id !== lane.packFormat || pack.form !== lane.form || pack.media_type !== "image/jpeg" || pack.slide_count !== SLIDE_COUNT || pack.caption !== caption || !Array.isArray(pack.slides) || pack.slides.length !== SLIDE_COUNT
    || (pack.integration_id !== undefined && pack.integration_id !== lane.integrationId)
    || (pack.native_owner !== undefined && pack.native_owner !== lane.nativeOwner)
    || (pack.caption_ref !== undefined && pack.caption_ref !== contract.captionRef)) fail("marketing native carousel pack identity is invalid");
  const ordered = pack.slides.map((slide, i) => {
    const expectedRole = i === 0 ? "hook" : (i === SLIDE_COUNT - 1 ? (lane.lastSlideRole || (lane.platform === "tiktok" ? "cta" : "body")) : "body");
    if (!slide || slide.position !== i + 1 || slide.role !== expectedRole || typeof slide.text !== "string" || !OBJ.test(String(slide.media_ref || ""))) fail("marketing native carousel pack slide is invalid");
    return slide.media_ref;
  });
  if (JSON.stringify(ordered) !== JSON.stringify(contract.mediaRefs)) fail("marketing native carousel pack media order mismatch");
}
function assertApproval(approval, contract, lane) {
  const packBound = approval.pack_ref === contract.packRef || approval.pack_sha256 === contract.packHash;
  const refsBound = JSON.stringify(approval.media_refs) === JSON.stringify(contract.mediaRefs);
  const hashesBound = JSON.stringify(approval.media_sha256) === JSON.stringify(contract.mediaHashes)
    && approval.media_order_sha256 === mediaOrderHash(contract.mediaHashes);
  if (approval.schema_version !== 1 || !["marketing_native_carousel_publication_approval", "marketing_native_carousel_approval"].includes(approval.kind) || approval.status !== "approved" || approval.tenant_id !== contract.tenantId || approval.product_id !== lane.productId || approval.locale !== lane.locale || approval.platform !== lane.platform || approval.account_id !== lane.accountId || approval.integration_ref !== lane.integrationRef || !packBound || (!refsBound && !hashesBound) || approval.caption_sha256 !== contract.captionHash
    || (approval.native_owner !== undefined && approval.native_owner !== lane.nativeOwner)
    || (approval.creative_id !== undefined && lane.creativeId && approval.creative_id !== lane.creativeId)) fail("marketing native carousel approval mismatch");
}
function jpegDimensions(bytes, label) {
  const sof = new Set([0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7, 0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf]);
  let offset = 2;
  while (offset + 3 < bytes.length) {
    if (bytes[offset] !== 0xff) { offset += 1; continue; }
    while (offset < bytes.length && bytes[offset] === 0xff) offset += 1;
    const marker = bytes[offset]; offset += 1;
    if (marker === 0xd8 || marker === 0xd9 || marker === 0x01 || (marker >= 0xd0 && marker <= 0xd7)) continue;
    if (offset + 1 >= bytes.length) break;
    const length = bytes.readUInt16BE(offset);
    if (length < 2 || offset + length > bytes.length) break;
    if (sof.has(marker)) {
      if (length < 7) break;
      return { height: bytes.readUInt16BE(offset + 3), width: bytes.readUInt16BE(offset + 5) };
    }
    offset += length;
  }
  fail(`${label} JPEG dimensions are invalid`);
}
function assertMarketingCarouselJpeg(file, label, limits = {}) {
  const bytes = fs.readFileSync(file);
  if (bytes.length < 3 || bytes[0] !== 0xff || bytes[1] !== 0xd8 || bytes[2] !== 0xff) fail(`${label} is not JPEG`);
  if (limits.maxWidth === undefined && limits.maxHeight === undefined) return null;
  const dimensions = jpegDimensions(bytes, label);
  if (dimensions.width <= 0 || dimensions.height <= 0) fail(`${label} JPEG dimensions must be positive`);
  if (limits.maxWidth !== undefined && dimensions.width > limits.maxWidth) fail(`${label} JPEG width exceeds ${limits.maxWidth}`);
  if (limits.maxHeight !== undefined && dimensions.height > limits.maxHeight) fail(`${label} JPEG height exceeds ${limits.maxHeight}`);
  return dimensions;
}

function postizEnv(token) {
  const env = {};
  for (const key of ["PATH", "LANG", "LC_ALL", "TMPDIR"]) if (process.env[key] !== undefined) env[key] = process.env[key];
  env.POSTIZ_API_KEY = token;
  return env;
}
function runPostizCarouselProcess(input) {
  const root = path.resolve(__dirname, "../../..");
  const args = [path.join(root, "skills/video/lm-distribution/postiz_video.py")];
  for (const file of input.mediaPaths) args.push("--image", file);
  args.push("--caption-file", input.captionPath, "--integration", input.integrationId, "--platform", input.platform, "--title", input.title);
  const result = spawnSync(input.python || "python3", args, { cwd: root, env: postizEnv(input.token), encoding: "utf8", timeout: 20 * 60 * 1000, maxBuffer: 4 * 1024 * 1024 });
  if (result.status !== 0) { const error = new Error(`marketing native carousel Postiz failed with exit ${result.status}`); error.unknownEffect = true; throw error; }
  const lines = String(result.stdout || "").split(/\r?\n/).filter(Boolean);
  if (lines.length !== 1) { const error = new Error("marketing native carousel Postiz returned invalid JSON"); error.unknownEffect = true; throw error; }
  try { return JSON.parse(lines[0]); } catch { const error = new Error("marketing native carousel Postiz returned invalid JSON"); error.unknownEffect = true; throw error; }
}

function provider(result, lane) {
  const state = result && (result.state || result.status);
  const postId = result && (result.provider_post_id || result.post_id);
  const url = result && (result.public_url || result.post_url);
  const reconciled = result && (result.reconciled === true || result.provider_reconciled === true);
  const direct = lane.platform === "instagram" && directPostPattern(lane).test(String(url || ""));
  const photoProof = lane.platform === "tiktok" && url == null
    && result.integration_id === lane.integrationId && result.content_sha256 === lane.captionRef.slice(-64)
    && result.title === lane.title && result.posting_method === "DIRECT_POST"
    && /^p_pub_url~v2\.[0-9]+$/.test(String(result.release_id || ""));
  if (!result || state !== "PUBLISHED" || reconciled !== true || !PROVIDER_ID.test(String(postId || "")) || (!direct && !photoProof)) { const error = new Error("marketing native carousel provider result contract mismatch"); error.unknownEffect = true; throw error; }
  return { postId: String(postId), url: direct ? String(url) : null, ...(photoProof ? { state, integrationId: result.integration_id, contentSha256: result.content_sha256, title: result.title, postingMethod: result.posting_method, releaseId: result.release_id } : {}) };
}
function laneForReceipt(receipt) {
  try {
    const media = Array.isArray(receipt.media_sha256)
      ? receipt.media_sha256.map((hash) => `object://sha256/${hash}`)
      : receipt.media_sha256;
    return selectMarketingNativeCarouselLane({
      productId: receipt.product_id,
      formatId: receipt.format_id,
      form: receipt.form,
      locale: receipt.locale,
      accountId: receipt.account_id,
      integrationRef: receipt.integration_ref,
      creativeId: receipt.creative_id,
      packRef: `object://sha256/${receipt.pack_sha256}`,
      mediaRefs: media,
      captionRef: `object://sha256/${receipt.caption_sha256}`,
    });
  } catch {
    return null;
  }
}
function verifyMarketingNativeCarouselPublicationReceipt(receipt) {
  if (!receipt || typeof receipt !== "object" || Array.isArray(receipt) || receipt.schema_version !== 1 || receipt.kind !== "marketing_native_carousel_distribution" || receipt.status !== "published" || !ID.test(String(receipt.creative_id || "")) || !HASH.test(String(receipt.pack_sha256 || "")) || !Array.isArray(receipt.media_sha256) || receipt.media_sha256.length !== SLIDE_COUNT || receipt.media_sha256.some((hash) => !HASH.test(String(hash || ""))) || !HASH.test(String(receipt.media_order_sha256 || "")) || receipt.media_order_sha256 !== mediaOrderHash(receipt.media_sha256) || !HASH.test(String(receipt.caption_sha256 || "")) || !PROVIDER_ID.test(String(receipt.provider_post_id || "")) || receipt.provider_reconciled !== true) return false;
  const lane = laneForReceipt(receipt);
  if (!lane || receipt.product_id !== lane.productId || receipt.format_id !== lane.formatId || receipt.form !== lane.form || receipt.locale !== lane.locale || receipt.account_id !== lane.accountId || receipt.integration_ref !== lane.integrationRef) return false;
  const direct = lane.platform === "instagram" && directPostPattern(lane).test(String(receipt.public_url || ""));
  const photoApiProof = lane.platform === "tiktok"
    && receipt.public_url == null
    && receipt.provider_state === "PUBLISHED"
    && receipt.provider_integration_id === lane.integrationId
    && receipt.provider_content_sha256 === receipt.caption_sha256
    && receipt.provider_title === lane.title
    && receipt.provider_posting_method === "DIRECT_POST"
    && /^p_pub_url~v2\.[0-9]+$/.test(String(receipt.provider_release_id || ""));
  if (!direct && !photoApiProof) return false;
  try { instant(receipt.published_at, "marketing native carousel receipt published_at"); return true; } catch { return false; }
}
function summary(receipt) {
  if (!verifyMarketingNativeCarouselPublicationReceipt(receipt)) fail("marketing native carousel receipt verification failed");
  const lane = laneForReceipt(receipt);
  return { status: receipt.status, product_id: lane.productId, format_id: lane.formatId, form: lane.form, locale: lane.locale, account_id: lane.accountId, integration_ref: lane.integrationRef, creative_id: receipt.creative_id, public_url: receipt.public_url, provider_post_id: receipt.provider_post_id, provider_reconciled: true, pack_sha256: receipt.pack_sha256, media_sha256: [...receipt.media_sha256], caption_sha256: receipt.caption_sha256 };
}

function defaultLedgerPath(tenantId, paths, productId = PRODUCT_ID) {
  return path.join(paths.dataDir, "tenants", encodeURIComponent(text(tenantId, "tenant")), "marketing", "native-carousel-publication", productId, "distribution.jsonl");
}
function services(deps = {}, lane = JA_LANE) {
  let paths;
  const runtime = () => paths || (paths = resolveRuntimePaths(process.env));
  return { objectStore: deps.objectStore || { resolve: (ref) => createContentObjectStore({ objectDir: runtime().objectDir }).resolve(ref) }, secretProvider: deps.secretProvider, ledgerPath: deps.ledgerPath || ((tenantId) => defaultLedgerPath(tenantId, runtime(), lane.productId)), runDistribution: deps.runDistribution || runPostizCarouselProcess, now: deps.now || (() => new Date().toISOString()) };
}
function ledgerFor(s, tenantId, productId = PRODUCT_ID) { if (typeof s.ledgerPath === "function") return s.ledgerPath(tenantId, productId); if (typeof s.ledgerPath === "string" && s.ledgerPath.trim()) return s.ledgerPath; fail("marketing native carousel distribution ledger path is invalid"); }
function appendRow(file, job, receipt) { fs.mkdirSync(path.dirname(file), { recursive: true, mode: 0o700 }); fs.appendFileSync(file, `${JSON.stringify({ effect_key: job.effect_key, job_id: job.job_id, receipt })}\n`, { encoding: "utf8", mode: 0o600 }); fs.chmodSync(file, 0o600); }

async function executeMarketingNativeCarouselPublicationJob(job, deps = {}) {
  const contract = normalizeJob(job);
  const lane = contract.lane;
  const s = services(deps);
  if (!s.objectStore || typeof s.objectStore.resolve !== "function") fail("marketing native carousel object store is required");
  if (!s.secretProvider || typeof s.secretProvider.get !== "function") fail("marketing native carousel secret provider is required");
  const packPath = s.objectStore.resolve(contract.packRef);
  const mediaPaths = contract.mediaRefs.map((ref) => s.objectStore.resolve(ref));
  const captionPath = s.objectStore.resolve(contract.captionRef);
  const approvalPath = s.objectStore.resolve(contract.approvalRef);
  assertIntegrity(packPath, contract.packHash, "marketing native carousel pack");
  mediaPaths.forEach((file, i) => { assertIntegrity(file, contract.mediaHashes[i], `marketing native carousel media ${i + 1}`); assertMarketingCarouselJpeg(file, `marketing native carousel media ${i + 1}`, lane.platform === "tiktok" ? { maxWidth: 1080, maxHeight: 1920 } : {}); });
  assertIntegrity(captionPath, contract.captionHash, "marketing native carousel caption");
  assertIntegrity(approvalPath, objectHash(contract.approvalRef, "approval"), "marketing native carousel approval");
  const caption = fs.readFileSync(captionPath, "utf8");
  const pack = readJson(packPath, "marketing native carousel pack");
  assertPack(pack, { ...contract, expectedCaption: caption }, caption, lane);
  assertApproval(readJson(approvalPath, "marketing native carousel approval"), contract, lane);
  const token = await s.secretProvider.get(job.tenant_id, contract.postizTokenRef);
  if (typeof token !== "string" || !token.trim()) fail("marketing native carousel Postiz token is invalid");
  writeMarketingEffectIdentity({
    jobId: job.job_id,
    effectKey: job.effect_key,
    productId: lane.productId,
    formatId: lane.formatId,
    form: lane.form,
    locale: lane.locale,
    platform: lane.platform,
    creativeId: contract.creativeId,
    slot: contract.slot,
    integrationRef: contract.integrationRef,
    accountId: lane.accountId,
    captionSha256: contract.captionHash,
    mediaSha256: contract.mediaHashes,
    packSha256: contract.packHash,
    mediaOrderSha256: mediaOrderHash(contract.mediaHashes),
  });
  let result;
  try { result = await s.runDistribution({ tenantId: job.tenant_id, productId: lane.productId, formatId: lane.formatId, form: lane.form, locale: lane.locale, platform: lane.platform, title: pack.slides[0].text, creativeId: contract.creativeId, accountId: lane.accountId, integrationRef: contract.integrationRef, integrationId: lane.integrationId, packPath, mediaPaths: [...mediaPaths], captionPath, token }); } catch (cause) { const error = new Error(cause && cause.message ? cause.message : String(cause)); error.unknownEffect = true; throw error; }
  const published = provider(result, lane);
  const receipt = { schema_version: 1, kind: "marketing_native_carousel_distribution", status: "published", product_id: lane.productId, format_id: lane.formatId, form: lane.form, locale: lane.locale, platform: lane.platform, account_id: lane.accountId, integration_ref: contract.integrationRef, creative_id: contract.creativeId, pack_sha256: contract.packHash, media_sha256: [...contract.mediaHashes], media_order_sha256: mediaOrderHash(contract.mediaHashes), caption_sha256: contract.captionHash, provider_post_id: published.postId, provider_reconciled: true, public_url: published.url, ...(published.url == null ? { provider_state: published.state, provider_integration_id: published.integrationId, provider_content_sha256: published.contentSha256, provider_title: published.title, provider_posting_method: published.postingMethod, provider_release_id: published.releaseId } : {}), published_at: instant(s.now(), "marketing native carousel publication time") };
  if (!verifyMarketingNativeCarouselPublicationReceipt(receipt)) { const error = new Error("marketing native carousel publication receipt verification failed"); error.unknownEffect = true; throw error; }
  appendRow(ledgerFor(s, job.tenant_id, lane.productId), job, receipt);
  return { receipt, result };
}

function effectParts(key) { const m = EFFECT.exec(text(key, "effect key")); return m || fail("marketing native carousel effect key is invalid"); }
function reconcile(effect, s) {
  const key = effect && (effect.effect_key || effect.effectKey); const file = ledgerFor(s, effect.tenant_id || effect.tenantId); let lines;
  try { lines = fs.readFileSync(file, "utf8").split(/\r?\n/).filter(Boolean); } catch (error) { if (error.code === "ENOENT") return { state: "unknown" }; fail("marketing native carousel distribution ledger is invalid"); }
  let malformed = false;
  const parsed = lines.map((line) => { try { return JSON.parse(line); } catch { malformed = true; return null; } });
  if (malformed) return { state: "unknown" };
  const rows = parsed.filter((row) => row && row.effect_key === key);
  if (!rows.length) return { state: "unknown" };
  const receipt = rows.at(-1).receipt || rows.at(-1);
  const m = effectParts(key);
  if (!verifyMarketingNativeCarouselPublicationReceipt(receipt) || receipt.creative_id !== m[1] || receipt.pack_sha256 !== m[2] || receipt.media_order_sha256 !== m[3] || receipt.caption_sha256 !== m[4]) return { state: "unknown" };
  return { state: "present", receipt };
}
function createMarketingNativeCarouselPublicationLoopAdapter(deps = {}) {
  return Object.freeze({ plan: async (input) => [buildMarketingNativeCarouselPublicationJob(input)], execute: (job, extra = {}) => executeMarketingNativeCarouselPublicationJob(job, { ...deps, ...extra }), reconcile: async (effect) => reconcile(effect, services(deps)), verify: verifyMarketingNativeCarouselPublicationReceipt, report: summary });
}

module.exports = { ADAPTER_ID, LOOP_ID, CAPABILITY, PRODUCT_ID, FORMAT_ID, FORM_ID, ACCOUNT_ID, ACCOUNT_REF, INTEGRATION_REF, PACK_FORMAT_ID, JA_LANE, EN_AFFIRMATION_LANE, EN_AFFIRMATION_TIKTOK_LANE, EN_SLIDESHOW_TIKTOK_LANE, JA_MAIN_TIKTOK_LANE, JA_JP1_TIKTOK_LANE, JA_BUDDHA_TIKTOK_LANE, assertMarketingCarouselJpeg, buildMarketingNativeCarouselPublicationJob, buildMarketingNativeCarouselJob: buildMarketingNativeCarouselPublicationJob, createMarketingNativeCarouselPublicationLoopAdapter, createMarketingNativeCarouselAdapter: createMarketingNativeCarouselPublicationLoopAdapter, executeMarketingNativeCarouselPublicationJob, executeMarketingNativeCarouselJob: executeMarketingNativeCarouselPublicationJob, normalizeMarketingNativeCarouselJob: normalizeJob, selectMarketingNativeCarouselLane, runPostizCarouselProcess, safeMarketingNativeCarouselSummary: summary, verifyMarketingNativeCarouselPublicationReceipt, verifyMarketingNativeCarouselReceipt: verifyMarketingNativeCarouselPublicationReceipt };
