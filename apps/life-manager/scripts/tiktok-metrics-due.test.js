"use strict";
const assert = require("node:assert/strict"); const fs = require("node:fs"); const os = require("node:os"); const path = require("node:path"); const test = require("node:test");
const crypto = require("node:crypto");
const { TARGETS, discoverTarget, discoverTargets, runDue, runNativeDue, snapshotFile } = require("./tiktok-metrics-due.js");
const { postizAnalytics } = require("./tiktok-native-metrics-read.js");
const { JA_JP1_TIKTOK_LANE, verifyMarketingNativeCarouselPublicationReceipt } = require("../lib/marketing-native-carousel-publication-adapter.js");
const EXPECTED = { tenant_id: "dais-local", product_id: "anicca-ios", locale: "ja", account_id: "@anicca.jp4", native_owner: "anicca.jp4", integration_id: "cmn8x8hdv028uqx0y4gdfse5t", provider_post_id: "cmt328uot00s2qk0y23e8ptii", shortcode: "7676495865816632583", video_id: "7676495865816632583", public_url: "https://www.tiktok.com/@anicca.jp4/video/7676495865816632583", caption: "今すぐやれ", published_at: "2026-08-21T14:46:13.240Z" };

test("TikTok due runner leaves no snapshot when the local Telegram credential is unavailable", async (t) => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-tiktok-no-telegram-"));
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "lm-tiktok-no-credentials-"));
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  t.after(() => fs.rmSync(home, { recursive: true, force: true }));
  const expected = { ...EXPECTED, published_at: "2026-10-14T22:00:00.000Z" };
  const nowMs = Date.parse(expected.published_at) + 2 * 3600_000;
  const results = await runDue(nowMs, { HOME: home, LM_DATA_DIR: dataDir }, [expected]);
  const checkpoint = results.find((row) => row.video_id === expected.video_id && row.window === "2h");
  assert.equal(checkpoint.state, "source_unavailable");
  assert.match(checkpoint.error, /local_telegram_credential_unavailable/);
  assert.equal(fs.existsSync(snapshotFile(dataDir, expected, "2h")), false);
});

test("photo API metrics run before a due native video's failed browser acquisition", async (t) => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-tiktok-api-before-browser-"));
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  const guard = path.join(dataDir, "guard");
  const marker = path.join(dataDir, "guard-called");
  const credentials = path.join(dataDir, ".local/share/anicca/credentials.json");
  fs.mkdirSync(path.dirname(credentials), { recursive: true });
  fs.writeFileSync(credentials, JSON.stringify({ credentials: [
    { service: "telegram-life-manager", bot_token: "test-only-token", chat_id: "test-only-chat" },
  ] }), { mode: 0o600 });
  fs.writeFileSync(guard, '#!/bin/bash\nprintf "%s\\n" "$2" >> "$TEST_BROWSER_MARKER"\nexit 10\n', { mode: 0o700 });
  const native = { ...EXPECTED, published_at: "2026-10-23T00:00:00.000Z" };
  const photo = { ...native, provider_post_id: "photo-post", video_id: "photo-post", shortcode: "photo-post", postiz_photo_only: true, public_url: "unavailable" };
  let apiBeforeBrowser = false;
  const originalFetch = global.fetch;
  global.fetch = async (url) => {
    if (String(url).includes("api.postiz.com")) {
      apiBeforeBrowser = !fs.existsSync(marker);
      return { ok: true, json: async () => [] };
    }
    throw new Error("unexpected external request");
  };
  t.after(() => { global.fetch = originalFetch; });
  const env = {
    ...process.env, LM_DATA_DIR: dataDir, HOME: dataDir, LM_POSTIZ_API_KEY: "test-only",
    LM_TELEGRAM_BOT_TOKEN: "fake", LM_TELEGRAM_ALERT_CHAT_ID: "fake",
    AI_BROWSER_GUARD: guard, AI_ENSURE_PROVISION_BROWSER: guard, AI_ENSURE_BROWSER: guard,
    BROWSER_WAIT_SECONDS: "0", TEST_BROWSER_MARKER: marker,
  };
  const results = await runDue(Date.parse("2026-10-23T02:00:00.000Z"), env, [native, photo], "api");
  assert.equal(apiBeforeBrowser, true);
  assert.equal(fs.existsSync(marker), false);
  assert.equal(results.find((row) => row.video_id === photo.video_id && row.window === "2h").state, "pending");
  const nativeResults = await runNativeDue(Date.parse("2026-10-23T02:00:00.000Z"), env, [native, photo]);
  assert.equal(fs.existsSync(marker), true, "a due native video must acquire its browser identity");
  assert.match(fs.readFileSync(marker, "utf8"), /^tiktok-anicca-jp\n/);
  const unavailable = nativeResults.find((row) => row.video_id === native.video_id && row.window === "2h");
  assert.equal(unavailable.state, "source_unavailable");
  assert.match(unavailable.error, /unreachable/);
  assert.equal(fs.existsSync(snapshotFile(dataDir, native, "2h")), false);
  const calls = fs.readFileSync(marker, "utf8");
  for (const now of ["2026-10-23T01:00:00.000Z", "2026-10-23T04:00:00.000Z"]) {
    assert.deepEqual(await runNativeDue(Date.parse(now), env, [native]), []);
    assert.equal(fs.readFileSync(marker, "utf8"), calls);
  }
  const existing = snapshotFile(dataDir, native, "2h");
  fs.mkdirSync(path.dirname(existing), { recursive: true });
  fs.writeFileSync(existing, "{}");
  assert.deepEqual(await runNativeDue(Date.parse("2026-10-23T02:00:00.000Z"), env, [native]), []);
  assert.equal(fs.readFileSync(marker, "utf8"), calls);
});

