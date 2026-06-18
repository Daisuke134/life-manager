#!/usr/bin/env node
// ~/anicca/skills/life/ask/ask-local.js — the LOCAL ask consumer (self-contained, no aniccaai.com).
// Closes the loop: travel writes life-ask-queue.jsonl → this mails the question via gog Gmail →
// polls Gmail for the reply → writes the location back to the gcal event → clears travel state so
// the move block gets inserted next travel run. Send-channel == read-channel (both Gmail).
//   node ask-local.js --action question   # mail the queued questions
//   node ask-local.js --action poll        # ingest replies → register location
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const C = require("../config");

const GOG_ACCOUNT = C.profile.account();
const DAIS_EMAIL = C.profile.ownerEmail();
const QUEUE = process.env.LIFE_ASK_QUEUE || C.dataPath("life-ask-queue.jsonl");
const TRAVEL_STATE = C.dataPath("travel_filled.json");
const CAL_ID = C.profile.calId();
const { makeTransport } = require("../adapters/transport");
const T = makeTransport({
  account: GOG_ACCOUNT,
  keyring: C.env("GOG_KEYRING_PASSWORD"),
  calId: CAL_ID,
});

// ── pure (unit-tested) ─────────────────────────────────────────────────────────
function loadQueue(p) {
  p = p || QUEUE;
  let raw = ""; try { raw = fs.readFileSync(p, "utf8"); } catch { return []; }
  const byId = new Map();
  for (const line of raw.split("\n")) {
    const t = line.trim(); if (!t) continue;
    let r; try { r = JSON.parse(t); } catch { continue; } // tolerate corrupt/half lines
    if (!r.eventId) continue;
    byId.set(r.eventId, r); // latest record wins
  }
  return [...byId.values()];
}
function buildQuestionEmail(row) {
  const s = (row.summary || "予定").trim();
  const subject = `[Anicca] 場所を教えてください: ${s} [ASK-${row.eventId}]`;
  // Prefer the agent-crafted, user-specific question (reason "ask:<q>"); else the fixed template.
  const agentQ = typeof row.reason === "string" && row.reason.startsWith("ask:") ? row.reason.slice(4) : "";
  const why = row.reason === "no_route" ? "の移動経路が分かりませんでした" : "の場所が分かりませんでした";
  const ask = agentQ || `「${s}」${why}。\nこの予定はどこで行われますか？ 駅名や住所をこのメールに返信してください。`;
  const body = `${ask}\n\nEvent ID: ${row.eventId}`;
  return { subject, body };
}
const GREETING = /^(はい|うん|ok|okay|yes|了解|わかりました|承知|ありがとう|どうも|thanks?|thank you)[!！。.、,\s]*$/i;
function parseReply(subject, body) {
  const m = /\[ASK-([^\]]+)\]/.exec(subject || "");
  if (!m) return null;
  let location = "";
  for (const line of (body || "").split("\n")) {
    const t = line.trim();
    if (!t || t.startsWith(">") || /^On .*wrote:/.test(t) || /^Event ID:/i.test(t)) continue;
    if (GREETING.test(t)) continue; // skip a top-posted greeting ("はい！") — take the real answer line
    if (/[？?]\s*$/.test(t)) continue; // skip a question line (the bot's own prompt, echoed when same-account)
    location = t; break;
  }
  return { eventId: m[1], location };
}

// ── side-effecting (E2E) ───────────────────────────────────────────────────────
function gogSend({ to, subject, body }) { return T.mail.send({ to, subject, body }); }
function gogSearchReplyThreads() {
  try { return T.mail.search(`from:${DAIS_EMAIL} subject:"[ASK-" newer_than:7d`); } catch { return []; }
}
function gogGetBody(id) { try { return T.mail.getBody(id); } catch { return { subject: "", body: "" }; } }
function setEventLocation(eventId, location) {
  try { return T.calendar.updateLocation(eventId, location); }
  catch (e) { console.error("[ask] setEventLocation failed:", e.message); return false; }
}
function baseId(id) { return String(id || "").split("_")[0]; }  // strip recurring-event _2026..Z suffix
function clearTravelState(eventId) {
  let s; try { s = JSON.parse(fs.readFileSync(TRAVEL_STATE, "utf8")); } catch { return; }
  const b = baseId(eventId);
  let changed = false;
  for (const k of Object.keys(s)) {
    if (s[k] !== "asked") continue;  // only clear ASK-records (not inserted-block ids)
    if (k.split("|").some((h) => h === eventId || baseId(h) === b)) { delete s[k]; changed = true; }
  }
  if (changed) fs.writeFileSync(TRAVEL_STATE, JSON.stringify(s, null, 2));
}
function writeQueue(rows) {
  fs.mkdirSync(path.dirname(QUEUE), { recursive: true });
  fs.writeFileSync(QUEUE, rows.map((r) => JSON.stringify(r)).join("\n") + (rows.length ? "\n" : ""));
}

function runQuestions({ dryRun = false } = {}) {
  const rows = loadQueue();
  const sentIds = new Map();
  for (const r of rows) {
    if (r.asked) continue;
    const { subject, body } = buildQuestionEmail(r);
    if (dryRun) { console.log("[ask] would mail:", subject); continue; }
    sentIds.set(r.eventId, gogSend({ to: DAIS_EMAIL, subject, body }));
  }
  if (!dryRun && sentIds.size) {  // re-read to MERGE any rows travel appended meanwhile (no overwrite-race)
    const fresh = loadQueue();
    for (const r of fresh) if (sentIds.has(r.eventId)) { r.asked = true; r.messageId = sentIds.get(r.eventId); }
    writeQueue(fresh);
  }
  console.log(JSON.stringify({ action: "question", queued: rows.length, sent: sentIds.size }));
  return sentIds.size;
}
function runPoll({ dryRun = false } = {}) {
  const threads = gogSearchReplyThreads();
  const queuedIds = new Set(loadQueue().map((r) => r.eventId));
  const resolved = new Set();
  let registered = 0;
  for (const th of threads) {  // single pass per thread (no double gogGetBody)
    const { subject, body } = gogGetBody(th.id);
    const r = parseReply(subject || th.subject, body);
    if (!r || !r.location || !queuedIds.has(r.eventId)) continue;
    if (dryRun) { console.log("[ask] would register:", r.eventId, "→", r.location); continue; }
    if (setEventLocation(r.eventId, r.location)) { clearTravelState(r.eventId); resolved.add(r.eventId); registered++; }
  }
  if (!dryRun && resolved.size) writeQueue(loadQueue().filter((r) => !resolved.has(r.eventId)));  // re-read to merge appends
  console.log(JSON.stringify({ action: "poll", threads: threads.length, registered }));
  return registered;
}

module.exports = { loadQueue, buildQuestionEmail, parseReply, runQuestions, runPoll, baseId };

if (require.main === module) {
  const args = process.argv.slice(2);
  const action = args.includes("--action") ? args[args.indexOf("--action") + 1] : "question";
  const dryRun = args.includes("--dry-run");
  try { (action === "poll" ? runPoll : runQuestions)({ dryRun }); }
  catch (e) { console.error("[ask-local] fatal:", e.message); process.exit(1); }
}
