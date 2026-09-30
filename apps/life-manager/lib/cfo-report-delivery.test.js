"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { reportDestination, notifyCfoReport } = require("./cfo-report-delivery.js");
test("email is default and Telegram requires explicit selection", () => {
  assert.throws(() => reportDestination({ chatId: "123" }));
  assert.deepEqual(reportDestination({ reportEmail: "owner@example.test" }),
    { channel: "email", recipient: "owner@example.test" });
  assert.deepEqual(reportDestination({ reportChannel: "telegram", chatId: "123" }),
    { channel: "telegram", recipient: "123" });
});
test("email send is owner-bound, idempotent and requires provider receipt", async () => {
  let calls = 0;
  const options = { reportEmail: "owner@example.test", sendEmail: async input => {
    calls++;
    assert.equal(input.to, "owner@example.test");
    assert.equal(input.idempotencyKey, "cfo:test:email:2026-09-30:12");
    return { sent: true, id: "receipt-1" };
  }};
  const result = await notifyCfoReport({ eventKey: "cfo:test:email:2026-09-30:12", message: "test" }, options);
  assert.equal(calls, 1); assert.equal(result.provider_message_id, "receipt-1");
  assert.equal((await notifyCfoReport({ eventKey: "test", message: "test" }, {
    reportEmail: "owner@example.test", sendEmail: async () => ({ sent: true }),
  })).delivery, "pending");
});