test("native batch uses the leased endpoint and releases the lease outside its work timeout", async (t) => {
  const home = fs.mkdtempSync(path.join(os.tmpdir(), "lm-tiktok-guarded-window-"));
  t.after(() => fs.rmSync(home, { recursive: true, force: true }));
  const guard = path.join(home, "guard");
  const node = path.join(home, "native-reader-boundary");
  const seen = path.join(home, "seen.json");
  const released = path.join(home, "released");
  const credentials = path.join(home, ".local/share/anicca/credentials.json");
  fs.mkdirSync(path.dirname(credentials), { recursive: true });
  fs.writeFileSync(credentials, JSON.stringify({ credentials: [
    { service: "telegram-life-manager", bot_token: "test-only-token", chat_id: "test-only-chat" },
  ] }), { mode: 0o600 });
  fs.writeFileSync(guard, '#!/bin/bash\ncase "$1" in\nacquire) printf "http://127.0.0.1:13377\\n";;\nrelease) touch "$TEST_RELEASED";;\n*) exit 64;;\nesac\n', { mode: 0o700 });
  fs.writeFileSync(node, `#!/bin/bash
"$TEST_REAL_NODE" - "$@" <<'JS'
const fs = require("node:fs");
const [reader, phase] = process.argv.slice(2);
fs.writeFileSync(process.env.TEST_SEEN, JSON.stringify({ reader, phase, endpoint: process.env.LM_CDP_ENDPOINT }));
process.stdout.write(JSON.stringify([{ video_id: "7676495865816632583", window: "2h", state: "measured" }]));
JS
`, { mode: 0o700 });
  const observation = await runNativeDue(Date.parse("2026-10-23T02:00:00.000Z"), {
    ...process.env, HOME: home, LM_NODE: node, AI_BROWSER_GUARD: guard,
    LM_CDP_ENDPOINT: "http://127.0.0.1:19999", TEST_REAL_NODE: process.execPath,
    TEST_SEEN: seen, TEST_RELEASED: released,
  }, [{ ...EXPECTED, published_at: "2026-10-23T00:00:00.000Z" }]);
  const call = JSON.parse(fs.readFileSync(seen, "utf8"));
  assert.equal(call.endpoint, "http://127.0.0.1:13377");
  assert.equal(call.phase, "--native-leased");
  assert.match(call.reader, /tiktok-metrics-due\.js$/);
  assert.deepEqual(observation, [{ video_id: "7676495865816632583", window: "2h", state: "measured" }]);
  assert.equal(fs.existsSync(released), true);
});

