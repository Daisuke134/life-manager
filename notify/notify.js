#!/usr/bin/env node
// ~/anicca/skills/life/notify/notify.js
// B-notify skill entrypoint — spec27 WF-B B-notify (email-only approval gate).
//
// Two modes (selected by first CLI arg or NOTIFY_MODE env var):
//
//   node notify.js scan   (default)
//     1. List today's GCal events via `gog` CLI
//     2. detectLateRiskEvents — events with a started [Travel] block
//     3. For each at-risk event:
//        a. Build draft message body (buildAttendeeDraft)
//        b. Save draft to AgentMail Drafts (durable hold)
//        c. Send approval email to owner (buildApprovalEmail)
//     Exits 0 if OK (even when 0 late risks found).
//
//   node notify.js webhook --draftId <id> --reply <text>
//     1. extractApproval from reply text
//     2. If approved: fetch draft from AgentMail → send to attendees
//     Exits 0 on success, 1 on error.
//
// Env (resolved via config.js: LIFE_ENV_FILE / repo-local ./.env / process.env):
//   AGENTMAIL_API_KEY      — required (AgentMail bearer token)
//   AGENTMAIL_INBOX_ID     — required (e.g. anicca-genesis@agentmail.to)
//   OWNER_EMAIL            — required (recipient of approval email, e.g. you@example.com)
//   GOG_KEYRING_PASSWORD   — required for GCal via gog CLI
//   GOG_ACCOUNT            — Google account (default: you@example.com)
//   GCAL_ID                — Calendar ID (default: primary)
//
// This skill is the local Anicca body implementation; the matching Netlify
// function (apps/landing/netlify/functions/life-notify.js) runs the same
// business logic (notify-logic.js) in the cloud, triggered by heartbeat POSTs.
//
// Pattern mirrors ~/anicca/skills/life/travel/travel.js (proven WF-B template).

"use strict";

const path = require("path");
const fs = require("fs");

// ── Config ──────────────────────────────────────────────────────────────────

const TRAVEL_PREFIX = "[Travel] ";
const AGENTMAIL_BASE = "https://api.agentmail.to/v0";
const C = require("../config");
const ENV = C.ENV;
const GOG_BIN = C.bins.gog();
const AGENTMAIL_API_KEY = process.env.AGENTMAIL_API_KEY || ENV.AGENTMAIL_API_KEY || "";
const AGENTMAIL_INBOX_ID = process.env.AGENTMAIL_INBOX_ID || ENV.AGENTMAIL_INBOX_ID || "";
const OWNER_EMAIL = C.env("OWNER_EMAIL") || C.profile.ownerEmail();
const GOG_ACCOUNT = C.profile.account();
const GOG_KEYRING_PASSWORD = C.env("GOG_KEYRING_PASSWORD");
const GCAL_ID = C.profile.calId();
const { makeTransport } = require("../adapters/transport");
const T = makeTransport({ bin: GOG_BIN, account: GOG_ACCOUNT, keyring: GOG_KEYRING_PASSWORD, calId: GCAL_ID });

// Late detection: a grace window so we don't nag the instant the travel block starts, plus a real
// motion gate (if the user already left home, they are NOT late). Falls back to grace+clock when
// no live location is available.
const GRACE_MS = Number(process.env.LIFE_LATE_GRACE_MIN || ENV.LIFE_LATE_GRACE_MIN || 5) * 60000;
const HOME = {
  lat: Number(process.env.HOME_LAT || ENV.HOME_LAT || 35.67988),
  lon: Number(process.env.HOME_LON || ENV.HOME_LON || 139.723692),
};
let locate = null;
try { locate = require("../locate/locate"); } catch { /* motion gate optional */ }

// Transport: "agentmail" (default, legacy) or "gog" (Gmail via gog CLI — spec mandate).
const NOTIFY_TRANSPORT = (process.env.NOTIFY_TRANSPORT || ENV.NOTIFY_TRANSPORT || "agentmail").toLowerCase();
// Safety: when set, EVERY stakeholder send is redirected here (round-trip test without
// emailing a real third party). Approval email to OWNER is unaffected.
const NOTIFY_TEST_STAKEHOLDER = process.env.NOTIFY_TEST_STAKEHOLDER || ENV.NOTIFY_TEST_STAKEHOLDER || "";

