"use strict";

const { resolveUserTzOffsetH, localDay } = require("./user-tz.js");
const { evaluateMentalOpportunity } = require("./mental-opportunity.js");
const { selectMentalQuote } = require("./mental-catalog.js");
const { validateMentalMessage } = require("./mental-copy.js");
const { evaluateMentalSafety } = require("./mental-safety.js");
const {
  DECISION_POLICY_VERSION,
  profileVersion,
} = require("./mental-decision-log.js");

function calendarBusy(events, nowMs) {
  return (Array.isArray(events) ? events : []).some((event) => Number(event.startMs) <= nowMs
    && Number(event.endMs) > nowMs);
}

function familyCandidates(window) {
  if (window === "evening_direction") return ["manifestation", "affirmation"];
  if (window === "midday_awareness") return ["mindfulness_inquiry"];
  return ["affirmation"];
}

function normalizeQuietHours(user = {}) {
  if (user.mental_quiet_start_minute == null || user.mental_quiet_end_minute == null) return null;
  const start = Number(user.mental_quiet_start_minute);
  const end = Number(user.mental_quiet_end_minute);
  if (!Number.isInteger(start) || !Number.isInteger(end)
      || start < 0 || start > 1440 || end < 0 || end > 1440) return null;
  return { start, end };
}

function decisionInput({ user, profile, nowMs, base, calendarBusy: busy, family, candidateQuoteIds, selectedQuoteId, silenceReason, status }) {
  return {
    uid: user.uid,
    policyVersion: DECISION_POLICY_VERSION,
    profileVersion: profileVersion(profile),
    sourceOutcomeId: null,
    candidateQuoteIds: candidateQuoteIds || [],
    selectedQuoteId: selectedQuoteId || null,
    silenceReason: silenceReason || null,
    calendarBusy: Boolean(busy),
    window: base.window,
    telegramMessageId: null,
    locale: profile.locale || "ja",
    family: family || base.family || null,
    localDay: base.localDay,
    observedAt: new Date(nowMs).toISOString(),
    status,
  };
}

async function persistSilence({ user, profile, nowMs, base, calendarBusy: busy, candidateQuoteIds = [], reason }, deps) {
  if (!base.window || typeof deps.recordDecision !== "function") return null;
  try {
    return await deps.recordDecision(decisionInput({
      user, profile, nowMs, base, calendarBusy: busy, candidateQuoteIds,
      silenceReason: reason, status: "silence",
    }));
  } catch {
    return { recorded: false, duplicate: false };
  }
}

async function mentalV1UserOnce(user, nowMs, deps = {}) {
  if (!user || !user.uid || !user.telegram_chat_id) return { decision: "suppress", reason: "unreachable" };
  const safety = evaluateMentalSafety({ verdict: deps.safetyVerdict });
  if (safety.decision !== "continue") return { decision: "suppress", reason: safety.reason };
  if (Array.isArray(deps.allowedUids) && deps.allowedUids.length > 0
      && !deps.allowedUids.includes(String(user.uid))) {
    return { decision: "suppress", reason: "mental-v1-not-allowlisted" };
  }
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
  const busy = calendarBusy(events, nowMs);
  let profile = deps.profile || {};
  if (typeof deps.readProfile === "function") {
    try { profile = await deps.readProfile(user.uid, nowMs); }
    catch { return { decision: "suppress", reason: "profile-unavailable" }; }
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
    calendarBusy: busy,
    quietHours: deps.quietHours || null,
    profile,
  });
  if (base.decision !== "send") {
    const recorded = await persistSilence({ user, profile, nowMs, base, calendarBusy: busy, reason: base.reason }, deps);
    return recorded ? { ...base, decisionRecorded: Boolean(recorded.recorded || recorded.duplicate) } : base;
  }

  const day = base.localDay || localDay(nowMs, tzOffsetH);
  let quote = null;
  let selectedFamily = null;
  for (const family of familyCandidates(base.window)) {
    quote = selectMentalQuote({
      uid: user.uid,
      localDay: day,
      window: base.window,
      family,
      profile,
      recentQuoteIds: state.recentQuoteIds || [],
      locale: profile.locale || "ja",
    });
    if (quote) { selectedFamily = family; break; }
  }
  if (!quote) {
    const silence = { decision: "suppress", reason: "no-eligible-quote", window: base.window, family: base.family, localDay: day };
    const recorded = await persistSilence({ user, profile, nowMs, base: silence, calendarBusy: busy, reason: silence.reason }, deps);
    return recorded ? { ...silence, decisionRecorded: Boolean(recorded.recorded || recorded.duplicate) } : silence;
  }
  const valid = validateMentalMessage(quote.text);
  if (!valid.ok) {
    const silence = { decision: "suppress", reason: "catalog-copy-invalid", window: base.window, family: selectedFamily, localDay: day };
    const recorded = await persistSilence({ user, profile, nowMs, base: silence, calendarBusy: busy, candidateQuoteIds: [quote.id], reason: silence.reason }, deps);
    return recorded ? { ...silence, decisionRecorded: Boolean(recorded.recorded || recorded.duplicate) } : silence;
  }

  let decisionReceipt = null;
  if (typeof deps.recordDecision === "function") {
    try {
      decisionReceipt = await deps.recordDecision(decisionInput({
        user, profile, nowMs, base, calendarBusy: busy,
        family: selectedFamily, candidateQuoteIds: [quote.id], selectedQuoteId: quote.id, status: "planned",
      }));
    } catch {
      return { decision: "suppress", reason: "decision-log-unavailable", window: base.window, family: selectedFamily, localDay: day };
    }
    if (!decisionReceipt || (!decisionReceipt.recorded && !decisionReceipt.duplicate)) {
      return { decision: "suppress", reason: "decision-log-unavailable", window: base.window, family: selectedFamily, localDay: day };
    }
    if (decisionReceipt.duplicate) {
      return { decision: "suppress", reason: "decision-already-recorded", window: base.window, family: selectedFamily, localDay: day };
    }
  }

  const response = await deps.sendMessage(deps.telegramToken, user.telegram_chat_id, quote.text);
  const messageId = response && response.result && response.result.message_id;
  if (!response || !response.ok || messageId === undefined || messageId === null) {
    if (decisionReceipt && typeof deps.failDecision === "function") {
      await deps.failDecision(decisionReceipt.decisionKey, "telegram-send-failed").catch(() => {});
    }
    return { ...base, family: selectedFamily, templateId: quote.id, delivered: false };
  }
  let decisionRecorded = true;
  if (decisionReceipt && typeof deps.completeDecision === "function") {
    decisionRecorded = Boolean(await deps.completeDecision(decisionReceipt.decisionKey, String(messageId)).catch(() => false));
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
    decisionRecorded,
    telegramMessageId: messageId,
  };
}

module.exports = { mentalV1UserOnce, calendarBusy, familyCandidates, normalizeQuietHours, decisionInput };
