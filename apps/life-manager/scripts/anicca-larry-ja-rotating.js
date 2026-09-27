#!/usr/bin/env node
"use strict";

// mobile-app-command.js (the shared dispatcher every mobile-app-loops.json
// entry goes through) requires the runner to be a .js file invoked as
// `node <runner> <action>` with no extra flags -- so a bash wrapper can't sit
// in front of anicca-larry-ja-canary.js for this owner. This thin entrypoint
// is the real integration point instead: it resolves a rotation-selected,
// automated-gate-approved pack for the current slot (generate-larry-slide-
// pack.js), feeds it into the JA Larry lane's existing env-var contract, and
// delegates straight to runAniccaCarouselCanary -- so every check already in
// anicca-larry-ja-canary.js / marketing-native-carousel-publication-adapter.js
// still runs unchanged at publish time.

const { resolveLarryJaSlot } = require("./generate-larry-slide-pack.js");
const { runAniccaCarouselCanary } = require("./anicca-larry-ja-canary.js");

const ACTION = "run-ja-larry-production";

async function runAniccaLarryJaRotatingCanary(argv = [], deps = {}) {
  if (argv.length !== 1 || argv[0] !== ACTION) {
    throw new Error(`usage: anicca-larry-ja-rotating.js ${ACTION}`);
  }
  const env = deps.env || process.env;
  const now = deps.now || (() => new Date().toISOString());
  const resolve = deps.resolveLarryJaSlot || resolveLarryJaSlot;
  const run = deps.runAniccaCarouselCanary || runAniccaCarouselCanary;

  const { slot, selected } = resolve({ env, now });
  const rotatedEnv = {
    ...env,
    LM_ANICCA_LARRY_JA_PACK_REF: selected.packRef,
    LM_ANICCA_LARRY_JA_MEDIA_REFS: JSON.stringify(selected.mediaRefs),
    LM_ANICCA_LARRY_JA_CAPTION_REF: selected.captionRef,
    LM_ANICCA_LARRY_JA_APPROVAL_REF: selected.approvalRef,
  };
  return run([ACTION, "--slot", slot], { ...deps, env: rotatedEnv, now });
}

if (require.main === module) {
  runAniccaLarryJaRotatingCanary(process.argv.slice(2))
    .then((result) => process.stdout.write(`${JSON.stringify(result)}\n`))
    .catch((error) => { process.stderr.write(`${error.message}\n`); process.exitCode = 1; });
}

module.exports = { runAniccaLarryJaRotatingCanary };
