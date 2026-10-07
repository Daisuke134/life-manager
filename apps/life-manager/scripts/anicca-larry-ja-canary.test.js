"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createContentObjectStore, importContentObject } = require("../lib/content-object-store.js");
const { createMarketingLaneManifest, writeMarketingLaneManifest } = require("../lib/marketing-lane-manifest.js");
const {
  ACCOUNT_ID,
  EN_AFFIRMATION_LANE,
  EN_AFFIRMATION_TIKTOK_LANE,
  EN_SLIDESHOW_TIKTOK_LANE,
  JA_JP1_TIKTOK_LANE,
  JA_MAIN_TIKTOK_LANE,
  INTEGRATION_REF,
} = require("../lib/marketing-native-carousel-publication-adapter.js");
const {
  EN_AFFIRMATION_LANE: EN_RUNNER_LANE,
  EN_AFFIRMATION_TIKTOK_LANE: EN_TIKTOK_RUNNER_LANE,
  EN_SLIDESHOW_TIKTOK_LANE: TIKTOK_SLIDESHOW_RUNNER_LANE,
  JA_MAIN_TIKTOK_LANE: JA_MAIN_TIKTOK_RUNNER_LANE,
  assertProductionControls,
  isVerifiedPostizPhotoPublication,
  parseArgs,
  runAniccaCarouselCanary,
  runAniccaEnAffirmationInstagramCanary,
  runAniccaEnSlideshowTikTokCanary,
  runAniccaLarryJaCanary,
} = require("./anicca-larry-ja-canary.js");

const SLOT = "2026-08-26T07:30:00.000Z";
const CAPTION = "メンタルが勝手に安定する\n口癖５選\n\n#anicca #affirmation";
const EN_PACK_REF = "object://sha256/e23cd41257832d2032fd889bd9a16ec95ea8dc213cdd7a2e3f820fbe1578669e";
const EN_MEDIA_REFS = [
  "object://sha256/da8d8265a1344b68a877d776b0cec5b599dc7b3bbd6abc833fcef06e7416df1f",
  "object://sha256/4fe9ab673f095d39368744974c677cbb5f8305dc2a9dcd1ef1b4b87759d8b42a",
  "object://sha256/1af8a8c790a733ff1cedca85aaf3de010671a03f54223205da0fd9575a242840",
  "object://sha256/d097d7b7254ee0a35c95844a89e1f8d1d644775dea134f960ac5e8cb80d230f9",
  "object://sha256/71ded59ff8a1de5251e607a6ba808945c85537bfca3fbd7f20c65f2912f00e34",
  "object://sha256/418ad1907d64e4835939bda677709aace44092a936e8a18a7cb8aeeca7652f4f",
];
const EN_CAPTION_REF = "object://sha256/bf90a15a5a615d2bb295c1829f7329f391a870fe4e950c8099972c20bf6e64a0";
const EN_APPROVAL_REF = "object://sha256/7740cd09733d0cb7a5d8f32ff4614c3e07ebae27df0e3eae8bca8df80b968845";
const EN_OBJECT_SOURCE = path.join(os.homedir(), ".local", "state", "life-manager", "objects", "sha256");

