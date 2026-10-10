#!/usr/bin/env node
"use strict";

// mobile-app-command.js (the shared dispatcher every mobile-app-loops.json
// entry goes through) requires the runner to be a .js file invoked as
// `node <runner> <action>` with no extra flags -- so a bash wrapper can't sit
// in front of anicca-larry-ja-canary.js for these owners. This thin
// entrypoint is the real integration point instead: it resolves a rotation-
// selected, automated-gate-approved pack for the current slot
// (generate-larry-slide-pack.js), feeds it into the target lane's existing
// env-var contract, and delegates straight to runAniccaCarouselCanary -- so
// every check already in anicca-larry-ja-canary.js /
// marketing-native-carousel-publication-adapter.js still runs unchanged at
// publish time.
//
// Originally JA Larry Instagram only. Generalized (2026-09-29) to every
// other native-carousel/slideshow lane that was reposting the same fixed
// pack forever (TikTok "Affirmation Girl", TikTok "anicca"/anicca_slideshow,
// "アニッチャ iOS", "アニッチャ お笑い", Instagram "anicca", plus jp1 TikTok
// which has the identical structural bug even though it wasn't in the
// measured repeat list) -- same runRotatingCarouselCanary function,
// parameterized by lane + action + production-slot schedule, not a fork per
// lane.

const { resolveLarryJaSlot } = require("./generate-larry-slide-pack.js");
const {
  runAniccaCarouselCanary,
  JA_LARRY_PRODUCTION_SLOTS,
  EN_AFFIRMATION_PRODUCTION_SLOTS,
  EN_AFFIRMATION_TIKTOK_PRODUCTION_SLOTS,
  EN2_AFFIRMATION_TIKTOK_PRODUCTION_SLOTS,
  EN_SLIDESHOW_PRODUCTION_SLOTS,
  JA_MAIN_TIKTOK_PRODUCTION_SLOTS,
  JA_JP1_TIKTOK_PRODUCTION_SLOTS,
  JA_BUDDHA_TIKTOK_PRODUCTION_SLOTS,
} = require("./anicca-larry-ja-canary.js");
const {
  JA_LANE,
  EN_AFFIRMATION_LANE,
  EN_AFFIRMATION_TIKTOK_LANE,
  EN2_AFFIRMATION_TIKTOK_LANE,
  EN_SLIDESHOW_TIKTOK_LANE,
  JA_MAIN_TIKTOK_LANE,
  JA_JP1_TIKTOK_LANE,
  JA_BUDDHA_TIKTOK_LANE,
} = require("../lib/marketing-native-carousel-publication-adapter.js");

const ACTION = "run-ja-larry-production";

async function runRotatingCarouselCanary(argv = [], { action, lane, productionSlots, deps = {} }) {
  if (argv.length !== 1 || argv[0] !== action) {
    throw new Error(`usage: anicca-larry-ja-rotating.js ${action}`);
  }
  const env = deps.env || process.env;
  const now = deps.now || (() => new Date().toISOString());
  const resolve = deps.resolveLarryJaSlot || resolveLarryJaSlot;
  const run = deps.runAniccaCarouselCanary || runAniccaCarouselCanary;

  const resolution = await resolve({ env, now, lane, productionSlots });
  if (resolution.alreadyPublished === true) {
    return {
      status: "already_published",
      slot: resolution.slot,
      publication: {
        created: false,
        provider_post_id: resolution.providerPostId,
        provider_reconciled: true,
      },
    };
  }
  const { slot, selected } = resolution;
  const rotatedEnv = {
    ...env,
    [lane.packEnv]: selected.packRef,
    [lane.mediaEnv]: JSON.stringify(selected.mediaRefs),
    [lane.captionEnv]: selected.captionRef,
    [lane.approvalEnv]: selected.approvalRef,
  };
  return run([action, "--slot", slot], {
    ...deps,
    env: rotatedEnv,
    now,
    allowEarlyCatchUp: resolution.catchUp === true,
  });
}

