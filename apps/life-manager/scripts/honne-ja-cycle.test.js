"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { ANICCA_EN_CARD_INSTAGRAM_SLOTS, ANICCA_EN_WIDGET_INSTAGRAM_SLOTS, ANICCA_HE_SLOTS, ANICCA_JP4_SLOTS, ANICCA_MAIN_INSTAGRAM_SLOTS, ANICCA_MAIN_SLOTS, CAPAFY_IG_SLOTS, PRODUCTION_SLOTS, noDueSlotResult, parseArgs, runHonneJaCycle, runSlot, telegramNativeUrlVerified } = require("./honne-ja-cycle.js");
const { createContentObjectStore } = require("../lib/content-object-store.js");
const { marketingCtaLine } = require("../lib/marketing-app-store-cta.js");

const ALL_LANE_COMMANDS = ["run", "run-anicca-main", "run-anicca-main-instagram", "run-anicca-en-card-instagram", "run-anicca-en-widget-instagram", "run-anicca-ai-youtube", "run-anicca-affirmation-youtube", "run-anicca-ja-widget-instagram", "run-anicca-jp4", "run-anicca-he", "run-capafy-ig"];

test("YouTube changed-caption slot reuses a verified publication or holds unresolved prior work", async () => {
  const { reusePriorYouTubePublication } = require("./honne-ja-cycle.js");
  const receipt = {
    schema_version: 1, kind: "marketing_video_distribution", status: "published",
    product_id: "anicca-ios", format_id: "reelclaw-card", form: "nudge-card",
    locale: "en", slot: "2026-10-11T05:15:00.000Z", creative_id: "prior-creative",
    platform: "youtube", video_sha256: "a".repeat(64), caption_sha256: "b".repeat(64),
    public_url: "https://www.youtube.com/watch?v=iEDdaIWdwY4",
    provider_post_id: "prior-post", provider_route: "postiz", provider_reconciled: true,
    published_at: "2026-10-11T05:18:08.723Z",
  };
  const refs = { product_ref: "product://anicca-ios", format_ref: "format://reelclaw-card",
    locale_ref: "locale://en", platform_ref: "platform://youtube",
    slot_ref: "schedule-slot://2026-10-11T05:15:00.000Z" };
  const current = { tenant_id: "dais-local", job_id: "changed-caption-job", input_refs: refs };
  const priorJob = { job_id: "prior-job", status: "completed", input_refs: { ...refs,
    form_ref: "form://nudge-card", creative_ref: "creative://anicca-ios/prior-creative",
    video_ref: `object://sha256/${receipt.video_sha256}`, caption_ref: `object://sha256/${receipt.caption_sha256}` } };
  const store = (value) => ({ async readPriorPublicationForSlot() { return value; } });
  const reused = await reusePriorYouTubePublication(store({ job: priorJob, receipt }), current);
  assert.equal(reused.created, false);
  assert.equal(reused.public_url, receipt.public_url);
  assert.equal(reused.provider_post_id, receipt.provider_post_id);
  assert.equal(reused.reused_prior_slot, true);
  assert.equal(await reusePriorYouTubePublication(store(null), current), null);
  for (const value of [null, { ...receipt, provider_reconciled: false }, { ...receipt, slot: "2026-10-10T05:15:00.000Z" },
    { ...receipt, creative_id: "wrong-creative" }, { ...receipt, video_sha256: "c".repeat(64) },
    { ...receipt, caption_sha256: "d".repeat(64) }, { ...receipt, form: "nudge-widget" }]) {
    const held = await reusePriorYouTubePublication(store({ job: priorJob, receipt: value }), current);
    assert.equal(held.held, true);
    assert.equal(held.reason, "prior_slot_publication_unresolved");
    assert.equal(held.prior_job_id, priorJob.job_id);
    assert.equal(held.public_url, null);
  }
});

test("Every Honne JA lane's product/platform/locale resolves to a real App Store CTA line", () => {
  for (const command of ALL_LANE_COMMANDS) {
    const lane = parseArgs([command]).lane;
    const line = marketingCtaLine({ productId: lane.product, platform: lane.platform, locale: lane.locale });
    assert.ok(line.length > 0, `${command} produced an empty CTA`);
    if (lane.platform === "youtube") assert.match(line, /apps\.apple\.com/);
    else assert.doesNotMatch(line, /apps\.apple\.com/);
  }
});

test("Honne JA production cadence has three exact idempotent slots", () => {
  assert.deepEqual([...PRODUCTION_SLOTS], ["08:30", "12:30", "21:30"]);
  assert.equal(runSlot(null, Date.parse("2026-08-22T04:00:00.000Z")), "2026-08-22T03:30:00.000Z");
  assert.equal(runSlot(null, Date.parse("2026-08-22T13:00:00.000Z")), "2026-08-22T12:30:00.000Z");
  assert.throws(() => runSlot(null, Date.parse("2026-08-21T23:29:00.000Z")), /no due slot/i);
});