function sha256(value) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function fixture() {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-larry-ja-canary-"));
  const objectStore = createContentObjectStore({ objectDir: path.join(dataDir, "objects") });
  const importBytes = (name, bytes) => {
    const source = path.join(dataDir, name);
    fs.writeFileSync(source, bytes);
    return importContentObject(source, { objectDir: path.join(dataDir, "objects") }).ref;
  };
  const captionRef = importBytes("caption.txt", Buffer.from(CAPTION));
  const mediaRefs = Array.from({ length: 6 }, (_, index) => importBytes(
    `slide-${index + 1}.jpg`,
    Buffer.from([0xff, 0xd8, 0xff, index + 1, 0xff, 0xd9]),
  ));
  const pack = {
    schema_version: 1,
    kind: "marketing_native_carousel_pack",
    product_id: "anicca-ios",
    locale: "ja",
    platform: "instagram",
    account_id: ACCOUNT_ID,
    renderer_id: "larry",
    format_id: "native-photo-carousel",
    form: "affirmation-carousel",
    variant: "ja-v1",
    media_type: "image/jpeg",
    slide_count: 6,
    caption: CAPTION,
    slides: mediaRefs.map((media_ref, index) => ({
      position: index + 1,
      role: index === 0 ? "hook" : "body",
      text: `slide-${index + 1}`,
      media_ref,
    })),
  };
  const packRef = importBytes("pack.json", Buffer.from(JSON.stringify(pack)));
  const approval = {
    schema_version: 1,
    kind: "marketing_native_carousel_publication_approval",
    status: "approved",
    tenant_id: "dais-local",
    product_id: "anicca-ios",
    locale: "ja",
    platform: "instagram",
    account_id: ACCOUNT_ID,
    integration_ref: INTEGRATION_REF,
    pack_ref: packRef,
    media_refs: mediaRefs,
    caption_sha256: captionRef.slice(-64),
  };
  const approvalRef = importBytes("approval.json", Buffer.from(JSON.stringify(approval)));
  const env = {
    LM_DATA_DIR: dataDir,
    LM_RUNTIME_TENANT_ID: "dais-local",
    LM_ANICCA_LARRY_JA_PACK_REF: packRef,
    LM_ANICCA_LARRY_JA_MEDIA_REFS: mediaRefs.join(","),
    LM_ANICCA_LARRY_JA_CAPTION_REF: captionRef,
    LM_ANICCA_LARRY_JA_APPROVAL_REF: approvalRef,
    LM_POSTIZ_API_KEY: "postiz-secret-fixture",
    LM_TELEGRAM_BOT_TOKEN: "telegram-secret-fixture",
    LM_TELEGRAM_ALERT_CHAT_ID: "123456789",
  };
  return { dataDir, env, objectStore, importBytes, packRef, mediaRefs, captionRef, approvalRef };
}

function enFixture() {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-anicca-en-affirmation-canary-"));
  const objectDir = path.join(dataDir, "objects");
  const objectStore = createContentObjectStore({ objectDir });
  const refs = [EN_PACK_REF, ...EN_MEDIA_REFS, EN_CAPTION_REF, EN_APPROVAL_REF];
  for (const ref of refs) {
    const source = path.join(EN_OBJECT_SOURCE, ref.slice(-64));
    assert.equal(fs.statSync(source, { throwIfNoEntry: false })?.isFile(), true, `missing EN object ${ref}`);
    const destination = path.join(objectDir, "sha256", ref.slice(-64));
    fs.mkdirSync(path.dirname(destination), { recursive: true, mode: 0o700 });
    fs.copyFileSync(source, destination);
  }
  const liveMarketingDir = path.join(os.homedir(), ".local", "state", "life-manager", "marketing");
  const testMarketingDir = path.join(dataDir, "marketing");
  fs.mkdirSync(testMarketingDir, { recursive: true, mode: 0o700 });
  for (const name of ["lane-manifest.json", "publication-effect-fence.json"]) {
    fs.copyFileSync(path.join(liveMarketingDir, name), path.join(testMarketingDir, name));
    fs.chmodSync(path.join(testMarketingDir, name), 0o600);
  }
  const liveManifest = JSON.parse(fs.readFileSync(path.join(testMarketingDir, "lane-manifest.json"), "utf8"));
  const defaultOffRows = liveManifest.lanes.map((row) => ({
    ...row,
    verified: true,
    ...(row.production_armed === true ? { lane_state: "default-off", production_armed: false } : {}),
  }));
  writeMarketingLaneManifest(createMarketingLaneManifest({
    tenant_id: liveManifest.tenant_id,
    integrations: defaultOffRows,
    holds: liveManifest.holds.map((row) => ({ ...row, verified: true })),
  }, { tenantId: liveManifest.tenant_id, assignments: defaultOffRows.map((row) => ({ ...row })) }), { dataDir });
  return {
    dataDir,
    objectStore,
    controlBytes: {
      manifest: fs.readFileSync(path.join(dataDir, "marketing", "lane-manifest.json")),
      fence: fs.readFileSync(path.join(dataDir, "marketing", "publication-effect-fence.json")),
    },
    env: {
      LM_DATA_DIR: dataDir,
      LM_RUNTIME_TENANT_ID: "dais-local",
      [EN_RUNNER_LANE.packEnv]: EN_PACK_REF,
      [EN_RUNNER_LANE.mediaEnv]: EN_MEDIA_REFS.join(","),
      [EN_RUNNER_LANE.captionEnv]: EN_CAPTION_REF,
      [EN_RUNNER_LANE.approvalEnv]: EN_APPROVAL_REF,
      LM_POSTIZ_API_KEY: "postiz-secret-fixture",
      LM_TELEGRAM_BOT_TOKEN: "telegram-secret-fixture",
      LM_TELEGRAM_ALERT_CHAT_ID: "123456789",
    },
  };
}

