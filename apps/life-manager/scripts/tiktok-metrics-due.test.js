"use strict";
const assert = require("node:assert/strict"); const fs = require("node:fs"); const os = require("node:os"); const path = require("node:path"); const test = require("node:test");
const crypto = require("node:crypto");
const { TARGETS, discoverTarget, discoverTargets, runDue } = require("./tiktok-metrics-due.js");
const { JA_JP1_TIKTOK_LANE, verifyMarketingNativeCarouselPublicationReceipt } = require("../lib/marketing-native-carousel-publication-adapter.js");
const EXPECTED = { tenant_id: "dais-local", product_id: "anicca-ios", locale: "ja", account_id: "@anicca.jp4", native_owner: "anicca.jp4", integration_id: "cmn8x8hdv028uqx0y4gdfse5t", provider_post_id: "cmt328uot00s2qk0y23e8ptii", shortcode: "7676495865816632583", video_id: "7676495865816632583", public_url: "https://www.tiktok.com/@anicca.jp4/video/7676495865816632583", caption: "今すぐやれ", published_at: "2026-08-21T14:46:13.240Z" };

test("JP4 due loop reports delayed and daily once while true 24h stays pending", async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-jp4-due-")); let sends = 0; const env = { LM_DATA_DIR: dataDir, LM_TELEGRAM_BOT_TOKEN: "fake", LM_TELEGRAM_ALERT_CHAT_ID: "fake" };
  const originalFetch = global.fetch; global.fetch = async () => ({ ok: true, json: async () => ({ ok: true, result: { message_id: ++sends } }) });
  try { const now = Date.parse(EXPECTED.published_at) + 18.5 * 3600_000; const first = await runDue(now, env, [EXPECTED]); assert.equal(first.find((row) => row.window === "2h").state, "source_delayed"); assert.equal(first.find((row) => row.window === "24h").state, "pending"); assert.equal(first.find((row) => row.window === "daily").state, "reported"); assert.equal(sends, 2); const replay = await runDue(now, env, [EXPECTED]); assert.equal(replay.find((row) => row.window === "2h").state, "complete"); assert.equal(replay.find((row) => row.window === "daily").state, "complete"); assert.equal(sends, 2); } finally { global.fetch = originalFetch; }
});

test("discovery keeps verified Honne EN and JA relationship-confession lanes isolated", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-honne-en-due-")); const caption = "I still think about you";
  const captionPath = path.join(dataDir, "objects", "caption"); fs.mkdirSync(path.dirname(captionPath), { recursive: true }); fs.writeFileSync(captionPath, caption);
  const sha = crypto.createHash("sha256").update(caption).digest("hex"); const directory = path.join(dataDir, "tenants/dais-local/marketing/video-publication/honne-ai"); fs.mkdirSync(directory, { recursive: true });
  const valid = { ts: "2026-08-21T09:48:55.372Z", platform: "tiktok", status: "published", provider_reconciled: true, format_id: "reelclaw", form: "relationship-confession", locale: "en", public_url: "https://www.tiktok.com/@honne_reveal/video/7676419421304425748", provider_id: "cmt2rn5b302jdph0ylu324jb3", caption_path: captionPath, caption_sha256: sha };
  const ja = { ...valid, locale: "ja", public_url: "https://www.tiktok.com/@honnevideo/video/7676425660641889537", provider_id: "cmt2siqgp0009nt0yoi1qz7lf" };
  fs.writeFileSync(path.join(directory, "distribution.jsonl"), `${JSON.stringify({ ...valid, form: "relationship-intent", public_url: "https://www.tiktok.com/@honne_reveal/video/1" })}\n${JSON.stringify(valid)}\n${JSON.stringify(ja)}\n`);
  const found = discoverTargets(dataDir); assert.deepEqual(found.map((row) => [row.account_id, row.locale, row.video_id]), [["@honne_reveal", "en", "7676419421304425748"], ["@honnevideo", "ja", "7676425660641889537"]]); assert.equal(found[0].caption, caption);
});

