"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  RUNNERS_BY_ACTION,
  runAniccaLarryJaRotatingCanary,
  runAniccaEnAffirmationTikTokRotatingCanary,
  runAniccaBuddhaTikTokRotatingCanary,
} = require("./anicca-larry-ja-rotating.js");
const { EN_AFFIRMATION_TIKTOK_LANE, JA_BUDDHA_TIKTOK_LANE } = require("../lib/marketing-native-carousel-publication-adapter.js");

const SLOT = "2026-09-28T01:30:00.000Z";
const SELECTED = {
  packRef: `object://sha256/${"a".repeat(64)}`,
  mediaRefs: Array.from({ length: 6 }, (_, i) => `object://sha256/${String(i).repeat(64)}`.slice(0, 74)),
  captionRef: `object://sha256/${"b".repeat(64)}`,
  approvalRef: `object://sha256/${"c".repeat(64)}`,
};

test("runAniccaLarryJaRotatingCanary rejects any command other than run-ja-larry-production", async () => {
  await assert.rejects(runAniccaLarryJaRotatingCanary([]), /usage/i);
  await assert.rejects(runAniccaLarryJaRotatingCanary(["run"]), /usage/i);
  await assert.rejects(runAniccaLarryJaRotatingCanary(["run-ja-larry-production", "extra"]), /usage/i);
});

test("runAniccaLarryJaRotatingCanary resolves the slot's pack and feeds it into the canary's env-var contract", async () => {
  let resolveCall = null;
  let runCall = null;
  const result = await runAniccaLarryJaRotatingCanary(["run-ja-larry-production"], {
    env: { LM_DATA_DIR: "/tmp/x", LM_RUNTIME_TENANT_ID: "dais-local", EXISTING: "kept" },
    now: () => "2026-09-28T00:00:00.000Z",
    resolveLarryJaSlot: (args) => { resolveCall = args; return { slot: SLOT, selected: SELECTED }; },
    runAniccaCarouselCanary: (argv, deps) => { runCall = { argv, deps }; return Promise.resolve({ ok: true }); },
  });

  assert.deepEqual(result, { ok: true });
  assert.equal(resolveCall.env.LM_DATA_DIR, "/tmp/x");
  assert.deepEqual(runCall.argv, ["run-ja-larry-production", "--slot", SLOT]);
  assert.equal(runCall.deps.env.EXISTING, "kept");
  assert.equal(runCall.deps.env.LM_ANICCA_LARRY_JA_PACK_REF, SELECTED.packRef);
  assert.equal(runCall.deps.env.LM_ANICCA_LARRY_JA_MEDIA_REFS, JSON.stringify(SELECTED.mediaRefs));
  assert.equal(runCall.deps.env.LM_ANICCA_LARRY_JA_CAPTION_REF, SELECTED.captionRef);
  assert.equal(runCall.deps.env.LM_ANICCA_LARRY_JA_APPROVAL_REF, SELECTED.approvalRef);
});

test("runAniccaLarryJaRotatingCanary propagates a rotation resolution failure instead of posting anything", async () => {
  await assert.rejects(runAniccaLarryJaRotatingCanary(["run-ja-larry-production"], {
    resolveLarryJaSlot: () => { throw new Error("no unposted candidate available"); },
    runAniccaCarouselCanary: () => { throw new Error("must not be called"); },
  }), /no unposted candidate available/);
});

test("rotating runner skips the canary when the current slot already has a verified publication", async () => {
  let canaryCalls = 0;
  const result = await runAniccaEnAffirmationTikTokRotatingCanary(["run-en-affirmation-tiktok-production"], {
    env: { LM_DATA_DIR: "/tmp/x", LM_RUNTIME_TENANT_ID: "dais-local" },
    resolveLarryJaSlot: () => ({ slot: SLOT, selected: null, alreadyPublished: true, providerPostId: "postiz-slot-1" }),
    runAniccaCarouselCanary: () => { canaryCalls += 1; throw new Error("must not publish a second pack in the same slot"); },
  });

  assert.deepEqual(result, {
    status: "already_published",
    slot: SLOT,
    publication: { created: false, provider_post_id: "postiz-slot-1", provider_reconciled: true },
  });
  assert.equal(canaryCalls, 0);
});