function enTikTokFixture() {
  const lane = EN_TIKTOK_RUNNER_LANE;
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-anicca-en-tiktok-canary-"));
  const objectDir = path.join(dataDir, "objects");
  const objectStore = createContentObjectStore({ objectDir });
  const importBytes = (name, bytes) => {
    const source = path.join(dataDir, name);
    fs.writeFileSync(source, bytes);
    return importContentObject(source, { objectDir }).ref;
  };
  const mediaRefs = [...lane.mediaRefs];
  for (const ref of mediaRefs) {
    const source = path.join(EN_OBJECT_SOURCE, ref.slice(-64));
    assert.equal(fs.statSync(source, { throwIfNoEntry: false })?.isFile(), true, `missing TikTok media ${ref}`);
    const destination = path.join(objectDir, "sha256", ref.slice(-64));
    fs.mkdirSync(path.dirname(destination), { recursive: true, mode: 0o700 });
    fs.copyFileSync(source, destination);
  }
  const caption = "A kinder thought for the next hard moment.\n\n#affirmations #Anicca";
  const captionRef = importBytes("caption.txt", Buffer.from(caption));
  const pack = {
    schema_version: 1,
    kind: "marketing_native_carousel_pack",
    product_id: lane.productId,
    locale: lane.locale,
    platform: lane.platform,
    account_id: lane.accountId,
    renderer_id: lane.renderer,
    format_id: lane.packFormat,
    form: lane.form,
    media_type: "image/jpeg",
    slide_count: 6,
    caption,
    slides: mediaRefs.map((media_ref, index) => ({
      position: index + 1,
      role: index === 0 ? "hook" : index === 5 ? "cta" : "body",
      text: `fresh-test-slide-${index + 1}`,
      media_ref,
    })),
  };
  const packRef = importBytes("pack.json", Buffer.from(JSON.stringify(pack)));
  const approval = {
    schema_version: 1,
    kind: "marketing_native_carousel_publication_approval",
    status: "approved",
    tenant_id: "dais-local",
    product_id: lane.productId,
    locale: lane.locale,
    platform: lane.platform,
    account_id: lane.accountId,
    integration_ref: lane.integrationRef,
    pack_ref: packRef,
    media_refs: mediaRefs,
    caption_sha256: captionRef.slice(-64),
  };
  const approvalRef = importBytes("approval.json", Buffer.from(JSON.stringify(approval)));
  const liveMarketingDir = path.join(os.homedir(), ".local", "state", "life-manager", "marketing");
  const testMarketingDir = path.join(dataDir, "marketing");
  fs.mkdirSync(testMarketingDir, { recursive: true, mode: 0o700 });
  for (const name of ["lane-manifest.json", "publication-effect-fence.json"]) {
    fs.copyFileSync(path.join(liveMarketingDir, name), path.join(testMarketingDir, name));
    fs.chmodSync(path.join(testMarketingDir, name), 0o600);
  }
  return {
    dataDir,
    objectStore,
    env: {
      LM_DATA_DIR: dataDir,
      LM_RUNTIME_TENANT_ID: "dais-local",
      [lane.packEnv]: packRef,
      [lane.mediaEnv]: mediaRefs.join(","),
      [lane.captionEnv]: captionRef,
      [lane.approvalEnv]: approvalRef,
      LM_POSTIZ_API_KEY: "postiz-secret-fixture",
      LM_TELEGRAM_BOT_TOKEN: "telegram-secret-fixture",
      LM_TELEGRAM_ALERT_CHAT_ID: "123456789",
    },
  };
}

