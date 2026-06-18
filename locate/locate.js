#!/usr/bin/env node
// ~/anicca/skills/life/locate/locate.js — B-locate skill (spec28 §2/§6 P-lm-local-calling).
//
// LOCAL Life Manager calling behaviour (the skill inside OSS Anicca, BYOK, local-run):
//
//   WITH Telegram Live Location (24/7 share → LIFE_DATA_DIR/location/<tg_user_id>.json):
//     The ONLY trigger is "are they MOVING?". Anicca keeps calling — regardless of whether a
//     prior call was answered — until the user has provably moved (>= MOVE_THRESHOLD_M from
//     the origin fix). Pickup never satisfies the stop condition; only motion does.
//
//   WITHOUT live location (no fresh fix on disk):
//     Schedule-based cadence relative to the next event's start: call at
//     T-15min, T-14min, T-13min, plus a T-5min EMERGENCY call. Four fires, deterministic.
//
// This module is PURE + node:test-covered for the two decision cores:
//   - scheduleDueCalls(...)  → which of the 15/14/13/5 fires are due now
//   - hasMoved(...)          → haversine motion gate that ends the keep-calling loop
// The side-effecting loop (runLiveLocationLoop / runScheduleLoop) wires those cores to
// call/call.js placeCall() (the real Telnyx↔Gemini-Charon bridge) and to the on-disk
// Telegram Live Location fix written by anicca-life-manager/scripts/telegram_bot.py.
//
// Prior art reused (verified live code):
//   ~/anicca/skills/life/call/call.js                                   → placeCall()
//   ~/anicca/skills/anicca-life-manager/scripts/lateness_check.py       → haversine_m / _user_moved / RELENTLESS loop
//   ~/anicca/skills/anicca-life-manager/scripts/telegram_bot.py         → location file schema {lat,lon,tst,received_at}
//
// Usage:
//   node locate.js                          auto: live-location loop if a fresh fix exists, else schedule loop
//   node locate.js --mode live              force the live-location keep-calling loop
//   node locate.js --mode schedule          force the 15/14/13+5 schedule cadence loop
//   node locate.js --event-start <iso>      next event start (schedule mode); default = +15min
//   node locate.js --dry-run                decide only; never place a real call

"use strict";

const path = require("path");
const fs = require("fs");

// The real carrier bridge (Telnyx → Gemini Live Charon). Pure shim; placeCall returns exit code.
const { placeCall } = require("../call/call");

// ── Config (env-overridable, mirrors lateness_check.py defaults) ──────────────

const C = require("../config");
const LOCATION_STATE_DIR = process.env.LIFE_LOCATION_DIR || C.dataPath("location");

// A live fix older than this many ms = sharing is OFF → fall back to schedule cadence.
const STALE_MS = Number(process.env.LIFE_LOCATION_STALE_MS || 10 * 60 * 1000); // 10 min
// Moved this far from the origin fix ⇒ "actually moving" ⇒ stop calling.
const MOVE_THRESHOLD_M = Number(process.env.LIFE_MOVE_THRESHOLD_M || 300);
// Schedule cadence offsets before the event start (minutes). 5 = EMERGENCY.
const SCHEDULE_OFFSETS_MIN = (process.env.LIFE_SCHEDULE_OFFSETS || "15,14,13,5")
  .split(",").map((s) => Number(s.trim())).filter((n) => Number.isFinite(n));
const EMERGENCY_OFFSET_MIN = Number(process.env.LIFE_EMERGENCY_OFFSET_MIN || 5);
// Live-location loop: gap between re-dials while the user is NOT moving.
const LIVE_GAP_MS = Number(process.env.LIFE_LIVE_GAP_MS || 120 * 1000); // 2 min
const LIVE_MAX_ATTEMPTS = Number(process.env.LIFE_LIVE_MAX_ATTEMPTS || 30);
// Schedule loop poll granularity.
const SCHEDULE_TICK_MS = Number(process.env.LIFE_SCHEDULE_TICK_MS || 30 * 1000);

// ── Pure geometry (verbatim port of lateness_check.haversine_m) ───────────────

/**
 * Great-circle distance in metres between two WGS84 points.
 * @returns {number} metres
 */
function haversineM(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = (d) => (d * Math.PI) / 180;
  const p1 = toRad(lat1);
  const p2 = toRad(lat2);
  const dp = toRad(lat2 - lat1);
  const dl = toRad(lon2 - lon1);
  const a =
    Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(a));
}

/**
 * Motion gate — the ONLY stop condition for the live-location keep-calling loop.
 * Port of lateness_check._user_moved: true iff displacement >= thresholdM.
 * @param {{lat:number,lon:number}|null} origin
 * @param {{lat:number,lon:number}|null} fresh
 * @param {number} thresholdM
 * @returns {boolean}
 */
