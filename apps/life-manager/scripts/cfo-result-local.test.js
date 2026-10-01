"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { runResultCfo } = require("./cfo-result-local.js");
function setup(t) {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "cfo-result-"));
  t.after(() => fs.rmSync(stateDir, { recursive: true, force: true }));
  let value = "1";
  const messages = [];
  const options = { stateDir, subjectId: "owner", reportEmail: "owner@example.test",
    collect: async date => ({ reporting_date: date, rows: [{ loop_id: "capafy",
      revenue: { status: "verified", amounts: { USD: value }, receipts: ["receipt:1"] } }] }),
    notify: async input => { messages.push(input); return { delivery: "delivered", provider_message_id: "id" }; } };
  return { options, messages, change: v => { value = v; } };
}
test("hourly report has one receipt per hour, reflects new income next hour", async t => {
  const { options, messages, change } = setup(t);
  assert.equal((await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" })).status, "sent");
  change("2");
  assert.equal((await runResultCfo({ ...options, now: "2026-09-30T12:57:00Z" })).status, "quiet");
  assert.equal((await runResultCfo({ ...options, now: "2026-09-30T13:00:00Z" })).status, "sent");
  assert.equal(messages.length, 2); assert.match(messages[1].message, /USD 2/);
  assert.notEqual(messages[0].eventKey, messages[1].eventKey);
});
test("daily cadence stays quiet; ambiguous send freezes text and original key", async t => {
  const { options, messages, change } = setup(t);
  let attempt = 0;
  const notify = async input => { messages.push(input); return ++attempt === 1
    ? { delivery: "pending" } : { delivery: "delivered", provider_message_id: "recovered" }; };
  await assert.rejects(runResultCfo({ ...options, notify, reportCadence: "daily", now: "2026-09-30T12:00:00Z" }), /receipt_missing/);
  change("999");
  assert.equal((await runResultCfo({ ...options, notify, reportCadence: "daily", now: "2026-09-30T13:00:00Z" })).status, "sent");
  assert.equal(messages[0].message, messages[1].message);
  assert.equal(messages[0].eventKey, messages[1].eventKey);
  assert.equal((await runResultCfo({ ...options, reportCadence: "daily", now: "2026-09-30T14:00:00Z" })).status, "quiet");
});
test("pending receipt cannot be silently retargeted", async t => {
  const { options } = setup(t);
  await assert.rejects(runResultCfo({ ...options, now: "2026-09-30T12:00:00Z", notify: async () => ({}) }));
  await assert.rejects(runResultCfo({ ...options, reportEmail: "other@example.test", now: "2026-09-30T13:00:00Z" }), /destination_changed/);
});
test("wrong-day and broken source collection never send", async t => {
  const { options, messages } = setup(t);
  await assert.rejects(runResultCfo({ ...options, now: "2026-09-30T12:00:00Z", collect: async () => ({ reporting_date: "2026-09-29" }) }), /date_mismatch/);
  assert.equal(messages.length, 0);
});

test("same-period replay is quiet and never invokes the provider twice", async t => {
  const { options, messages } = setup(t);
  assert.equal((await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" })).status, "sent");
  assert.equal((await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" })).status, "quiet");
  await assert.rejects(
    runResultCfo({ ...options, subjectId: "other-owner", now: "2026-09-30T12:00:00Z" }),
    /subject_changed/,
  );
  assert.equal(messages.length, 1);
});

test("sent state rejects a different tenant in the next period", async t => {
  const { options, messages } = setup(t);
  assert.equal((await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" })).status, "sent");
  await assert.rejects(
    runResultCfo({ ...options, subjectId: "other-owner", now: "2026-09-30T13:00:00Z" }),
    /subject_changed/,
  );
  assert.equal(messages.length, 1);
});

test("pending delivery is bound to subjectId and rejects a different tenant", async t => {
  const { options, messages } = setup(t);
  await assert.rejects(
    runResultCfo({ ...options, notify: async input => {
      messages.push(input);
      return { delivery: "pending" };
    }, now: "2026-09-30T12:00:00Z" }),
    /receipt_missing/,
  );
  await assert.rejects(
    runResultCfo({ ...options, subjectId: "other-owner", now: "2026-09-30T13:00:00Z" }),
    /subject_changed/,
  );
  assert.equal(messages.length, 1);
});
