// lib/telegram-reply.js — turn a free-text Telegram reply into a calendar location update.
//
// Mirrors the email reply path (ask.js READ phase) but for Telegram: find the user by their
// telegram_chat_id, list their events still missing a location, let Gemini match the reply to the
// right one (agentMatchReply — no regex), and patch the real calendar via Composio.
"use strict";

const { agentMatchReply } = require("./ask.js");
const { getCalendar } = require("./transport/index.js");
const { placeKey, rememberPlace } = require("./places-memory.js");
const { webMessageUserBySender, webTelegramUserBySender } = require("./message-links.js");
const { webTravelEntitled } = require("./billing.js");

async function userByChatId(chatId, deps = {}) {
  const url = deps.supaUrl || process.env.SUPABASE_URL;
  const key = deps.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) return null;
  const fetchImpl = deps.fetchImpl || fetch;
  const r = await fetchImpl(
    `${url}/rest/v1/lm_users?telegram_chat_id=eq.${encodeURIComponent(chatId)}&select=uid,calendar_provider,paid&limit=1`,
    { headers: { apikey: key, Authorization: `Bearer ${key}` } });
  const d = await r.json().catch(() => []);
  if (Array.isArray(d) && d[0]) return d[0];
  return webTelegramUserBySender(chatId, { ...deps, supaUrl: url, supaKey: key });
}

function needsLocation(e) {
  const s = (e.summary || "").trim();
  if (s.startsWith("[Travel]") || s.startsWith("[Ask]")) return false;
  if (!((e.start || {}).dateTime)) return false;
  return !((e.location || "").trim());
}

async function markUserAnswer(uid, eventId, fetchImpl) {
  const url = process.env.SUPABASE_URL, key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key || !uid || !eventId) return;
  const f = fetchImpl || fetch;
  await f(`${url}/rest/v1/lm_ask_log?uid=eq.${encodeURIComponent(uid)}&event_id=eq.${encodeURIComponent(eventId)}`, {
    method: "PATCH",
    headers: { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json", Prefer: "return=minimal" },
    body: JSON.stringify({ answered_at: new Date().toISOString(), resolved_from: "user_answer" }),
  }).catch(() => {});
}

// Returns { filled, event, location }. deps (lookupUser/calendar/match/remember) are injectable so the
// patch→remember wiring (REQ-46) has an executable test (FIND-001/004); real defaults in production.
async function resolveTelegramReply(chatId, text, deps = {}) {
  const composioKey = process.env.COMPOSIO_API_KEY, geminiKey = process.env.GEMINI_API_KEY;
  const out = { filled: false, event: "", location: "" };
  if (!deps.calendar && (!composioKey || !geminiKey)) return out;
  const lookupUser = deps.lookupUser || userByChatId;
  const match0 = deps.match || ((t, p) => agentMatchReply(t, p, geminiKey));
  const remember = deps.remember || rememberPlace;
  const user = await lookupUser(chatId);
  if (!user || user.calendar_provider !== "composio_gcal") return out;
  const cal = deps.calendar || getCalendar({ apiKey: composioKey, gmailAccountId: user.gmail_account_id });

  const now = Date.now();
  const items = await cal.listEventsRaw(user.uid, {
    timeMin: new Date(now).toISOString().replace(/\.\d{3}Z$/, "Z"),
    timeMax: new Date(now + 7 * 86400 * 1000).toISOString().replace(/\.\d{3}Z$/, "Z"),
    maxResults: 50,
  });
  const pending = items.filter(needsLocation);
  if (!pending.length) return out;

  const match = await match0(text, pending.map((e) => ({ id: e.id, summary: e.summary })));
  if (!match) return out;
  const ev = pending.find((e) => e.id === match.eventId);
  if (!ev) return out;
  await cal.patchEvent(user.uid, { calendar_id: "primary", event_id: ev.id, location: match.location });
  await (deps.markAnswered || markUserAnswer)(user.uid, ev.id);
  // PC-1 (C3 REQ-46): remember so a future same-summary event autofills without re-asking.
  const ok = await remember(user.uid, placeKey(ev.summary, ev.recurringEventId), match.location, process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY);
  if (!ok) console.error(`[tg-reply] rememberPlace FAILED uid=${user.uid.slice(0, 12)} — will re-ask (FIND-003)`);
  return { filled: true, event: ev.summary || "your event", location: match.location };
}

