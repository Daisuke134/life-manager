"use strict";

const WINDOWS = new Set(["morning_orientation", "midday_awareness", "evening_direction"]);
const FAMILIES = new Set(["affirmation", "manifestation", "mindfulness_inquiry"]);
const LOCALES = new Set(["ja", "en"]);

function fail(message) { throw new Error(`mental decision row ${message}`); }

function validateDecisionRow(row) {
  if (!row || typeof row !== "object" || Array.isArray(row)) fail("must be an object");
  const allowed = ["uid", "policyVersion", "profileVersion", "sourceOutcomeId", "candidateQuoteIds", "selectedQuoteId", "silenceReason", "calendarBusy", "window", "telegramMessageId", "locale", "family", "observedAt"];
  if (Object.keys(row).some((key) => !allowed.includes(key))) fail("contains unknown fields");
  if (!row.uid || !row.policyVersion || !row.profileVersion || !Array.isArray(row.candidateQuoteIds)) fail("identity invalid");
  if (row.selectedQuoteId !== null && (!row.selectedQuoteId || !row.candidateQuoteIds.includes(row.selectedQuoteId))) fail("selected quote invalid");
  if (row.selectedQuoteId === null && !row.silenceReason) fail("silence reason missing");
  if (row.selectedQuoteId !== null && row.silenceReason !== null) fail("send cannot have silence reason");
  // Policy violations are observations the scorecard must count, not malformed input. In
  // particular, a busy-time send and an unsupported locale are valid replay rows that should
  // increase the violation counters below. Keep structural validation (window shape and a
  // non-empty locale) separate from policy validation.
  if (!WINDOWS.has(row.window) || typeof row.locale !== "string" || !row.locale) fail("window or locale invalid");
  if (row.selectedQuoteId !== null && !FAMILIES.has(row.family)) fail("family invalid");
  if (row.telegramMessageId !== null && !String(row.telegramMessageId)) fail("telegram message ID invalid");
  if (!Number.isFinite(Date.parse(row.observedAt))) fail("observedAt invalid");
  return Object.freeze({ ...row });
}

function scorePolicyRows(rows) {
  const valid = (Array.isArray(rows) ? rows : []).map(validateDecisionRow);
  const delivered = valid.filter((row) => row.telegramMessageId !== null);
  const byDay = new Map();
  const templates = new Map();
  for (const row of delivered) {
    const day = new Date(row.observedAt).toISOString().slice(0, 10);
    byDay.set(day, (byDay.get(day) || 0) + 1);
    const key = row.selectedQuoteId;
    templates.set(key, (templates.get(key) || 0) + 1);
  }
  return {
    delivered: delivered.length,
    busy_send: valid.filter((row) => row.calendarBusy && row.telegramMessageId !== null).length,
    unsupported_locale: valid.filter((row) => !LOCALES.has(row.locale)).length,
    duplicate_template: [...templates.values()].reduce((sum, count) => sum + Math.max(0, count - 1), 0),
    cap_overflow: [...byDay.values()].reduce((sum, count) => sum + Math.max(0, count - 3), 0),
    silence: valid.length - delivered.length,
  };
}

function comparePolicyReplays(oldRows, newRows, { oldMaterialReports = 0, newMaterialReports = oldMaterialReports } = {}) {
  const oldScore = scorePolicyRows(oldRows);
  const newScore = scorePolicyRows(newRows);
  const oldViolations = oldScore.busy_send + oldScore.unsupported_locale + oldScore.duplicate_template + oldScore.cap_overflow;
  const newViolations = newScore.busy_send + newScore.unsupported_locale + newScore.duplicate_template + newScore.cap_overflow;
  return { promote: newViolations < oldViolations && newMaterialReports >= oldMaterialReports, oldScore, newScore };
}

module.exports = { validateDecisionRow, scorePolicyRows, comparePolicyReplays };