// Root-cause regression coverage: the same rotating wrapper function that
// fixed JA Larry Instagram must also drive the other previously-repeating
// lanes, feeding each its OWN env var names (lane.packEnv/mediaEnv/
// captionEnv/approvalEnv) rather than JA_LANE's -- otherwise it would rotate
// JA Larry's env vars while a different lane's canary keeps reading its own
// (still unrotated) ones.
test("runAniccaEnAffirmationTikTokRotatingCanary feeds EN_AFFIRMATION_TIKTOK_LANE's own env vars, not JA_LANE's", async () => {
  let resolveCall = null;
  let runCall = null;
  const result = await runAniccaEnAffirmationTikTokRotatingCanary(["run-en-affirmation-tiktok-production"], {
    env: { LM_DATA_DIR: "/tmp/x", LM_RUNTIME_TENANT_ID: "dais-local" },
    now: () => "2026-09-28T00:00:00.000Z",
    resolveLarryJaSlot: (args) => { resolveCall = args; return { slot: SLOT, selected: SELECTED }; },
    runAniccaCarouselCanary: (argv, deps) => { runCall = { argv, deps }; return Promise.resolve({ ok: true }); },
  });
  assert.deepEqual(result, { ok: true });
  assert.equal(resolveCall.lane, EN_AFFIRMATION_TIKTOK_LANE);
  assert.deepEqual(runCall.argv, ["run-en-affirmation-tiktok-production", "--slot", SLOT]);
  assert.equal(runCall.deps.env[EN_AFFIRMATION_TIKTOK_LANE.packEnv], SELECTED.packRef);
  assert.equal(runCall.deps.env[EN_AFFIRMATION_TIKTOK_LANE.captionEnv], SELECTED.captionRef);
  assert.equal(runCall.deps.env.LM_ANICCA_LARRY_JA_PACK_REF, undefined);
});

test("the EN2 action rotates the shared affirmation template for its exact integration and slots", async () => {
  const action = "run-en2-affirmation-tiktok-production";
  const runner = RUNNERS_BY_ACTION[action];
  assert.equal(typeof runner, "function");
  let resolveCall = null;
  let runCall = null;
  const result = await runner([action], {
    env: { LM_DATA_DIR: "/tmp/x", LM_RUNTIME_TENANT_ID: "dais-local" },
    resolveLarryJaSlot: (input) => { resolveCall = input; return { slot: SLOT, selected: SELECTED }; },
    runAniccaCarouselCanary: async (argv, deps) => { runCall = { argv, deps }; return { argv }; },
  });
  assert.deepEqual({
    integrationId: resolveCall.lane.integrationId,
    accountId: resolveCall.lane.accountId,
    lane: resolveCall.lane.lane,
    workerLabel: resolveCall.lane.workerLabel,
    rotationEnabled: resolveCall.lane.rotationEnabled,
    productionSlots: resolveCall.productionSlots,
  }, {
    integrationId: "cmlt171eq04d9r00yzzceb6bw",
    accountId: "@aniccaen2",
    lane: "anicca-en2-affirmation-tiktok",
    workerLabel: "anicca-en2-affirmation-tiktok-canary",
    rotationEnabled: true,
    productionSlots: ["09:30", "14:30", "20:30"],
  });
  assert.deepEqual(result, { argv: [action, "--slot", SLOT] });
  assert.equal(runCall.deps.env[EN_AFFIRMATION_TIKTOK_LANE.packEnv], SELECTED.packRef);
  assert.equal(runCall.deps.env[EN_AFFIRMATION_TIKTOK_LANE.mediaEnv], JSON.stringify(SELECTED.mediaRefs));
});

test("runAniccaBuddhaTikTokRotatingCanary rejects any command other than run-ja-buddha-tiktok-production", async () => {
  await assert.rejects(runAniccaBuddhaTikTokRotatingCanary([]), /usage/i);
  await assert.rejects(runAniccaBuddhaTikTokRotatingCanary(["run-ja-main-tiktok-production"]), /usage/i);
});

test("runAniccaBuddhaTikTokRotatingCanary feeds JA_BUDDHA_TIKTOK_LANE's own env vars", async () => {
  let runCall = null;
  await runAniccaBuddhaTikTokRotatingCanary(["run-ja-buddha-tiktok-production"], {
    env: { LM_DATA_DIR: "/tmp/x", LM_RUNTIME_TENANT_ID: "dais-local" },
    now: () => "2026-09-28T00:00:00.000Z",
    resolveLarryJaSlot: () => ({ slot: SLOT, selected: SELECTED }),
    runAniccaCarouselCanary: (argv, deps) => { runCall = { argv, deps }; return Promise.resolve({ ok: true }); },
  });
  assert.equal(runCall.deps.env[JA_BUDDHA_TIKTOK_LANE.packEnv], SELECTED.packRef);
  assert.equal(runCall.deps.env[JA_BUDDHA_TIKTOK_LANE.mediaEnv], JSON.stringify(SELECTED.mediaRefs));
});
