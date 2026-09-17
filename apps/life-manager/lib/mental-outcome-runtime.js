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

module.exports = { handleVerifiedOutcome };
