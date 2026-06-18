#!/usr/bin/env node
// ~/anicca/skills/life/call.js — B-call skill top-level entrypoint (spec27 WF-B B-call).
//
// This file provides the rubric-named flat path: ~/anicca/skills/life/call.js
// It re-exports the full implementation from the canonical location:
//   ~/anicca/skills/life/call/call.js
//
// Usage is identical to the canonical module:
//   node ~/anicca/skills/life/call.js                    place the real Charon call to Dais (Telnyx)
//   node ~/anicca/skills/life/call.js --provider twilio  use the Twilio carrier instead
//   node ~/anicca/skills/life/call.js --to +E164         override the destination
//   node ~/anicca/skills/life/call.js --dry-run          build the dial payload only, no side effects
//
// The canonical source (call/call.js) wires the products-repo Charon/Gemini bridge
// (call-logic.js + call-bridge.cjs + life-call*.mjs) to the chosen carrier. Telnyx is the
// default for +81 because Twilio fraud-control (error 21216) blocks +<YOUR_E164_NUMBER>.

"use strict";

// Delegate entirely to the canonical implementation so the flat shim and the
// subdirectory implementation never drift.
const canonical = require("./call/call");
module.exports = canonical;

// Run as CLI entrypoint: parse args and place the call via the canonical impl.
// (require.main is THIS shim, so call/call.js's own CLI block does not fire — we
// drive placeCall() directly here with the same flags.)
if (require.main === module) {
  const argv = process.argv.slice(2);
  const opts = { dryRun: argv.includes("--dry-run") };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--provider") opts.provider = argv[++i];
    else if (argv[i].startsWith("--provider=")) opts.provider = argv[i].split("=")[1];
    else if (argv[i] === "--to") opts.to = argv[++i];
    else if (argv[i].startsWith("--to=")) opts.to = argv[i].split("=")[1];
  }
  process.exit(canonical.placeCall(opts));
}