// Durable store of pending approvals for the gog path (token -> {to,subject,body}).
// Computed lazily so tests can isolate it via a temp HOME.
function pendingPath() {
  return C.dataPath("life-notify-pending.jsonl");
}

// ── Pure logic (mirrors notify-logic.js in the Netlify function) ─────────────

// Short, mailbox-searchable token embedded in the approval email subject so a
// later reply (which Gmail prefixes with "Re: <subject>") can be matched back.
function approvalToken(seed) {
  return "AN-" + require("crypto").createHash("sha1")
    .update(String(seed) + ":" + Date.now()).digest("hex").slice(0, 8).toUpperCase();
}

// Extract an AN-XXXXXXXX token from a (reply) subject line, or null.
function tokenFromSubject(subject) {
  const m = (subject || "").match(/\[(AN-[0-9A-F]{8})\]/);
  return m ? m[1] : null;
}

function appendPending(rec, p = pendingPath()) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.appendFileSync(p, JSON.stringify(rec) + "\n");
}

function findPending(token, p = pendingPath()) {
  if (!fs.existsSync(p)) return null;
  const lines = fs.readFileSync(p, "utf8").trim().split("\n").filter(Boolean);
  for (const l of lines) {
    try { const r = JSON.parse(l); if (r.token === token && !r.sent) return r; } catch {}
  }
  return null;
}

function markSent(token, p = pendingPath()) {
  if (!fs.existsSync(p)) return;
  const lines = fs.readFileSync(p, "utf8").trim().split("\n").filter(Boolean);
  const out = lines.map((l) => {
    try { const r = JSON.parse(l); if (r.token === token) r.sent = true; return JSON.stringify(r); }
    catch { return l; }
  });
  fs.writeFileSync(p, out.join("\n") + "\n");
}

/**
 * Returns true if a GCal event summary is an auto-inserted travel block.
 * @param {string} summary
 * @returns {boolean}
 */
function isTravelBlock(summary) {
  return typeof summary === "string" && summary.startsWith(TRAVEL_PREFIX);
}

/**
 * Returns true when a travel block has already started (late-risk).
 * @param {{ travelStartMs: number, nowMs: number }} opts
 * @returns {boolean}
 */
function isLateRisk({ travelStartMs, nowMs, graceMs = GRACE_MS, moved = false }) {
  if (moved) return false;                       // they already left → not late, never nag
  return nowMs > travelStartMs + graceMs;        // only after the grace window, not the instant it starts
}

/**
 * Given today's GCal events and current time, return late-risk events:
 * those with a matching [Travel] block that has already started.
 * @param {Array<object>} events
 * @param {number} nowMs
 * @returns {Array<{event: object, travelEvent: object, isLate: boolean}>}
 */
function detectLateRiskEvents(events, nowMs) {
  if (!Array.isArray(events)) return [];

  const travelBlocks = new Map();
  for (const e of events) {
    if (!e.start || !e.start.dateTime) continue;
    if (!isTravelBlock(e.summary || "")) continue;
    const dest = (e.summary || "").slice(TRAVEL_PREFIX.length).trim();
    travelBlocks.set(dest, e);
  }

  const risks = [];
  for (const e of events) {
    if (!e.start || !e.start.dateTime) continue;
    if (isTravelBlock(e.summary || "")) continue;

    const title = (e.summary || "").trim();
    const travelBlock = travelBlocks.get(title);
    if (!travelBlock) continue;

    const travelStartMs = new Date(travelBlock.start.dateTime).getTime();
    // real motion gate: if a fresh live location shows the user already left home, they're not late
    let moved = false;
    try {
      const live = locate && locate.readLiveLocation ? locate.readLiveLocation() : null;
      moved = !!(live && locate.hasMoved(HOME, live));
    } catch { /* no live location → fall back to grace+clock */ }
    if (isLateRisk({ travelStartMs, nowMs, moved })) {
      risks.push({ event: e, travelEvent: travelBlock, isLate: true });
    }
  }
  return risks;
}

/**
 * Estimate minutes late (clamped ≥5, rounded to nearest 5).
 * @param {{ travelStartMs: number, nowMs: number }} opts
 * @returns {number}
 */