test("Anicca main Instagram has three exact daily Reel slots", () => {
  assert.deepEqual([...ANICCA_MAIN_INSTAGRAM_SLOTS], ["08:10", "13:10", "19:10"]);
  const lane = parseArgs(["run-anicca-main-instagram"]).lane;
  assert.equal(lane.platform, "instagram"); assert.equal(lane.account, "@anicca.jp1");
});

test("Anicca EN Card Instagram is exact-account bound at three daily slots", () => {
  assert.deepEqual([...ANICCA_EN_CARD_INSTAGRAM_SLOTS], ["08:45", "12:45", "21:30"]);
  const lane = parseArgs(["run-anicca-en-card-instagram"]).lane;
  assert.equal(lane.platform, "instagram");
  assert.equal(lane.account, "@anicca.encards");
  assert.equal(lane.integrationId, "cmpc3gx4001nklg0y27a8o66q");
  assert.equal(lane.instagramProfileRef, "profile://instagram/anicca.encards");
  assert.equal(lane.packKey, "LM_ANICCA_EN_CARD_PACK_REF");
  assert.equal(lane.mediaKey, "LM_ANICCA_EN_CARD_MEDIA_REFS");
  const url = "https://www.instagram.com/reel/ExactArtifact1/";
  assert.equal(telegramNativeUrlVerified(lane, {}, url), true);
});

test("Anicca EN Widget Instagram publishes only the exact account at three daily slots", () => {
  assert.deepEqual([...ANICCA_EN_WIDGET_INSTAGRAM_SLOTS], ["07:30", "09:30", "19:00"]);
  const lane = parseArgs(["run-anicca-en-widget-instagram"]).lane;
  assert.equal(lane.format, "reelclaw-widget");
  assert.equal(lane.platform, "instagram");
  assert.equal(lane.account, "@anicca.en");
  assert.equal(lane.integrationId, "cmn8y95rg02d2qx0y09bbk5pb");
  assert.equal(lane.instagramProfileRef, "profile://instagram/anicca.en");
  assert.equal(lane.packKey, "LM_ANICCA_EN_WIDGET_PRODUCTION_PACK_REF");
  assert.equal(lane.mediaKey, "LM_ANICCA_EN_WIDGET_PRODUCTION_MEDIA_REFS");
});

test("Honne JA production CLI accepts only an optional exact slot", () => {
  const slot = "2026-08-22T03:30:00.000Z";
  assert.equal(parseArgs(["run"]).slot, null);
  assert.equal(parseArgs(["run", "--slot", slot]).slot, slot);
  assert.throws(() => parseArgs(["run", "--slot"]), /usage/i);
  assert.throws(() => runSlot("invalid", Date.now()), /timestamp is invalid/i);
});

test("the mobile no-due result uses the exact no-effect receipt contract", () => {
  const error = Object.assign(new Error("marketing cycle has no due slot yet"), { code: "NO_DUE_SLOT" });
  assert.deepEqual(noDueSlotResult(error), { status: "no_due_slot", reason: "no_due_slot" });
  assert.equal(noDueSlotResult(new Error("other failure")), null);
});

test("a failed publication with no provider effect retries once; an unknown effect stays held", async (t) => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "honne-publication-retry-"));
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  const objectStore = createContentObjectStore({ objectDir: path.join(dataDir, "objects") });
  const importText = (name, value) => {
    const source = path.join(dataDir, name);
    fs.writeFileSync(source, value);
    return objectStore.import(source).ref;
  };
  const packRef = importText("pack.json", "{}");
  const mediaRef = importText("media.bin", "media");
  const approvalRef = importText("approval.json", JSON.stringify({
    scope: "standing", product_id: "honne-ai", locale: "ja", platform: "tiktok", account: "@honnevideo",
  }));
  const videoRef = importText("video.mp4", "video");
  const copyRef = importText("copy.txt", "I can speak honestly.");
  const artifact = {
    creative_id: "retry-creative",
    form: "relationship-confession",
    video_ref: videoRef,
    copy_ref: copyRef,
  };
  const jobs = new Map();
  const receipts = new Map();
  const calls = [];
  let generationJobId;
  let publicationJobId;
  const store = {
    async enqueueJob(input) {
      const existing = jobs.get(input.jobId);
      if (existing) return { created: false, job: existing };
      const job = {
        job_id: input.jobId,
        tenant_id: input.tenantId,
        loop_id: input.loopId,
        capability: input.capability,
        effect_class: input.effectClass,
        effect_key: input.effectKey,
        input_refs: input.inputRefs,
        max_attempts: input.maxAttempts,
        attempt: input.capability === "marketing.video.publish" ? 1 : 0,
        status: input.capability === "marketing.video.publish" ? "failed" : "queued",
        unknown_effect: false,
      };
      jobs.set(job.job_id, job);
      if (job.capability === "marketing.video.generate") generationJobId = job.job_id;
      if (job.capability === "marketing.video.publish") publicationJobId = job.job_id;
      return { created: true, job };
    },
    async readReceipt({ jobId }) {
      if (jobId === generationJobId) return artifact;
      return receipts.get(jobId) || null;
    },
    async readJob({ jobId }) { return jobs.get(jobId) || null; },
    async retryJob({ jobId }) {
      calls.push("retry");
      const job = jobs.get(jobId);
      assert.equal(job.status, "failed");
      assert.equal(job.unknown_effect, false);
      job.status = "queued";
      return job;
    },
    async claimJob({ jobId, workerId }) {
      calls.push("claim");
      const job = jobs.get(jobId);
      if (!job || job.status !== "queued") return null;
      job.status = "running";
      job.attempt += 1;
      job.lease_owner = workerId;
      return { ...job };
    },
    async heartbeatJob() {},
    async completeJob({ jobId, receipt }) { receipts.set(jobId, receipt); },
    async failJob({ jobId, unknownEffect }) {
      calls.push("fail");
      const job = jobs.get(jobId);
      job.status = "failed";
      job.unknown_effect = unknownEffect;
    },
  };
  const env = {
    LM_DATA_DIR: dataDir,
    LM_RUNTIME_TENANT_ID: "dais-local",
    LM_HONNE_JA_PACK_REF: packRef,
    LM_HONNE_JA_MEDIA_REFS: mediaRef,
    LM_HONNE_JA_PUBLICATION_APPROVAL_REF: approvalRef,
  };
  const args = ["run", "--slot", "2026-10-13T22:30:00.000Z"];
  const deps = { dataDir, env, nowMs: Date.parse(args[2]), store };

  await assert.rejects(runHonneJaCycle(args, deps), (error) => {
    assert.match(error.message, /Mobile marketing receipt unavailable/i);
    assert.ok(error.message.includes(publicationJobId));
    return true;
  });
  assert.deepEqual(calls, ["retry", "claim", "fail"]);
  assert.equal(jobs.get(publicationJobId).attempt, 2);
  assert.equal(jobs.get(publicationJobId).unknown_effect, false);

  jobs.get(publicationJobId).unknown_effect = true;
  await assert.rejects(runHonneJaCycle(args, deps), (error) => {
    assert.match(error.message, /Mobile marketing job is not claimable/i);
    assert.ok(error.message.includes(publicationJobId));
    return true;
  });
  assert.deepEqual(calls, ["retry", "claim", "fail", "claim"]);
});

