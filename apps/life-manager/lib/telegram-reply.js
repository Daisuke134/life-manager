// lib/telegram-reply.js — turn a free-text Telegram reply into a calendar location update.
//
// Mirrors the email reply path (ask.js READ phase) but for Telegram: find the user by their
// telegram_chat_id, list their events still missing a location, let Gemini match the reply to the
// right one (agentMatchReply — no regex), and patch the real calendar via Composio.
"use strict";

const { agentMatchReply } = require("./ask.js");
const { getCalendar } = require("./transport/index.js");
const { placeKey, rememberPlace } = require("./places-memory.js");
const { webTelegramUserBySender } = require("./message-links.js");

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

module.exports = { resolveTelegramReply, userByChatId, markUserAnswer };
