"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const {
  GATE_APPROVED,
  auditMarketingDestinationRegistry,
  findMarketingDestinationTarget,
  loadMarketingDestinationContract,
  validateMarketingDestinationContract,
} = require("./marketing-destination-contract.js");
const {
  EN_AFFIRMATION_LANE,
  EN_AFFIRMATION_TIKTOK_LANE,
  EN2_AFFIRMATION_TIKTOK_LANE,
  EN_SLIDESHOW_TIKTOK_LANE,
  JA_MAIN_TIKTOK_LANE,
  JA_JP1_TIKTOK_LANE,
  JA_BUDDHA_TIKTOK_LANE,
  selectMarketingNativeCarouselLane,
} = require("./marketing-native-carousel-publication-adapter.js");

const CONTRACT = path.resolve(__dirname, "../../../config/marketing-destinations.json");

test("the marketing destination SSOT fixes every retained route and every non-target connection", () => {
  const value = loadMarketingDestinationContract(CONTRACT);
  assert.equal(value.targets.length, 21);
  assert.equal(value.targets.filter((row) => ["anicca", "honne-ai"].includes(row.product_id)).length, 18);
  assert.equal(value.targets.filter((row) => row.product_id.startsWith("ebook-")).length, 3);
  assert.equal(value.targets.filter((row) => row.product_id === "ebook-ja").length, 2);
  assert.equal(value.holds.length, 12);
  assert.equal(value.holds.filter((row) => row.integration_id).length, 9);
  assert.equal(value.holds.filter((row) => row.integration_id === null).length, 3);
  assert.deepEqual(
    value.holds.find((row) => row.postiz_profile === "@monk_anicca"),
    { platform: "instagram", postiz_profile: "@monk_anicca", integration_id: null,
      reason: "english_monk_instagram_not_connected", target_daily_limit: 0 },
  );
  assert.ok(value.targets.every((row) => [2, 3].includes(row.cadence_jst.length)));
  assert.deepEqual(
    value.targets.filter((row) => row.cadence_jst.length === 2).map((row) => row.lane_id),
    ["ebook-en-tiktok"],
  );
  const englishMonk = value.targets.find((row) => row.lane_id === "ebook-en-tiktok");
  assert.deepEqual(
    [englishMonk.native_handle, englishMonk.integration_id, englishMonk.renderer_id,
      englishMonk.cadence_jst],
    ["@monk_anicca", "cmo5rwq2p00twn10yrsdglng3", "heygen-avatar-iv", ["08:00", "21:00"]],
  );
  assert.equal(value.holds.some((row) => row.integration_id === "cmo5rwq2p00twn10yrsdglng3"), false);
  assert.equal(value.targets.some((row) => row.native_handle === "@obou.anicca" && row.product_id !== "ebook-ja"), false);
  assert.equal(value.targets.some((row) => row.native_handle === "@obou.anicca" && row.product_id === "ebook-ja"), true);
  assert.deepEqual(
    value.targets
      .filter((row) => ["cmp9pedr700ttqh0yj8o57fog", "cmn8ycvtn02djqx0ytuisn9mw"].includes(row.integration_id))
      .map((row) => [row.postiz_profile, row.native_handle]),
    [["@anicca.affirmation", "@anicca.ios"], ["@anicca.jp1", "@anicca.ios.jp"]],
  );
  assert.deepEqual(
    value.holds.filter((row) => row.integration_id === null).map((row) => `${row.platform}:${row.postiz_profile}`).sort(),
    ["instagram:@monk_anicca", "tiktok:@anicca.videojp", "tiktok:@anicca_girl"],
  );
});

