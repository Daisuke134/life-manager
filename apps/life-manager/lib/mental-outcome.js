"use strict";

const { selectMentalQuote } = require("./mental-catalog.js");

const MIN_GAP_MS = 3 * 60 * 60 * 1000;
const DAILY_CAP = 3;
const ALLOWED_KINDS = new Set(["interview", "offer", "rejection"]);
const FAMILY_BY_KIND = Object.freeze({
  interview: "manifestation",
  offer: "affirmation",
  rejection: "affirmation",
});

function decideMentalOutcome({ outcome, nowMs, localDay, calendarBusy, sentTodayCount, lastSentMs, sentOutcomeIds = [], profile = {} } = {}) {
  if (!outcome || typeof outcome !== "object" || !outcome.sourceOutcomeId
      || !ALLOWED_KINDS.has(outcome.kind) || !Number.isFinite(outcome.verifiedAt)
      || !outcome.evidenceRef) {
    return { decision: "suppress", reason: "outcome-not-verified" };
  }
  if (calendarBusy) return { decision: "suppress", reason: "calendar-busy" };
  if (sentOutcomeIds.includes(outcome.sourceOutcomeId)) {
    return { decision: "suppress", reason: "outcome-already-served" };
  }
  if (Number(sentTodayCount) >= DAILY_CAP) return { decision: "suppress", reason: "daily-cap-reached" };
  if (Number.isFinite(lastSentMs) && nowMs - lastSentMs < MIN_GAP_MS) {
    return { decision: "suppress", reason: "too-soon-after-last" };
  }
  const quote = selectMentalQuote({
    uid: String(outcome.sourceOutcomeId),
    localDay: String(localDay || new Date(nowMs).toISOString().slice(0, 10)),
    window: "midday_awareness",
    family: FAMILY_BY_KIND[outcome.kind],
    profile,
    recentQuoteIds: profile.recentQuoteIds || [],
    locale: profile.locale || "ja",
  });
  if (!quote) return { decision: "suppress", reason: "no-eligible-quote" };
  return {
    decision: "send",
    sourceOutcomeId: outcome.sourceOutcomeId,
    kind: outcome.kind,
    quote,
  };
}

module.exports = { DAILY_CAP, MIN_GAP_MS, decideMentalOutcome };