function hasMoved(origin, fresh, thresholdM = MOVE_THRESHOLD_M) {
  if (!origin || !fresh) return false;
  if (
    typeof origin.lat !== "number" || typeof origin.lon !== "number" ||
    typeof fresh.lat !== "number" || typeof fresh.lon !== "number"
  ) return false;
  return haversineM(origin.lat, origin.lon, fresh.lat, fresh.lon) >= thresholdM;
}

// ── Pure cadence (the 15/14/13 + 5-EMERGENCY schedule core) ───────────────────

/**
 * Decide which schedule calls are due at `nowMs` for an event starting at `eventStartMs`.
 *
 * Fires once per offset: at each offset O (minutes before start), the call is "due" when
 * now is in the 1-minute window [start - O, start - O + tickMs). `already` lists offsets
 * already fired so the loop never double-dials the same slot. The 5-min slot is flagged
 * `emergency:true`.
 *
 * @param {object} o
 * @param {number} o.nowMs
 * @param {number} o.eventStartMs
 * @param {number[]} [o.offsetsMin]   default [15,14,13,5]
 * @param {number} [o.emergencyMin]   default 5
 * @param {number[]} [o.already]      offsets already fired
 * @param {number} [o.tickMs]         window width; default = SCHEDULE_TICK_MS
 * @returns {Array<{offsetMin:number, emergency:boolean}>} due calls (may be empty)
 */
function scheduleDueCalls(o) {
  const {
    nowMs, eventStartMs,
    offsetsMin = SCHEDULE_OFFSETS_MIN,
    emergencyMin = EMERGENCY_OFFSET_MIN,
    already = [],
    tickMs = SCHEDULE_TICK_MS,
  } = o;
  const due = [];
  for (const offMin of offsetsMin) {
    if (already.includes(offMin)) continue;
    const fireAt = eventStartMs - offMin * 60_000;
    if (nowMs >= fireAt && nowMs < fireAt + tickMs) {
      due.push({ offsetMin: offMin, emergency: offMin === emergencyMin });
    }
  }
  return due;
}

/**
 * Full ordered schedule plan for an event (for inspection / --dry-run): the absolute
 * epoch-ms each of the 15/14/13/5 calls should fire at.
 * @returns {Array<{offsetMin:number, fireAtMs:number, emergency:boolean}>}
 */
function schedulePlan(eventStartMs, offsetsMin = SCHEDULE_OFFSETS_MIN, emergencyMin = EMERGENCY_OFFSET_MIN) {
  return offsetsMin
    .map((offMin) => ({ offsetMin: offMin, fireAtMs: eventStartMs - offMin * 60_000, emergency: offMin === emergencyMin }))
    .sort((a, b) => a.fireAtMs - b.fireAtMs);
}

// ── Live Location IO (reads telegram_bot.py's on-disk fixes) ──────────────────

/**
 * Read the freshest Telegram Live Location fix, or null if none / all stale.
 * Mirrors lateness_check.get_location: bare <telegram_user_id>.json files (all-digit stem),
 * freshest by mtime, staleness judged on received_at (bot heartbeat).
 * @param {object} [opts]
 * @param {string} [opts.dir]      override LOCATION_STATE_DIR
 * @param {number} [opts.staleMs]  override STALE_MS
 * @param {number} [opts.nowMs]    override Date.now (tests)
 * @returns {{lat:number, lon:number, tst:number, age_ms:number}|null}
 */
function readLiveLocation(opts = {}) {
  const dir = opts.dir || LOCATION_STATE_DIR;
  const staleMs = opts.staleMs == null ? STALE_MS : opts.staleMs;
  const nowMs = opts.nowMs == null ? Date.now() : opts.nowMs;
  let files;
  try {
    files = fs.readdirSync(dir)
      .filter((f) => /^\d+\.json$/.test(f))
      .map((f) => path.join(dir, f))
      .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs);
  } catch {
    return null; // dir missing = no sharing
  }
  if (files.length === 0) return null;
  let rec;
  try {
    rec = JSON.parse(fs.readFileSync(files[0], "utf8"));
  } catch {
    return null;
  }
  if (typeof rec.lat !== "number" || typeof rec.lon !== "number") return null;
  const signalTs = (rec.received_at || rec.tst); // seconds (telegram_bot.py writes epoch seconds)
  const ageMs = nowMs - signalTs * 1000;
  if (ageMs > staleMs) return null; // sharing died / stopped → caller falls back to schedule
  return { lat: rec.lat, lon: rec.lon, tst: signalTs, age_ms: ageMs };
}

// ── Side-effecting call helper ────────────────────────────────────────────────