test("Anicca main uses only its three historical JA widget slots", () => {
  assert.deepEqual([...ANICCA_MAIN_SLOTS], ["08:00", "16:00", "22:37"]);
  assert.equal(parseArgs(["run-anicca-main"]).lane.account, "@anicca.jp");
  assert.equal(runSlot(null, Date.parse("2026-08-22T07:30:00.000Z"), ANICCA_MAIN_SLOTS), "2026-08-22T07:00:00.000Z");
});

test("JP4 lane is account-bound and capped at three isolated slots", () => {
  const lane = parseArgs(["run-anicca-jp4"]).lane;
  assert.equal(lane.account, "@anicca.jp4"); assert.equal(lane.integrationId, "cmn8x8hdv028uqx0y4gdfse5t"); assert.equal(lane.approvalKey, "LM_ANICCA_JP4_TIKTOK_APPROVAL_REF"); assert.deepEqual([...ANICCA_JP4_SLOTS], ["09:15", "15:15", "20:45"]); assert.equal(lane.slots.length, 3);
});

test("every anicca-ios lane opts into fresh hook text; honne lanes keep pack text", () => {
  for (const command of ALL_LANE_COMMANDS) {
    const lane = parseArgs([command]).lane;
    assert.equal(Boolean(lane.freshHookText), lane.product === "anicca-ios", command);
  }
});

test("HE lane is account-bound and capped at three isolated slots", () => {
  const lane = parseArgs(["run-anicca-he"]).lane;
  assert.equal(lane.account, "@anicca.he"); assert.equal(lane.integrationId, "cmq2aoena08bhqp0yx1epjcik"); assert.equal(lane.approvalKey, "LM_ANICCA_HE_TIKTOK_APPROVAL_REF"); assert.deepEqual([...ANICCA_HE_SLOTS], ["07:15", "13:45", "18:15"]); assert.equal(lane.slots.length, 3);
});

test("Capafy IG Reel lane exists, is account-bound, and resolves its integration id from env (not a literal)", () => {
  const lane = parseArgs(["run-capafy-ig"]).lane;
  assert.equal(lane.product, "capafy-skills");
  assert.equal(lane.platform, "instagram");
  assert.equal(lane.account, "@capafy.hooklab");
  assert.equal(lane.instagramProfileRef, "profile://instagram/capafy.hooklab");
  assert.equal(lane.integrationEnvKey, "CAPAFY_IG_POSTIZ_INTEGRATION_ID");
  assert.equal(lane.integrationId, undefined);
  assert.equal(lane.contentGenerator, "capafy");
  assert.deepEqual([...CAPAFY_IG_SLOTS], ["09:00", "14:00", "20:00"]);
  assert.equal(lane.slots.length, 3);
});

test("Capafy IG Reel fails closed with the exact missing env key when its Postiz integration id is unset", async () => {
  await assert.rejects(
    runHonneJaCycle(["run-capafy-ig"], { env: {} }),
    /CAPAFY_IG_POSTIZ_INTEGRATION_ID is required/,
  );
});
