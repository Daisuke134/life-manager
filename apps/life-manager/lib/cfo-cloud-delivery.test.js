"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { deliverCloudCfoEmail } = require("./cfo-cloud-delivery.js");
test("cloud email stores frozen text, verifies id and suppresses duplicate", async () => {
  let row, sends = 0;
  const deps = { cfoReceiptIO: { read: async () => row,
    claim: async (_, payload) => { row = payload; return true; },
    mark: async (_, patch) => { Object.assign(row, patch); } },
    sendEmail: async args => { sends++; assert.equal(args.to, "owner@example.test"); return { sent: true, id: "provider-id" }; } };
  const input = { uid: "owner", periodKey: "2026-09-30:12", recipient: "owner@example.test", message: "results", observedAt: "2026-09-30T12:00:00Z" };
  assert.equal((await deliverCloudCfoEmail(input, deps)).status, "sent");
  assert.equal((await deliverCloudCfoEmail(input, deps)).status, "duplicate");
  assert.equal(sends, 1);
  await assert.rejects(deliverCloudCfoEmail({ ...input, recipient: "other@example.test" }, deps), /receipt_invalid/);
});
test("ambiguous email result keeps pending message and requires same recipient", async () => {
  let row, calls = 0;
  const deps = { cfoReceiptIO: { read: async () => row,
    claim: async (_, payload) => { row = payload; return true; }, mark: async (_, patch) => Object.assign(row, patch) },
    sendEmail: async args => { calls++; assert.equal(args.text, "frozen"); return { sent: true }; } };
  const input = { uid: "owner", periodKey: "day", recipient: "owner@example.test", message: "frozen", observedAt: "2026-09-30T12:00:00Z" };
  await assert.rejects(deliverCloudCfoEmail(input, deps), /receipt_missing/);
  await assert.rejects(deliverCloudCfoEmail({ ...input, message: "new" }, deps), /receipt_missing/);
  await assert.rejects(deliverCloudCfoEmail({ ...input, recipient: "other@example.test" }, deps), /recipient_changed/);
  await assert.rejects(deliverCloudCfoEmail({ ...input, observedAt: "2026-10-01T12:00:00Z" }, deps), /idempotency_expired/);
  assert.equal(calls, 2);
});