function dialOnce({ dryRun, reason }) {
  if (dryRun) {
    console.log(JSON.stringify({ event: "would-call", reason }));
    return 0;
  }
  console.log(JSON.stringify({ event: "calling", reason }));
  return placeCall({});
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ── Loop 1: WITH live location — keep calling until MOVING ────────────────────

/**
 * Keep calling until the user provably moves (>= MOVE_THRESHOLD_M from the first fix).
 * Pickup does NOT stop the loop — only motion does. Returns when moved or attempts spent.
 * Injectable deps make it unit-testable; defaults wire to the real IO + carrier.
 */
async function runLiveLocationLoop(opts = {}) {
  const dryRun = !!opts.dryRun;
  const thresholdM = opts.thresholdM == null ? MOVE_THRESHOLD_M : opts.thresholdM;
  const maxAttempts = opts.maxAttempts == null ? LIVE_MAX_ATTEMPTS : opts.maxAttempts;
  const gapMs = opts.gapMs == null ? LIVE_GAP_MS : opts.gapMs;
  const getLoc = opts.getLocation || readLiveLocation;
  const dial = opts.dial || dialOnce;
  const wait = opts.sleep || sleep;

  const origin = getLoc();
  if (!origin) return { stopped: "no-location", attempts: 0 };

  let attempts = 0;
  while (attempts < maxAttempts) {
    const fresh = getLoc();
    if (hasMoved(origin, fresh, thresholdM)) {
      return { stopped: "moved", attempts };
    }
    dial({ dryRun, reason: `not-moving (attempt ${attempts + 1})` });
    attempts += 1;
    if (attempts >= maxAttempts) break;
    await wait(gapMs);
  }
  // Re-check after the final dial so a last-moment move is still honoured.
  if (hasMoved(origin, getLoc(), thresholdM)) return { stopped: "moved", attempts };
  return { stopped: "max-attempts", attempts };
}

// ── Loop 2: WITHOUT live location — 15/14/13 + 5-EMERGENCY ─────────────────────

/**
 * Schedule cadence: fire 15/14/13-min-before + a 5-min EMERGENCY call, each once.
 * Returns when all four offsets have fired (or the event has clearly passed).
 */
async function runScheduleLoop(opts = {}) {
  const dryRun = !!opts.dryRun;
  const eventStartMs = opts.eventStartMs;
  const offsetsMin = opts.offsetsMin || SCHEDULE_OFFSETS_MIN;
  const emergencyMin = opts.emergencyMin == null ? EMERGENCY_OFFSET_MIN : opts.emergencyMin;
  const tickMs = opts.tickMs == null ? SCHEDULE_TICK_MS : opts.tickMs;
  const now = opts.now || (() => Date.now());
  const dial = opts.dial || dialOnce;
  const wait = opts.sleep || sleep;

  const fired = [];
  // Run until every offset has fired or we are well past the last (smallest-offset) fire time.
  const lastFireMs = eventStartMs - Math.min(...offsetsMin) * 60_000;
  while (fired.length < offsetsMin.length) {
    const nowMs = now();
    const due = scheduleDueCalls({ nowMs, eventStartMs, offsetsMin, emergencyMin, already: fired, tickMs });
    for (const d of due) {
      dial({ dryRun, reason: `T-${d.offsetMin}min${d.emergency ? " EMERGENCY" : ""}` });
      fired.push(d.offsetMin);
    }
    if (fired.length >= offsetsMin.length) break;
    if (nowMs > lastFireMs + tickMs) break; // event passed; stop waiting forever
    await wait(tickMs);
  }
  return { fired };
}

// ── CLI ───────────────────────────────────────────────────────────────────────

function parseArgs(argv) {
  const opts = { dryRun: argv.includes("--dry-run") };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--mode") opts.mode = argv[++i];
    else if (argv[i].startsWith("--mode=")) opts.mode = argv[i].split("=")[1];
    else if (argv[i] === "--event-start") opts.eventStart = argv[++i];
    else if (argv[i].startsWith("--event-start=")) opts.eventStart = argv[i].split("=")[1];
  }
  return opts;
}

async function main(argv) {
  const opts = parseArgs(argv);
  const live = readLiveLocation();
  const mode = opts.mode || (live ? "live" : "schedule");

  if (mode === "live") {
    const r = await runLiveLocationLoop({ dryRun: opts.dryRun });
    console.log(JSON.stringify({ ok: true, mode: "live", ...r }));
    return 0;
  }
  const eventStartMs = opts.eventStart
    ? new Date(opts.eventStart).getTime()
    : Date.now() + 15 * 60_000;
  const r = await runScheduleLoop({ dryRun: opts.dryRun, eventStartMs });
  console.log(JSON.stringify({ ok: true, mode: "schedule", ...r }));
  return 0;
}

module.exports = {
  haversineM,
  hasMoved,
  scheduleDueCalls,
  schedulePlan,
  readLiveLocation,
  runLiveLocationLoop,
  runScheduleLoop,
  MOVE_THRESHOLD_M,
  SCHEDULE_OFFSETS_MIN,
  EMERGENCY_OFFSET_MIN,
};

if (require.main === module) {
  main(process.argv.slice(2))
    .then((code) => process.exit(code))
    .catch((err) => {
      console.error("[locate] fatal:", err.message);
      process.exit(1);
    });
}
