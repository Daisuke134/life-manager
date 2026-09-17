"use strict";

const crypto = require("node:crypto");
const { loadMentalCatalog } = require("./mental-catalog.js");
const { recordMentalProfileTag } = require("./mental-profile-store.js");

const FAMILIES = new Set(["affirmation", "manifestation", "mindfulness_inquiry"]);

function base(url) { return String(url).replace(/\/$/, ""); }
function headers(key) { return { apikey: key, Authorization: `Bearer ${key}` }; }

function classifyMentalCorrection(text) {
  const value = String(text || "").trim();
  if (!value) return null;
  if (/(短く|短め|簡潔に|もっと短|shorter|brief|too long)/i.test(value)) {
    return { kind: "tone", tag: "direct" };
  }
  if (/(優しく|やさしく|柔らかく|gentler|softer)/i.test(value)) {
    return { kind: "tone", tag: "gentle" };
  }
  if (/(この言い方|この表現|wording|言い回し).*(嫌|苦手|違和感|好きじゃない|don't like|wrong)/i.test(value)) {
    return { kind: "tone_switch" };
  }
  // A timing complaint is recognized only as a correction candidate. V1 has no persisted
  // per-window preference column yet, so it is never converted into a guessed profile tag.
  if (/(この時間|時間.*邪魔|wrong time|too early|too late|interrupt)/i.test(value)) {
    return { kind: "timing_unimplemented" };
  }
  return null;
}

function sourceRefHash({ uid, chatId, messageId, replyToMessageId, tag }) {
  return crypto.createHash("sha256")
    .update(`${uid}:${chatId}:${messageId}:${replyToMessageId}:${tag}`)
    .digest("hex");
}

function alternateTone(quote) {
  const tones = new Set(Array.isArray(quote && quote.tones) ? quote.tones : []);
  if (tones.size !== 1) return null;
  if (tones.has("gentle")) return "direct";
  if (tones.has("direct")) return "gentle";
  return null;
}

async function readReferencedMentalSend({ uid, messageId, supa, fetchImpl = globalThis.fetch } = {}) {
  const url = supa && (supa.url || supa.supaUrl);
  const key = supa && (supa.key || supa.supaKey);
  if (!url || !key || !uid || !messageId) return null;
  const query = `uid=eq.${encodeURIComponent(uid)}&telegram_message_id=eq.${encodeURIComponent(messageId)}`
    + "&select=telegram_message_id,template_id,family,window,sent_at&limit=1";
  const response = await fetchImpl(`${base(url)}/rest/v1/lm_mental_send_log?${query}`, {
    headers: headers(key),
  }).catch(() => null);
  if (!response || !response.ok) return null;
  const rows = await response.json().catch(() => null);
  const row = Array.isArray(rows) ? rows[0] : null;
  if (!row || !FAMILIES.has(String(row.family || "")) || !row.template_id) return null;
  return {
    telegramMessageId: String(row.telegram_message_id),
    templateId: String(row.template_id),
    family: String(row.family),
    window: String(row.window || ""),
    sentAt: String(row.sent_at || ""),
  };
}

function quoteById(templateId, locale = "ja") {
  return loadMentalCatalog(locale).find((quote) => quote.id === templateId) || null;
}

async function handleMentalCorrectionMessage(update, user, deps = {}) {
  if (!update || update.kind !== "message" || !update.text || !user || !user.uid
      || !update.chatId || !update.messageId || !update.replyToMessageId) {
    return { handled: false };
  }
  const correction = classifyMentalCorrection(update.text);
  if (!correction) return { handled: false };
  const readSend = deps.readReferencedSend || ((input) => readReferencedMentalSend({
    ...input,
    supa: { url: deps.supaUrl, key: deps.supaKey },
  }));
  const sent = await readSend({ uid: user.uid, messageId: update.replyToMessageId });
  if (!sent) return { handled: false };
  const quote = quoteById(sent.templateId, deps.locale || "ja");
  if (correction.kind === "timing_unimplemented") {
    return { handled: true, recorded: false, reason: "timing-preference-not-supported" };
  }
  const tag = correction.kind === "tone" ? correction.tag : alternateTone(quote);
  if (!tag) return { handled: true, recorded: false, reason: correction.kind === "timing_unimplemented" ? "timing-preference-not-supported" : "ambiguous-tone" };
  const row = {
    uid: String(user.uid),
    kind: "tone",
    tag,
    weight: 1,
    basis: "explicit_correction",
    explicit: true,
    sourceRefHash: sourceRefHash({
      uid: user.uid,
      chatId: update.chatId,
      messageId: update.messageId,
      replyToMessageId: update.replyToMessageId,
      tag,
    }),
    observedAt: new Date(Number(update.observedAtMs) || Date.now()).toISOString(),
    expiresAt: null,
    supersededBy: null,
  };
  try {
    const result = await (deps.recordTag || ((value) => recordMentalProfileTag(value, {
      url: deps.supaUrl,
      key: deps.supaKey,
    })))(row);
    return { handled: true, recorded: Boolean(result && result.recorded), duplicate: Boolean(result && result.duplicate), tag };
  } catch {
    return { handled: true, recorded: false, reason: "profile-write-failed" };
  }
}

module.exports = {
  classifyMentalCorrection,
  sourceRefHash,
  alternateTone,
  readReferencedMentalSend,
  handleMentalCorrectionMessage,
};
