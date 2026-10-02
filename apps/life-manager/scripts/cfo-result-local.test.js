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
    occurrenceId: "life-manager-cfo-hourly:run-1",
    collect: async date => ({ reporting_date: date, rows: [{ loop_id: "capafy",
      revenue: { status: "verified", amounts: { USD: value }, receipts: ["receipt:1"] } }] }),
    notify: async input => { messages.push(input); return { delivery: "delivered", provider_message_id: "id" }; } };
  return { options, messages, change: v => { value = v; } };
}
test("hourly report has one receipt per hour, reflects new income next hour", async t => {
  const { options, messages, change } = setup(t);
  const first = await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" });
  assert.equal(first.status, "sent");
  assert.equal(first.resolutionKind, "sent");
  const firstState = JSON.parse(fs.readFileSync(path.join(options.stateDir, "last-result-report.json")));
  assert.equal(firstState.occurrenceId, options.occurrenceId);
  assert.match(firstState.messageSha256, /^[a-f0-9]{64}$/);
  assert.equal(firstState.resolutionKind, "sent");
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

test("same-period replay is quiet, keeps provider receipt, and rebinds current occurrence", async t => {
  const { options, messages } = setup(t);
  assert.equal((await runResultCfo({ ...options, now: "2026-09-30T12:00:00Z" })).status, "sent");
  const replay = await runResultCfo({
    ...options,
    occurrenceId: "life-manager-cfo-hourly:run-2",
    now: "2026-09-30T12:00:00Z",
  });
  assert.equal(replay.status, "quiet");
  assert.equal(replay.resolutionKind, "duplicate");
  const state = JSON.parse(fs.readFileSync(path.join(options.stateDir, "last-result-report.json")));
  assert.equal(state.occurrenceId, "life-manager-cfo-hourly:run-2");
  assert.equal(state.providerMessageId, "id");
  assert.equal(state.resolutionKind, "duplicate");
  assert.match(state.messageSha256, /^[a-f0-9]{64}$/);
  await assert.rejects(
    runResultCfo({ ...options, subjectId: "other-owner", now: "2026-09-30T12:00:00Z" }),
    /subject_changed/,
  );
  assert.equal(messages.length, 1);
});

test("pending retry with an already-delivered outbox receipt is duplicate, not sent", async t => {
  const { options, messages } = setup(t);
  let attempt = 0;
  const notify = async input => {
    messages.push(input);
    attempt += 1;
    return attempt === 1
      ? { delivery: "pending", provider_message_id: null }
      : { delivery: "delivered", provider_message_id: "id", attempted: 0 };
  };
  await assert.rejects(
    runResultCfo({ ...options, notify, reportCadence: "daily", now: "2026-09-30T12:00:00Z" }),
    /receipt_missing/,
  );
  const result = await runResultCfo({
    ...options,
    notify,
    occurrenceId: "life-manager-cfo-hourly:retry-run",
    reportCadence: "daily",
    now: "2026-09-30T13:00:00Z",
  });
  assert.equal(result.status, "quiet");
  assert.equal(result.resolutionKind, "duplicate");
  const state = JSON.parse(fs.readFileSync(path.join(options.stateDir, "last-result-report.json")));
  assert.equal(state.occurrenceId, "life-manager-cfo-hourly:retry-run");
  assert.equal(state.resolutionKind, "duplicate");
  assert.equal(state.providerMessageId, "id");
});

test("missing or malformed occurrence is rejected before report state is written", async t => {
  const { options } = setup(t);
  await assert.rejects(
    runResultCfo({ ...options, occurrenceId: undefined, now: "2026-09-30T12:00:00Z" }),
    /cfo_occurrence_invalid/,
  );
  await assert.rejects(
    runResultCfo({ ...options, occurrenceId: "wrong-owner:run-1", now: "2026-09-30T12:00:00Z" }),
    /cfo_occurrence_invalid/,
  );
  assert.equal(fs.existsSync(path.join(options.stateDir, "last-result-report.json")), false);
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

test("hourly entrypoint forwards the host occurrence into the current result producer", () => {
  const source = fs.readFileSync(path.join(__dirname, "cfo-hourly-local.js"), "utf8");
  assert.match(source, /occurrenceId:\s*env\.LIFE_MANAGER_OCCURRENCE_ID/);
});