function estimateMinutesLate({ travelStartMs, nowMs }) {
  const diff = Math.round((nowMs - travelStartMs) / 60_000);
  const clamped = Math.max(5, diff);
  return Math.round(clamped / 5) * 5;
}

/**
 * Build the short draft message to send to attendees.
 * @param {{ eventSummary: string, minutesLate: number }} opts
 * @returns {string}
 */
function buildAttendeeDraft({ eventSummary, minutesLate }) {
  return (
    `I'll be approximately ${minutesLate} minutes late to "${eventSummary}". ` +
    `Apologies for the short notice — I'm on my way.`
  );
}

/**
 * Build the approval email body for the calendar owner.
 * @param {{ ownerEmail, eventSummary, attendees, draftBody, draftId }} opts
 * @returns {{ to, subject, body }}
 */
function buildApprovalEmail({ ownerEmail, eventSummary, attendees, draftBody, draftId }) {
  const recipientList =
    attendees && attendees.length > 0
      ? attendees.map((a) => a.email).join(", ")
      : "(no attendees found — reply OK to dismiss)";

  const subject = `[Anicca] Late alert for "${eventSummary}" — reply OK to notify`;

  const body = [
    `You appear to be running late for: "${eventSummary}"`,
    ``,
    `Anicca will send the following to: ${recipientList}`,
    ``,
    `───────────────────────────────`,
    draftBody,
    `───────────────────────────────`,
    ``,
    `Reply "OK" to this email to approve and send.`,
    `Reply anything else (or ignore) to cancel.`,
    ``,
    `Draft ID: ${draftId}`,
    `Powered by Anicca B-notify (spec27)`,
  ].join("\n");

  return { to: ownerEmail, subject, body };
}

/**
 * Parse an inbound reply body to determine if the owner approved.
 * Accepts: "ok", "ok!", "ok,", "ok " (case-insensitive), "はい".
 * @param {string} replyBody
 * @returns {boolean}
 */
function extractApproval(replyBody) {
  if (typeof replyBody !== "string") return false;
  const trimmed = replyBody.trim();
  const lower = trimmed.toLowerCase();
  // accept a realistic approval vocabulary (EN + JA), at the start of the reply
  if (/^(ok\b|okay\b|yes\b|yep\b|go\b|sure\b|approve)/.test(lower)) return true;
  if (/^(はい|うん|いいよ|了解|承知|送って|送信|おk|オッケー|オーケー|ヨシ|よし|お願い)/.test(trimmed)) return true;
  return false;
}

// ── GCal via gog CLI ─────────────────────────────────────────────────────────

// All GCal/Gmail I/O goes through the Life Manager transport adapter (local=gog / cloud=composio).
function listTodayEvents() {
  const today = new Date().toISOString().slice(0, 10);
  return T.calendar.list({ from: today, to: today, max: 250 });  // +--max 250 (safe; 1-day window)
}
function gogGmailSend({ to, subject, body }) { T.mail.send({ to, subject, body }); }  // +--json (return ignored)
function gogGmailSearch(query) { return T.mail.search(query); }  // [{id,subject}]; callers use .id/.subject
function gogGmailBody(threadId) { return T.mail.getBody(threadId).body; }  // unwrap to STRING (prior contract)

// ── AgentMail REST helpers ─────────────────────────────────────────────────

/** Headers for all AgentMail REST calls */
function amHeaders() {
  return {
    Authorization: `Bearer ${AGENTMAIL_API_KEY}`,
    "Content-Type": "application/json",
  };
}

/**
 * Save a draft to AgentMail Drafts.
 * @param {{ to, subject, body }} draft
 * @returns {Promise<{ id: string }>}
 */
async function saveAgentMailDraft({ to, subject, body }) {
  const url = `${AGENTMAIL_BASE}/inboxes/${encodeURIComponent(AGENTMAIL_INBOX_ID)}/drafts`;
  const r = await fetch(url, {
    method: "POST",
    headers: amHeaders(),
    body: JSON.stringify({ to, subject, body }),
  });
  if (!r.ok) {
    const msg = await r.text();
    throw new Error(`AgentMail draft save ${r.status}: ${msg}`);
  }
  return r.json();
}

