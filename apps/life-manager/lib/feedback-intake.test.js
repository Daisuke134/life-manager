"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  classifyFeedback,
  scrubFeedback,
  buildFeedbackIntake,
  persistFeedback,
  handleFeedbackMessage,
} = require("./feedback-intake.js");


test("only explicit English/Japanese feedback prefixes enter the developer loop", () => {
  assert.deepEqual(classifyFeedback("feedback: Calendar card is confusing"), {
    kind: "feedback",
    body: "Calendar card is confusing",
  });
  assert.deepEqual(classifyFeedback("フィードバック：通知が遅い"), {
    kind: "feedback",
    body: "通知が遅い",
  });
  for (const text of ["/start", "通知をオフ", "calendar card is confusing", "feedback:   "]) {
    assert.equal(classifyFeedback(text), null);
  }
});


test("scrubber removes contact, address, URL, handle, and secret-shaped values", () => {
  const email = `person${"@"}example.com`;
  const phone = ["+81", "9012345678"].join("");
  const postal = ["〒", "123", "-", "4567"].join("");
  const raw = [
    "Calendar failed",
    email,
    phone,
    postal,
    "https://example.com/private?token=value",
    "@private_handle",
    "api_key=not-a-real-key",
    "name: Private Person",
  ].join(" ");
  const scrubbed = scrubFeedback(raw);
  for (const forbidden of [email, phone, postal, "example.com", "private_handle", "not-a-real-key", "Private Person"]) {
    assert.equal(scrubbed.includes(forbidden), false);
  }
  assert.match(scrubbed, /\[email\]/);
  assert.match(scrubbed, /\[phone\]/);
  assert.match(scrubbed, /\[address\]/);
  assert.match(scrubbed, /\[url\]/);
  assert.match(scrubbed, /\[handle\]/);
  assert.match(scrubbed, /\[secret\]/);
  assert.match(scrubbed, /\[name\]/);
});


test("closed intake schema contains no raw text, chat id, actor id, or user id", () => {
  const intake = buildFeedbackIntake({
    text: "feedback: call button does nothing",
    uid: "real-user-id",
    chatId: "123456",
    messageId: "44",
    provenanceKey: "fixture-provenance-key",
  });
  assert.deepEqual(Object.keys(intake).sort(), ["labels", "source_ref", "summary"]);
  assert.equal(intake.summary, "call button does nothing");
  assert.deepEqual(intake.labels, ["feedback", "call"]);
  assert.match(intake.source_ref, /^tg:sha256:[a-f0-9]{32}$/);
  const serialized = JSON.stringify(intake);
  for (const forbidden of ["real-user-id", "123456", '"44"', "fixture-provenance-key"]) {
    assert.equal(serialized.includes(forbidden), false);
  }
});


test("Telegram product feedback retains a complete scrubbed learning contract", () => {
  const intake = buildFeedbackIntake({
    text: [
      "feedback: Feedback intake should create a product issue.",
      "source_event_id: dais-chat-2026-07-10-life-manager-tobe",
      "user_segment: dogfood",
      "opportunity: Improve itself from feedback and production metrics.",
      "desired_outcome: product_velocity,self_improvement",
      "evidence: docs/superpowers/specs/2026-07-10-life-manager-autopilot-product-loop-design.md",
      "proposed_assumption_test: Send dogfood feedback through Telegram intake.",
      "success_metric: issue_created_from_feedback=true; evidence_present=true",
    ].join("\n"),
    uid: "real-user-id",
    chatId: "123456",
    messageId: "44",
    provenanceKey: "fixture-provenance-key",
  });
  assert.equal(intake.summary, "Feedback intake should create a product issue.");
  assert.equal(intake.source_event_id, "dais-chat-2026-07-10-life-manager-tobe");
  assert.equal(intake.user_segment, "dogfood");
  assert.equal(intake.success_metric, "issue_created_from_feedback=true; evidence_present=true");
  assert.equal(JSON.stringify(intake).includes("real-user-id"), false);
});


test("Postgres persistence uses parameters, writes only the closed intake, and is idempotent", async () => {
  const seen = [];
  const query = async (sql, params) => {
    seen.push({ sql, params });
    return { rows: [{ id: "feedback-row-1" }] };
  };
  const intake = {
    source_ref: "tg:sha256:11111111111111111111111111111111",
    summary: "calendar card is confusing",
    labels: ["feedback", "calendar"],
  };
  const result = await persistFeedback(intake, {
    query,
  });
  assert.deepEqual(result, { id: "feedback-row-1", duplicate: false });
  assert.match(seen[0].sql, /INSERT INTO public\.lm_feedback_intake/i);
  assert.match(seen[0].sql, /ON CONFLICT \(source_ref\) DO NOTHING/i);
  assert.deepEqual(seen[0].params, [intake.source_ref, intake.summary, intake.labels]);
  assert.equal(seen[0].sql.includes(intake.summary), false);
});


test("handler acknowledges persisted feedback without echoing its content", async () => {
  const sent = [];
  const stored = [];
  const result = await handleFeedbackMessage(
    { text: "feedback: notification arrived late", chatId: "100", messageId: "7" },
    { uid: "u1" },
    {
      provenanceKey: "fixture-provenance-key",
      persist: async (intake) => { stored.push(intake); return { id: "row-1", duplicate: false }; },
      send: async (_token, chatId, text) => sent.push({ chatId, text }),
      token: "fixture-token",
    },
  );
  assert.equal(result.handled, true);
  assert.equal(stored.length, 1);
  assert.equal(sent.length, 1);
  assert.equal(sent[0].text, "Thanks — your privacy-safe feedback was recorded.");
  assert.equal(sent[0].text.includes("notification arrived late"), false);
});
