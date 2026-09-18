"use strict";

const crypto = require("node:crypto");

const DECISION_POLICY_VERSION = "mental-v1-20260918";
const DECISION_STATUSES = new Set(["planned", "silence"]);
const WINDOWS = new Set(["morning_orientation", "midday_awareness", "evening_direction"]);
const FAMILIES = new Set(["affirmation", "manifestation", "mindfulness_inquiry"]);

function base(url) { return String(url).replace(/\/$/, ""); }
function headers(key, extra = {}) {
  return { apikey: key, Authorization: `Bearer ${key}`, ...extra };
}

function profileVersion(profile = {}) {
  const stable = {
    locale: profile.locale || "ja",
    themes: Array.isArray(profile.themes) ? [...profile.themes].sort() : [],
    tones: Array.isArray(profile.tones) ? [...profile.tones].sort() : [],
    avoidThemes: Array.isArray(profile.avoidThemes) ? [...profile.avoidThemes].sort() : [],
    goals: Array.isArray(profile.goals) ? [...profile.goals].sort() : [],
    weights: profile.weights && typeof profile.weights === "object"
      ? Object.fromEntries(Object.entries(profile.weights).sort(([a], [b]) => a.localeCompare(b)))
      : {},
  };
  return crypto.createHash("sha256").update(JSON.stringify(stable)).digest("hex").slice(0, 16);
}

function decisionKey(input) {
  const stable = {
    uid: String(input.uid),
    policyVersion: String(input.policyVersion),
    sourceOutcomeId: input.sourceOutcomeId == null ? null : String(input.sourceOutcomeId),
    localDay: input.localDay == null ? null : String(input.localDay),
    window: String(input.window),
    selectedQuoteId: input.selectedQuoteId == null ? null : String(input.selectedQuoteId),
    silenceReason: input.silenceReason == null ? null : String(input.silenceReason),
  };
  return crypto.createHash("sha256").update(JSON.stringify(stable)).digest("hex");
}

function buildDecisionRow(input = {}) {
  if (!input.uid || !input.policyVersion || !input.profileVersion) throw new Error("decision identity required");
  if (!Array.isArray(input.candidateQuoteIds)) throw new Error("candidateQuoteIds must be an array");
  if (!WINDOWS.has(input.window)) throw new Error("decision window invalid");
  if (typeof input.locale !== "string" || !input.locale) throw new Error("decision locale invalid");
  if (!Number.isFinite(Date.parse(input.observedAt))) throw new Error("decision observedAt invalid");
  if (input.selectedQuoteId == null && !input.silenceReason) throw new Error("silence reason required");
  if (input.selectedQuoteId != null && !input.candidateQuoteIds.includes(input.selectedQuoteId)) {
    throw new Error("selected quote must be a candidate");
  }
  if (input.selectedQuoteId != null && input.family != null && !FAMILIES.has(input.family)) {
    throw new Error("decision family invalid");
  }
  const status = input.status || (input.selectedQuoteId == null ? "silence" : "planned");
  if (!DECISION_STATUSES.has(status)) throw new Error("decision status invalid");
  const row = {
    uid: String(input.uid),
    policyVersion: String(input.policyVersion),
    profileVersion: String(input.profileVersion),
    sourceOutcomeId: input.sourceOutcomeId == null ? null : String(input.sourceOutcomeId),
    candidateQuoteIds: input.candidateQuoteIds.map(String),
    selectedQuoteId: input.selectedQuoteId == null ? null : String(input.selectedQuoteId),
    silenceReason: input.silenceReason == null ? null : String(input.silenceReason),
    calendarBusy: Boolean(input.calendarBusy),
    window: String(input.window),
    telegramMessageId: input.telegramMessageId == null ? null : String(input.telegramMessageId),
    locale: String(input.locale),
    family: input.family == null ? null : String(input.family),
    localDay: input.localDay == null ? null : String(input.localDay),
    observedAt: new Date(input.observedAt).toISOString(),
    status,
  };
  return Object.freeze({ ...row, decisionKey: decisionKey(row) });
}

function supaConfig(supa) {
  const url = supa && (supa.url || supa.supaUrl);
  const key = supa && (supa.key || supa.supaKey);
  if (!url || !key) throw new Error("mental decision store unavailable");
  return { url: base(url), key };
}

function rowBody(row) {
  return {
    decision_key: row.decisionKey,
    uid: row.uid,
    policy_version: row.policyVersion,
    profile_version: row.profileVersion,
    source_outcome_id: row.sourceOutcomeId,
    candidate_quote_ids: row.candidateQuoteIds,
    selected_quote_id: row.selectedQuoteId,
    silence_reason: row.silenceReason,
    calendar_busy: row.calendarBusy,
    window: row.window,
    telegram_message_id: row.telegramMessageId,
    locale: row.locale,
    family: row.family,
    local_day: row.localDay,
    status: row.status,
    observed_at: row.observedAt,
  };
}

async function recordMentalDecision(input, supa, fetchImpl = globalThis.fetch) {
  const row = buildDecisionRow(input);
  const { url, key } = supaConfig(supa);
  const response = await fetchImpl(`${url}/rest/v1/lm_mental_decision_log`, {
    method: "POST",
    headers: headers(key, { "Content-Type": "application/json", Prefer: "return=minimal" }),
    body: JSON.stringify(rowBody(row)),
  }).catch(() => null);
  if (response && response.status === 409) return { recorded: false, duplicate: true, decisionKey: row.decisionKey };
  if (!response || !response.ok) throw new Error(`mental decision write failed (${response ? response.status : "no response"})`);
  return { recorded: true, duplicate: false, decisionKey: row.decisionKey };
}

async function patchDecision(decisionKeyValue, body, supa, fetchImpl = globalThis.fetch) {
  if (!/^[0-9a-f]{64}$/.test(String(decisionKeyValue))) throw new Error("decision key invalid");
  const { url, key } = supaConfig(supa);
  const response = await fetchImpl(`${url}/rest/v1/lm_mental_decision_log?decision_key=eq.${encodeURIComponent(decisionKeyValue)}&status=eq.planned`, {
    method: "PATCH",
    headers: headers(key, { "Content-Type": "application/json", Prefer: "return=minimal" }),
    body: JSON.stringify({ ...body, updated_at: new Date().toISOString() }),
  }).catch(() => null);
  return Boolean(response && response.ok);
}

async function completeMentalDecision(decisionKeyValue, telegramMessageId, supa, fetchImpl = globalThis.fetch) {
  if (telegramMessageId == null || String(telegramMessageId) === "") throw new Error("telegram message ID required");
  return patchDecision(decisionKeyValue, { status: "delivered", telegram_message_id: String(telegramMessageId) }, supa, fetchImpl);
}

async function failMentalDecision(decisionKeyValue, reason, supa, fetchImpl = globalThis.fetch) {
  if (!reason) throw new Error("decision failure reason required");
  return patchDecision(decisionKeyValue, {
    status: "send_failed", selected_quote_id: null, silence_reason: String(reason), telegram_message_id: null,
  }, supa, fetchImpl);
}

module.exports = {
  DECISION_POLICY_VERSION,
  profileVersion,
  decisionKey,
  buildDecisionRow,
  recordMentalDecision,
  completeMentalDecision,
  failMentalDecision,
};
