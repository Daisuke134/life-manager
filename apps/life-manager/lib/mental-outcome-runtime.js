"use strict";

const { decideMentalOutcome } = require("./mental-outcome.js");

async function handleVerifiedOutcome(outcome, deps = {}) {
  const decision = decideMentalOutcome({
    outcome,
    nowMs: deps.nowMs,
    localDay: deps.localDay,
    calendarBusy: Boolean(deps.calendarBusy),
    sentTodayCount: deps.sentTodayCount,
    lastSentMs: deps.lastSentMs,
    sentOutcomeIds: deps.sentOutcomeIds,
    profile: deps.profile,
  });
  if (decision.decision !== "send") return decision;
  const user = deps.user || {};
  const response = await deps.sendMessage(deps.telegramToken, user.telegram_chat_id, decision.quote.text);
  const messageId = response && response.result && response.result.message_id;
  if (!response || !response.ok || messageId === undefined || messageId === null) {
    return { ...decision, delivered: false };
  }
  const recorded = await deps.recordOutcomeSend({
    uid: user.uid,
    sourceOutcomeId: outcome.sourceOutcomeId,
    evidenceRef: outcome.evidenceRef,
    quoteId: decision.quote.id,
    telegramMessageId: String(messageId),
  });
  return {
    ...decision,
    delivered: true,
    recorded: Boolean(recorded),
    telegramMessageId: String(messageId),
  };
}

async function runVerifiedOutcomes(user, nowMs, deps = {}) {
  if (typeof deps.fetchVerifiedOutcomes !== "function") return [];
  let outcomes;
  try {
    outcomes = await deps.fetchVerifiedOutcomes(user.uid, { nowMs });
  } catch {
    return [{ decision: "suppress", reason: "outcome-provider-unavailable" }];
  }
  if (!Array.isArray(outcomes) || outcomes.length === 0) return [];
  let state = { sentOutcomeIds: [], sentTodayCount: 0, lastSentMs: null };
  if (typeof deps.readOutcomeSendState === "function") {
    try {
      state = await deps.readOutcomeSendState(user.uid, nowMs, { strict: true });
    } catch {
      return [{ decision: "suppress", reason: "outcome-send-state-unavailable" }];
    }
  }
  const results = [];
  for (const outcome of outcomes) {
    const result = await handleVerifiedOutcome(outcome, {
      ...deps,
      user,
      nowMs,
      sentOutcomeIds: state.sentOutcomeIds,
      sentTodayCount: state.sentTodayCount,
      lastSentMs: state.lastSentMs,
    });
    results.push(result);
    if (result.delivered) {
      state = {
        sentOutcomeIds: [...state.sentOutcomeIds, outcome.sourceOutcomeId],
        sentTodayCount: state.sentTodayCount + 1,
        lastSentMs: nowMs,
      };
    }
  }
  return results;
}

module.exports = { handleVerifiedOutcome, runVerifiedOutcomes };