test("missed TikTok windows and per-post daily snapshots stay local while true 24h stays pending", async (t) => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-jp4-due-")); t.after(() => fs.rmSync(dataDir, { recursive: true, force: true })); let sends = 0; const env = { LM_DATA_DIR: dataDir, LM_TELEGRAM_BOT_TOKEN: "fake", LM_TELEGRAM_ALERT_CHAT_ID: "fake" };
  const originalFetch = global.fetch; global.fetch = async () => ({ ok: true, json: async () => ({ ok: true, result: { message_id: ++sends } }) });
  try { const now = Date.parse(EXPECTED.published_at) + 18.5 * 3600_000; const first = await runDue(now, env, [EXPECTED]); assert.equal(sends, 0); assert.equal(first.find((row) => row.window === "2h").state, "checkpoint_missed"); assert.equal(first.find((row) => row.window === "24h").state, "pending"); assert.equal(first.find((row) => row.window === "daily").state, "persisted"); const replay = await runDue(now, env, [EXPECTED]); assert.equal(replay.find((row) => row.window === "2h").state, "checkpoint_missed"); assert.equal(replay.find((row) => row.window === "daily").state, "complete"); assert.equal(sends, 0); } finally { global.fetch = originalFetch; }
});

test("TikTok metrics ignore publications older than the existing 30-day retention window", async (t) => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-tiktok-metrics-age-")); t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  const old = { ...EXPECTED, published_at: "2026-08-01T00:00:00.000Z" };
  const result = await runDue(Date.parse("2026-10-12T00:00:00.000Z"), { LM_DATA_DIR: dataDir }, [old]);
  assert.deepEqual(result, []);
  assert.equal(fs.existsSync(path.join(dataDir, "tenants", old.tenant_id, "marketing", "metrics")), false);
});