test("enabled @aniccaen2 resolves to one Anicca iOS English affirmation route with three slots", () => {
  const contract = loadMarketingDestinationContract(CONTRACT);
  const integrationId = "cmlt171eq04d9r00yzzceb6bw";
  const target = contract.targets.find((row) => row.integration_id === integrationId);
  assert.ok(target, "enabled Postiz integration @aniccaen2 must not remain a zero-slot hold");

  assert.deepEqual({
    productId: target.job_product_id,
    profile: target.postiz_profile,
    account: target.native_handle,
    format: target.job_format_id,
    mediaForm: target.media_form,
    approvedPack: target.approved_pack,
    approvedPackRef: target.approved_pack_ref,
    loop: target.loop_name,
    cadence: target.cadence_jst,
  }, {
    productId: "anicca-ios",
    profile: "@aniccaen2",
    account: "@aniccaen2",
    format: "larry",
    mediaForm: "affirmation-carousel",
    approvedPack: "anicca-ios-larry-affirmation-en-tiktok.pack.json",
    approvedPackRef: "gate-approved",
    loop: "life-manager-anicca-en2-affirmation-tiktok",
    cadence: ["09:30", "14:30", "20:30"],
  });

  const registry = JSON.parse(fs.readFileSync(path.resolve(__dirname, "../../../config/loop-registry.json"), "utf8"));
  assert.equal(auditMarketingDestinationRegistry(contract, registry).targets, 21);
});

test("the carousel publisher selects @aniccaen2 by its exact Postiz integration", () => {
  const lane = selectMarketingNativeCarouselLane({
    productId: "anicca-ios",
    formatId: "larry",
    form: "affirmation-carousel",
    locale: "en",
    accountId: "@aniccaen2",
    integrationRef: "integration://postiz/tiktok/cmlt171eq04d9r00yzzceb6bw",
  });
  assert.deepEqual({ accountId: lane.accountId, integrationId: lane.integrationId, lane: lane.lane }, {
    accountId: "@aniccaen2",
    integrationId: "cmlt171eq04d9r00yzzceb6bw",
    lane: "anicca-en2-affirmation-tiktok",
  });
});

test("duplicate retained handles across platforms fail closed", () => {
  const value = JSON.parse(fs.readFileSync(CONTRACT, "utf8"));
  value.targets[1].native_handle = value.targets[0].native_handle;
  assert.throws(() => validateMarketingDestinationContract(value), /duplicate native handle/i);
});

test("two-slot cadence is limited to the approved eBook lanes", () => {
  const cases = new Map([
    ["ebook-en-tiktok", ["08:00", "21:00"]],
    ["ebook-ja-instagram", ["07:00", "20:00"]],
    ["ebook-ja-tiktok", ["07:00", "20:00"]],
  ]);
  for (const [laneId, cadence] of cases) {
    const value = JSON.parse(fs.readFileSync(CONTRACT, "utf8"));
    const target = value.targets.find((row) => row.lane_id === laneId);
    assert.ok(target);
    target.cadence_jst = cadence;
    assert.doesNotThrow(() => validateMarketingDestinationContract(value));
  }

  const value = JSON.parse(fs.readFileSync(CONTRACT, "utf8"));
  const otherLane = value.targets.find((row) => !cases.has(row.lane_id));
  otherLane.cadence_jst = ["07:00", "20:00"];
  assert.throws(() => validateMarketingDestinationContract(value), /cadence_jst/);
});

test("English eBook two-slot exception is bound to its Monk TikTok identity", () => {
  const value = JSON.parse(fs.readFileSync(CONTRACT, "utf8"));
  const target = value.targets.find((row) => row.lane_id === "ebook-en-tiktok");
  target.platform = "instagram";
  assert.throws(() => validateMarketingDestinationContract(value), /cadence_jst/);
});

test("Japanese eBook two-slot exceptions are bound to exact Watercolor integrations", () => {
  for (const laneId of ["ebook-ja-instagram", "ebook-ja-tiktok"]) {
    const value = JSON.parse(fs.readFileSync(CONTRACT, "utf8"));
    const target = value.targets.find((row) => row.lane_id === laneId);
    target.cadence_jst = ["07:00", "20:00"];
    target.integration_id = "unexpected-watercolor-integration";
    assert.throws(() => validateMarketingDestinationContract(value), /cadence_jst/);
  }
});