function enVerification(value, receipt) {
  const objectDir = path.join(value.dataDir, "objects");
  const evidencePath = path.join(value.dataDir, "evidence.txt");
  fs.writeFileSync(evidencePath, "six exact frames verified");
  const evidenceRef = importContentObject(evidencePath, { objectDir }).ref;
  const verificationPath = path.join(value.dataDir, "verification.json");
  fs.writeFileSync(verificationPath, JSON.stringify({
    schema_version: 1,
    kind: "marketing_native_carousel_native_verification",
    status: "verified",
    product_id: "anicca-ios",
    account_id: "@anicca.affirmation",
    native_owner: "@anicca.ios",
    integration_ref: "integration://postiz/instagram/cmp9pedr700ttqh0yj8o57fog",
    public_url: receipt.public_url,
    pack_sha256: receipt.pack_sha256,
    media_sha256: receipt.media_sha256,
    media_order_sha256: receipt.media_order_sha256,
    caption_sha256: receipt.caption_sha256,
    evidence_ref: evidenceRef,
    verified_at: "2026-08-26T08:00:00.000Z",
  }));
  return importContentObject(verificationPath, { objectDir }).ref;
}

function providerCalls(calls, result = {}) {
  return async (input) => {
    calls.push(input);
    return {
      state: "PUBLISHED",
      reconciled: true,
      post_id: "postiz-larry-canary-1",
      post_url: "https://www.instagram.com/p/LarryCanary1/",
      ...result,
    };
  };
}

function verification(fixtureValue, receipt, overrides = {}) {
  const evidenceRef = fixtureValue.importBytes("visual-evidence.txt", Buffer.from("six exact frames verified"));
  return fixtureValue.importBytes("verification.json", Buffer.from(JSON.stringify({
    schema_version: 1,
    kind: "marketing_native_carousel_native_verification",
    status: "verified",
    product_id: "anicca-ios",
    account_id: ACCOUNT_ID,
    integration_ref: INTEGRATION_REF,
    public_url: receipt.public_url,
    pack_sha256: receipt.pack_sha256,
    media_sha256: receipt.media_sha256,
    media_order_sha256: receipt.media_order_sha256,
    caption_sha256: receipt.caption_sha256,
    evidence_ref: evidenceRef,
    verified_at: "2026-08-26T08:00:00.000Z",
    ...overrides,
  })));
}

test("CLI accepts only run with a mandatory exact ISO slot", () => {
  assert.deepEqual(parseArgs(["run", "--slot", SLOT]), { command: "run", slot: SLOT });
  assert.throws(() => parseArgs(["run"]), /usage/i);
  assert.throws(() => parseArgs(["run", "--slot"]), /usage/i);
  assert.throws(() => parseArgs(["publish"]), /usage/i);
});