test("Postiz analytics uses the day range for each TikTok metric checkpoint", async () => {
  const originalFetch = global.fetch; const requested = [];
  global.fetch = async (url) => { requested.push(new URL(url).searchParams.get("date")); return { ok: true, json: async () => [] }; };
  try {
    for (const [window, days] of [["2h", "1"], ["24h", "1"], ["72h", "3"], ["7d", "7"]]) {
      requested.length = 0;
      await postizAnalytics({ integrationId: "integration-id", providerPostId: "post-id", window }, { LM_POSTIZ_API_KEY: "test-only" });
      assert.deepEqual(requested, [days, days]);
    }
  } finally { global.fetch = originalFetch; }
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
  const directory = path.join(dataDir, "tenants/dais-local/marketing/video-publication/anicca-ios"); fs.mkdirSync(directory, { recursive: true }); const base = { ts: "2026-08-21T10:10:15.268Z", platform: "tiktok", status: "published", provider_reconciled: true, format_id: "reelclaw-card", form: "nudge-card", locale: "ja", creative_id: "ANI-JA-QUOTE-1", provider_id: "cmt2s158o02kyph0yvht8d8wd", caption_path: captionPath, caption_sha256: sha };
  fs.writeFileSync(path.join(directory, "distribution.jsonl"), `${JSON.stringify({ ...base, public_url: "https://www.tiktok.com/@anicca.jp/video/7676422253638176020" })}\n`);
  const [found] = discoverTargets(dataDir); assert.equal(found.account_id, "@anicca.jp"); assert.equal(found.native_owner, "anicca.jp"); assert.equal(found.integration_id, "cmp9sdev5012voh0y58qs45xc"); assert.equal(found.format_id, "reelclaw-card"); assert.equal(found.form, "nudge-card"); assert.equal(found.creative_id, "ANI-JA-QUOTE-1");
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
  assert.equal(found[0].creative_id, "JP4-0");
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
    format_id: row.format_id,
    form: row.form,
    creative_id: row.creative_id,
    public_url: row.public_url,
    postiz_photo_only: row.postiz_photo_only,
  })), [{
    account_id: "@anicca.jp1",
    integration_id: lane.integrationId,
    provider_post_id: "postiz-jp1-carousel-1",
    format_id: lane.formatId,
    form: lane.form,
    creative_id: receipt.creative_id,
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

test("Postiz carousel metrics use the exact published permalink in the snapshot and Telegram report", async (t) => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-tiktok-photo-permalink-"));
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  const home = path.join(dataDir, "test-home");
  const credentialsFile = path.join(home, ".local", "share", "anicca", "credentials.json");
  fs.mkdirSync(path.dirname(credentialsFile), { recursive: true });
  fs.writeFileSync(credentialsFile, JSON.stringify({ credentials: [
    { service: "telegram-life-manager", bot_token: "local-token-fixture", chat_id: "local-chat-fixture" },
  ] }));
  const photoUrl = "https://www.tiktok.com/@anicca.jpx/photo/7695154487559851270";
  const expected = {
    ...EXPECTED,
    account_id: "@anicca.jp1",
    native_owner: "anicca.jp1",
    integration_id: "cmlrv8jq000hun60yy57eaptx",
    provider_post_id: "cmv2wroi617qzmq0yrxabocjm",
    shortcode: "cmv2wroi617qzmq0yrxabocjm",
    video_id: "cmv2wroi617qzmq0yrxabocjm",
    public_url: "unavailable",
    published_at: "2026-10-10T21:30:00.000Z",
    postiz_photo_only: true,
  };
  const accountRows = [
    ["Followers", 10], ["Following", 5], ["Total Likes", 20], ["Videos", 12],
    ["Views", 100], ["Recent Likes", 4], ["Recent Comments", 1], ["Recent Shares", 2],
  ].map(([label, total]) => ({ label, data: [{ total }] }));
  const postRows = [{ label: "Views", data: [{ total: 45 }] }, { label: "Likes", data: [{ total: 3 }] }];
  let listedPosts = [
    { id: "different-post", state: "PUBLISHED", integration: { id: expected.integration_id }, releaseURL: "https://www.tiktok.com/@anicca.jpx/photo/1" },
    { id: expected.provider_post_id, state: "PUBLISHED", integration: { id: "wrong-integration" }, releaseURL: "https://www.tiktok.com/@wrong/photo/2" },
    { id: expected.provider_post_id, state: "QUEUED", integration: { id: expected.integration_id }, releaseURL: "https://www.tiktok.com/@anicca.jpx/photo/3" },
    { id: expected.provider_post_id, state: "PUBLISHED", integration: { id: expected.integration_id }, releaseURL: photoUrl },
    ...Array.from({ length: 100 }, (_, i) => ({ id: `unrelated-${i}`, state: "PUBLISHED", integration: { id: "another-integration" }, releaseURL: `https://www.tiktok.com/@other/photo/${i}` })),
  ];
  const originalFetch = global.fetch;
  let telegramText = "";
  let telegramBotUrl = "";
  global.fetch = async (url, init = {}) => {
    const address = String(url);
    if (address.includes("/analytics/post/")) return { ok: true, json: async () => postRows };
    if (address.includes("/analytics/")) return { ok: true, json: async () => accountRows };
    if (address.includes("/posts?")) return { ok: true, json: async () => listedPosts };
    if (address.includes("api.telegram.org") && address.includes("/sendMessage")) {
      telegramBotUrl = address;
      telegramText = JSON.parse(init.body).text;
      return { ok: true, json: async () => ({ ok: true, result: { message_id: 2 } }) };
    }
    throw new Error(`unexpected request: ${address}`);
  };
  try {
    const now = Date.parse("2026-10-10T23:45:00.000Z");
    const result = await runDue(now, {
      HOME: home,
      LM_DATA_DIR: dataDir,
      LM_POSTIZ_API_KEY: "test-only",
      LM_TELEGRAM_BOT_TOKEN: "cloud-token-fixture",
      LM_TELEGRAM_ALERT_CHAT_ID: "cloud-chat-fixture",
    }, [expected]);
    const twoHour = result.find((row) => row.window === "2h");
    assert.equal(twoHour.state, "measured");
    const snapshot = JSON.parse(fs.readFileSync(path.join(dataDir, "tenants", expected.tenant_id, "marketing", "metrics", expected.native_owner, expected.shortcode, "2h.combined.json"), "utf8"));
    assert.equal(snapshot.public_url, photoUrl);
    assert.match(telegramBotUrl, /local-token-fixture/);
    assert.equal(telegramBotUrl.includes("cloud-token-fixture"), false);
    assert.match(telegramText, new RegExp(photoUrl.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));

    const profileOnlyURL = "https://www.tiktok.com/@anicca_buddha";
    const profileExpected = {
      ...expected,
      account_id: "@anicca_buddha",
      native_owner: "anicca_buddha",
      integration_id: "cmp9txjdp01c8oh0yb6dhlarr",
      provider_post_id: "cmv2xvo4717ywqz0ynar3tp1r",
      shortcode: "cmv2xvo4717ywqz0ynar3tp1r",
      video_id: "cmv2xvo4717ywqz0ynar3tp1r",
    };
    listedPosts = [{ id: profileExpected.provider_post_id, state: "PUBLISHED", integration: { id: profileExpected.integration_id }, releaseURL: profileOnlyURL }];
    telegramText = "";
    await runDue(now, {
      HOME: home,
      LM_DATA_DIR: dataDir,
      LM_POSTIZ_API_KEY: "test-only",
      LM_TELEGRAM_BOT_TOKEN: "cloud-token-fixture",
      LM_TELEGRAM_ALERT_CHAT_ID: "cloud-chat-fixture",
    }, [profileExpected]);
    const profileSnapshot = JSON.parse(fs.readFileSync(path.join(dataDir, "tenants", profileExpected.tenant_id, "marketing", "metrics", profileExpected.native_owner, profileExpected.shortcode, "2h.combined.json"), "utf8"));
    assert.equal(profileSnapshot.public_url, "unavailable");
    assert.match(telegramText, /投稿リンクは取得できませんでした/);
    assert.equal(telegramText.includes(profileOnlyURL), false);
    assert.match(telegramBotUrl, /local-token-fixture/);
    assert.equal(telegramBotUrl.includes("cloud-token-fixture"), false);
  } finally {
    global.fetch = originalFetch;
  }
});

test("delayed Postiz photo metrics persist an exact permalink without a per-post Telegram send", async (t) => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-tiktok-photo-delayed-link-"));
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  const photoUrl = "https://www.tiktok.com/@anicca.jpx/photo/7695154487559851270";
  const expected = {
    ...EXPECTED,
    account_id: "@anicca.jp1",
    native_owner: "anicca.jp1",
    integration_id: "cmlrv8jq000hun60yy57eaptx",
    provider_post_id: "cmv2wroi617qzmq0yrxabocjm",
    shortcode: "cmv2wroi617qzmq0yrxabocjm",
    video_id: "cmv2wroi617qzmq0yrxabocjm",
    public_url: "unavailable",
    published_at: "2026-10-10T21:30:00.000Z",
    postiz_photo_only: true,
  };
  const originalFetch = global.fetch;
  let telegramText = "";
  global.fetch = async (url, init = {}) => {
    const address = String(url);
    if (address.includes("/posts?")) return { ok: true, json: async () => [{
      id: expected.provider_post_id,
      state: "PUBLISHED",
      integration: { id: expected.integration_id },
      releaseURL: photoUrl,
    }] };
    if (address.includes("api.telegram.org") && address.includes("/sendMessage")) {
      telegramText = JSON.parse(init.body).text;
      return { ok: true, json: async () => ({ ok: true, result: { message_id: 3 } }) };
    }
    throw new Error(`unexpected request: ${address}`);
  };
  try {
    const result = await runDue(Date.parse("2026-10-11T01:05:00.000Z"), {
      LM_DATA_DIR: dataDir,
      LM_POSTIZ_API_KEY: "test-only",
      LM_TELEGRAM_BOT_TOKEN: "fake",
      LM_TELEGRAM_ALERT_CHAT_ID: "fake",
    }, [expected]);
    const twoHour = result.find((row) => row.window === "2h");
    assert.equal(twoHour.state, "checkpoint_missed");
    const snapshot = JSON.parse(fs.readFileSync(path.join(dataDir, "tenants", expected.tenant_id, "marketing", "metrics", expected.native_owner, expected.shortcode, "2h.combined.json"), "utf8"));
    assert.equal(snapshot.public_url, photoUrl);
    assert.equal(snapshot.post.views.status, "unavailable");
    assert.equal(telegramText, "");
  } finally {
    global.fetch = originalFetch;
  }
});