test("discovery keeps Anicca main and JP4 identities separate", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-anicca-main-due-")); const caption = "強い人の口癖、5つだけ"; const captionPath = path.join(dataDir, "objects", "caption"); fs.mkdirSync(path.dirname(captionPath), { recursive: true }); fs.writeFileSync(captionPath, caption); const sha = crypto.createHash("sha256").update(caption).digest("hex");
  const directory = path.join(dataDir, "tenants/dais-local/marketing/video-publication/anicca-ios"); fs.mkdirSync(directory, { recursive: true }); const base = { ts: "2026-08-21T10:10:15.268Z", platform: "tiktok", status: "published", provider_reconciled: true, format_id: "reelclaw-card", form: "nudge-card", locale: "ja", provider_id: "cmt2s158o02kyph0yvht8d8wd", caption_path: captionPath, caption_sha256: sha };
  fs.writeFileSync(path.join(directory, "distribution.jsonl"), `${JSON.stringify({ ...base, public_url: "https://www.tiktok.com/@anicca.jp/video/7676422253638176020" })}\n`);
  const [found] = discoverTargets(dataDir); assert.equal(found.account_id, "@anicca.jp"); assert.equal(found.native_owner, "anicca.jp"); assert.equal(found.integration_id, "cmp9sdev5012voh0y58qs45xc");
});

test("discovery attributes a reused provider row and native URL only to its first video lineage", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-jp4-collision-due-"));
  const directory = path.join(dataDir, "tenants/dais-local/marketing/video-publication/anicca-ios");
  const objects = path.join(dataDir, "objects/sha256"); fs.mkdirSync(directory, { recursive: true }); fs.mkdirSync(objects, { recursive: true });
  const captions = ["first caption", "second caption"];
  const rows = captions.map((caption, index) => {
    const captionSha = crypto.createHash("sha256").update(caption).digest("hex"); fs.writeFileSync(path.join(objects, captionSha), caption);
    return { ts: `2026-08-23T0${6 + index}:19:03.000Z`, platform: "tiktok", status: "published", provider_reconciled: true,
      creative_id: `JP4-${index}`, video_sha256: `${index + 1}`.repeat(64), caption_path: path.join(objects, captionSha), caption_sha256: captionSha,
      provider_id: "cmt5exlqb00cjqk0yu6q2xftc", public_url: "https://www.tiktok.com/@anicca.jp4/video/7677106804039355656",
      format_id: "reelclaw-card", form: "nudge-card", locale: "ja" };
  });
  fs.writeFileSync(path.join(directory, "distribution.jsonl"), `${rows.map(JSON.stringify).join("\n")}\n`);
  const found = discoverTarget(dataDir, TARGETS[0]);
  assert.equal(found.length, 1);
  assert.equal(found[0].caption, "first caption");
});

test("HE discovery uses only its exact reconciled durable receipt fallback", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-anicca-he-due-")); const caption = "今すぐやれ\n\n完璧より完了。"; const sha = crypto.createHash("sha256").update(caption).digest("hex"); const object = path.join(dataDir, "objects/sha256", sha); fs.mkdirSync(path.dirname(object), { recursive: true }); fs.writeFileSync(object, caption); const receipts = path.join(dataDir, "marketing/receipts.jsonl"); fs.mkdirSync(path.dirname(receipts), { recursive: true }); fs.writeFileSync(receipts, `${JSON.stringify({ job_id: "wrong", receipt: { public_url: "https://www.tiktok.com/@anicca.he/video/1" } })}\n${JSON.stringify({ job_id: "marketing-video-publication:7732e4c1e7ff88ccad12a0295e6740125f58da2d6e07558e6f9e432bf85349dd", receipt: { status: "published", product_id: "anicca-ios", format_id: "reelclaw-card", form: "nudge-card", locale: "ja", platform: "tiktok", provider_reconciled: true, public_url: "https://www.tiktok.com/@anicca.he/video/7676500512308481296", provider_post_id: "cmt32u9dj00jxqp0yqdh6yi96", caption_sha256: sha, published_at: "2026-08-21T15:02:41.000Z" } })}\n`); const target = TARGETS.find((row) => row.account_id === "@anicca.he"); const [found] = discoverTarget(dataDir, target); assert.equal(found.account_id, "@anicca.he"); assert.equal(found.provider_post_id, "cmt32u9dj00jxqp0yqdh6yi96"); assert.equal(found.caption, caption);
});