test("first canary publishes once and holds Telegram without native verification", async () => {
  const value = fixture();
  const publicationCalls = [];
  const telegramCalls = [];
  const result = await runAniccaLarryJaCanary(["run", "--slot", SLOT], {
    env: value.env,
    runDistribution: providerCalls(publicationCalls),
    sendTelegram: async (...args) => { telegramCalls.push(args); return { ok: true, result: { message_id: 1 } }; },
    now: () => "2026-08-26T07:31:00.000Z",
  });
  assert.deepEqual(result, {
    slot: SLOT,
    publication: { created: true, public_url: "https://www.instagram.com/p/LarryCanary1/", provider_post_id: "postiz-larry-canary-1" },
    telegram: { created: false, held: true, message_id: null },
  });
  assert.equal(publicationCalls.length, 1);
  assert.equal(telegramCalls.length, 0);
  assert.doesNotMatch(JSON.stringify(result), /postiz-secret|telegram-secret|openclaw|\/Users\//i);
  const jobs = fs.readFileSync(path.join(value.dataDir, "marketing", "jobs.jsonl"), "utf8");
  assert.doesNotMatch(jobs, /postiz-secret|telegram-secret|\/Users\/|openclaw/i);
});

test("tenant and ordered-ref environment bindings are exact", async () => {
  const wrongTenant = fixture();
  wrongTenant.env.LM_RUNTIME_TENANT_ID = "other-tenant";
  await assert.rejects(runAniccaLarryJaCanary(["run", "--slot", SLOT], { env: wrongTenant.env }), /tenant/i);
  const wrongMedia = fixture();
  wrongMedia.env.LM_ANICCA_LARRY_JA_MEDIA_REFS = wrongMedia.mediaRefs.slice(0, 5).join(",");
  await assert.rejects(runAniccaLarryJaCanary(["run", "--slot", SLOT], { env: wrongMedia.env }), /media/i);
});

test("missing or mismatched native verification holds Telegram", async () => {
  const value = fixture();
  const publicationCalls = [];
  const first = await runAniccaLarryJaCanary(["run", "--slot", SLOT], { env: value.env, runDistribution: providerCalls(publicationCalls) });
  value.env.LM_ANICCA_LARRY_JA_NATIVE_VERIFICATION_REF = verification(value, {
    public_url: first.publication.public_url,
    pack_sha256: "f".repeat(64),
    media_sha256: value.mediaRefs.map((ref) => ref.slice(-64)),
    media_order_sha256: sha256(JSON.stringify(value.mediaRefs.map((ref) => ref.slice(-64)))),
    caption_sha256: value.captionRef.slice(-64),
  });
  const held = await runAniccaLarryJaCanary(["run", "--slot", SLOT], { env: value.env, runDistribution: providerCalls(publicationCalls) });
  assert.equal(held.publication.created, false);
  assert.deepEqual(held.telegram, { created: false, held: true, message_id: null });
  assert.equal(publicationCalls.length, 1);
});

test("exact native verification releases one natural Telegram receipt and replay is idempotent", async () => {
  const value = fixture();
  const publicationCalls = [];
  const telegramCalls = [];
  const options = {
    env: value.env,
    runDistribution: providerCalls(publicationCalls),
    sendTelegram: async (...args) => { telegramCalls.push(args); return { ok: true, result: { message_id: 42 } }; },
    now: () => "2026-08-26T07:31:00.000Z",
  };
  const first = await runAniccaLarryJaCanary(["run", "--slot", SLOT], options);
  const receiptPath = path.join(value.dataDir, "marketing", "receipts.jsonl");
  const publicationReceipt = JSON.parse(fs.readFileSync(receiptPath, "utf8")).receipt;
  value.env.LM_ANICCA_LARRY_JA_NATIVE_VERIFICATION_REF = verification(value, publicationReceipt);
  const replayOptions = { ...options, now: () => "2026-08-26T08:01:00.000Z" };
  const second = await runAniccaLarryJaCanary(["run", "--slot", SLOT], replayOptions);
  const third = await runAniccaLarryJaCanary(["run", "--slot", SLOT], replayOptions);
  assert.equal(first.telegram.held, true);
  assert.deepEqual(second.telegram, { created: true, held: false, message_id: 42 });
  assert.deepEqual(third.telegram, { created: false, held: false, message_id: 42 });
  assert.equal(publicationCalls.length, 1);
  assert.equal(telegramCalls.length, 1);
});

test("native verification must be strictly after publication and no later than trusted now", async () => {
  const value = fixture();
  const publicationCalls = [];
  const baseOptions = {
    env: value.env,
    runDistribution: providerCalls(publicationCalls),
    now: () => "2026-08-26T07:31:00.000Z",
  };
  await runAniccaLarryJaCanary(["run", "--slot", SLOT], baseOptions);
  const receipt = JSON.parse(fs.readFileSync(path.join(value.dataDir, "marketing", "receipts.jsonl"), "utf8")).receipt;
  for (const [verifiedAt, trustedNow] of [
    [receipt.published_at, "2026-08-26T08:01:00.000Z"],
    ["2026-08-26T07:30:59.000Z", "2026-08-26T08:01:00.000Z"],
    ["2026-08-26T08:02:00.000Z", "2026-08-26T08:01:00.000Z"],
  ]) {
    value.env.LM_ANICCA_LARRY_JA_NATIVE_VERIFICATION_REF = verification(value, receipt, { verified_at: verifiedAt });
    const held = await runAniccaLarryJaCanary(["run", "--slot", SLOT], { ...baseOptions, now: () => trustedNow });
    assert.equal(held.telegram.held, true);
  }
  value.env.LM_ANICCA_LARRY_JA_NATIVE_VERIFICATION_REF = verification(value, receipt, { verified_at: "2026-08-26T08:00:00.000Z" });
  const released = await runAniccaLarryJaCanary(["run", "--slot", SLOT], { ...baseOptions, now: () => "2026-08-26T08:01:00.000Z", sendTelegram: async () => ({ ok: true, result: { message_id: 77 } }) });
  assert.deepEqual(released.telegram, { created: true, held: false, message_id: 77 });
});

test("a provider result without a direct /p receipt never sends Telegram", async () => {
  const value = fixture();
  const telegramCalls = [];
  await assert.rejects(
    runAniccaLarryJaCanary(["run", "--slot", SLOT], {
      env: value.env,
      runDistribution: providerCalls([], { post_url: "https://www.instagram.com/@ani.cca1234" }),
      sendTelegram: async (...args) => { telegramCalls.push(args); return { ok: true, result: { message_id: 9 } }; },
    }),
    /receipt|provider|publication/i,
  );
  assert.equal(telegramCalls.length, 0);
});

test("EN affirmation CLI selects its frozen lane while JA run remains unchanged", () => {
  assert.deepEqual(parseArgs(["run", "--slot", SLOT]), { command: "run", slot: SLOT });
  assert.deepEqual(parseArgs(["run-en-affirmation", "--slot", SLOT]), { command: "run-en-affirmation", slot: SLOT });
  assert.deepEqual(parseArgs(["run-ja-larry-production"]), { command: "run-ja-larry-production", slot: null });
  assert.deepEqual(parseArgs(["run-en-affirmation-production"]), { command: "run-en-affirmation-production", slot: null });
  assert.equal(EN_RUNNER_LANE.accountId, "@anicca.affirmation");
  assert.equal(EN_RUNNER_LANE.nativeOwner, "@anicca.ios");
});

test("EN slideshow TikTok command selects only its immutable lane", () => {
  assert.deepEqual(parseArgs(["run-en-slideshow-tiktok", "--slot", SLOT]), { command: "run-en-slideshow-tiktok", slot: SLOT });
  assert.deepEqual(parseArgs(["run-en-slideshow-tiktok-production"]), { command: "run-en-slideshow-tiktok-production", slot: null });
  assert.equal(TIKTOK_SLIDESHOW_RUNNER_LANE, EN_SLIDESHOW_TIKTOK_LANE);
  assert.equal(TIKTOK_SLIDESHOW_RUNNER_LANE.accountId, "@anicca_slideshow");
  assert.equal(TIKTOK_SLIDESHOW_RUNNER_LANE.integrationId, "cmnenjkff01j1pa0ysufmzhfr");
  assert.throws(() => runAniccaEnSlideshowTikTokCanary(["run-en-affirmation", "--slot", SLOT], {}), /accepts only/i);
});

test("EN2 TikTok production command accepts only its exact due slot shape", () => {
  const command = "run-en2-affirmation-tiktok-production";
  assert.deepEqual(parseArgs([command]), { command, slot: null });
  assert.deepEqual(parseArgs([command, "--slot", SLOT]), { command, slot: SLOT });
});

test("TikTok Postiz liveness accepts the exact CTA-adjusted caption hash", () => {
  const lane = { platform: "tiktok" };
  const baseCaptionSha = "a".repeat(64);
  const finalCaptionSha = "b".repeat(64);
  const receipt = {
    public_url: null,
    provider_state: "PUBLISHED",
    provider_posting_method: "DIRECT_POST",
    provider_content_sha256: finalCaptionSha,
    caption_sha256: baseCaptionSha,
    caption_with_cta_sha256: finalCaptionSha,
  };

  assert.equal(isVerifiedPostizPhotoPublication(lane, receipt), true);
  assert.equal(isVerifiedPostizPhotoPublication(lane, {
    ...receipt,
    provider_content_sha256: baseCaptionSha,
  }), false);
  assert.equal(isVerifiedPostizPhotoPublication(lane, {
    ...receipt,
    caption_with_cta_sha256: undefined,
    provider_content_sha256: baseCaptionSha,
  }), false);
});

test("production TikTok runner records Postiz-only evidence and does not resend publication or liveness", async () => {
  const value = enTikTokFixture();
  const providerCallsMade = [];
  const telegramCalls = [];
  const now = () => "2026-10-07T11:16:00.000Z";
  const options = {
    env: value.env,
    objectStore: value.objectStore,
    now,
    runDistribution: async (input) => {
      providerCallsMade.push(input);
      return {
        state: "PUBLISHED",
        reconciled: true,
        post_id: "postiz-tiktok-photo-fixture",
        post_url: null,
        integration_id: EN_AFFIRMATION_TIKTOK_LANE.integrationId,
        content_sha256: sha256(fs.readFileSync(input.captionPath)),
        title: input.title,
        posting_method: "DIRECT_POST",
        release_id: "p_pub_url~v2.123",
      };
    },
    sendTelegram: async (...args) => {
      telegramCalls.push(args);
      return { ok: true, result: { message_id: 77 } };
    },
  };

  const first = await runAniccaCarouselCanary([
    "run-en-affirmation-tiktok-production",
    "--slot",
    "2026-10-07T11:15:00.000Z",
  ], options);
  const replay = await runAniccaCarouselCanary([
    "run-en-affirmation-tiktok-production",
    "--slot",
    "2026-10-07T11:15:00.000Z",
  ], options);

  assert.deepEqual(first.telegram, { created: true, held: false, message_id: 77 });
  assert.equal(first.publication.public_url, null);
  assert.match(telegramCalls[0][2], /Postiz API status: PUBLISHED/);
  assert.match(telegramCalls[0][2], /exact locally stored approved assets and caption matched/);
  assert.equal(replay.publication.created, false);
  assert.deepEqual(replay.telegram, { created: false, held: false, message_id: 77 });
  assert.equal(providerCallsMade.length, 1);
  assert.equal(telegramCalls.length, 1);
});

test("JA main TikTok production command selects the recovered Larry sunset lane", () => {
  assert.deepEqual(parseArgs(["run-ja-main-tiktok", "--slot", SLOT]), { command: "run-ja-main-tiktok", slot: SLOT });
  assert.deepEqual(parseArgs(["run-ja-main-tiktok-production"]), { command: "run-ja-main-tiktok-production", slot: null });
  assert.equal(JA_MAIN_TIKTOK_RUNNER_LANE, JA_MAIN_TIKTOK_LANE);
  assert.equal(JA_MAIN_TIKTOK_RUNNER_LANE.accountId, "@anicca.jp");
  assert.equal(JA_MAIN_TIKTOK_RUNNER_LANE.integrationId, "cmp9sdev5012voh0y58qs45xc");
  assert.equal(JA_MAIN_TIKTOK_RUNNER_LANE.renderer, "larry");
});

test("JA jp1 production controls keep the Postiz alias separate from its native handle", () => {
  assert.equal(JA_JP1_TIKTOK_LANE.manifestProfile, "@anicca.jpx");
  assert.equal(JA_JP1_TIKTOK_LANE.accountId, "@anicca.jp1");
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-jp1-production-controls-"));
  const target = {
    integration_id: JA_JP1_TIKTOK_LANE.integrationId,
    tenant_id: "dais-local",
    product_id: "anicca",
    locale: "ja",
    platform: "tiktok",
    account: JA_JP1_TIKTOK_LANE.manifestAccount,
    profile: JA_JP1_TIKTOK_LANE.manifestProfile,
    provider: "postiz",
    disabled: false,
    verified: true,
    owner: "life-manager",
    disposition: "target",
    renderer: "larry",
    format: "larry",
    approved_pack: JA_JP1_TIKTOK_LANE.approvedPackName,
    canary_state: "verified",
    target_daily_limit: 3,
    lane_state: "production-armed",
    production_armed: true,
  };
  const hold = {
    integration_id: "control-test-hold",
    platform: "x",
    account: "@control-test-hold",
    provider: "postiz",
    provider_disabled: false,
    owner: "life-manager",
    disposition: "hold",
    target_daily_limit: 0,
    verified: true,
  };
  const manifest = createMarketingLaneManifest({
    tenant_id: "dais-local",
    integrations: [target],
    holds: [hold],
  }, { tenantId: "dais-local", assignments: [target] });
  fs.mkdirSync(path.join(dataDir, "marketing"), { recursive: true, mode: 0o700 });
  fs.writeFileSync(path.join(dataDir, "marketing", "lane-manifest.json"), `${JSON.stringify(manifest)}\n`);
  fs.writeFileSync(path.join(dataDir, "marketing", "publication-effect-fence.json"), JSON.stringify({ state: "closed" }));
  assert.doesNotThrow(() => assertProductionControls({ dataDir }, JA_JP1_TIKTOK_LANE));
});

test("EN affirmation accepts an alternate gate-approved pack when its per-job approval matches", async () => {
  const value = enFixture();
  const sourceDir = path.join(os.homedir(), ".local", "state", "life-manager", "objects", "sha256");
  const alternatePack = JSON.parse(fs.readFileSync(path.join(sourceDir, EN_PACK_REF.slice(-64)), "utf8"));
  alternatePack.variant = "en-affirmation-alternate";
  const alternatePackPath = path.join(value.dataDir, "alternate-pack.json");
  fs.writeFileSync(alternatePackPath, JSON.stringify(alternatePack));
  const alternatePackRef = importContentObject(alternatePackPath, { objectDir: path.join(value.dataDir, "objects") }).ref;
  const alternateApproval = JSON.parse(fs.readFileSync(path.join(sourceDir, EN_APPROVAL_REF.slice(-64)), "utf8"));
  alternateApproval.pack_ref = alternatePackRef;
  const alternateApprovalPath = path.join(value.dataDir, "alternate-approval.json");
  fs.writeFileSync(alternateApprovalPath, JSON.stringify(alternateApproval));
  const alternateApprovalRef = importContentObject(alternateApprovalPath, { objectDir: path.join(value.dataDir, "objects") }).ref;
  value.env[EN_RUNNER_LANE.packEnv] = alternatePackRef;
  value.env[EN_RUNNER_LANE.approvalEnv] = alternateApprovalRef;
  let secrets = 0;
  const publicationCalls = [];
  const result = await runAniccaEnAffirmationInstagramCanary(["run-en-affirmation", "--slot", SLOT], {
    env: value.env,
    objectStore: value.objectStore,
    secretProvider: { get: async () => { secrets += 1; return "secret"; } },
    runDistribution: providerCalls(publicationCalls, { post_url: "https://www.instagram.com/p/AlternateCanary/" }),
  });
  assert.equal(secrets, 1);
  assert.equal(publicationCalls.length, 1);
  assert.equal(result.publication.created, true);
  assert.deepEqual(result.telegram, { created: false, held: true, message_id: null });
});

test("EN affirmation publishes a direct /p/ once, holds then releases native-owner Telegram, and replays zero", async () => {
  const value = enFixture();
  const publicationCalls = [];
  const telegramCalls = [];
  const options = {
    env: value.env,
    objectStore: value.objectStore,
    runDistribution: providerCalls(publicationCalls),
    sendTelegram: async (...args) => { telegramCalls.push(args); return { ok: true, result: { message_id: 42 } }; },
    now: () => "2026-08-26T07:31:00.000Z",
  };
  const first = await runAniccaEnAffirmationInstagramCanary(["run-en-affirmation", "--slot", SLOT], options);
  assert.deepEqual(fs.readFileSync(path.join(value.dataDir, "marketing", "lane-manifest.json")), value.controlBytes.manifest);
  assert.deepEqual(fs.readFileSync(path.join(value.dataDir, "marketing", "publication-effect-fence.json")), value.controlBytes.fence);
  const publicationReceipt = JSON.parse(fs.readFileSync(path.join(value.dataDir, "marketing", "receipts.jsonl"), "utf8")).receipt;
  value.env[EN_RUNNER_LANE.verificationEnv] = enVerification(value, publicationReceipt);
  const replayOptions = { ...options, now: () => "2026-08-26T08:01:00.000Z" };
  const second = await runAniccaEnAffirmationInstagramCanary(["run-en-affirmation", "--slot", SLOT], replayOptions);
  const third = await runAniccaEnAffirmationInstagramCanary(["run-en-affirmation", "--slot", SLOT], replayOptions);
  assert.equal(first.publication.public_url.startsWith("https://www.instagram.com/p/"), true);
  assert.equal(first.telegram.held, true);
  assert.deepEqual(second.telegram, { created: true, held: false, message_id: 42 });
  assert.deepEqual(third.telegram, { created: false, held: false, message_id: 42 });
  assert.equal(publicationCalls.length, 1);
  assert.equal(telegramCalls.length, 1);
  assert.match(telegramCalls[0][2], /@anicca\.ios/);
  assert.doesNotMatch(telegramCalls[0][2], /@anicca\.affirmation/);
});

test("EN affirmation restores the exact closed controls when the provider effect is unknown", async () => {
  const value = enFixture();
  await assert.rejects(runAniccaEnAffirmationInstagramCanary(["run-en-affirmation", "--slot", SLOT], {
    env: value.env,
    objectStore: value.objectStore,
    runDistribution: async () => { throw new Error("response lost"); },
    now: () => "2026-08-26T07:31:00.000Z",
  }), /receipt is unavailable|response lost|unknown|provider/i);
  assert.deepEqual(fs.readFileSync(path.join(value.dataDir, "marketing", "lane-manifest.json")), value.controlBytes.manifest);
  assert.deepEqual(fs.readFileSync(path.join(value.dataDir, "marketing", "publication-effect-fence.json")), value.controlBytes.fence);
});