test("a target without an exact pack, form, cadence, label, or entrypoint fails closed", () => {
  const value = JSON.parse(fs.readFileSync(CONTRACT, "utf8"));
  for (const field of ["approved_pack_ref", "media_form", "cadence_jst", "label", "entrypoint"]) {
    const candidate = structuredClone(value);
    delete candidate.targets[0][field];
    assert.throws(() => validateMarketingDestinationContract(candidate), new RegExp(field));
  }
});

test("the loop registry exactly matches the destination SSOT labels, entrypoints, and cadences", () => {
  const contract = loadMarketingDestinationContract(CONTRACT);
  const registry = JSON.parse(fs.readFileSync(path.resolve(__dirname, "../../../config/loop-registry.json"), "utf8"));
  assert.equal(auditMarketingDestinationRegistry(contract, registry).targets, 21);
  const candidate = structuredClone(registry);
  candidate.loops[contract.targets[0].loop_name].cadence.calendar_interval[0].Minute = 1;
  assert.throws(() => auditMarketingDestinationRegistry(contract, candidate), /cadence/i);
});

test("publication identity selects exactly one route and rejects cross-family content", () => {
  const contract = loadMarketingDestinationContract(CONTRACT);
  const input = {
    jobProductId: "honne-ai",
    locale: "en",
    platform: "tiktok",
    integrationId: "cmoig11ew001zlv0yk6vqo1us",
    jobFormatId: "reelclaw",
    mediaForm: "relationship-confession",
  };
  assert.equal(findMarketingDestinationTarget(contract, input).lane_id, "honne-en");
  assert.equal(findMarketingDestinationTarget(contract, { ...input, jobFormatId: "reelclaw-card" }), null);
  assert.equal(findMarketingDestinationTarget(contract, { ...input, mediaForm: "nudge-card" }), null);
  assert.equal(findMarketingDestinationTarget(contract, { ...input, integrationId: "cmp9sdev5012voh0y58qs45xc" }), null);
});

test("GATE_APPROVED is a valid approved_pack_ref sentinel; any other non-object-ref string still fails closed", () => {
  const value = JSON.parse(fs.readFileSync(CONTRACT, "utf8"));
  value.targets[0].approved_pack_ref = GATE_APPROVED;
  assert.doesNotThrow(() => validateMarketingDestinationContract(value));
  value.targets[0].approved_pack_ref = "not-a-real-sentinel-or-ref";
  assert.throws(() => validateMarketingDestinationContract(value), /approved_pack_ref/);
});

test("the JA Larry lane is the gate-approved lane (rotation, not a single pinned pack)", () => {
  const contract = loadMarketingDestinationContract(CONTRACT);
  const lane = contract.targets.find((row) => row.lane_id === "anicca-ios-ja-larry-instagram");
  assert.equal(lane.approved_pack_ref, GATE_APPROVED);
});

test("every rotating Anicca carousel lane delegates fresh-pack approval to the per-job gate", () => {
  const contract = loadMarketingDestinationContract(CONTRACT);
  const rotating = [
    EN_AFFIRMATION_LANE,
    EN_AFFIRMATION_TIKTOK_LANE,
    EN2_AFFIRMATION_TIKTOK_LANE,
    EN_SLIDESHOW_TIKTOK_LANE,
    JA_MAIN_TIKTOK_LANE,
    JA_JP1_TIKTOK_LANE,
    JA_BUDDHA_TIKTOK_LANE,
  ].filter((lane) => lane.rotationEnabled === true);

  assert.equal(rotating.length, 7);
  for (const lane of rotating) {
    const target = findMarketingDestinationTarget(contract, {
      jobProductId: lane.productId,
      locale: lane.locale,
      platform: lane.platform,
      integrationId: lane.integrationId,
      jobFormatId: lane.formatId,
      mediaForm: lane.form,
    });
    assert.ok(target, `${lane.name} has an exact destination`);
    assert.equal(target.approved_pack_ref, GATE_APPROVED, `${lane.name} accepts only gate-approved rotated packs`);
  }
  const staticTarget = contract.targets.find((row) => row.lane_id === "anicca-ios-en-card-instagram");
  assert.ok(staticTarget);
  assert.match(staticTarget.approved_pack_ref, /^object:\/\/sha256\//);
});