test("discovery includes exact published JP1 native-carousel receipt for Postiz-only metrics", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-jp1-carousel-metrics-"));
  const lane = JA_JP1_TIKTOK_LANE;
  const caption = "毎日届く言葉で心を軽くする";
  const captionSha = crypto.createHash("sha256").update(caption).digest("hex");
  const objectDir = path.join(dataDir, "objects", "sha256");
  fs.mkdirSync(objectDir, { recursive: true });
  fs.writeFileSync(path.join(objectDir, captionSha), caption, { mode: 0o600 });
  const mediaSha = lane.mediaRefs.map((ref) => ref.slice(-64));
  const captionWithCtaSha = crypto.createHash("sha256").update(`${caption}\nApp Store`).digest("hex");
  const receipt = {
    schema_version: 1,
    kind: "marketing_native_carousel_distribution",
    status: "published",
    product_id: lane.productId,
    format_id: lane.formatId,
    form: lane.form,
    locale: lane.locale,
    platform: lane.platform,
    account_id: lane.accountId,
    integration_ref: lane.integrationRef,
    creative_id: lane.creativeId,
    pack_sha256: lane.packRef.slice(-64),
    media_sha256: mediaSha,
    media_order_sha256: crypto.createHash("sha256").update(JSON.stringify(mediaSha)).digest("hex"),
    caption_sha256: captionSha,
    caption_with_cta_sha256: captionWithCtaSha,
    provider_post_id: "postiz-jp1-carousel-1",
    provider_reconciled: true,
    public_url: null,
    published_at: "2026-10-11T06:30:00.000Z",
    provider_state: "PUBLISHED",
    provider_integration_id: lane.integrationId,
    provider_content_sha256: captionWithCtaSha,
    provider_title: lane.title || "JP1 carousel",
    provider_posting_method: "DIRECT_POST",
    provider_release_id: "p_pub_url~v2.7678198747632977937",
  };
  assert.equal(verifyMarketingNativeCarouselPublicationReceipt(receipt), true);
  const ledger = path.join(dataDir, "tenants/dais-local/marketing/native-carousel-publication/anicca-ios/distribution.jsonl");
  fs.mkdirSync(path.dirname(ledger), { recursive: true });
  const staleUnreconciled = { ...receipt, provider_post_id: "old-unreconciled-carousel", published_at: "2026-09-01T06:30:00.000Z", provider_reconciled: false };
  fs.writeFileSync(ledger, `${[
    { effect_key: "exact", job_id: "jp1-slot", receipt },
    { effect_key: "stale", job_id: "jp1-stale", receipt: staleUnreconciled },
  ].map(JSON.stringify).join("\n")}\n`);

  const found = discoverTargets(dataDir, Date.parse("2026-10-11T07:00:00.000Z"))
    .filter((row) => row.provider_post_id === receipt.provider_post_id);
  assert.deepEqual(found.map((row) => ({
    account_id: row.account_id,
    integration_id: row.integration_id,
    provider_post_id: row.provider_post_id,
    public_url: row.public_url,
    postiz_photo_only: row.postiz_photo_only,
  })), [{
    account_id: "@anicca.jp1",
    integration_id: lane.integrationId,
    provider_post_id: "postiz-jp1-carousel-1",
    public_url: "unavailable",
    postiz_photo_only: true,
  }]);
});

test("Postiz-only carousel metrics stay pending when the API has not populated post analytics", async (t) => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-tiktok-postiz-delay-"));
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  const expected = {
    ...EXPECTED,
    account_id: "@anicca.jp1",
    native_owner: "anicca.jp1",
    integration_id: "cmlrv8jq000hun60yy57eaptx",
    provider_post_id: "postiz-jp1-carousel-delay",
    shortcode: "postiz-jp1-carousel-delay",
    video_id: "postiz-jp1-carousel-delay",
    public_url: "unavailable",
    published_at: "2026-10-10T21:30:00.000Z",
    postiz_photo_only: true,
  };
  const accountRows = [
    ["Followers", 10], ["Following", 5], ["Total Likes", 20], ["Videos", 12],
    ["Views", 100], ["Recent Likes", 4], ["Recent Comments", 1], ["Recent Shares", 2],
  ].map(([label, total]) => ({ label, data: [{ total }] }));
  const originalFetch = global.fetch;
  global.fetch = async (url) => ({
    ok: true,
    json: async () => String(url).includes("/analytics/post/")
      ? []
      : String(url).includes("/analytics/")
        ? accountRows
        : { ok: true, result: { message_id: 1 } },
  });
  try {
    const now = Date.parse("2026-10-10T23:45:00.000Z"); // 08:45 JST, within the 2h window's grace.
    const result = await runDue(now, {
      LM_DATA_DIR: dataDir,
      LM_POSTIZ_API_KEY: "test-only",
      LM_TELEGRAM_BOT_TOKEN: "fake",
      LM_TELEGRAM_ALERT_CHAT_ID: "fake",
    }, [expected]);
    const twoHour = result.find((row) => row.window === "2h");
    assert.equal(twoHour.state, "pending");
    assert.equal(twoHour.reason, "postiz_post_analytics_empty");
    assert.equal(fs.existsSync(path.join(dataDir, "tenants", expected.tenant_id, "marketing", "metrics", expected.native_owner, expected.shortcode, "2h.combined.json")), false);
  } finally {
    global.fetch = originalFetch;
  }
});
