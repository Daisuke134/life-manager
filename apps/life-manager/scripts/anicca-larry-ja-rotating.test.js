"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
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
