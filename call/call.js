#!/usr/bin/env node
// ~/anicca/skills/life/call/call.js — B-call skill entrypoint (spec27 WF-B B-call).
//
// Anicca phones the user (Dais, +<YOUR_E164_NUMBER>) ~15 min before each calendar event and
// talks two-way via Gemini Live (voice = Charon, male) bridged over the carrier's Media
// Streaming. The hard, bug-prone parts (μ-law↔PCM transcode + exact wire shapes) live in
// the products repo as pure, tested logic; this skill wires them to a carrier + Gemini.
//
// Provider-agnostic: the SAME Charon/Gemini bridge serves Twilio AND Telnyx. Telnyx is the
// default for +81 because Twilio fraud-control (error 21216) permanently blocks
// +<YOUR_E164_NUMBER> (JP geo-permissions are fully enabled — the block is account+destination
// fraud control that lifts only via an async Support ticket). Telnyx's outbound profile
// "anicca-out" has JP whitelisted and can legally dial +81.
// Design: docs/superpowers/specs/2026-06-16-life-call-telnyx-charon-design.md (products repo).
//
// Pure logic source of truth (products repo, node:test-covered):
//   apps/landing/netlify/functions/_lib/call-logic.js
//     buildGeminiSetup / buildGeminiAudioInput / parseGeminiAudio  (Gemini Live, Charon)
//     twilioMuLawToGeminiPcm16 / geminiPcm24ToTwilioMuLaw          (G.711 ↔ PCM16/24)
//     buildTwilioMediaFrame / buildConnectStreamTwiml              (Twilio path)
//     buildTelnyxMediaFrame / parseTelnyxStart / telnyxDialBody    (Telnyx path)
//
// Executable runners (products repo) that place the REAL call + record it:
//   apps/landing/scripts/call-bridge.cjs       --provider twilio|telnyx
//   apps/landing/scripts/life-call.mjs         (Twilio)
//   apps/landing/scripts/life-call-telnyx.mjs  (Telnyx — the +81 path to Dais)
//
// Usage:
//   node ~/anicca/skills/life/call.js                       place the real Charon call to Dais (Telnyx)
//   node ~/anicca/skills/life/call.js --provider twilio     use the Twilio carrier instead
//   node ~/anicca/skills/life/call.js --to +E164            override the destination
//   node ~/anicca/skills/life/call.js --dry-run             build the dial payload only, no side effects

"use strict";

const path = require("path");
const fs = require("fs");
const { spawnSync } = require("child_process");
const C = require("../config");

// Merge Life Manager env into process.env so a cron-fired call has TELNYX/GEMINI/GOG keys even if the
// executor didn't inject them. Does NOT overwrite already-set vars.
for (const [k, v] of Object.entries(C.ENV)) {
  if (process.env[k] === undefined) process.env[k] = v;
}

/** Map a provider name to its in-repo runner (consolidated into skills/life/call/lib). */
function runnerFor(provider) {
  const lib = path.join(__dirname, "lib");
  return String(provider).toLowerCase() === "twilio"
    ? path.join(lib, "runner-twilio.mjs")
    : path.join(lib, "runner-telnyx.mjs"); // default: Telnyx (+81 / Dais)
}

/**
 * Place the real Charon call by delegating to the products-repo runner.
 * @param {object} [opts]
 * @param {string} [opts.provider="telnyx"] - "telnyx" | "twilio"
 * @param {string} [opts.to] - E.164 destination (default = the runner's Dais number)
 * @param {boolean} [opts.dryRun=false]
 * @returns {number} the runner's exit code
 */
function placeCall(opts = {}) {
  const provider = opts.provider || process.env.LIFE_CALL_PROVIDER || "telnyx";
  const runner = runnerFor(provider);
  const args = [runner];
  if (opts.to) args.push(`--to=${opts.to}`);
  if (opts.event) args.push(`--event=${JSON.stringify(opts.event)}`);
  if (opts.urgency) args.push(`--urgency=${opts.urgency}`);
  if (opts.dryRun) args.push("--dry-run");
  // Capture the runner's full output to a log so a GATEWAY-context call is debuggable
  // (the gateway exec doesn't surface stdout). Also tee to our own stdout.
  const logPath = C.dataPath("life-call.log");
  let logFd = null;
  try { fs.mkdirSync(path.dirname(logPath), { recursive: true }); logFd = fs.openSync(logPath, "a"); } catch { /* logging optional */ }
  if (logFd != null) fs.writeSync(logFd, `\n===== ${new Date().toISOString()} call to=${opts.to || "default"} urgency=${opts.urgency || "-"} PATH=${process.env.PATH || ""} TELNYX=${process.env.TELNYX_API_KEY ? "y" : "n"} GEMINI=${process.env.GEMINI_API_KEY ? "y" : "n"} =====\n`);
  const r = spawnSync("node", args, { stdio: ["ignore", logFd != null ? logFd : "inherit", logFd != null ? logFd : "inherit"], env: process.env });
  if (logFd != null) { try { fs.writeSync(logFd, `===== exit ${r.status} =====\n`); fs.closeSync(logFd); } catch { /* */ } }
  return r.status == null ? 1 : r.status;
}

module.exports = { placeCall, runnerFor };

// CLI: parse --provider/--to/--dry-run and place the call.
if (require.main === module) {
  const argv = process.argv.slice(2);
  const opts = { dryRun: argv.includes("--dry-run") };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--provider") opts.provider = argv[++i];
    else if (argv[i].startsWith("--provider=")) opts.provider = argv[i].split("=")[1];
    else if (argv[i] === "--to") opts.to = argv[++i];
    else if (argv[i].startsWith("--to=")) opts.to = argv[i].split("=")[1];
    else if (argv[i].startsWith("--event=")) opts.event = JSON.parse(argv[i].slice("--event=".length));
    else if (argv[i].startsWith("--urgency=")) opts.urgency = argv[i].slice("--urgency=".length);
  }
  process.exit(placeCall(opts));
}