test("daily metrics catch up the latest elapsed 22 JST report day across midnight without replay effects", async (t) => {
  const originalFetch = global.fetch;
  let notifications = 0;
  global.fetch = async (url) => {
    if (!String(url).startsWith("https://api.telegram.org/")) throw new Error(`unexpected network request in isolated metrics test: ${url}`);
    return { ok: true, json: async () => ({ ok: true, result: { message_id: ++notifications } }) };
  };
  t.after(() => { global.fetch = originalFetch; });
  for (const [observedAt, reportDay] of [
    ["2026-10-23T12:59:59.000Z", "2026-10-22"],
    ["2026-10-23T13:00:00.000Z", "2026-10-23"],
    ["2026-10-23T15:14:00.000Z", "2026-10-23"],
    ["2026-10-24T12:59:59.000Z", "2026-10-23"],
    ["2026-10-24T13:00:00.000Z", "2026-10-24"],
  ]) {
    await t.test(observedAt, async (t) => {
      const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-metrics-midnight-"));
      t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
      const attributionRoot = path.join(dataDir, "tenants/dais-local/marketing/attribution");
      const pointers = new Map();
      for (const day of ["2026-10-22", "2026-10-23", "2026-10-24"]) {
        for (const [relative, value] of [
          [`asc/${day}/acquisition.json`, { report_day: day, products: [], rows: [], snapshot_ref: `asc-${day}` }],
          [`revenuecat/${day}/subscriptions.json`, { report_day: day, products: [], snapshot_ref: `revenuecat-${day}` }],
          [`coverage/${day}/summary.json`, { kind: "marketing_product_metric_summary", product_id: "mobile-marketing", period: "daily", observed_at: `${day}T13:00:00.000Z`, report_key: `attribution-${day}`, source_refs: [], products: [], message: "Life Manager：fixture coverage unavailable" }],
        ]) {
          const file = path.join(attributionRoot, relative);
          fs.mkdirSync(path.dirname(file), { recursive: true });
          fs.writeFileSync(file, JSON.stringify(value));
          pointers.set(file, fs.readFileSync(file, "utf8"));
        }
      }
      const env = { LM_DATA_DIR: dataDir, LM_TELEGRAM_BOT_TOKEN: "fake", LM_TELEGRAM_ALERT_CHAT_ID: "fake" };
      const nowMs = Date.parse(observedAt);
      const api = await runDue(nowMs, env, null, "api");
      assert.equal(api.find((row) => row.window === "asc-daily")?.snapshot_ref, `asc-${reportDay}`);
      assert.equal(api.find((row) => row.window === "revenuecat-daily")?.snapshot_ref, `revenuecat-${reportDay}`);
      assert.equal(api.some((row) => row.window === "daily-product"), false);
      const final = await runDue(nowMs, env, null, "finalize");
      assert.deepEqual(final.filter((row) => row.window === "daily-product").map((row) => row.product_id), ["honne-ai", "anicca-ios"]);
      assert.equal(final.some((row) => row.window === "asc-daily"), false);
      for (const productId of ["honne-ai", "anicca-ios"]) {
        const directory = path.join(dataDir, "tenants/dais-local/marketing/metrics/summaries", productId, "daily");
        assert.deepEqual(fs.readdirSync(directory), [`${reportDay}.json`]);
        const file = path.join(directory, `${reportDay}.json`);
        assert.equal(JSON.parse(fs.readFileSync(file, "utf8")).observed_at, observedAt);
        pointers.set(file, fs.readFileSync(file, "utf8"));
      }
      const notificationsBeforeReplay = notifications;
      const replay = await runDue(nowMs, env, null, "api");
      assert.equal(replay.find((row) => row.window === "asc-daily").state, "complete");
      assert.equal(replay.find((row) => row.window === "revenuecat-daily").state, "complete");
      await runDue(nowMs, env, null, "finalize");
      assert.equal(notifications, notificationsBeforeReplay);
      for (const [file, bytes] of pointers) assert.equal(fs.readFileSync(file, "utf8"), bytes);
    });
  }
});