/**
 * Send a message directly via AgentMail.
 * @param {{ to, subject, body }} msg
 * @returns {Promise<{ id: string }>}
 */
async function sendAgentMailEmail({ to, subject, body }) {
  const url = `${AGENTMAIL_BASE}/inboxes/${encodeURIComponent(AGENTMAIL_INBOX_ID)}/messages/send`;
  const r = await fetch(url, {
    method: "POST",
    headers: amHeaders(),
    body: JSON.stringify({ to, subject, body }),
  });
  if (!r.ok) {
    const msg = await r.text();
    throw new Error(`AgentMail send ${r.status}: ${msg}`);
  }
  return r.json();
}

/**
 * Fetch a saved draft by ID.
 * @param {string} draftId
 * @returns {Promise<{ id, to, subject, body }>}
 */
async function getAgentMailDraft(draftId) {
  const url = `${AGENTMAIL_BASE}/inboxes/${encodeURIComponent(AGENTMAIL_INBOX_ID)}/drafts/${encodeURIComponent(draftId)}`;
  const r = await fetch(url, { headers: amHeaders() });
  if (!r.ok) {
    const msg = await r.text();
    throw new Error(`AgentMail draft get ${r.status}: ${msg}`);
  }
  return r.json();
}

// ── Scan mode ─────────────────────────────────────────────────────────────────

async function runScan() {
  // Validate required env
  if (!OWNER_EMAIL) throw new Error("OWNER_EMAIL is required");
  if (NOTIFY_TRANSPORT !== "gog") {
    if (!AGENTMAIL_API_KEY) throw new Error("AGENTMAIL_API_KEY is required");
    if (!AGENTMAIL_INBOX_ID) throw new Error("AGENTMAIL_INBOX_ID is required");
  }

  const events = listTodayEvents();
  const nowMs = Date.now();
  const risks = detectLateRiskEvents(events, nowMs);

  if (risks.length === 0) {
    console.log(JSON.stringify({ ok: true, scanned: events.length, lateRisks: 0, alerted: [] }));
    return;
  }

  const alerted = [];
  for (const { event: ev, travelEvent } of risks) {
    const travelStartMs = new Date(travelEvent.start.dateTime).getTime();
    const minutesLate = estimateMinutesLate({ travelStartMs, nowMs });
    const attendees = ev.attendees || [];
    const attendeeEmails = attendees.map((a) => a.email).filter(Boolean);
    const draftTo = attendeeEmails.length > 0 ? attendeeEmails.join(",") : OWNER_EMAIL;

    const stakeholderTo = NOTIFY_TEST_STAKEHOLDER || draftTo;   // G5 safety redirect
    const draftBody = buildAttendeeDraft({ eventSummary: ev.summary, minutesLate });

    if (NOTIFY_TRANSPORT === "gog") {
      const token = approvalToken(ev.summary + stakeholderTo);
      appendPending({ token, to: stakeholderTo, subject: `Update re "${ev.summary}"`, body: draftBody, sent: false, ts: Date.now() });
      const subject = `[Anicca] Late alert for "${ev.summary}" — reply OK to notify [${token}]`;
      const body = [
        `You appear to be running late for: "${ev.summary}".`,
        ``, `Anicca will send the following to: ${stakeholderTo}`,
        ``, `──────────`, draftBody, `──────────`,
        ``, `Reply "OK" to this email to approve and send.`,
        `Approval token: ${token}`,
      ].join("\n");
      gogGmailSend({ to: OWNER_EMAIL, subject, body });   // approval email to Dais via Gmail
      alerted.push({ event: ev.summary, token, minutesLate, transport: "gog" });
      continue;
    }
    // else: legacy AgentMail path (unchanged below)

    let draft;
    try {
      draft = await saveAgentMailDraft({
        to: draftTo,
        subject: `Late notice for "${ev.summary}"`,
        body: draftBody,
      });
    } catch (err) {
      console.error(`[notify] draft save failed for "${ev.summary}":`, err.message);
      alerted.push({ error: `draft_save: ${err.message}`, event: ev.summary });
      continue;
    }

    const approvalEmail = buildApprovalEmail({
      ownerEmail: OWNER_EMAIL,
      eventSummary: ev.summary,
      attendees,
      draftBody,
      draftId: draft.id,
    });

    try {
      await sendAgentMailEmail({
        to: approvalEmail.to,
        subject: approvalEmail.subject,
        body: approvalEmail.body,
      });
      alerted.push({ event: ev.summary, draftId: draft.id, minutesLate });
    } catch (err) {
      console.error(`[notify] approval email failed for "${ev.summary}":`, err.message);
      alerted.push({ error: `approval_send: ${err.message}`, event: ev.summary });
    }
  }

  const result = { ok: true, scanned: events.length, lateRisks: risks.length, alerted };
  console.log(JSON.stringify(result));
}

