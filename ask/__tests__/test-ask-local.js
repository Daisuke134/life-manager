// TDD (RED first) for the LOCAL ask consumer — reads life-ask-queue.jsonl (from travel),
// mails the question via gog, polls Gmail for the reply, parses the location.
// No network in unit tests — pure functions only. Run: node --test skills/life/ask/__tests__/test-ask-local.js
"use strict";
const test = require("node:test");
const assert = require("node:assert");
const os = require("node:os");
const fs = require("node:fs");
const path = require("node:path");
const A = require("../ask-local");

test("buildQuestionEmail names the event + embeds a parseable token", () => {
  const { subject, body } = A.buildQuestionEmail({ eventId: "evt123", summary: "仕事", reason: "unknown_location" });
  assert.match(subject, /\[ASK-evt123\]/); // token the poll matches on
  assert.match(body, /仕事/);              // names the actual event
  assert.match(body, /Event ID:\s*evt123/);
});

test("parseReply extracts eventId from the subject token + location from the first reply line", () => {
  const subject = "Re: [Anicca] 場所を教えてください: 仕事 [ASK-evt123]";
  const body = "渋谷スクランブルスクエア\n\nOn Tue wrote:\n> 「仕事」はどこで…\n> Event ID: evt123";
  const r = A.parseReply(subject, body);
  assert.equal(r.eventId, "evt123");
  assert.equal(r.location, "渋谷スクランブルスクエア"); // ignores the quoted (>) lines
});

test("parseReply returns null when no token present", () => {
  assert.equal(A.parseReply("random subject", "hi"), null);
});

test("parseReply skips a top-posted greeting and takes the real answer", () => {
  const subject = "Re: [Anicca] 場所を教えてください: 仕事 [ASK-evt9]";
  const body = "はい！\n渋谷ヒカリエ\n\n> Event ID: evt9";
  const r = A.parseReply(subject, body);
  assert.equal(r.location, "渋谷ヒカリエ"); // not "はい！"
});

test("baseId strips the recurring-event suffix", () => {
  assert.equal(A.baseId("abc_20260604T140000Z"), "abc");
  assert.equal(A.baseId("plain"), "plain");
});

test("loadQueue dedups by eventId keeping the latest", () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "askq-"));
  const q = path.join(dir, "life-ask-queue.jsonl");
  fs.writeFileSync(q,
    JSON.stringify({ eventId: "a", summary: "x", reason: "unknown_location", ts: 1 }) + "\n" +
    "CORRUPT half line\n" +
    JSON.stringify({ eventId: "a", summary: "x", reason: "no_route", ts: 2 }) + "\n" +
    JSON.stringify({ eventId: "b", summary: "y", reason: "unknown_location", ts: 3 }) + "\n");
  const rows = A.loadQueue(q);
  assert.equal(rows.length, 2);                  // a (latest) + b ; corrupt line skipped
  const a = rows.find((r) => r.eventId === "a");
  assert.equal(a.reason, "no_route");            // kept the latest record for a
});