test("missing Honne weekly data stays unavailable and does not stop Anicca metrics", async (t) => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-metrics-product-isolation-"));
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  const reportDay = "2026-10-12";
  const attributionRoot = path.join(dataDir, "tenants/dais-local/marketing/attribution");
  for (const [relative, value] of [
    [`asc/${reportDay}/acquisition.json`, { report_day: reportDay, products: [], rows: [] }],
    [`revenuecat/${reportDay}/subscriptions.json`, { report_day: reportDay, products: [] }],
    [`coverage/${reportDay}/summary.json`, { kind: "marketing_product_metric_summary", product_id: "mobile-marketing", period: "daily", observed_at: `${reportDay}T13:00:00.000Z`, report_key: `attribution-${reportDay}`, source_refs: [], products: [], message: "Life Manager：fixture coverage unavailable" }],
  ]) {
    const file = path.join(attributionRoot, relative);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify(value));
  }
  const aniccaSummaryDir = path.join(dataDir, "tenants/dais-local/marketing/metrics/summaries/anicca-ios/daily");
  fs.mkdirSync(aniccaSummaryDir, { recursive: true });
  fs.writeFileSync(path.join(aniccaSummaryDir, `${reportDay}.json`), JSON.stringify({
    schema_version: 1,
    kind: "marketing_product_metric_summary",
    period: "daily",
    report_key: reportDay,
    observed_at: "2026-10-12T13:30:00.000Z",
    product_id: "anicca-ios",
    source_status: "partial",
    source_refs: [],
    message: "Anicca source is available",
  }));

  const target = TARGETS[0];
  const caption = "毎日届く言葉で心を軽くする";
  const captionSha = crypto.createHash("sha256").update(caption).digest("hex");
  const captionFile = path.join(dataDir, "objects", "sha256", captionSha);
  fs.mkdirSync(path.dirname(captionFile), { recursive: true });
  fs.writeFileSync(captionFile, caption, { mode: 0o600 });
  const videoId = "7695990000000000003";
  const publicUrl = `https://www.tiktok.com/@${target.account_id.slice(1)}/video/${videoId}`;
  const distributionRow = {
    ts: "2026-10-12T13:50:00.000Z",
    platform: "tiktok",
    status: "published",
    provider_reconciled: true,
    format_id: target.format_id,
    form: target.form,
    locale: target.locale,
    provider_id: "cmetricsvideo20261012",
    public_url: publicUrl,
    caption_path: captionFile,
    caption_sha256: captionSha,
  };
  const ledger = path.join(dataDir, "tenants/dais-local/marketing/video-publication/anicca-ios/distribution.jsonl");
  fs.mkdirSync(path.dirname(ledger), { recursive: true });
  fs.writeFileSync(ledger, `${JSON.stringify(distributionRow)}\n`);

  const metricFile = path.join(dataDir, "tenants/dais-local/marketing/metrics", target.native_owner, videoId, "2h.combined.json");
  fs.mkdirSync(path.dirname(metricFile), { recursive: true });
  fs.writeFileSync(metricFile, JSON.stringify({
    schema_version: 1,
    kind: "tiktok_combined_metric_snapshot",
    tenant_id: "dais-local",
    product_id: "anicca-ios",
    locale: target.locale,
    account_id: target.account_id,
    native_owner: target.native_owner,
    provider_post_id: distributionRow.provider_id,
    shortcode: videoId,
    video_id: videoId,
    public_url: publicUrl,
    caption,
    published_at: distributionRow.ts,
    window: "2h",
    observed_at: "2026-10-12T14:30:00.000Z",
    caption_sha256: captionSha,
    sources: { tiktok_native: { status: "measured" }, postiz_post: { status: "measured" } },
    post: { views: { status: "measured", value: 9 } },
    account_metrics: { status: "unavailable", reason: "provider_field_missing" },
  }));

  const originalFetch = global.fetch;
  let telegramId = 0;
  global.fetch = async (url) => {
    if (String(url).startsWith("https://api.telegram.org/")) return { ok: true, json: async () => ({ ok: true, result: { message_id: ++telegramId } }) };
    throw new Error(`unexpected network request in isolated metrics test: ${url}`);
  };
  try {
    const env = {
      LM_DATA_DIR: dataDir,
      LM_TELEGRAM_BOT_TOKEN: "fake",
      LM_TELEGRAM_ALERT_CHAT_ID: "fake",
    };
    const api = await runDue(Date.parse("2026-10-12T14:30:00.000Z"), env, null, "api");
    assert.equal(api.some((row) => row.window === "daily-product" || row.window === "daily"), false);
    fs.unlinkSync(metricFile);
    const final = await runDue(Date.parse("2026-10-12T14:30:00.000Z"), env, null, "finalize");
    assert.equal(final.some((row) => row.window === "asc-daily" || row.window === "weekly-product" || row.window === "2h"), false);
    assert.equal(final.find((row) => row.video_id === videoId && row.window === "daily").state, "pending");
    assert.equal(final.find((row) => row.video_id === videoId && row.window === "daily").reason, "no_metric_snapshot");
    const results = [...api, ...final];
    assert.equal(results.find((row) => row.window === "weekly-product").state, "partial");
    assert.equal(results.find((row) => row.product_id === "honne-ai" && row.window === "daily-product").state, "unavailable");
    assert.equal(results.find((row) => row.product_id === "anicca-ios" && row.window === "daily-product").state, "partial");
    assert.equal(results.find((row) => row.video_id === videoId && row.window === "2h").state, "complete");
    const weekly = JSON.parse(fs.readFileSync(path.join(dataDir, "tenants/dais-local/marketing/metrics/summaries/mobile-marketing/weekly/2026-W42.json"), "utf8"));
    assert.equal(weekly.source_status, "partial");
    assert.deepEqual(weekly.unavailable_products, ["honne-ai"]);
    const honne = JSON.parse(fs.readFileSync(path.join(dataDir, "tenants/dais-local/marketing/metrics/summaries/honne-ai/daily", `${reportDay}.json`), "utf8"));
    assert.equal(honne.source_status, "unavailable");
    assert.match(honne.message, /取得不可/);
  } finally {
    global.fetch = originalFetch;
  }
});


test("unpublished photo target ignores unrelated receipts while malformed exact receipts still fail", (t) => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "lm-photo-unpublished-receipts-"));
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  const target = TARGETS.find((row) => row.postiz_photo_only);
  const file = path.join(dataDir, "marketing/receipts.jsonl");
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify({ job_id: "marketing-liveness:other-summary", receipt: { message_id: 708 } }) + "\n");
  assert.deepEqual(discoverTarget(dataDir, target), []);
  for (const row of [{ job_id: target.receipt_job_id }, { job_id: target.receipt_job_id, receipt: { status: "failed" } }]) {
    fs.writeFileSync(file, JSON.stringify(row) + "\n");
    assert.throws(() => discoverTarget(dataDir, target), /Postiz photo receipt invalid/);
  }
});
