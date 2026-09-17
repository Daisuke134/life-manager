"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
  classifyMentalCorrection,
  alternateTone,
  handleMentalCorrectionMessage,
  readReferencedMentalSend,
  sourceRefHash,
} = require("./mental-correction.js");

test("correction parser accepts only explicit, bounded natural corrections", () => {
  assert.deepEqual(classifyMentalCorrection("この時間は邪魔"), { kind: "timing_unimplemented" });
  assert.deepEqual(classifyMentalCorrection("こういう時は短く"), { kind: "tone", tag: "direct" });
  assert.deepEqual(classifyMentalCorrection("もう少し優しく"), { kind: "tone", tag: "gentle" });
  assert.deepEqual(classifyMentalCorrection("この言い方は嫌"), { kind: "tone_switch" });
  assert.equal(classifyMentalCorrection("今日は予定がある"), null);
});

test("generic wording correction only switches an unambiguous single-tone quote", () => {
  assert.equal(alternateTone({ tones: ["gentle"] }), "direct");
  assert.equal(alternateTone({ tones: ["direct"] }), "gentle");
  assert.equal(alternateTone({ tones: ["gentle", "direct"] }), null);
});

test("correction requires a reply to a durable mental message and writes no raw text", async () => {
  const saved = [];
  const result = await handleMentalCorrectionMessage({
    kind: "message", chatId: "chat", messageId: "8", replyToMessageId: "7",
    observedAtMs: Date.parse("2026-09-18T00:00:00Z"), text: "こういう時は短く",
  }, { uid: "u1" }, {
    readReferencedSend: async ({ uid, messageId }) => {
      assert.deepEqual({ uid, messageId }, { uid: "u1", messageId: "7" });
      return { templateId: "antara:courage-quiet:ja", family: "affirmation", window: "morning_orientation" };
    },
    recordTag: async (row) => { saved.push(row); return { recorded: true, duplicate: false }; },
  });
  assert.deepEqual({ handled: result.handled, recorded: result.recorded, tag: result.tag }, { handled: true, recorded: true, tag: "direct" });
  assert.equal(saved.length, 1);
  assert.equal(saved[0].basis, "explicit_correction");
  assert.match(saved[0].sourceRefHash, /^[a-f0-9]{64}$/);
  assert.equal(JSON.stringify(saved[0]).includes("こういう時は短く"), false);
});

test("unreconciled or ambiguous corrections stay silent and do not mutate profile", async () => {
  let writes = 0;
  const base = { kind: "message", chatId: "chat", messageId: "8", replyToMessageId: "7", text: "この言い方は嫌" };
  assert.deepEqual(await handleMentalCorrectionMessage(base, { uid: "u1" }, {
    readReferencedSend: async () => null,
    recordTag: async () => { writes += 1; return { recorded: true }; },
  }), { handled: false });
  assert.deepEqual(await handleMentalCorrectionMessage(base, { uid: "u1" }, {
    readReferencedSend: async () => ({ templateId: "antara:courage-quiet:ja", family: "affirmation" }),
    recordTag: async () => { writes += 1; return { recorded: true }; },
  }), { handled: true, recorded: false, reason: "ambiguous-tone" });
  assert.equal(writes, 0);
});

test("timing complaints are acknowledged internally but never mapped to a tone tag", async () => {
  let writes = 0;
  const result = await handleMentalCorrectionMessage({
    kind: "message", chatId: "chat", messageId: "9", replyToMessageId: "7", text: "この時間は邪魔",
  }, { uid: "u1" }, {
    readReferencedSend: async () => ({ templateId: "mental-buddy-breath-anchor:ja", family: "mindfulness_inquiry" }),
    recordTag: async () => { writes += 1; return { recorded: true }; },
  });
  assert.deepEqual(result, { handled: true, recorded: false, reason: "timing-preference-not-supported" });
  assert.equal(writes, 0);
});

test("source reference is deterministic and contains no raw identifiers", () => {
  const digest = sourceRefHash({ uid: "u1", chatId: "chat", messageId: "8", replyToMessageId: "7", tag: "direct" });
  assert.equal(digest, sourceRefHash({ uid: "u1", chatId: "chat", messageId: "8", replyToMessageId: "7", tag: "direct" }));
  assert.match(digest, /^[a-f0-9]{64}$/);
});

test("referenced send lookup is receipt-only and rejects non-MENTAL rows", async () => {
  let seen;
  const row = await readReferencedMentalSend({ uid: "u1", messageId: "7", supa: { url: "https://supa", key: "service" }, fetchImpl: async (url, init) => {
    seen = { url, init };
    return { ok: true, json: async () => [{ telegram_message_id: "7", template_id: "q1", family: "affirmation", window: "morning_orientation", sent_at: "2026-09-18T00:00:00Z" }] };
  } });
  assert.equal(row.templateId, "q1");
  assert.match(seen.url, /telegram_message_id=eq\.7/);
  assert.match(seen.url, /template_id/);
  assert.doesNotMatch(seen.url, /body|subject|snippet|chat_id/);
  const ignored = await readReferencedMentalSend({ uid: "u1", messageId: "8", supa: { url: "https://supa", key: "service" }, fetchImpl: async () => ({ ok: true, json: async () => [{ telegram_message_id: "8", template_id: "legacy", family: "legacy" }] }) });
  assert.equal(ignored, null);
});