async function runAniccaLarryJaRotatingCanary(argv = [], deps = {}) {
  return runRotatingCarouselCanary(argv, { action: ACTION, lane: JA_LANE, productionSlots: JA_LARRY_PRODUCTION_SLOTS, deps });
}
async function runAniccaEnAffirmationInstagramRotatingCanary(argv = [], deps = {}) {
  return runRotatingCarouselCanary(argv, { action: "run-en-affirmation-production", lane: EN_AFFIRMATION_LANE, productionSlots: EN_AFFIRMATION_PRODUCTION_SLOTS, deps });
}
async function runAniccaEnAffirmationTikTokRotatingCanary(argv = [], deps = {}) {
  return runRotatingCarouselCanary(argv, { action: "run-en-affirmation-tiktok-production", lane: EN_AFFIRMATION_TIKTOK_LANE, productionSlots: EN_AFFIRMATION_TIKTOK_PRODUCTION_SLOTS, deps });
}
async function runAniccaEn2AffirmationTikTokRotatingCanary(argv = [], deps = {}) {
  return runRotatingCarouselCanary(argv, { action: "run-en2-affirmation-tiktok-production", lane: EN2_AFFIRMATION_TIKTOK_LANE, productionSlots: EN2_AFFIRMATION_TIKTOK_PRODUCTION_SLOTS, deps });
}
async function runAniccaEnSlideshowTikTokRotatingCanary(argv = [], deps = {}) {
  return runRotatingCarouselCanary(argv, { action: "run-en-slideshow-tiktok-production", lane: EN_SLIDESHOW_TIKTOK_LANE, productionSlots: EN_SLIDESHOW_PRODUCTION_SLOTS, deps });
}
async function runAniccaMainTikTokRotatingCanary(argv = [], deps = {}) {
  return runRotatingCarouselCanary(argv, { action: "run-ja-main-tiktok-production", lane: JA_MAIN_TIKTOK_LANE, productionSlots: JA_MAIN_TIKTOK_PRODUCTION_SLOTS, deps });
}
async function runAniccaJp1TikTokRotatingCanary(argv = [], deps = {}) {
  return runRotatingCarouselCanary(argv, { action: "run-ja-jp1-tiktok-production", lane: JA_JP1_TIKTOK_LANE, productionSlots: JA_JP1_TIKTOK_PRODUCTION_SLOTS, deps });
}
async function runAniccaBuddhaTikTokRotatingCanary(argv = [], deps = {}) {
  return runRotatingCarouselCanary(argv, { action: "run-ja-buddha-tiktok-production", lane: JA_BUDDHA_TIKTOK_LANE, productionSlots: JA_BUDDHA_TIKTOK_PRODUCTION_SLOTS, deps });
}

const RUNNERS_BY_ACTION = Object.freeze({
  "run-ja-larry-production": runAniccaLarryJaRotatingCanary,
  "run-en-affirmation-production": runAniccaEnAffirmationInstagramRotatingCanary,
  "run-en-affirmation-tiktok-production": runAniccaEnAffirmationTikTokRotatingCanary,
  "run-en2-affirmation-tiktok-production": runAniccaEn2AffirmationTikTokRotatingCanary,
  "run-en-slideshow-tiktok-production": runAniccaEnSlideshowTikTokRotatingCanary,
  "run-ja-main-tiktok-production": runAniccaMainTikTokRotatingCanary,
  "run-ja-jp1-tiktok-production": runAniccaJp1TikTokRotatingCanary,
  "run-ja-buddha-tiktok-production": runAniccaBuddhaTikTokRotatingCanary,
});

if (require.main === module) {
  const action = process.argv[2];
  const runner = RUNNERS_BY_ACTION[action];
  const run = runner || (() => Promise.reject(new Error(`usage: anicca-larry-ja-rotating.js <${Object.keys(RUNNERS_BY_ACTION).join("|")}>`)));
  run(process.argv.slice(2))
    .then((result) => process.stdout.write(`${JSON.stringify(result)}\n`))
    .catch((error) => {
      if (error && ["NO_DUE_SLOT", "DAILY_LIMIT_REACHED"].includes(error.code)) {
        const reason = error.code === "NO_DUE_SLOT" ? "no_due_slot" : "daily_limit_reached";
        process.stdout.write(`${JSON.stringify({ status: reason, reason })}\n`);
        return;
      }
      process.stderr.write(`${error.message}\n`);
      process.exitCode = 1;
    });
}

module.exports = {
  RUNNERS_BY_ACTION,
  runRotatingCarouselCanary,
  runAniccaLarryJaRotatingCanary,
  runAniccaEnAffirmationInstagramRotatingCanary,
  runAniccaEnAffirmationTikTokRotatingCanary,
  runAniccaEn2AffirmationTikTokRotatingCanary,
  runAniccaEnSlideshowTikTokRotatingCanary,
  runAniccaMainTikTokRotatingCanary,
  runAniccaJp1TikTokRotatingCanary,
  runAniccaBuddhaTikTokRotatingCanary,
};
