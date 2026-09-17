"use strict";

const CALL_OUTCOMES = Object.freeze({
  CONVERSATION: "conversation",
  NO_ANSWER: "no_answer",
  DIAL_FAILED: "dial_failed",
});

const NO_ANSWER_CAUSES = new Set(["timeout", "no_answer", "no_answer_timeout"]);
const DIAL_FAILED_CAUSES = new Set(["busy", "user_busy", "rejected", "declined", "failed", "network_error"]);

function normalizedCause(value) {
  return typeof value === "string" ? value.trim().toLowerCase() : "";
}

function connectedSeconds(value) {
  const seconds = Number(value);
  return Number.isFinite(seconds) && seconds >= 0 ? Math.ceil(seconds) : null;
}

function classifyCallOutcome({ amdResult, connectedSeconds: duration, hangupCause } = {}) {
  if (amdResult === "human" || amdResult === "not_sure") return CALL_OUTCOMES.CONVERSATION;
  const seconds = connectedSeconds(duration);
  const cause = normalizedCause(hangupCause);
  if (seconds === 0 && NO_ANSWER_CAUSES.has(cause)) return CALL_OUTCOMES.NO_ANSWER;
  if (seconds === 0 && DIAL_FAILED_CAUSES.has(cause)) return CALL_OUTCOMES.DIAL_FAILED;
  if (amdResult === "machine" && seconds === 0) return CALL_OUTCOMES.NO_ANSWER;
  return null;
}

module.exports = { CALL_OUTCOMES, classifyCallOutcome };