// ── Webhook mode ──────────────────────────────────────────────────────────────

async function runWebhook(args) {
  if (!AGENTMAIL_API_KEY) throw new Error("AGENTMAIL_API_KEY is required");
  if (!AGENTMAIL_INBOX_ID) throw new Error("AGENTMAIL_INBOX_ID is required");

  // Parse --draftId and --reply from CLI args
  const draftIdIdx = args.indexOf("--draftId");
  const replyIdx = args.indexOf("--reply");
  if (draftIdIdx === -1 || replyIdx === -1) {
    throw new Error("webhook mode requires --draftId <id> --reply <text>");
  }
  const draftId = args[draftIdIdx + 1];
  const replyBody = args[replyIdx + 1];

  if (!draftId || !replyBody) {
    throw new Error("--draftId and --reply must have non-empty values");
  }

  const approved = extractApproval(replyBody);
  if (!approved) {
    console.log(JSON.stringify({ ok: true, approved: false, sent: 0 }));
    return;
  }

  const draft = await getAgentMailDraft(draftId);
  const attendeeEmails = Array.isArray(draft.to) ? draft.to : [draft.to].filter(Boolean);

  let sentCount = 0;
  for (const to of attendeeEmails) {
    try {
      await sendAgentMailEmail({
        to,
        subject: draft.subject || "Update from Anicca",
        body: draft.body || "",
      });
      sentCount += 1;
    } catch (err) {
      console.error(`[notify] send failed to ${to}:`, err.message);
    }
  }

  console.log(JSON.stringify({ ok: true, approved: true, sent: sentCount }));
}

// ── Poll mode (gog path — closes G1: Dais replies OK → stakeholder gets mail) ──

async function runPoll() {
  // Replies arrive as "Re: [Anicca] Late alert ... [AN-XXXX]" from OWNER.
  // gog gmail search => threads[]; body must be fetched per-thread via gog gmail get.
  const threads = gogGmailSearch(
    'from:' + OWNER_EMAIL + ' subject:"[Anicca] Late alert" newer_than:1d'
  );
  const sent = [];
  for (const t of threads) {
    const tok = tokenFromSubject(t.subject || "");
    if (!tok) continue;
    const pending = findPending(tok);
    if (!pending) continue;                       // unknown or already sent
    const body = gogGmailBody(t.id);              // per-thread body fetch (no snippet on list)
    if (!extractApproval(body)) continue;         // require "OK" in the reply body
    gogGmailSend({ to: pending.to, subject: pending.subject, body: pending.body });
    markSent(tok);
    sent.push({ token: tok, to: pending.to });
  }
  console.log(JSON.stringify({ ok: true, mode: "poll", sent }));
}

// ── Main ──────────────────────────────────────────────────────────────────────

// Only run the CLI when executed directly; importing for tests must not scan/poll.
if (require.main === module) {
  const [, , mode = "scan", ...rest] = process.argv;
  (async () => {
    try {
      if (mode === "webhook") {
        await runWebhook(rest);
      } else if (mode === "poll") {
        await runPoll();
      } else {
        await runScan();
      }
      process.exit(0);
    } catch (err) {
      console.error("[notify] fatal:", err.message);
      process.exit(1);
    }
  })();
}

module.exports = {
  isTravelBlock,
  isLateRisk,
  detectLateRiskEvents,
  estimateMinutesLate,
  buildAttendeeDraft,
  buildApprovalEmail,
  extractApproval,
  approvalToken,
  tokenFromSubject,
  appendPending,
  findPending,
  markSent,
};