function imessageOnlineAnswer(text) {
  const value = String(text || "").trim().toLowerCase();
  if (["オンライン", "online", "remote"].includes(value)) return "online";
  if (["対面", "offline", "in person"].includes(value)) return "offline";
  return null;
}

async function pendingIMessageAsks(uid, deps = {}) {
  const supaUrl = deps.supaUrl || process.env.SUPABASE_URL;
  const supaKey = deps.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!uid || !supaUrl || !supaKey) return [];
  const fetchImpl = deps.fetchImpl || fetch;
  const url = new URL(`${supaUrl.replace(/\/$/, "")}/rest/v1/lm_ask_log`);
  url.searchParams.set("uid", `eq.${uid}`);
  url.searchParams.set("answered_at", "is.null");
  url.searchParams.set("question_context->>replyChannel", "eq.imessage");
  url.searchParams.set("select", "event_id,reply_token,question_type,question_context,answer_value,answered_at");
  url.searchParams.set("limit", "20");
  const response = await fetchImpl(url.toString(), { headers: { apikey: supaKey, Authorization: `Bearer ${supaKey}` } });
  if (!response || !response.ok) return [];
  const rows = await response.json().catch(() => null);
  return Array.isArray(rows) ? rows.filter((row) => row && row.question_context && row.question_context.replyChannel === "imessage") : [];
}

async function updateIMessageAsk(uid, row, update, deps = {}) {
  const supaUrl = deps.supaUrl || process.env.SUPABASE_URL;
  const supaKey = deps.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!uid || !row || !row.event_id || !row.reply_token || !supaUrl || !supaKey) return null;
  const fetchImpl = deps.fetchImpl || fetch;
  const url = new URL(`${supaUrl.replace(/\/$/, "")}/rest/v1/lm_ask_log`);
  url.searchParams.set("uid", `eq.${uid}`);
  url.searchParams.set("event_id", `eq.${row.event_id}`);
  url.searchParams.set("reply_token", `eq.${row.reply_token}`);
  url.searchParams.set("answered_at", "is.null");
  url.searchParams.set("question_context->>replyChannel", "eq.imessage");
  url.searchParams.set("select", "uid,event_id,question_type,question_context,answer_value,answered_at");
  const response = await fetchImpl(url.toString(), {
    method: "PATCH",
    headers: { apikey: supaKey, Authorization: `Bearer ${supaKey}`, "Content-Type": "application/json", Prefer: "return=representation" },
    body: JSON.stringify(update),
  }).catch(() => null);
  const rows = response && response.ok ? await response.json().catch(() => []) : [];
  return Array.isArray(rows) && rows[0] ? rows[0] : null;
}

