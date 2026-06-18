#!/usr/bin/env node
// ~/anicca/skills/life/planner.js — schedule-based call planner (NOT polling).
// A thin cron runs this every ~10 min; it does NOT call. It lists gcal events and, for EVERY timed
// event × offset [15,10,5] whose fire time is still in the future, registers a one-shot
//   openclaw cron add --at <iso> --delete-after-run --tools exec
//     --message "Use exec to run: node call/call.js --event=<json> --urgency=<tone>"
// so the Charon call fires at the exact minute, names the event, and escalates (15 calm/10 firm/5 harsh).
// LEAVE time = the 🚆移動/[Travel] block that ENDS at the event start (travel included), else the event start.
// Idempotent by deterministic job name. No fixed guesses, no polling.
"use strict";
const path = require("node:path");
const { execFileSync } = require("node:child_process");
const C = require("./config");

const GOG_BIN = C.bins.gog();
const GOG_ACCOUNT = C.profile.account();
const { makeTransport } = require("./adapters/transport");
const CAL = makeTransport({
  bin: GOG_BIN,
  account: GOG_ACCOUNT,
  keyring: C.env("GOG_KEYRING_PASSWORD"),
}).calendar;
const OPENCLAW = C.bins.scheduler();
const AGENT = process.env.LIFE_AGENT_ID || "anicca";
const CALL_JS = path.join(__dirname, "call", "call.js");
const OFFSETS = (process.env.LIFE_SCHEDULE_OFFSETS || "15,10,5").split(",").map((s) => Number(s.trim())).filter((n) => Number.isFinite(n));
const HORIZON_DAYS = Number(process.env.LIFE_PLAN_HORIZON_DAYS || 2);
const TRAVEL_PREFIXES = ["🚆", "🚌", "🚶", "🚇", "移動", "[Travel] "];

// ── pure (unit-tested) ─────────────────────────────────────────────────────────
function toneFor(off) { return off >= 15 ? "calm" : off >= 10 ? "firm" : "harsh"; }
function isTravel(summary) { const s = (summary || "").trim(); return TRAVEL_PREFIXES.some((p) => s.startsWith(p)); }
function safeName(s) { return (s || "").replace(/[^A-Za-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 36) || "x"; }
function leaveTimeMs(ev, all) {
  const evStart = ev.start && ev.start.dateTime;
  if (!evStart) return null;
  const block = (all || []).find((e) => isTravel(e.summary) && e.end && e.end.dateTime === evStart);
  const iso = (block && block.start && block.start.dateTime) || evStart;
  return Date.parse(iso);
}

// ── side-effecting ─────────────────────────────────────────────────────────────
function listEvents() {
  const to = new Date(Date.now() + HORIZON_DAYS * 864e5).toISOString().slice(0, 10);
  let items;
  try { items = CAL.list({ from: "today", to, max: 250 }); }
  catch (e) { console.error("[plan] gog list failed:", e.message); return []; }
  return items.map((e) => ({ id: e.id, summary: e.summary || "", location: e.location || "", start: e.start || {}, end: e.end || {} }));
}
function existingJobNames() {
  try { const d = JSON.parse(execFileSync(OPENCLAW, ["cron", "list", "--json"], { timeout: 30000 }).toString()); const jobs = Array.isArray(d) ? d : (d.jobs || []); return new Set(jobs.map((j) => j && j.name).filter(Boolean)); } catch { return new Set(); }
}
function registerAt(name, fireIso, msg, dryRun) {
  if (dryRun) { console.log("[plan] would add", name, "@", fireIso, "->", msg.slice(0, 60)); return; }
  execFileSync(OPENCLAW, ["cron", "add", "--name", name, "--at", fireIso, "--delete-after-run", "--agent", AGENT, "--session", "isolated", "--wake", "now", "--tools", "exec", "--timeout-seconds", "180", "--message", msg], { timeout: 30000 });
}

function plan({ nowMs = Date.now(), dryRun = false } = {}) {
  const events = listEvents();
  const existing = existingJobNames();
  let added = 0;
  for (const ev of events) {
    try {
      const summary = (ev.summary || "").trim();
      if (isTravel(summary)) continue;          // skip travel blocks themselves
      if (!ev.start || !ev.start.dateTime) continue; // skip all-day
      const leaveMs = leaveTimeMs(ev, events);
      if (leaveMs == null) continue;
      const stamp = new Date(leaveMs).toISOString().slice(0, 16).replace(/[-:T]/g, "");
      const eventJson = JSON.stringify({ summary, start: ev.start, location: ev.location || "" });
      for (const off of OFFSETS) {
        const fireMs = leaveMs - off * 60000;
        if (fireMs <= nowMs) continue;          // already passed → no past --at
        const name = `life-call-${stamp}-${safeName(summary)}-${off}`;
        if (existing.has(name)) continue;       // idempotent
        const msg = `Use exec to run: node ${CALL_JS} --event=${JSON.stringify(eventJson)} --urgency=${toneFor(off)}`;
        registerAt(name, new Date(fireMs).toISOString(), msg, dryRun);
        added++;
      }
    } catch (e) { console.error("[plan] skip", (ev.summary || "").slice(0, 30), e.message); }
  }
  console.log(JSON.stringify({ action: "plan", events: events.length, scheduled: added }));
  return added;
}

module.exports = { toneFor, isTravel, safeName, leaveTimeMs, plan };

if (require.main === module) {
  try { plan({ dryRun: process.argv.includes("--dry-run") }); }
  catch (e) { console.error("[plan] fatal:", e.message); process.exit(1); }
}
