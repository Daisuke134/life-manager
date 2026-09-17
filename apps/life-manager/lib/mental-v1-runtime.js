"use strict";

const { resolveUserTzOffsetH, localDay } = require("./user-tz.js");
const { evaluateMentalOpportunity } = require("./mental-opportunity.js");
const { selectMentalQuote } = require("./mental-catalog.js");
const { validateMentalMessage } = require("./mental-copy.js");

function calendarBusy(events, nowMs) {
  return (Array.isArray(events) ? events : []).some((event) => Number(event.startMs) <= nowMs
    && Number(event.endMs) > nowMs);
}

function familyCandidates(window) {
  if (window === "evening_direction") return ["manifestation", "affirmation"];
  if (window === "midday_awareness") return ["mindfulness_inquiry"];
  return ["affirmation"];
}

async function mentalV1UserOnce(user, nowMs, deps = {}) {
  if (!user || !user.uid || !user.telegram_chat_id) return { decision: "suppress", reason: "unreachable" };
  const tzOffsetH = resolveUserTzOffsetH(
    { tzOffsetH: deps.tzOffsetH },
    user,
    nowMs,
    ["LM_MENTAL_UTC_OFFSET_HOURS"],
  );
  if (tzOffsetH === null) return { decision: "suppress", reason: "no-timezone" };

  let events;
  try {
    events = await deps.fetchUpcomingEvents(user.uid, { nowMs });
  } catch {
    return { decision: "suppress", reason: "calendar-unavailable" };
  }
  let state;
  try {
    state = await deps.readSendState(user.uid, nowMs, { strict: true });
  } catch {
    return { decision: "suppress", reason: "send-history-unavailable" };
  }
  const base = evaluateMentalOpportunity({
    uid: user.uid,
    nowMs,
    tzOffsetH,
    sentTodayCount: Number(state.sentTodayCount) || 0,
    lastSentMs: Number.isFinite(state.lastSentMs) ? state.lastSentMs : null,
    sentFamilies: Array.isArray(state.sentFamilies) ? state.sentFamilies : [],
    recentQuoteIds: Array.isArray(state.recentQuoteIds) ? state.recentQuoteIds : [],
    eligibleQuoteIds: null,
    calendarBusy: calendarBusy(events, nowMs),
    quietHours: deps.quietHours || null,
    profile: deps.profile || {},
  });
  if (base.decision !== "send") return base;

  const day = base.localDay || localDay(nowMs, tzOffsetH);
  let quote = null;
  let selectedFamily = null;
  for (const family of familyCandidates(base.window)) {
    quote = selectMentalQuote({
      uid: user.uid,
      localDay: day,
      window: base.window,
      family,
      profile: deps.profile || {},
      recentQuoteIds: state.recentQuoteIds || [],
      locale: (deps.profile && deps.profile.locale) || "ja",
    });
    if (quote) { selectedFamily = family; break; }
  }
  if (!quote) return { decision: "suppress", reason: "no-eligible-quote" };
  const valid = validateMentalMessage(quote.text);
  if (!valid.ok) return { decision: "suppress", reason: "catalog-copy-invalid" };

  const response = await deps.sendMessage(deps.telegramToken, user.telegram_chat_id, quote.text);
  const messageId = response && response.result && response.result.message_id;
  if (!response || !response.ok || messageId === undefined || messageId === null) {
    return { ...base, family: selectedFamily, templateId: quote.id, delivered: false };
  }
  const recorded = await deps.recordSend({
    uid: user.uid,
    trigger: base.window,
    family: selectedFamily,
    templateId: quote.id,
    localDay: day,
    window: base.window,
    telegramMessageId: String(messageId),
  });
  return {
    ...base,
    family: selectedFamily,
    templateId: quote.id,
    text: quote.text,
    delivered: true,
    recorded: Boolean(recorded),
    telegramMessageId: messageId,
  };
}

module.exports = { mentalV1UserOnce, calendarBusy, familyCandidates };