async function resolveIMessageReply(uid, senderId, replyText, deps = {}) {
  if (!uid || !senderId) return { filled: false, reason: "missing_identity" };
  const linkedUser = deps.linkedUser || await (deps.lookupUserImpl || webMessageUserBySender)("imessage", senderId, deps);
  if (!linkedUser || linkedUser.uid !== uid || linkedUser.web_message_imessage_sender_id !== senderId
    || linkedUser.calendar_provider !== "composio_gcal" || !linkedUser.calendar_connected_account_id) {
    return { filled: false, reason: "sender_tenant_mismatch" };
  }
  const nowMs = deps.nowMs === undefined ? Date.now() : Number(deps.nowMs);
  if (!webTravelEntitled(linkedUser, nowMs)) return { filled: false, reason: "billing_inactive" };
  const pending = await (deps.pendingAsksImpl || pendingIMessageAsks)(uid, deps);
  if (!Array.isArray(pending) || pending.length === 0) return { filled: false, reason: "no_pending_ask" };
  const rows = pending.filter((row) => row && row.question_context && row.question_context.replyChannel === "imessage");
  if (rows.length !== 1) return { filled: false, reason: "ambiguous_pending_ask" };
  const row = rows[0];
  const context = row.question_context;

  if (row.question_type === "calendar_online" && !context.awaitingLocation) {
    const answer = imessageOnlineAnswer(replyText);
    if (answer === "online") {
      const updated = await (deps.markOnlineAnswerImpl || updateIMessageAsk)(uid, row, {
      answered_at: new Date(nowMs).toISOString(),
        answer_value: "online", answer_source: "imessage",
        answer_provenance: { kind: "imessage_stream" }, resolved_from: "user_answer",
      }, deps);
      return updated ? { filled: false, online: true, event: context.summary || "" } : { filled: false, reason: "ask_already_answered" };
    }
    if (answer === "offline") {
      const updated = await (deps.markOfflineFollowupImpl || updateIMessageAsk)(uid, row, {
        answer_value: "offline", answer_source: "imessage",
        answer_provenance: { kind: "imessage_stream" }, resolved_from: "user_answer",
        question_context: { ...context, awaitingLocation: true },
      }, deps);
      return updated ? { filled: false, needsLocation: true, event: context.summary || "" } : { filled: false, reason: "ask_already_answered" };
    }
  }

  if (!process.env.GEMINI_API_KEY && !deps.geminiKey && !deps.match) return { filled: false, reason: "gemini_unavailable" };
  const composioKey = deps.composioKey || process.env.COMPOSIO_API_KEY;
  if (!deps.calendar && !composioKey) return { filled: false, reason: "calendar_unavailable" };
  const calendar = deps.calendar || getCalendar({ apiKey: composioKey, gmailAccountId: linkedUser.gmail_account_id });
  const now = nowMs;
  const items = await calendar.listEventsRaw(uid, {
    timeMin: new Date(now).toISOString().replace(/\.\d{3}Z$/, "Z"),
    timeMax: new Date(now + 7 * 86400 * 1000).toISOString().replace(/\.\d{3}Z$/, "Z"),
    maxResults: 50,
  });
  const ev = (items || []).find((item) => item && item.id === row.event_id);
  if (!ev) return { filled: false, reason: "pending_event_missing" };
  if (!needsLocation(ev)) {
    const updated = await (deps.markLocationAnsweredImpl || updateIMessageAsk)(uid, row, {
      answered_at: new Date(now).toISOString(), answer_source: "imessage",
      answer_provenance: { kind: "imessage_stream" }, resolved_from: "provider_readback",
    }, deps);
    return updated ? { filled: false, alreadySet: true, event: ev.summary || "" } : { filled: false, reason: "ask_already_answered" };
  }
  const match = await (deps.match || ((text, candidates) => agentMatchReply(text, candidates, deps.geminiKey || process.env.GEMINI_API_KEY)))(
    replyText, [{ id: ev.id, summary: ev.summary }],
  );
  if (!match || match.eventId !== ev.id || !match.location) return { filled: false, reason: "reply_not_a_location" };
  await calendar.patchEvent(uid, { calendar_id: "primary", event_id: ev.id, location: match.location });
  await (deps.remember || rememberPlace)(uid, placeKey(ev.summary, ev.recurringEventId), match.location, deps.supaUrl || process.env.SUPABASE_URL, deps.supaKey || process.env.SUPABASE_SERVICE_ROLE_KEY);
  const updated = await (deps.markLocationAnsweredImpl || updateIMessageAsk)(uid, row, {
    answered_at: new Date(now).toISOString(), answer_source: "imessage", candidate_location: match.location,
    answer_provenance: { kind: "imessage_stream" }, resolved_from: "user_answer",
    question_context: { ...context, awaitingLocation: false },
  }, deps);
  return updated ? { filled: true, event: ev.summary || "your event", location: match.location } : { filled: false, reason: "ask_already_answered" };
}

module.exports = { resolveIMessageReply, resolveTelegramReply, userByChatId, markUserAnswer };
